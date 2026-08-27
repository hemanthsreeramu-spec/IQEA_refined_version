"""
Ordered, chain-aware execution of an API suite.

Responsibilities, in order:
  1. work out an execution order (explicit Order, explicit Depends-On, and
     implicit edges inferred from who produces each ${var})
  2. resolve every ${var} in a row before it is sent
  3. send it through Apicore.makeapicall
  4. extract values from the response into the shared ApiContext
  5. skip rows whose upstream dependency failed, instead of firing them with
     a missing token and collecting noise failures

Deliberately free of Streamlit so both the Swagger and Document flows can call
it; progress is reported through an optional callback.
"""

import json
import re
from urllib.parse import unquote_plus

from .api_context import ApiContext, MissingVariableError, find_variables, parse_extract_spec
from . import api_core_model as api_utils

PATH_PARAM_PATTERN = re.compile(r"\{([^{}]+)\}")

# A ${var} written inside a longer string — removed before hunting for path
# placeholders so '${uid}' is not mistaken for the path parameter '{uid}'.
VAR_IN_TEXT_PATTERN = re.compile(r"\$\{[^{}]*\}")

RESULT_PASS = "PASS"
RESULT_FAIL = "FAIL"
RESULT_SKIP = "SKIP"


# ======================================================================
# row access — one adapter so both input shapes look the same in here
# ======================================================================
class RowView:
    def __init__(self, row, mode, index):
        self.row = row
        self.mode = mode
        self.index = index

    @property
    def is_file(self):
        return self.mode == "file"

    @property
    def name(self):
        # Both flows carry a test case name; the URL belongs in the Endpoint
        # column, not in the name. Fall back only when a row genuinely has none.
        named = str(self.row.get("test_case_name") or "").strip()
        if named:
            return named
        if self.is_file:
            return f"row_{self.index + 1}"
        return f"{self.method} {self.endpoint}"

    @property
    def method(self):
        key = "method" if self.is_file else "httpMethod"
        return str(self.row.get(key) or "").upper()

    @property
    def endpoint(self):
        return str(self.row.get("endpoint") or "")

    @property
    def validate(self):
        return bool(self.row.get("validate") if self.is_file else self.row.get("Validate?"))

    @property
    def performance(self):
        return bool(self.row.get("performance") if self.is_file else self.row.get("Performance?"))

    @property
    def extract_spec(self):
        # 'extract' is the new field; 'extract_token' is the legacy Excel column
        return self.row.get("extract") or self.row.get("extract_token") or ""

    @property
    def depends_on(self):
        raw = self.row.get("dependsOn") or self.row.get("depends_on") or ""
        if isinstance(raw, (list, tuple)):
            return [str(x).strip() for x in raw if str(x).strip()]
        return [part.strip() for part in re.split(r"[,;\n]+", str(raw)) if part.strip()]

    @property
    def order(self):
        raw = self.row.get("order")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @property
    def produces(self):
        return [name for name, _ in parse_extract_spec(self.extract_spec)]

    @property
    def open_path_params(self):
        """
        '{param}' names in the endpoint that nothing on the row itself fills.

        These are bound at run time from values extracted earlier in the run, so
        for ordering purposes they count as references exactly like ${param}.
        """
        filled = {
            str(name) for name, value in _param_items(self.row.get("pathParams"))
            if name and value is not None and str(value).strip()
        }
        return [name for name in path_placeholders(self.endpoint) if name not in filled]

    def references(self):
        """${var} names this row depends on, across every field we resolve."""
        return find_variables(
            {
                "endpoint": self.endpoint,
                "baseUrl": self.row.get("baseUrl"),
                "headers": self.row.get("headers"),
                "payload": self.row.get("payload"),
                "body_format": self.row.get("body_format"),
                "authorization": self.row.get("authorization"),
                # '${access_token}' in the sheet's bearer column is a dependency
                # like any other: without it here the row that consumes the token
                # can be ordered before the row that issues it.
                "_bearer_token": self.row.get("_bearer_token"),
                "pathParams": self.row.get("pathParams"),
                "queryParams": self.row.get("queryParams"),
                # A file name can be chained too: 'files=${invoice_name}'
                "attachments": self.row.get("attachments"),
            }
        )


# ======================================================================
# ordering
# ======================================================================
def build_execution_plan(rows, mode, global_headers=None):
    """
    Return (ordered_views, edges, notes).

    edges maps a row index to the set of row indexes it must run after.
    Ordering is a topological sort, ties broken by explicit Order then by the
    row's original position — so a suite with no dependencies at all keeps the
    exact order the user sees on screen.
    """
    views = [RowView(row, mode, i) for i, row in enumerate(rows)]
    notes = []

    by_name = {}
    for view in views:
        by_name.setdefault(view.name, view.index)

    # who produces which variable
    producer_of = {}
    for view in views:
        for var in view.produces:
            if var in producer_of:
                notes.append(
                    f"'{var}' is extracted by more than one API — "
                    f"'{views[producer_of[var]].name}' and '{view.name}'; the later one wins at runtime"
                )
            else:
                producer_of[var] = view.index

    # Same map keyed loosely, so a camelCase '{agentId}' in a Swagger path can
    # find a snake_case 'agent_id' extract. Only consulted when the exact name
    # misses, and only when one producer normalises to it.
    producer_loose = {}
    for var, index in producer_of.items():
        producer_loose.setdefault(_normalize(var), set()).add(index)

    edges = {view.index: set() for view in views}

    # A ${var} in a global header is referenced by every row that receives it, so
    # it has to create the same ordering edges as one written on the row itself.
    global_vars = find_variables(global_headers or {})

    for view in views:
        for var in global_vars - set(view.produces):
            producer = producer_of.get(var)
            if producer is not None and producer != view.index:
                edges[view.index].add(producer)

    for view in views:
        # explicit Depends-On
        for dep_name in view.depends_on:
            if dep_name in by_name:
                if by_name[dep_name] != view.index:
                    edges[view.index].add(by_name[dep_name])
            else:
                notes.append(f"'{view.name}' depends on '{dep_name}', which is not in the selected APIs")

        # implicit: whoever produces a ${var} this row references
        for var in view.references():
            producer = producer_of.get(var)
            if producer is None:
                continue
            if producer == view.index:
                notes.append(
                    f"'{view.name}' references ${{{var}}} but also extracts it — "
                    f"a value cannot be consumed by the API that produces it"
                )
                continue
            edges[view.index].add(producer)

        # implicit: a bare '{param}' left in the path is filled from the store
        # at send time, so whoever extracts that name has to run first
        for name in view.open_path_params:
            producer = _lookup_producer(name, producer_of, producer_loose)
            if producer is None or producer == view.index:
                continue
            edges[view.index].add(producer)

    ordered_indexes, cycle = _topological_sort(views, edges)
    if cycle:
        names = ", ".join(views[i].name for i in cycle)
        raise ValueError(f"Circular dependency between APIs: {names}")

    return [views[i] for i in ordered_indexes], edges, notes


def _sort_key(view):
    return (view.order if view.order is not None else 10**6, view.index)


def _topological_sort(views, edges):
    remaining = {view.index: set(edges[view.index]) for view in views}
    ordered = []

    while remaining:
        ready = [i for i, deps in remaining.items() if not deps]
        if not ready:
            return ordered, sorted(remaining)  # everything left is in a cycle

        ready.sort(key=lambda i: _sort_key(views[i]))
        chosen = ready[0]
        ordered.append(chosen)
        del remaining[chosen]
        for deps in remaining.values():
            deps.discard(chosen)

    return ordered, None


# ======================================================================
# path placeholders
# ======================================================================
def path_placeholders(endpoint):
    """
    The '{param}' names in a path, ignoring any ${var} placeholders.

    '/users/${uid}/orders/{order_id}' has one path parameter, 'order_id' —
    '${uid}' contains the substring '{uid}' but is a chained variable that
    resolves on its own, not an unfilled path parameter.
    """
    return PATH_PARAM_PATTERN.findall(VAR_IN_TEXT_PATTERN.sub("", str(endpoint or "")))


def _normalize(name):
    """Case- and separator-insensitive key: 'agentId' and 'agent_id' agree."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _lookup_producer(name, producer_of, producer_loose):
    """Row index that extracts `name`, exact match first, then loosely."""
    if name in producer_of:
        return producer_of[name]
    candidates = producer_loose.get(_normalize(name)) or set()
    return next(iter(candidates)) if len(candidates) == 1 else None


def bind_path_placeholders(endpoint, context):
    """
    Fill '{param}' placeholders left in a path from values already extracted.

    An endpoint copied off a Swagger path keeps its own braces —
    '/agents/{agent_id}' — and the natural expectation is that an upstream
    Extract-Values named agent_id fills it, without the endpoint also having to
    be rewritten as '/agents/${agent_id}'. Exact name first; failing that a
    case- and separator-insensitive match, so a camelCase path parameter binds
    to a snake_case extracted value. The loose match is used only when exactly
    one stored name normalises to it, so it can never pick between two.

    Returns (endpoint, bound, loosely_bound) — bound maps placeholder to the
    value used, loosely_bound maps it to the stored name it came from so the
    result row can say where the value came from.
    """
    names = path_placeholders(endpoint)
    if not names:
        return endpoint, {}, {}

    stored = context.as_dict()
    loose = {}
    for stored_name in stored:
        loose.setdefault(_normalize(stored_name), []).append(stored_name)

    bound, loosely_bound = {}, {}
    for name in names:
        if name in stored:
            source = name
        else:
            candidates = loose.get(_normalize(name)) or []
            if len(candidates) != 1:
                continue
            source = candidates[0]
            loosely_bound[name] = source

        value = stored[source]
        bound[name] = value
        endpoint = endpoint.replace("{" + name + "}", str(value))

    return endpoint, bound, loosely_bound


# ======================================================================
# request preparation
# ======================================================================
def _param_items(spec):
    """(name, value) pairs out of either param shape the grid produces."""
    if not spec:
        return []
    if isinstance(spec, dict):
        return list(spec.items())
    return [(entry.get("name"), entry.get("value")) for entry in spec if isinstance(entry, dict)]


def _flatten_params(spec, context):
    """
    Turn the grid's param metadata into a flat {name: value} dict, resolving
    ${vars} and dropping anything the user left blank.
    """
    flat = {}

    for name, value in _param_items(spec):
        if not name:
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        flat[name] = context.resolve(value, field=f"param '{name}'")

    return flat


def prepare_row(view, context, global_headers=None):
    """
    Resolve a row into something makeapicall can send.

    Returns (resolved_row, path_params, query_params, notes). Raises
    MissingVariableError if a ${var} was never produced.

    global_headers are merged in here rather than written onto the row, so the
    row on screen stays as the user typed it and nothing depends on the order in
    which they selected APIs and typed the header.
    """
    row = view.row
    path_params = _flatten_params(row.get("pathParams"), context)
    query_params = _flatten_params(row.get("queryParams"), context)

    resolvable = {k: v for k, v in row.items() if k not in ("pathParams", "queryParams")}
    resolved = context.resolve(resolvable, field=view.name)

    # An auth_type=BEARER row may carry its own token in the sheet. Read before
    # the global headers are merged: a row that brought its own token must not
    # have the UI's Authorization laid on top of it, since that header is
    # checked first when the request is built and would win by default.
    wants_bearer = view.is_file and str(row.get("auth_type") or "").strip().upper() == "BEARER"
    row_token = str(resolved.get("_bearer_token") or "").strip() if wants_bearer else ""

    if global_headers:
        headers = dict(resolved.get("headers") or {})
        produced = set(view.produces)
        for name, value in global_headers.items():
            if name in headers:
                continue  # an explicit per-row header wins
            if row_token and str(name).strip().lower() == "authorization":
                continue  # so does a token written on the row
            if find_variables(value) & produced:
                continue  # the API that issues the token must not consume it
            headers[name] = context.resolve(value, field=f"global header '{name}'")
        resolved["headers"] = headers

    # Substitute {param} placeholders in the endpoint path
    endpoint = str(resolved.get("endpoint") or "")
    for name, value in path_params.items():
        endpoint = endpoint.replace("{" + name + "}", str(value))

    # Whatever is still in braces is filled from values extracted earlier in
    # this run — the Excel flow has no path-parameter column at all, so this is
    # the only way '/agents/{agent_id}' can be chained there.
    endpoint, bound, loosely_bound = bind_path_placeholders(endpoint, context)
    for name, value in bound.items():
        path_params.setdefault(name, value)

    notes = [
        f"path {{{name}}} filled from extracted '{source}'"
        for name, source in loosely_bound.items()
    ]

    resolved["endpoint"] = endpoint
    resolved["queryParams"] = query_params
    resolved["pathParams"] = path_params

    # Excel rows using auth_type=BEARER, most specific source first:
    #   1. the sheet's bearer column, already resolved above
    #   2. a token captured earlier in this run under one of the usual names
    #   3. (in get_auth_headers) the UI global header, then auth_config.ini
    if wants_bearer:
        if row_token:
            resolved["_bearer_token"] = row_token
        else:
            for candidate in ("token", "access_token", "accessToken", "bearer_token"):
                if context.has(candidate):
                    resolved["_bearer_token"] = context.get(candidate)
                    break

    return resolved, path_params, query_params, notes


def unresolved_path_params(endpoint):
    return path_placeholders(endpoint)


# ======================================================================
# the run
# ======================================================================
def run_suite(
    rows,
    mode,
    context=None,
    validate_fn=None,
    on_progress=None,
    performance=False,
    global_headers=None,
):
    """
    Execute rows in dependency order.

    validate_fn(response, resolved_row, view) -> (result, extra_columns)
    on_progress(done, total, label)

    Returns (results, performance_paths, context, notes).
    """
    context = context or ApiContext()
    validate_fn = validate_fn or _default_validate

    ordered, edges, notes = build_execution_plan(rows, mode, global_headers)

    runnable = [v for v in ordered if v.validate or v.performance]
    total = len(runnable)

    core = api_utils.Apicore()
    results = []
    performance_paths = []

    failed_indexes = set()
    view_by_index = {view.index: view for view in ordered}

    for done, view in enumerate(runnable, start=1):
        if on_progress:
            on_progress(done, total, view.name)

        # ---- upstream failed? skip rather than fire a broken request ----
        blocking = _blocking_dependency(view.index, edges, failed_indexes)
        if blocking is not None:
            blocker = view_by_index[blocking].name
            results.append(
                _result_row(
                    view,
                    endpoint=view.endpoint,
                    status=RESULT_SKIP,
                    result=RESULT_SKIP,
                    note=f"skipped — upstream '{blocker}' did not pass",
                )
            )
            failed_indexes.add(view.index)
            continue

        # ---- editor left the row in an unparseable state? ----
        edit_error = (
            view.row.get("_headers_error")
            or view.row.get("_payload_error")
            # A named-but-missing file is refused here rather than sent without
            # the upload, which would come back as an opaque 400 — or worse, a
            # 200 that quietly did nothing.
            or view.row.get("_attachment_error")
        )
        if edit_error:
            remedy = (
                "add the file and run again"
                if edit_error == view.row.get("_attachment_error")
                else "fix the JSON and run again"
            )
            results.append(
                _result_row(view, endpoint=view.endpoint, status="NOT SENT", result=RESULT_FAIL,
                            note=f"{edit_error} — {remedy}")
            )
            failed_indexes.add(view.index)
            continue

        # ---- resolve ${vars} ----
        try:
            resolved, path_params, query_params, prep_notes = prepare_row(view, context, global_headers)
        # ValueError covers a generator that could not produce a value —
        # ${__fileBase64(missing.pdf)} fails this row, it does not kill the run.
        except (MissingVariableError, ValueError) as exc:
            results.append(
                _result_row(view, endpoint=view.endpoint, status="NOT SENT", result=RESULT_FAIL, note=str(exc))
            )
            failed_indexes.add(view.index)
            continue

        combined_url = f"{resolved.get('baseUrl', '')}{resolved.get('endpoint', '')}"

        leftover = unresolved_path_params(resolved.get("endpoint"))
        if leftover:
            results.append(
                _result_row(
                    view,
                    endpoint=combined_url,
                    status="NOT SENT",
                    result=RESULT_FAIL,
                    note=f"path parameter(s) not supplied: {', '.join(leftover)} — "
                         f"put a value in the endpoint, or have an earlier API "
                         f"Extract-Values a value named {leftover[0]}",
                )
            )
            failed_indexes.add(view.index)
            continue

        # ---- send ----
        response = None
        note_parts = list(prep_notes)
        if view.validate:
            try:
                response, combined_url, http_method = core.makeapicall(resolved, mode)
            except Exception as exc:
                results.append(
                    _result_row(view, endpoint=combined_url, status="ERROR", result=RESULT_FAIL, note=str(exc))
                )
                failed_indexes.add(view.index)
                continue

            if response is None:
                results.append(
                    _result_row(view, endpoint=combined_url, status="NO RESPONSE", result=RESULT_FAIL)
                )
                failed_indexes.add(view.index)
                continue

            result, extra = validate_fn(response, resolved, view)

            # ---- extract for downstream rows ----
            extracted, failures = context.extract(response, view.extract_spec, produced_by=view.name)
            if failures:
                note_parts.extend(failures)
                # A row whose extraction failed cannot satisfy its dependents
                if view.produces:
                    result = RESULT_FAIL

            if result != RESULT_PASS:
                failed_indexes.add(view.index)

            results.append(
                _result_row(
                    view,
                    endpoint=combined_url,
                    status=response.status_code,
                    result=result,
                    extracted=extracted,
                    note="; ".join(note_parts),
                    # makeapicall records the parts it opened on the resolved row
                    extra={**(extra or {}),
                           **describe_request(response, resolved.get("_multipart_summary"))},
                    query_params=query_params,
                    response_text=response.text,
                )
            )

        # ---- performance ----
        if performance and view.performance:
            try:
                path, _csv = core.makeperformancecall(resolved, mode)
                if path:
                    performance_paths.append(path)
            except Exception as exc:
                notes.append(f"performance run failed for '{view.name}': {exc}")

    return results, performance_paths, context, notes


def _blocking_dependency(index, edges, failed_indexes):
    for dep in edges.get(index, ()):
        if dep in failed_indexes:
            return dep
    return None


RESPONSE_PREVIEW_CHARS = 2000

# Header values that must never be written out in full — results are fed to the
# LLM analyser and saved into HTML reports on disk.
SENSITIVE_HEADERS = ("authorization", "cookie", "x-api-key", "api-key", "token", "secret", "auth")


def mask_header(name, value):
    if not any(marker in (name or "").lower() for marker in SENSITIVE_HEADERS):
        return value
    text = str(value)
    if len(text) <= 12:
        return "***"
    # Keep the scheme prefix visible — 'Bearer ' vs a raw token is exactly the
    # kind of mistake this view exists to catch.
    scheme, _, rest = text.partition(" ")
    if rest:
        return f"{scheme} {rest[:4]}…{rest[-4:]} ({len(rest)} chars)"
    return f"{text[:4]}…{text[-4:]} ({len(text)} chars)"


def describe_request(response, multipart_summary=None):
    """
    Read back the request requests actually sent, with secrets masked.

    A multipart body is described rather than transcribed: it is raw file bytes,
    and these results are shown in the grid, written into HTML reports and fed
    to the LLM analyser.
    """
    request = getattr(response, "request", None)
    if request is None:
        return {}

    headers = {k: mask_header(k, v) for k, v in dict(request.headers or {}).items()}
    body = request.body

    if _is_multipart(request):
        body = multipart_summary or f"<multipart/form-data, {_body_length(body)}>"
    elif _is_form_urlencoded(request):
        body = _mask_form_body(body)
    elif isinstance(body, bytes):
        try:
            body = body.decode("utf-8", errors="replace")
        except Exception:
            body = f"<{len(body)} bytes>"

    return {
        "Request URL": request.url,
        "Request Headers": json.dumps(headers, indent=2),
        "Request Body": _truncate(body, RESPONSE_PREVIEW_CHARS),
    }


def _is_multipart(request):
    return _sent_content_type(request).startswith("multipart/")


def _is_form_urlencoded(request):
    return _sent_content_type(request).startswith("application/x-www-form-urlencoded")


def _sent_content_type(request):
    headers = dict(request.headers or {})
    return str(headers.get("Content-Type") or headers.get("content-type") or "").lower()


# A form body carries credentials as ordinary fields, so the header masking above
# never sees them. 'password' is here and not in SENSITIVE_HEADERS because it is
# a body field name, not a header one.
SENSITIVE_BODY_FIELDS = SENSITIVE_HEADERS + (
    "password", "passwd", "pwd", "credential", "assertion", "client_id",
)


def _mask_form_body(body):
    """
    Mask credential fields in an x-www-form-urlencoded body.

    This body is shown in the results grid, written into the HTML report on disk
    and sent to the LLM analyser. A token request sends client_secret as a plain
    form field, so transcribing it verbatim would put the secret in all three.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    text = str(body or "")
    if "=" not in text:
        return text

    pairs = []
    for chunk in text.split("&"):
        name, separator, value = chunk.partition("=")
        if not separator:
            pairs.append(chunk)
            continue
        name = unquote_plus(name)
        pairs.append(f"{name}={_mask_form_value(name, unquote_plus(value))}")
    return "&".join(pairs)


def _mask_form_value(name, value):
    if not any(marker in (name or "").lower() for marker in SENSITIVE_BODY_FIELDS):
        return value
    text = str(value)
    if len(text) <= 12:
        return "***"
    return f"{text[:4]}…{text[-4:]} ({len(text)} chars)"


def _body_length(body):
    try:
        return f"{len(body)} bytes"
    except TypeError:
        # A streamed body (a file handle) has no length
        return "streamed"


def _result_row(view, endpoint, status, result, extracted=None, note="", extra=None,
                query_params=None, response_text=None):
    row = {
        "Test Case": view.name,
        "Method": view.method,
        "Endpoint": endpoint,
        "Status": status,
        "Result": result,
        "Extracted": ", ".join(f"{k}={_short(v)}" for k, v in (extracted or {}).items()),
        "Note": note or "",
        # Kept so the user can see what a response contains and work out the
        # jsonpath to extract from it.
        "Actual Response": _truncate(response_text, RESPONSE_PREVIEW_CHARS),
    }
    if query_params:
        row["Query"] = json.dumps(query_params)
    if extra:
        row.update(extra)
    return row


def _truncate(text, limit):
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + f"… [{len(text) - limit} more chars]"


def _short(value, limit=40):
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


# A create call may answer 200 or 201 depending on the implementation, and a spec
# usually documents only one of them — so these two are interchangeable. Any other
# expected code (204, 202, or a deliberate 4xx in a negative test) must match exactly.
INTERCHANGEABLE_SUCCESS = frozenset({200, 201})


def accepted_status_codes(expected):
    try:
        expected = int(expected)
    except (TypeError, ValueError):
        expected = 200
    return set(INTERCHANGEABLE_SUCCESS) if expected in INTERCHANGEABLE_SUCCESS else {expected}


def split_expected_parts(text):
    """
    Split an Expected-Message cell on commas that are not inside quotes.

    Quotes are treated as delimiters and dropped, so the messy shapes people
    actually paste all normalise:
        first_name:Janet, status:active
        "hbjhg","id":"3243"
        message:"Created, secured"      <- the inner comma stays in the value
    """
    parts, current, quote = [], [], None

    for char in str(text or ""):
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
            continue
        if char in "\"'":
            quote = char
            continue
        if char == ",":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)

    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def parse_expected_pairs(text):
    """
    Parse Expected-Message into checks.

    Returns [(key, value), ...] where key is None for a bare value — that means
    "this text must appear somewhere in the response" rather than naming a field.
    Splits on the FIRST colon only, so values containing ':' (URLs, timestamps)
    survive intact.
    """
    checks = []
    for part in split_expected_parts(text):
        if ":" in part:
            key, value = part.split(":", 1)
            key, value = key.strip().strip("\"'"), value.strip().strip("\"'")
            if key:
                checks.append((key, value))
            elif value:
                checks.append((None, value))
        else:
            checks.append((None, part.strip()))
    return checks


def values_match(actual, expected):
    """
    Compare a response value against the expected text.

    Partial by default — 'Janet' matches 'Janet Weaver' — because Expected-Message
    is written by hand and rarely reproduces a value byte for byte.

    Numbers and booleans are compared by value instead, since substring matching
    would let an expected id of 3 pass against an actual 13243.
    """
    if actual is None:
        return False, "not found"

    expected_text = str(expected).strip()
    if not expected_text:
        return True, "no value to check"

    # Numeric on both sides -> compare as numbers
    actual_number, expected_number = _as_number(actual), _as_number(expected_text)
    if actual_number is not None and expected_number is not None:
        return actual_number == expected_number, "numeric"

    # Booleans -> compare as booleans
    if isinstance(actual, bool) or expected_text.lower() in ("true", "false"):
        return str(actual).strip().lower() == expected_text.lower(), "boolean"

    # Structures -> search their JSON form
    if isinstance(actual, (dict, list)):
        return expected_text.lower() in json.dumps(actual, default=str).lower(), "contains"

    return expected_text.lower() in str(actual).strip().lower(), "contains"


def response_message(response, limit=200):
    """
    A short, human-readable summary of what the API actually said — the
    'message'/'detail' field when there is one, otherwise a trimmed body.
    """
    try:
        body = response.json()
    except Exception:
        try:
            body = json.loads(response.text)
        except Exception:
            body = None

    if isinstance(body, dict):
        for key in ("message", "detail", "error", "msg"):
            if key in body and body[key] not in (None, ""):
                value = body[key]
                return str(value if not isinstance(value, (dict, list)) else json.dumps(value))[:limit]

    text = " ".join(str(response.text or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _lookup_expected(body, key):
    """
    Find a value the Expected-Message column refers to.

    Checks the 'data' envelope first (the template's long-standing convention),
    then the top level, then anywhere nested — so a sheet does not have to know
    how deeply an API wraps its payload. A key starting with '$' is a jsonpath.
    """
    if key.startswith("$"):
        from .api_context import ApiContext
        value = ApiContext._json_path(body, key)
        return None if value.__class__.__name__ == "_NoMatch" else value

    if isinstance(body, dict):
        envelope = body.get("data")
        if isinstance(envelope, dict) and key in envelope:
            return envelope[key]
        if key in body:
            return body[key]

    found = _search_nested(body, key)
    return found


def _search_nested(node, key, depth=0):
    if depth > 6:
        return None
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            hit = _search_nested(value, key, depth + 1)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for item in node:
            hit = _search_nested(item, key, depth + 1)
            if hit is not None:
                return hit
    return None


def document_validate(response, resolved_row, view):
    """
    Validation for Excel-driven rows: status code, plus the Expected-Message
    fields when that cell is filled. Applied uniformly to every method — a POST
    is not required to echo its whole request back, which almost no API does.
    """
    expected = resolved_row.get("expected_status") or resolved_row.get("Expected-StatusCode") or 200
    accepted = accepted_status_codes(expected)
    extra = {
        "Expected Status": " or ".join(str(code) for code in sorted(accepted)),
        "Expected Response": resolved_row.get("expected_message", "") or "",
        "Actual Message": response_message(response),
    }

    # Status code is checked first — the field checks only run once it matches,
    # so a 401 is reported as an auth failure rather than a pile of missing fields.
    if response.status_code not in accepted:
        extra["Validation"] = f"status {response.status_code} not in {sorted(accepted)}"
        return RESULT_FAIL, extra

    checks = parse_expected_pairs(resolved_row.get("expected_message"))
    if not checks:
        extra["Validation"] = "status only (no Expected-Message)"
        return RESULT_PASS, extra

    body = None
    try:
        body = response.json()
    except Exception:
        try:
            body = json.loads(response.text)
        except Exception:
            body = None

    raw_text = response.text or ""
    mismatches, matched, observed = [], 0, []

    for key, want in checks:
        if key is not None and body is not None:
            found = _lookup_expected(body, key)
            observed.append(f"{key}={found if found is not None else '<missing>'}")

        if key is None:
            # Bare value — must appear anywhere in the response
            if str(want).lower() in raw_text.lower():
                matched += 1
            else:
                mismatches.append(f"'{want}' not found anywhere in the response")
            continue

        if body is None:
            mismatches.append(f"{key}: response is not JSON, cannot look up fields")
            continue

        actual = _lookup_expected(body, key)
        is_match, rule = values_match(actual, want)
        if is_match:
            matched += 1
        elif rule == "not found":
            mismatches.append(f"{key}: not present in the response")
        else:
            mismatches.append(f"{key}: expected '{want}', got '{actual}'")

    # Report the values actually seen for the fields being checked — that is
    # what a reader wants next to the expected text, ahead of a generic message.
    if observed:
        extra["Actual Message"] = "; ".join(observed)[:300]

    if mismatches:
        extra["Validation"] = "; ".join(mismatches)
        return RESULT_FAIL, extra

    extra["Validation"] = f"{matched} check(s) matched"
    return RESULT_PASS, extra


def _default_validate(response, resolved_row, view):
    expected = resolved_row.get("Expected-StatusCode") or resolved_row.get("expected_status") or 200
    accepted = accepted_status_codes(expected)
    result = RESULT_PASS if response.status_code in accepted else RESULT_FAIL
    return result, {"Expected Status": " or ".join(str(code) for code in sorted(accepted))}
