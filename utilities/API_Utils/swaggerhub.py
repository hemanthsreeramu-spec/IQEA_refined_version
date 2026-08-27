import requests
import json
import re
import openai
import csv
import allure
from bs4 import BeautifulSoup
import allure_commons
from allure_commons.logger import AllureFileLogger
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
import os
from datetime import datetime

from . import api_files
load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("AZURE_OPENAI_API_KEY")
os.environ["OPENAI_API_BASE"] = os.getenv("AZURE_OPENAI_ENDPOINT")
client = openai.OpenAI(api_key =  os.environ["OPENAI_API_KEY"],
                       base_url = os.environ["OPENAI_API_BASE"])
# # Access the variables
# api_key = os.getenv("AZURE_OPENAI_API_KEY")
# endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
#
# # Set the environment variables explicitly if needed
# os.environ["AZURE_OPENAI_API_KEY"] = api_key
# os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint
def init_allure_results():
    allure_dir = "allure-results"

    import os, shutil
    if os.path.exists(allure_dir):
        shutil.rmtree(allure_dir)
    os.makedirs(allure_dir, exist_ok=True)

    plugin_name = "allure_file_logger"

    # Safe unregister if exists
    try:
        allure_commons.plugin_manager.unregister(name=plugin_name)
    except:
        pass

    # Fresh register
    file_logger = AllureFileLogger(allure_dir)
    allure_commons.plugin_manager.register(file_logger, name=plugin_name)
    print("✔ Allure logger registered cleanly")

import requests
swaggerhub_api_key= "3870e0b0-429d-45d8-8502-a85fafab4b51"
def load_openapi_spec(
    url: str
) -> dict:
    """
    Load OpenAPI/Swagger JSON from SwaggerHub apiproxy endpoint
    using API Key authentication.
    """

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {swaggerhub_api_key}",
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers,
        verify=False,
        timeout=30
    )

    # Clear, user-friendly errors
    if response.status_code == 401:
        raise Exception("Unauthorized: Invalid SwaggerHub API Key")
    if response.status_code == 403:
        raise Exception("Forbidden: API Key has no access to this API")
    if response.status_code == 404:
        raise Exception(
            "API not found or requires authentication. "
            "Ensure the SwaggerHub URL and API key are correct."
        )

    response.raise_for_status()
    return response.json()

# def load_openapi_spec(url: str) -> dict:
#     """
#     Load OpenAPI/Swagger JSON from a given URL.
#     Works for SwaggerHub JSON endpoints.
#     """
#     response = requests.get(url, verify=False)
#     response.raise_for_status()
#     return response.json()


def extract_api_details(openapi_json: dict) -> dict:
    """
    Extracts endpoints, methods, parameters, headers, request bodies,
    responses, and authentication details.
    """
    extracted = {}

    paths = openapi_json.get("paths", {})
    components = openapi_json.get("components", {})

    for path, methods in paths.items():
        extracted[path] = {}

        for method, details in methods.items():
            method = method.lower()

            # Skip non-HTTP keys
            if method not in ["get", "post", "put", "delete", "patch", "options", "head"]:
                continue

            extracted[path][method] = {}

            # Basic info
            extracted[path][method]["summary"] = details.get("summary", "")
            extracted[path][method]["description"] = details.get("description", "")

            # -------------------------
            # Extract Parameters
            # -------------------------
            params = details.get("parameters", [])
            extracted[path][method]["parameters"] = []

            for param in params:
                extracted[path][method]["parameters"].append({
                    "name": param.get("name"),
                    "in": param.get("in"),              # query, path, header
                    "required": param.get("required", False),
                    "schema": param.get("schema", {})
                })

            # -------------------------
            # Extract Request Body
            # -------------------------
            request_body = details.get("requestBody", {})

            if request_body:
                content = request_body.get("content", {})
                extracted[path][method]["requestBody"] = content
            else:
                extracted[path][method]["requestBody"] = {}

            # -------------------------
            # Extract Responses
            # -------------------------
            responses = details.get("responses", {})
            extracted[path][method]["responses"] = responses

            # -------------------------
            # Extract Security
            # -------------------------
            security = details.get("security", [])
            extracted[path][method]["security"] = security

    # -------------------------
    # Global Security Schemes
    # -------------------------
    extracted["securitySchemes"] = components.get("securitySchemes", {})

    return extracted


def split_parameters(parameters, endpoint):
    """
    Split an operation's parameters into path and query entries for the UI.

    Returns two lists of {name, required, value, description}. `value` is
    pre-filled from the schema default when there is one, and is otherwise left
    blank for the user to fill with a literal or a ${var} reference.

    Path placeholders present in the endpoint but missing from `parameters`
    are still listed — otherwise the request goes out with literal braces.
    """
    path_params, query_params = [], []
    seen_path = set()

    for param in parameters or []:
        if not isinstance(param, dict):
            continue

        name = param.get("name")
        if not name:
            continue

        schema = param.get("schema") or {}
        default = schema.get("default")

        entry = {
            "name": name,
            "required": bool(param.get("required", False)),
            "value": "" if default is None else default,
            "description": (schema.get("description") or param.get("description") or ""),
        }

        location = (param.get("in") or "").lower()
        if location == "path":
            entry["required"] = True  # a path param is always required
            path_params.append(entry)
            seen_path.add(name)
        elif location == "query":
            query_params.append(entry)

    # Any {placeholder} in the path that the spec did not declare
    for name in re.findall(r"\{([^{}]+)\}", endpoint or ""):
        if name not in seen_path:
            path_params.append({"name": name, "required": True, "value": "", "description": ""})
            seen_path.add(name)

    return path_params, query_params


def build_data_dictionary(swagger_api_details, base_url,spec):
    """
    Convert Swagger/OpenAPI extracted info into the format required by makeapicall().

    swagger_api_details = {
        "/users": {
            "get": {
                "summary": "...",
                "parameters": [...],
                "requestBody": {...},
                "responses": {...},
                "security": [...]
            }
        }
    }
    """
    data_dict_list = []

    for endpoint, methods in swagger_api_details.items():

        # Skip securitySchemes object
        if endpoint == "securitySchemes":
            continue

        for method, details in methods.items():
            print("swegger_details_to_build",details)
            http_method = method.upper()

            # ----------------------------
            # Collect Payload (if exists)
            # ----------------------------
            payload = {}
            attachments = []
            request_body = details.get("requestBody", {}) or {}

            body_content_type, schema = _pick_request_body(request_body)
            is_multipart = is_multipart_content_type(body_content_type)

            if is_multipart:
                # Describe the file fields as attachments and keep them out of
                # the payload: sampled into it, an upload field would be sent as
                # the text "string". The filename is the one thing the spec
                # cannot supply, so it is left for the user to fill in.
                file_fields, schema = split_multipart_schema(schema, spec)
                attachments = [
                    {"field": name, "filename": "", "content_type": None, "required": True}
                    for name in file_fields
                ]

            if schema:
                payload = generate_sample_payload(schema, spec)
                if not isinstance(payload, (dict, list)):
                    payload = {}

            print("*********Api_payload**********", payload)
            if attachments:
                print("*********Api_attachments**********", attachments)
            # ----------------------------
            # Collect Authentication Header
            # ----------------------------
            headers = {}
            security = details.get("security", [])
            security_schemes = swagger_api_details.get("securitySchemes", {})

            if security:
                for sec in security:
                    for scheme_name in sec.keys():
                        if scheme_name in security_schemes:
                            scheme = security_schemes[scheme_name]

                            if scheme["type"] == "apiKey":
                                headers[scheme["name"]] = "REPLACE_WITH_AUTH_KEY"

                            if scheme["type"] == "http" and scheme["scheme"] == "bearer":
                                headers["Authorization"] = "Bearer REPLACE_TOKEN"

            # Default header. A multipart endpoint deliberately gets none:
            # requests writes Content-Type at send time together with the
            # boundary it generates, and any value set here would leave the
            # server unable to parse the body.
            if not is_multipart:
                headers.setdefault("Content-Type", "application/json")

            # ----------------------------
            # Expected Response
            # ----------------------------
            responses = details.get("responses", {})
            expected_output = {}
            expected_status = None

            # Pick first success response
            for status_code, resp_val in responses.items():
                if str(status_code).startswith("2"):
                    expected_status = int(status_code)
                    expected_output = {"expected_response_schema": resp_val}
                    break

            # ----------------------------
            # Path / Query parameters
            # ----------------------------
            path_params, query_params = split_parameters(details.get("parameters", []), endpoint)

            # ----------------------------
            # Create FINAL Data Dict
            # ----------------------------
            final_dict = {
                "baseUrl": base_url,
                "endpoint": endpoint,
                "httpMethod": http_method,
                "payload": payload,
                "headers": headers,
                "expectedOutput": expected_output,
                "Expected-StatusCode": expected_status,
                "pathParams": path_params,
                "queryParams": query_params,
                # Upload fields read off the spec, awaiting a file name. Empty
                # for every ordinary JSON endpoint.
                "attachments": attachments,
                "body_mode": "form",
                "body_part_name": api_files.DEFAULT_JSON_PART_NAME,
                "requestContentType": body_content_type,
                # Chaining fields — filled in by the UI
                "extract": "",
                "dependsOn": "",
                "order": None,
            }

            data_dict_list.append(final_dict)

    return data_dict_list


# def generate_sample_payload(schema):
#     """
#     Converts a Swagger schema into a simple sample payload.
#     """
#     if "type" not in schema:
#         return {}
#
#     if schema["type"] == "object":
#         payload = {}
#         props = schema.get("properties", {})
#         for key, val in props.items():
#             if val.get("type") == "string":
#                 payload[key] = "string"
#             elif val.get("type") == "integer":
#                 payload[key] = 0
#             elif val.get("type") == "boolean":
#                 payload[key] = True
#             elif val.get("type") == "array":
#                 payload[key] = []
#             elif val.get("type") == "object":
#                 payload[key] = generate_sample_payload(val)
#         return payload
#
#     return {}
def resolve_ref(ref: str, swagger_spec: dict):
    """
    Resolve Swagger $ref paths
    Example: #/components/schemas/Pet
    """
    ref_path = ref.lstrip("#/").split("/")
    value = swagger_spec
    for key in ref_path:
        value = value.get(key, {})
    return value
# Content types that carry an upload rather than a JSON document.
MULTIPART_CONTENT_TYPES = ("multipart/form-data", "multipart/mixed", "multipart/related")


def is_multipart_content_type(content_type):
    return str(content_type or "").split(";")[0].strip().lower() in MULTIPART_CONTENT_TYPES


def _resolved_schema(schema, swagger_spec, depth=0):
    """Follow $ref and allOf far enough to read a schema's properties."""
    if not isinstance(schema, dict) or depth > 8:
        return schema if isinstance(schema, dict) else {}

    if "$ref" in schema:
        return _resolved_schema(resolve_ref(schema["$ref"], swagger_spec), swagger_spec, depth + 1)

    if schema.get("allOf"):
        merged = {"type": "object", "properties": {}, "required": []}
        for part in schema["allOf"]:
            resolved = _resolved_schema(part, swagger_spec, depth + 1)
            merged["properties"].update(resolved.get("properties") or {})
            merged["required"].extend(resolved.get("required") or [])
        return merged

    return schema


def _is_binary_schema(schema, swagger_spec, depth=0):
    """
    True for a property Swagger UI renders as a file picker.

    'type: string, format: binary' is the OpenAPI 3 spelling; an array of those
    is a field accepting several files.
    """
    schema = _resolved_schema(schema, swagger_spec, depth)
    if not isinstance(schema, dict):
        return False
    if str(schema.get("format") or "").lower() in ("binary", "byte", "base64"):
        return True
    if schema.get("type") == "array" and depth < 4:
        return _is_binary_schema(schema.get("items") or {}, swagger_spec, depth + 1)
    return False


def _pick_request_body(request_body):
    """
    Choose which declared body an endpoint should be exercised with.

    Returns (content_type, schema). A JSON body wins whenever the endpoint
    offers one; multipart is chosen only when that is what it actually declares.
    This used to take whichever content type came first, so a multipart endpoint
    produced a JSON payload built from a multipart schema — with the file field
    sampled in as the text "string" — and could never work.
    """
    content = (request_body or {}).get("content")

    if not isinstance(content, dict) or not content:
        # extract_api_details stores the content map directly, so the content
        # types can also sit at the top level. Normalised here rather than
        # handled separately, so the JSON preference applies to both shapes.
        content = {
            content_type: value
            for content_type, value in (request_body or {}).items()
            if isinstance(value, dict) and "schema" in value
        }

    if not content:
        return "", {}

    for content_type in content:
        if "json" in str(content_type).lower():
            return str(content_type), (content[content_type] or {}).get("schema") or {}

    content_type = next(iter(content))
    return str(content_type), (content[content_type] or {}).get("schema") or {}


def split_multipart_schema(schema, swagger_spec):
    """
    Split a multipart schema into its file fields and its ordinary parameters.

    Returns (file_fields, param_schema): file_fields are the names Swagger UI
    would render as file pickers, and param_schema is the schema with those
    properties removed, so a sample payload of just the parameters can be built
    from it.
    """
    resolved = _resolved_schema(schema, swagger_spec)
    properties = resolved.get("properties") if isinstance(resolved, dict) else None
    if not isinstance(properties, dict):
        return [], schema

    file_fields = [
        name for name, prop in properties.items()
        if _is_binary_schema(prop, swagger_spec)
    ]
    if not file_fields:
        return [], schema

    param_schema = dict(resolved)
    param_schema["properties"] = {
        name: prop for name, prop in properties.items() if name not in file_fields
    }
    if isinstance(param_schema.get("required"), list):
        param_schema["required"] = [
            name for name in param_schema["required"] if name not in file_fields
        ]
    return file_fields, param_schema


def generate_sample_payload(schema: dict, swagger_spec: dict):
    """
    Generate sample JSON payload from Swagger schema
    """
    if not schema:
        return {}

    # Resolve $ref
    if "$ref" in schema:
        resolved = resolve_ref(schema["$ref"], swagger_spec)
        return generate_sample_payload(resolved, swagger_spec)

    # Use example if present
    if "example" in schema:
        return schema["example"]
    if schema.get("examples"):
        examples = schema["examples"]
        return examples[0] if isinstance(examples, list) else examples

    # Use default / first enum value when the type is loosely defined
    if "default" in schema and "properties" not in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]

    # OpenAPI 3.1 / FastAPI optional fields: anyOf / oneOf / allOf
    for combiner in ("anyOf", "oneOf"):
        if schema.get(combiner):
            options = [o for o in schema[combiner] if isinstance(o, dict)]
            # Prefer a concrete (non-null) variant
            concrete = [o for o in options if o.get("type") != "null"] or options
            if concrete:
                return generate_sample_payload(concrete[0], swagger_spec)

    if schema.get("allOf"):
        merged = {}
        for part in schema["allOf"]:
            if isinstance(part, dict):
                value = generate_sample_payload(part, swagger_spec)
                if isinstance(value, dict):
                    merged.update(value)
        return merged

    schema_type = schema.get("type", "object")

    # OpenAPI 3.1 allows a list of types, e.g. ["string", "null"]
    if isinstance(schema_type, list):
        non_null = [t for t in schema_type if t != "null"]
        schema_type = non_null[0] if non_null else "null"

    if schema_type == "null":
        return None

    if schema_type == "object":
        payload = {}
        properties = schema.get("properties", {})
        for prop, prop_schema in properties.items():
            payload[prop] = generate_sample_payload(prop_schema, swagger_spec)
        return payload

    if schema_type == "array":
        items = schema.get("items", {})
        return [generate_sample_payload(items, swagger_spec)]

    if schema_type == "string":
        return "string"

    if schema_type == "integer":
        return 0

    if schema_type == "number":
        return 0.0

    if schema_type == "boolean":
        return True

    return None

def get_base_url(swagger_url, spec):
    """
    Resolve the base URL for API calls.

    swagger_url : the URL the spec was downloaded from (string)
    spec        : the parsed OpenAPI/Swagger document (dict)
    """
    from urllib.parse import urljoin, urlparse

    if not isinstance(swagger_url, str):
        raise TypeError(
            f"get_base_url() expects the Swagger URL as a string, got {type(swagger_url).__name__}"
        )

    # 1. servers[] block (OpenAPI 3)
    servers = spec.get("servers") or []
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        server_url = (servers[0].get("url") or "").strip()
        if server_url:
            # Relative server url (e.g. "/aiapi") -> resolve against the spec URL
            if not urlparse(server_url).netloc:
                server_url = urljoin(swagger_url, server_url)
            return server_url.rstrip("/")

    # 2. Swagger 2.0 style: host + basePath + schemes
    host = (spec.get("host") or "").strip()
    if host:
        schemes = spec.get("schemes") or ["https"]
        base_path = (spec.get("basePath") or "").strip()
        return f"{schemes[0]}://{host}{base_path}".rstrip("/")

    # 3. SwaggerHub URL -> mock server
    # e.g. https://api.swaggerhub.com/apis/tiger-b7b/equifax_new/1.0.0?format=json
    if "/apis/" in swagger_url:
        try:
            parts = swagger_url.split("/apis/")[1]
            org, api, version_with_query = parts.split("/")[:3]
            version = version_with_query.split("?")[0]
            print("⚠ No Base URL found inside Swagger. Using SwaggerHub mock server.")
            return f"https://virtserver.swaggerhub.com/{org}/{api}/{version}"
        except (IndexError, ValueError):
            pass

    # 4. Fallback: per OpenAPI spec, an omitted servers block defaults to the
    #    host serving the document. Paths in such specs already carry any prefix.
    parsed = urlparse(swagger_url)
    if parsed.scheme and parsed.netloc:
        print(f"⚠ No servers[] in spec. Using spec host as base URL: {parsed.scheme}://{parsed.netloc}")
        return f"{parsed.scheme}://{parsed.netloc}"

    raise ValueError(f"Could not determine base URL from spec or URL: {swagger_url}")


def run_allure_test(api_dict, utils):
    test_name = f"{api_dict.get('httpMethod')} {api_dict.get('endpoint')}"

    with allure.step(f"Executing: {test_name}"):
        utils.makeapicall(api_dict)

import pandas as pd
import json

from .api_context import parse_extract_spec


# ======================================================================
# Swagger -> Excel template export
# ======================================================================
# Column order of Input/Api_template.xlsx. Extra 'headers-*' columns found on
# the exported endpoints are inserted after headers-Authorization.
TEMPLATE_COLUMNS = [
    "Test_Case_Name", "httpMethod", "baseUrl", "endPoint",
    "headers", "BodyFormat", "Attachments", "Body-As",
    "headers-Authorization", "auth_type",
    "Request-username", "Request-password",
    "Expected-StatusCode", "Expected-Message",
    "Validate?", "Performance?",
    "Extract-Values", "Depends-On", "Execution-Order",
]

# Header names whose literal value is withheld from the exported file — a pasted
# bearer token belongs in the Global headers field at run time, not in a
# spreadsheet that gets shared around.
EXPORT_SENSITIVE_HEADERS = ("authorization", "cookie", "x-api-key", "api-key", "token", "secret")


def _is_secret_header(name, value):
    """
    True only for a sensitive header holding a literal value.

    'Bearer ${token}' carries no secret and is what makes a chain work, so it is
    exported as-is; 'Bearer eyJhbGciOi...' is withheld.
    """
    if not any(marker in str(name).lower() for marker in EXPORT_SENSITIVE_HEADERS):
        return False
    return "${" not in str(value)


def _unfilled_path_params(endpoint):
    """
    Path placeholders still needing a value.

    ${vars} are removed first — '/users/${uid}' contains the substring '{uid}'
    but is already bound to a chained value, not an unfilled parameter.
    """
    without_vars = re.sub(r"\$\{[^{}]*\}", "", str(endpoint or ""))
    return re.findall(r"\{([^{}]+)\}", without_vars)


def _loose_key(name):
    """Matches api_runner: '{agentId}' and an extracted 'agent_id' are the same."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def make_test_case_name(api, index, taken=None):
    """
    Build a readable, unique test-case name for a Swagger endpoint.

    Used both when endpoints are fetched (so results are labelled by name rather
    than URL) and when exporting, so the grid, the export and the result report
    all agree on what a test case is called.
    """
    taken = taken if taken is not None else set()

    existing = str(api.get("test_case_name") or "").strip()
    if existing and existing not in taken:
        taken.add(existing)
        return existing

    return _test_case_name(api, index, taken)


def _test_case_name(api, index, taken):
    """A unique, readable Test_Case_Name — Depends-On refers to rows by this."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(api.get("endpoint") or "")).strip("_")
    slug = re.sub(r"_+", "_", slug)[:48] or "endpoint"
    base = f"TC_{index:02d}_{str(api.get('httpMethod') or 'GET').upper()}_{slug}"

    name, suffix = base, 2
    while name in taken:
        name = f"{base}_{suffix}"
        suffix += 1
    taken.add(name)
    return name


def _endpoint_with_query(api):
    """
    Fold query parameters into endPoint as a query string.

    The template has no query column, and 'baseUrl + endPoint' is sent verbatim,
    so '?a=1&b=2' on the end works and keeps ${vars} resolvable.
    """
    endpoint = str(api.get("endpoint") or "")

    # Substitute any path parameter values the user supplied in the grid
    for param in api.get("pathParams") or []:
        if not isinstance(param, dict):
            continue
        value = param.get("value")
        if value is not None and str(value).strip():
            endpoint = endpoint.replace("{" + str(param.get("name")) + "}", str(value).strip())

    pairs = []
    for param in api.get("queryParams") or []:
        if not isinstance(param, dict):
            continue
        value = param.get("value")
        if value is None or not str(value).strip():
            continue
        pairs.append(f"{param.get('name')}={str(value).strip()}")

    if pairs:
        joiner = "&" if "?" in endpoint else "?"
        endpoint = f"{endpoint}{joiner}{'&'.join(pairs)}"

    return endpoint


def swagger_rows_to_template(api_list):
    """
    Map fetched Swagger endpoints onto the Excel template.

    Returns (DataFrame, warnings). Warnings flag rows that need attention before
    the exported sheet will run — unfilled path parameters, missing required
    query parameters, and any auth header deliberately left out.
    """
    rows, warnings, taken = [], [], set()
    extra_header_columns = []
    skipped_auth = set()

    # A '{param}' the suite extracts somewhere is bound at run time, so it is
    # not something the user has to fill in before the sheet will run.
    chained = set()
    for api in api_list:
        for name, _source in parse_extract_spec(api.get("extract")):
            chained.add(_loose_key(name))

    for index, api in enumerate(api_list, start=1):
        method = str(api.get("httpMethod") or "GET").upper()
        endpoint = _endpoint_with_query(api)
        name = make_test_case_name(api, index, taken)

        # Headers: content type into 'headers', the rest into headers-<Name>
        headers = api.get("headers") or {}
        content_type = "application/json"
        row_headers = {}
        for header_name, header_value in headers.items():
            if str(header_name).lower() == "content-type":
                content_type = header_value
                continue
            if _is_secret_header(header_name, header_value):
                skipped_auth.add(header_name)
                continue
            column = f"headers-{header_name}"
            row_headers[column] = header_value
            if column not in extra_header_columns and column != "headers-Authorization":
                extra_header_columns.append(column)

        payload = api.get("payload")
        if method in ("POST", "PUT", "PATCH") and payload:
            body = json.dumps(payload, indent=2)
        else:
            body = "NODATA"

        # Attachments travel to the sheet in the same 'field=name' text the
        # Document flow reads back, so a row set up here runs there unchanged.
        attachments = api.get("attachments") or []
        attachment_cell = api_files.format_attachment_spec(attachments)
        if attachments:
            # Documents intent for whoever reads the sheet; the value itself is
            # dropped at send time so requests can set the boundary.
            content_type = "multipart/form-data"
            missing_names = [
                part.get("field") for part in attachments
                if isinstance(part, dict) and not str(part.get("filename") or "").strip()
            ]
            if missing_names:
                warnings.append(
                    f"{name}: upload field(s) {', '.join(str(f) for f in missing_names)} still "
                    f"need a file name in Attachments (e.g. {missing_names[0]}=contract.pdf), "
                    f"and the file itself in {api_files.ATTACHMENT_SUBFOLDER}{os.sep}"
                )

        unfilled = [p for p in _unfilled_path_params(endpoint) if _loose_key(p) not in chained]
        if unfilled:
            warnings.append(f"{name}: path parameter(s) {', '.join(unfilled)} still need a value in endPoint")

        missing_query = [
            param.get("name") for param in (api.get("queryParams") or [])
            if isinstance(param, dict) and param.get("required")
            and (param.get("value") is None or not str(param.get("value")).strip())
        ]
        if missing_query:
            warnings.append(f"{name}: required query parameter(s) {', '.join(missing_query)} are empty")

        row = {
            "Test_Case_Name": name,
            "httpMethod": method,
            "baseUrl": api.get("baseUrl") or "",
            "endPoint": endpoint,
            "headers": content_type,
            "BodyFormat": body,
            "Attachments": attachment_cell,
            "Body-As": api_files.format_body_mode(
                api.get("body_mode") or "form",
                api.get("body_part_name") or api_files.DEFAULT_JSON_PART_NAME,
            ),
            "headers-Authorization": "",
            "auth_type": "NA",
            "Request-username": "",
            "Request-password": "",
            "Expected-StatusCode": api.get("Expected-StatusCode") or 200,
            "Expected-Message": "",
            "Validate?": "Y" if api.get("Validate?") else "N",
            "Performance?": "Y" if api.get("Performance?") else "N",
            "Extract-Values": api.get("extract") or "",
            "Depends-On": api.get("dependsOn") or "",
            "Execution-Order": api.get("order") or "",
        }
        row.update(row_headers)
        rows.append(row)

    if skipped_auth:
        warnings.append(
            "Auth header(s) " + ", ".join(sorted(skipped_auth))
            + " were not written to the file — paste the token under 'Chaining & auth → Global headers' "
              "when you run the document instead."
        )

    columns = list(TEMPLATE_COLUMNS)
    insert_at = columns.index("headers-Authorization") + 1
    for column in extra_header_columns:
        columns.insert(insert_at, column)
        insert_at += 1

    frame = pd.DataFrame(rows).reindex(columns=columns)
    return frame.where(pd.notna(frame), ""), warnings


TEMPLATE_REQUIRED_COLUMNS = ("Test_Case_Name", "httpMethod", "endPoint")


def read_template_frame(source):
    """
    Load a previously exported sheet as a raw DataFrame.

    Deliberately not read_excel_input — that normalises rows for execution and
    would drop the exact column layout (including any custom headers-* columns)
    that the merged file has to preserve.

    Returns (frame, error).
    """
    try:
        frame = pd.read_excel(source)
    except Exception as exc:
        return None, f"Could not read that file: {exc}"

    frame.columns = [str(column).strip() for column in frame.columns]

    missing = [c for c in TEMPLATE_REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        return None, (
            "That does not look like an exported API sheet — missing column(s): "
            + ", ".join(missing)
        )

    frame = frame.where(pd.notna(frame), "")
    # Drop fully blank rows so appending doesn't inherit spacer lines
    frame = frame[frame["httpMethod"].astype(str).str.strip().ne("")
                  | frame["endPoint"].astype(str).str.strip().ne("")]
    return frame.reset_index(drop=True), None


def merge_template_frames(base, new):
    """
    Append newly exported rows to a previously exported sheet.

    Columns are unioned (base order first) and duplicate Test_Case_Names in the
    incoming rows are suffixed, so adding the same endpoint again with a
    different payload gives a second, distinctly named test case rather than a
    silent collision that Depends-On could not tell apart.

    Returns (merged_frame, notes).
    """
    notes = []
    if base is None or base.empty:
        return new.reset_index(drop=True), notes
    if new is None or new.empty:
        return base.reset_index(drop=True), notes

    columns = list(base.columns) + [c for c in new.columns if c not in base.columns]
    added = [c for c in new.columns if c not in base.columns]
    if added:
        notes.append("New column(s) added to the sheet: " + ", ".join(added))

    taken = {str(name).strip() for name in base["Test_Case_Name"] if str(name).strip()}
    renamed = []

    new = new.copy()
    fresh_names = []
    for name in new["Test_Case_Name"]:
        candidate = str(name).strip() or "TC"
        if candidate in taken:
            stem, suffix = candidate, 2
            while f"{stem}_v{suffix}" in taken:
                suffix += 1
            renamed.append((candidate, f"{stem}_v{suffix}"))
            candidate = f"{stem}_v{suffix}"
        taken.add(candidate)
        fresh_names.append(candidate)
    new["Test_Case_Name"] = fresh_names

    if renamed:
        notes.append(
            f"{len(renamed)} row(s) renamed to stay unique: "
            + ", ".join(f"{old} → {fresh}" for old, fresh in renamed[:5])
            + (" …" if len(renamed) > 5 else "")
        )

    merged = pd.concat(
        [base.reindex(columns=columns), new.reindex(columns=columns)],
        ignore_index=True,
    )
    return merged.where(pd.notna(merged), ""), notes


def validate_template_frame(frame):
    """
    Problems that would break the sheet once uploaded, reported while the user
    is still editing it. Returns a list of messages.
    """
    problems = []
    if frame is None or len(frame) == 0:
        return problems

    names = [str(name).strip() for name in frame.get("Test_Case_Name", []) if str(name).strip()]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        problems.append(
            "Duplicate Test_Case_Name: " + ", ".join(duplicates)
            + " — Depends-On cannot tell them apart."
        )

    for position, record in enumerate(frame.to_dict("records"), start=2):
        label = str(record.get("Test_Case_Name") or "").strip() or f"row {position}"

        body = str(record.get("BodyFormat") or "").strip()
        if body and body.upper() not in ("NODATA", "NO_DATA", "NONE"):
            try:
                json.loads(body)
            except Exception as exc:
                problems.append(f"{label}: BodyFormat is not valid JSON — {exc}")

        if not str(record.get("httpMethod") or "").strip():
            problems.append(f"{label}: httpMethod is empty")
        if not str(record.get("endPoint") or "").strip():
            problems.append(f"{label}: endPoint is empty")

        # Attachments: catch a bad file name here rather than as a 400 mid-run.
        attachments_cell = record.get("Attachments")
        _parts, attachment_problems = api_files.parse_attachment_spec(attachments_cell, label)
        problems.extend(attachment_problems)

        if not api_files.is_blank(record.get("Body-As")) and api_files.is_blank(attachments_cell):
            problems.append(
                f"{label}: Body-As has no effect without an Attachments file — "
                f"a row with no upload is always sent as JSON"
            )

    return problems


def template_dataframe_to_bytes(frame, sheet_name="API_Details"):
    """Serialise the export to .xlsx bytes for a Streamlit download button."""
    import io

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name, index=False)
        worksheet = writer.sheets[sheet_name]
        for index, column in enumerate(frame.columns, start=1):
            longest = max(
                [len(str(column))]
                + [len(str(value).split("\n")[0]) for value in frame[column]]
            )
            letter = worksheet.cell(row=1, column=index).column_letter
            worksheet.column_dimensions[letter].width = min(max(longest + 2, 12), 42)

    buffer.seek(0)
    return buffer.getvalue()


def _cell(row, column, default=""):
    """Read a cell, treating NaN / blank as the default."""
    value = row.get(column, default)
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return value


def _cell_text(row, column, default=""):
    value = _cell(row, column, default)
    return value if isinstance(value, str) else ("" if value == "" else str(value))


def _first_cell_text(row, columns, default=""):
    """First non-empty value among several accepted column spellings."""
    for column in columns:
        value = _cell_text(row, column)
        if value:
            return value
    return default


# People retype the header by hand often enough that the underscored spelling
# alone is too brittle — a mismatch silently costs every row its name.
TEST_CASE_NAME_COLUMNS = (
    "Test_Case_Name", "Test Case Name", "TestCaseName", "Test_Case",
    "Test Case", "TestCase", "Test_Name", "Test Name", "TC_Name", "TC Name",
)

# The token an auth_type=BEARER row should send, written on the row itself.
# Usually chained — '${access_token}' captured by the login row — but a pasted
# token works too. A value here beats the global header typed in the UI, because
# something written against one row is more specific than a run-wide default;
# leave it blank and that global header is what the row falls back to.
BEARER_TOKEN_COLUMNS = (
    "_bearer_token", "bearer_token", "Bearer-Token", "Bearer Token",
    "BearerToken", "Bearer_Token",
)


def _normalize_flag(value, default=False):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip().upper()
    if not text:
        return default
    return text in ("Y", "YES", "TRUE", "1", "1.0")


def _row_headers(row):
    """
    Build the request headers for a sheet row.

    'headers' carries the content type (that is what the template has always
    held). Any 'headers-<Name>' column becomes a header of that name, so a sheet
    can add 'headers-x-api-key' or 'headers-X-Tenant' with no code change.
    """
    headers = {}

    content_type = _cell_text(row, "headers")
    if content_type:
        headers["Content-Type"] = content_type

    for column in row.index:
        name = str(column).strip()
        if not name.lower().startswith("headers-"):
            continue
        header_name = name.split("-", 1)[1].strip()
        value = _cell(row, column)
        if header_name and value != "":
            headers[header_name] = value if isinstance(value, str) else str(value)

    return headers

# {{name}} anywhere in a sheet cell means "read this from .env". Credentials
# belong there rather than in a spreadsheet that gets mailed around, and the same
# sheet then runs against dev and prod by swapping the .env.
ENV_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")


def resolve_env_placeholders(text, missing=None):
    """
    Substitute every {{name}} in one string with its .env value.

    Names are matched case-insensitively (api_client_id and API_CLIENT_ID both
    work) because .env conventions differ per team. A name with no value is
    collected in 'missing' rather than left as-is: the caller reports it, so an
    unset secret shows up as a clear message at upload time instead of a 401 from
    a request that quietly carried an empty client_secret.
    """
    collected = missing if missing is not None else []

    def substitute(match):
        name = match.group(1)
        for candidate in (name, name.upper(), name.lower()):
            value = os.getenv(candidate)
            if value:
                return value
        collected.append(name)
        return ""

    return ENV_PLACEHOLDER_PATTERN.sub(substitute, str(text))


def _resolve_in_value(value, missing):
    """Walk a parsed body and resolve placeholders in its strings."""
    if isinstance(value, str):
        return resolve_env_placeholders(value, missing)
    if isinstance(value, dict):
        return {key: _resolve_in_value(item, missing) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_in_value(item, missing) for item in value]
    return value


def _missing_env_message(names):
    unique = list(dict.fromkeys(names))
    return (f"{'these are' if len(unique) > 1 else 'this is'} not set in .env: "
            f"{', '.join(unique)}")


def json_conversion_model(raw_payload):
    """
    Parse a BodyFormat cell and resolve its {{env_var}} placeholders.

    Parsed first, substituted second — the other order breaks on any secret
    containing a quote, a backslash or a newline, because the replacement lands
    inside the JSON text and corrupts it. Doing it on the parsed values means the
    secret is never JSON syntax and can hold anything.

    Returns (payload, error). An unresolved placeholder still returns the payload
    alongside the error, so the row is reported and not silently blanked.
    """
    if isinstance(raw_payload, (dict, list)):
        parsed = raw_payload
    else:
        try:
            parsed = json.loads(str(raw_payload))
        except Exception as exc:
            return {}, f"BodyFormat is not valid JSON — {exc}"

    missing = []
    payload = _resolve_in_value(parsed, missing)

    if missing:
        return payload, f"BodyFormat references {_missing_env_message(missing)}"

    return payload, None


def _row_payload(row, label):
    """
    Parse BodyFormat and return (payload, error)
    """
    raw = _cell(row, "BodyFormat")

    # Blank payload
    if raw == "" or str(raw).strip().upper() in ("NODATA", "NO_DATA", "NONE"):
        return {}, None

    payload, error = json_conversion_model(raw)
    if error:
        return payload, f"{label}: {error}"

    if not isinstance(payload, (dict, list)):
        return {}, f"{label}: BodyFormat must be a JSON object or array, got {type(payload).__name__}"

    return payload, None


def read_excel_input(file_path):
    """
    Read the API Excel file into rows the shared runner can execute.

    Returns (api_list, errors). Errors are per-row problems worth showing at
    upload time — a malformed payload found now is far easier to fix than the
    same failure surfacing mid-run.
    """
    df = pd.read_excel(file_path)
    df.columns = [str(c).strip() for c in df.columns]

    api_list, errors = [], []

    for position, (_, row) in enumerate(df.iterrows(), start=2):  # row 1 is the header
        name = _first_cell_text(row, TEST_CASE_NAME_COLUMNS) or f"Row {position}"
        method = _cell_text(row, "httpMethod").upper()
        endpoint = _cell_text(row, "endPoint")
        base_url = _cell_text(row, "baseUrl")

        if not method and not endpoint:
            continue  # blank spacer row

        label = f"'{name}' (sheet row {position})"

        # A URL takes {{env_var}} too — a tenant id sits in the path of a token
        # endpoint, and it differs per environment while the sheet does not.
        url_missing = []
        endpoint = resolve_env_placeholders(endpoint, url_missing)
        base_url = resolve_env_placeholders(base_url, url_missing)

        # Older sheets wrote the bare name with no braces. Still honoured, but
        # only as a whole path segment: a plain substring replace also rewrites
        # an endpoint that legitimately contains the words, and dropping in an
        # empty value builds a URL like '//token' that fails somewhere else
        # entirely.
        if "api_tenant_id" in endpoint:
            tenant_id = os.getenv("api_tenant_id") or os.getenv("API_TENANT_ID") or ""
            if tenant_id:
                endpoint = re.sub(r"(?<![A-Za-z0-9_])api_tenant_id(?![A-Za-z0-9_])",
                                  tenant_id, endpoint)
            else:
                url_missing.append("api_tenant_id")

        if url_missing:
            errors.append(f"{label}: endpoint references {_missing_env_message(url_missing)}")

        payload, payload_error = _row_payload(row, label)
        if payload_error:
            errors.append(payload_error)

        # Attachments turn the row into multipart/form-data. The payload is not
        # replaced by them — in the usual upload row both are filled and the
        # parameters travel as form fields alongside the file.
        attachments, attachment_errors = api_files.parse_attachment_spec(
            _cell(row, "Attachments"), label
        )
        errors.extend(attachment_errors)
        body_mode, body_part_name = api_files.parse_body_mode(_cell(row, "Body-As"))

        try:
            expected_status = int(float(_cell(row, "Expected-StatusCode", 200) or 200))
        except (TypeError, ValueError):
            expected_status = 200
            errors.append(f"'{name}': Expected-StatusCode is not a number, using 200")

        order_raw = _cell(row, "Execution-Order", "")
        try:
            order = int(float(order_raw)) or None
        except (TypeError, ValueError):
            order = None

        api_data = {
            "test_case_name": name,
            "method": method,
            "baseUrl": base_url,
            "endpoint": endpoint,

            # Real headers dict — previously the sheet's header columns were
            # collected into keys nothing ever read, so they were never sent.
            "headers": _row_headers(row),
            

            # Parsed body; body_format kept so anything still reading it works
            "payload": payload,
            "body_format": _cell(row, "BodyFormat"),
            "_payload_error": payload_error,

            # Multipart upload. An empty list means "no file", which is the
            # existing JSON request path.
            "attachments": attachments,
            "body_mode": body_mode,
            "body_part_name": body_part_name,
            "_attachment_error": "; ".join(attachment_errors),

            "username": _cell_text(row, "Request-username"),
            "password": _cell_text(row, "Request-password"),
            "auth_type": _cell_text(row, "auth_type"),
            "_bearer_token": _first_cell_text(row, BEARER_TOKEN_COLUMNS),

            "expected_status": expected_status,
            "Expected-StatusCode": expected_status,
            "expected_message": _cell_text(row, "Expected-Message"),

            "validate": _normalize_flag(_cell(row, "Validate?", "Y"), default=True),
            "performance": _normalize_flag(_cell(row, "Performance?", "N"), default=False),

            # Chaining. 'Extract-token' is the legacy single-value column.
            "extract": _cell_text(row, "Extract-Values") or _cell_text(row, "Extract-token"),
            "dependsOn": _cell_text(row, "Depends-On"),
            "order": order,
        }

        if not api_data["_payload_error"]:
            api_data.pop("_payload_error")
        if not api_data["_attachment_error"]:
            api_data.pop("_attachment_error")
        # Dropped when blank rather than kept as "": every later check is
        # "did the sheet supply a token", and an empty string answers yes.
        if not api_data["_bearer_token"]:
            api_data.pop("_bearer_token")

        api_list.append(api_data)

    return api_list, errors
def generate_example_payload(schema: dict):
    """
    Generate sample payload from Swagger schema
    """
    if not schema:
        return {}

    if "$ref" in schema:
        return {"_ref": schema["$ref"]}

    payload = {}
    properties = schema.get("properties", {})

    for key, prop in properties.items():
        prop_type = prop.get("type", "string")

        if prop_type == "string":
            payload[key] = prop.get("example", "string")
        elif prop_type == "integer":
            payload[key] = prop.get("example", 0)
        elif prop_type == "boolean":
            payload[key] = prop.get("example", True)
        elif prop_type == "array":
            payload[key] = []
        elif prop_type == "object":
            payload[key] = generate_sample_payload(prop)
        else:
            payload[key] = None

    return payload


def api_response_prompt(api_response):
    """Ask for a table-first HTML report — prose walls are hard to scan."""
    return f"""You are a Senior API Quality Architect and Automation Expert.

You will be given the results of an API test run as structured rows.

Your job is to produce a **TABULAR** HTML quality report. Tables are the primary
output; prose is only allowed in the short verdict at the end.

### INPUT DATA
{api_response}

---

### OUTPUT RULES (STRICT)
- Return ONLY valid HTML. No markdown, no ``` fences, no <html>/<head>/<body> wrapper.
- Every section below MUST be an HTML <table>. Do not replace a table with a list.
- One row per API in the per-API tables. Never merge or omit APIs.
- Use only the data provided. If something is unknown, write "Not Available".
- Do not dump raw JSON.
- Add style="background:#fde8e8" to any <tr> whose result is FAIL,
  and style="background:#fef7e0" to any <tr> whose result is SKIP.

### REQUIRED OUTPUT

<h2>Run Summary</h2>
<table border="1" cellspacing="0" cellpadding="6">
<tr><th>Total</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Pass Rate</th><th>Overall Verdict</th></tr>
<tr>...one row of numbers...</tr>
</table>

<h2>Test Results</h2>
<table border="1" cellspacing="0" cellpadding="6">
<tr><th>Test Case</th><th>Method</th><th>Endpoint</th><th>Expected Status</th><th>Actual Status</th>
<th>Expected Message</th><th>Actual Message</th><th>Result</th><th>Root Cause</th></tr>
...one row per API...
</table>

<h2>Issues Identified</h2>
<table border="1" cellspacing="0" cellpadding="6">
<tr><th>#</th><th>Affected API</th><th>Issue</th><th>Severity</th><th>Evidence</th></tr>
...one row per distinct issue; if none, a single row saying "No issues identified"...
</table>

<h2>Risk Assessment</h2>
<table border="1" cellspacing="0" cellpadding="6">
<tr><th>Area</th><th>Risk Level</th><th>Justification</th></tr>
...one row per risk area (Functional, Security, Data Integrity, Reliability)...
</table>

<h2>Recommendations</h2>
<table border="1" cellspacing="0" cellpadding="6">
<tr><th>Priority</th><th>Recommendation</th><th>Applies To</th><th>Expected Benefit</th></tr>
...one row per action, ordered High -> Low...
</table>

<h2>Verdict</h2>
<p>Two or three sentences maximum.</p>
"""


def _legacy_api_response_prompt(api_response):
    formatted_summary = f"""You are a Senior API Quality Architect and Automation Expert.

    Your task is to analyze API execution results and provide a clear, structured
    QUALITY ANALYSIS REPORT in HTML format.

    You will be given API execution details including:
    - API name
    - HTTP method
    - Endpoint
    - Request payload (for POST/PUT)
    - Expected output (if provided)
    - Actual HTTP status code
    - Actual API response JSON

    Your responsibilities:
    1. Validate whether the HTTP status code matches expected behavior.
    2. Validate response correctness:
       - For GET APIs: verify expected fields and values.
       - For POST/PUT APIs: verify that request payload values are correctly reflected in the response.
    3. Identify missing fields, incorrect values, or contract mismatches.
    4. Detect potential functional risks or inconsistencies.
    5. Provide actionable recommendations to improve API quality.

    Rules:
    - Be precise and factual.
    - Do not invent data.
    - If information is missing, clearly state it.
    - Do NOT include raw JSON dumps unless required for explanation.

    ---

    ### INPUT DATA
    The following is the API execution data in JSON format:

    {api_response}

    ---

    ### OUTPUT FORMAT (STRICT)

    Generate a well-structured **HTML report** with the following sections:

    <h2>API Summary</h2>
    - Method
    - Endpoint
    - Status Code
    - Result (PASS / FAIL)

    <h2>Validation Results</h2>
    - Status code validation
    - Field/value validation details

    <h2>Issues Identified</h2>
    - List of defects or mismatches (if any)

    <h2>Risk Assessment</h2>
    - Low / Medium / High
    - Short justification

    <h2>Recommendations</h2>
    - Clear, actionable improvement points

    <h2>Overall Verdict</h2>
    - Final PASS or FAIL with reasoning

    Only return valid HTML.
    """
    return  formatted_summary

def api_performace_reponse_prompt(performance_response=None,performance_parameter=None):
    formatted_summary = f"""You are a Senior Performance Test Architect and Scalability Expert.

    Your task is to analyze performance test results generated by Locust
    and provide an insightful PERFORMANCE ANALYSIS REPORT in HTML format.

    You will be provided with:
    - API method and endpoint
    - Load test configuration (users, spawn rate, duration)
    - Raw Locust HTML report content

    Your responsibilities:
    1. Analyze key performance metrics:
       - Response times (avg, p95, p99)
       - Throughput (requests/sec)
       - Failure rate
    2. Identify performance bottlenecks and instability.
    3. Assess system scalability and reliability.
    4. Highlight SLA/SLO risks.
    5. Provide optimization and tuning recommendations.

    Rules:
    - Base analysis strictly on provided data.
    - Do not assume infrastructure details unless evident.
    - Be concise but insightful.
    - Avoid generic advice; tailor recommendations to observed metrics.

    ---

    ### INPUT DATA
    The following is the performance test data:

    {performance_response}
    {performance_parameter}
    ---
    
    ### OUTPUT FORMAT (STRICT)
    Do NOT wrap output in triple backticks like ```html,```java,```python,```.
    Generate a structured **HTML report** with the following sections:

    <h2>Test Overview</h2>
    - API Method & Endpoint
    - Load Configuration Summary

    <h2>Key Metrics Summary</h2>
    - Average Response Time
    - P95 / P99 Response Time
    - Throughput
    - Error Rate

    <h2>Performance Findings</h2>
    - Observed behavior under load
    - Bottlenecks or anomalies

    <h2>Risk Level</h2>
    - Low / Medium / High
    - Reasoning

    <h2>Recommendations</h2>
    - Performance optimizations
    - Configuration or architectural suggestions

    <h2>Production Readiness Verdict</h2>
    - Ready / Not Ready
    - Explanation

    Only return valid HTML.
    """
    return  formatted_summary
def locust_convert_prompt(Locust_extarcted_data=None,performance_config=None):
    formatted_summary = formatted_summary = f"""
You are a Senior Performance Test Architect with deep expertise in
analyzing Locust performance test results.

You will receive PERFORMANCE TEST OUTPUT extracted from Locust CSV files
AND the test execution configuration used to run the test.

---

### 📥 INPUT 1: Performance Test Configuration (Context Only)

The following configuration describes how the test was executed.
Use this information ONLY to provide contextual understanding of load,
NOT to infer or calculate performance metrics.

performance_config:
- ramp_users: total virtual users ramped
- spawn_rate: users started per second
- run_time: steady-state duration
- stop_time: graceful shutdown duration

{performance_config}

---

### 📥 INPUT 2: Extracted Locust CSV Data

The input contains performance data per API, including:
- stats.csv
- stats_history.csv
- failures.csv
- exceptions.csv

{Locust_extarcted_data}

---

### 🎯 YOUR OBJECTIVE

For EACH API present in the input:

1. Analyze performance metrics strictly from CSV-derived data.
2. Use the performance configuration ONLY to:
   - Describe load intensity
   - Explain observed behavior (e.g., latency under high load)
3. Generate a professional HTML performance report with:
   - Findings
   - Risks
   - Recommendations

---

### ⚠️ STRICT CONSTRAINTS

- Do NOT derive metrics from configuration values.
- Do NOT hallucinate numbers.
- If data is missing, display **"Not Available"**.
- Configuration values must never be treated as results.

---

### 📤 OUTPUT FORMAT (STRICT HTML ONLY)

Return ONLY valid HTML.

<!DOCTYPE html>
<html>
<head>
  <title>API Performance Test Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; }}
    h1, h2, h3 {{ color: #2c3e50; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
    th {{ background-color: #f4f6f8; }}
    .good {{ color: green; font-weight: bold; }}
    .moderate {{ color: orange; font-weight: bold; }}
    .poor {{ color: red; font-weight: bold; }}
    .na {{ color: gray; }}
  </style>
</head>

<body>

<h1>Test Execution Configuration</h1>
<table>
  <tr><th>Parameter</th><th>Value</th></tr>
  <tr><td>Ramp Users</td><td>{(performance_config or {}).get("ramp_users", "Not Available")}</td></tr>
  <tr><td>Spawn Rate (users/sec)</td><td>{(performance_config or {}).get("spawn_rate", "Not Available")}</td></tr>
  <tr><td>Run Time</td><td>{(performance_config or {}).get("run_time", "Not Available")}</td></tr>
  <tr><td>Stop Time</td><td>{(performance_config or {}).get("stop_time", "Not Available")}</td></tr>
</table>

<hr/>

<h1>Overall Performance Summary</h1>
<ul>
  <li><strong>Total APIs Tested:</strong> {{number}}</li>
  <li><strong>Overall Health:</strong> Good | Moderate | Poor | Not Available</li>
</ul>

<h2>Key Risks</h2>
<ul>
  <li>Risk 1</li>
  <li>Risk 2</li>
</ul>

<hr/>

<h1>API-wise Performance Analysis</h1>

<!-- One section per API -->
<section>
  <h2>API: &lt;endpoint or base_path&gt;</h2>

  <h3>Throughput</h3>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Requests / Second</td><td>value or Not Available</td></tr>
    <tr><td>Total Requests</td><td>value or Not Available</td></tr>
  </table>

  <h3>Latency</h3>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Average Response Time</td><td>value or Not Available</td></tr>
    <tr><td>P95 Response Time</td><td>value or Not Available</td></tr>
  </table>

  <h3>Reliability</h3>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Failure Count</td><td>value or Not Available</td></tr>
    <tr><td>Failure Rate</td><td>value or Not Available</td></tr>
    <tr><td>Observations</td><td>text or Not Available</td></tr>
  </table>

  <h3>Stability Assessment</h3>
  <p>Stable | Degrading | Unstable | Not Available</p>

  <h3>Recommendations</h3>
  <ul>
    <li>Recommendation 1</li>
    <li>Recommendation 2</li>
  </ul>
</section>

<hr/>

<h1>Final Recommendation</h1>
<p>Overall production readiness guidance.</p>

</body>
</html>

---

### ✅ QUALITY RULES

- Output ONLY HTML.Do NOT wrap output in triple backticks like ```html,```.
- Do NOT echo raw CSV data.
- Configuration is CONTEXT, not RESULT.
- Use precise engineering language.
"""


    return  formatted_summary
def get_queries_from_ai_updated(formatted_summary):
   print("going inside get_queries_from_ai_updated")
   model = "gpt-5-mini"
   try:
        response = client.chat.completions.create(model=model,
                                          messages=[{"role": "user",
                                                     "content": formatted_summary
                                                     }
                                                    ])
        print(response)
        return response.choices[0].message.content
   except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return None
# def get_queries_from_ai_updated(formatted_summary):
#     # Access the variables
#     api_key = os.getenv("AZURE_OPENAI_API_KEY")
#     endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
#
#     # Set the environment variables explicitly if needed
#     os.environ["AZURE_OPENAI_API_KEY"] = api_key
#     os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint
#     model = AzureChatOpenAI(
#         openai_api_version="2023-05-15",
#         azure_deployment="qepracticekey",
#     )
#     message = HumanMessage(content=formatted_summary)
#     output_value = model([message])
#     print(output_value)
#     return output_value.content



def collect_locust_reports_data(html_report_paths):
    """
    Reads Locust HTML reports and extracts ALL possible raw textual content
    (tables, labels, embedded JS text) for LLM-based interpretation.
    """

    collected_reports = []

    for report_path in html_report_paths:
        if not os.path.exists(report_path):
            continue

        with open(report_path, "r", encoding="utf-8", errors="ignore") as file:
            html_content = file.read()

        soup = BeautifulSoup(html_content, "html.parser")

        # 1️⃣ Extract visible text
        visible_text = soup.get_text(separator=" ", strip=True)

        # 2️⃣ Extract script text (sometimes contains metric labels / values)
        script_texts = []
        for script in soup.find_all("script"):
            if script.string:
                script_texts.append(script.string)

        combined_raw_text = (
            visible_text[:8000] + "\n\n" +
            "\n".join(script_texts)[:8000]
        )

        collected_reports.append({
            "report_name": os.path.basename(report_path),
            "raw_text": combined_raw_text
        })

    return {
        "total_reports": len(collected_reports),
        "reports": collected_reports
    }

def save_html_report(html_content, report_dir, report_name_prefix):
    """
    Saves HTML content to a file and returns the file path.

    Args:
        html_content (str): HTML string content
        report_dir (str): Directory where report should be saved
        report_name_prefix (str): Logical name (api_analysis / performance_analysis)

    Returns:
        str: Full file path of saved HTML report
    """

    # Ensure directory exists
    os.makedirs(report_dir, exist_ok=True)

    # Timestamp to avoid overwrite
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # Build file name
    file_name = f"{report_name_prefix}_{timestamp}.html"
    file_path = os.path.join(report_dir, file_name)

    # Write HTML content
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return file_path

if __name__ == "__main__":
    swagger_url = "https://api.swaggerhub.com/apis/tiger-b7b/equifax_new/1.0.0?format=json"

    openapi_spec = load_openapi_spec(swagger_url)
    api_details = extract_api_details(openapi_spec)

    # Extract Base URL from Swagger if exists, else ask user/UI
    base_url = get_base_url(swagger_url, openapi_spec)

    final_list = build_data_dictionary(api_details, base_url, openapi_spec)

    print(json.dumps(final_list, indent=4))

def read_csv_safe(file_path):
    if not os.path.exists(file_path):
        return []

    with open(file_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
CSV_SUFFIXES = [
    "_stats.csv",
    "_stats_history.csv",
    "_failures.csv",
    "_exceptions.csv"
]
def collect_locust_csv_from_paths(paths):
    aggregated_result = []

    for base_path in paths:
        api_result = {
            "base_path": base_path,
            "stats": [],
            "stats_history": [],
            "failures": [],
            "exceptions": []
        }

        for suffix in CSV_SUFFIXES:
            full_path = base_path + suffix

            if suffix == "_stats.csv":
                api_result["stats"] = read_csv_safe(full_path)

            elif suffix == "_stats_history.csv":
                api_result["stats_history"] = read_csv_safe(full_path)

            elif suffix == "_failures.csv":
                api_result["failures"] = read_csv_safe(full_path)

            elif suffix == "_exceptions.csv":
                api_result["exceptions"] = read_csv_safe(full_path)

        aggregated_result.append(api_result)
    print("*******aggregated_result**********",aggregated_result)
    return aggregated_result
