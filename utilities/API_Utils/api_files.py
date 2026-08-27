"""
File attachments for API requests.

Everything that turns a file name written on a sheet into bytes on the wire
lives here: where files are looked up, how the Attachments cell is parsed, and
how a payload plus its attachments become the arguments requests needs. Shared
by the Excel reader, the request builder, the ${__fileBase64} generator and the
performance worker, so all four agree on what a part is called.

The payload is never replaced by the attachments — in the usual row both are
filled and the parameters travel alongside the file.

Three encodings, because which one an API accepts is the API's decision:

  form    attachments + each payload key as its own text form field. The
          default, and what a Swagger UI file picker submits.
  json    attachments + the whole payload as one application/json part, for
          endpoints that bind the body to an object (Spring @RequestPart,
          .NET DTO-plus-file) and therefore need real numbers and nesting.
  inline  no multipart at all — ${__fileBase64(x)} embeds the file inside the
          ordinary JSON body. Driven by api_context's generators; this module
          only reads the file.

Files are looked up in Input/attachments, so a suite carries no machine-specific
paths and can be handed to anyone with the same folder. An absolute path in the
cell is still honoured for a one-off.
"""

import base64
import json
import mimetypes
import os
import re

ATTACHMENT_SUBFOLDER = os.path.join("Input", "attachments")

# Part name used when the Attachments cell names a file but not a field. It has
# to match what the endpoint calls its upload field; 'files' is the default
# because that is the common spelling for one accepting more than one file, and
# 'field=name.pdf' overrides it per entry.
DEFAULT_ATTACHMENT_FIELD = "files"

# Part name for the 'json' encoding when the row does not say what to call it.
DEFAULT_JSON_PART_NAME = "data"

BODY_AS_JSON_VALUES = ("json", "json-part", "jsonpart", "part", "dto", "object")
BODY_AS_FORM_VALUES = ("form", "fields", "form-data", "formdata", "multipart")

# A trailing ':type/subtype' is only read as a content type when it really looks
# like one, so 'D:\docs\invoice.pdf' keeps its drive letter.
MIME_PATTERN = re.compile(r"^[A-Za-z0-9.+_-]+/[A-Za-z0-9.+_*-]+$")

# Spellings a spreadsheet uses to mean "nothing here".
BLANK_VALUES = ("", "NAN", "NODATA", "NO_DATA", "NONE", "NA", "N/A", "-")

# Ceiling for ${__fileBase64}. Inlining is ~33% larger than the file and the
# whole string is held in memory, logged and reported, so a big upload belongs
# in the Attachments column instead.
MAX_INLINE_FILE_BYTES = 8 * 1024 * 1024

DEFAULT_CONTENT_TYPE = "application/octet-stream"


# ----------------------------------------------------------------------
# where files live
# ----------------------------------------------------------------------
def attachments_folder():
    """The folder relative names in the Attachments column resolve against."""
    return os.path.join(os.getcwd(), ATTACHMENT_SUBFOLDER)


def ensure_attachments_folder():
    folder = attachments_folder()
    os.makedirs(folder, exist_ok=True)
    return folder


def available_attachments():
    """Names of the files currently sitting in Input/attachments."""
    folder = attachments_folder()
    if not os.path.isdir(folder):
        return []
    return sorted(
        name for name in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, name))
    )


def resolve_attachment_path(filename):
    """
    Absolute path for one name from the Attachments column.

    An absolute path is honoured as typed; anything else is looked up under
    Input/attachments.
    """
    name = str(filename or "").strip().strip('"').strip("'")
    if not name:
        return ""
    if os.path.isabs(name):
        return os.path.normpath(name)
    return os.path.normpath(os.path.join(attachments_folder(), name))


def attachment_exists(filename):
    path = resolve_attachment_path(filename)
    return bool(path) and os.path.isfile(path)


def missing_attachment_message(filename, label=""):
    prefix = f"{label}: " if label else ""
    return (
        f"{prefix}attachment '{filename}' not found — put the file in "
        f"{ATTACHMENT_SUBFOLDER}{os.sep} (looked in {resolve_attachment_path(filename)})"
    )


def guess_content_type(path_or_name, declared=None):
    """Content type for a part: what the sheet declared, else guessed."""
    if declared and str(declared).strip():
        return str(declared).strip()
    guessed, _encoding = mimetypes.guess_type(str(path_or_name or ""))
    return guessed or DEFAULT_CONTENT_TYPE


# ----------------------------------------------------------------------
# parsing the sheet
# ----------------------------------------------------------------------
def is_blank(value):
    """True for an empty cell, in any of the spellings a sheet uses."""
    if value is None:
        return True
    # NaN — the only float not equal to itself. Checked without pandas so this
    # module stays importable by the Locust worker.
    if isinstance(value, float) and value != value:
        return True
    return str(value).strip().upper() in BLANK_VALUES


def _split_content_type(text):
    """Split a trailing ':type/subtype' off one attachment entry."""
    head, separator, tail = str(text).rpartition(":")
    if separator and MIME_PATTERN.match(tail.strip()):
        return head.strip(), tail.strip()
    return str(text).strip(), None


def parse_attachment_spec(raw, label=""):
    """
    Parse the Attachments cell into multipart part descriptors.

    Entries are separated by ';' or newlines. Accepted forms:

        contract.pdf                          -> part named 'files'
        files=contract.pdf                    -> part named explicitly
        files=contract.pdf:application/pdf    -> force the content type
        files=a.pdf; files=b.pdf              -> one field, two files
        files=${invoice_name}                 -> resolved at run time

    Returns (parts, errors), each part {'field', 'filename', 'content_type'}.
    Existence is checked here so a typo surfaces when the sheet is uploaded
    rather than as a 400 mid-run; a name still holding ${...} is left for the
    runner and is not checked. A field written with no file name at all
    ('files=') is an error rather than a silently skipped part — that row was
    meant to upload something, and sending it as plain JSON would look like a
    pass.
    """
    parts, errors = [], []
    entries = []

    if isinstance(raw, (list, tuple)):
        for item in raw:
            # Already-parsed parts: the Swagger flow keeps them as dicts
            if isinstance(item, dict):
                filename = str(item.get("filename") or "").strip()
                field = str(item.get("field") or "").strip() or DEFAULT_ATTACHMENT_FIELD
                if filename:
                    parts.append({
                        "field": field,
                        "filename": filename,
                        "content_type": item.get("content_type"),
                    })
                elif item.get("required"):
                    # A file field discovered in a Swagger spec, still unfilled
                    errors.append(
                        f"{label + ': ' if label else ''}attachment field '{field}' "
                        f"has no file name — add one, e.g. {field}=contract.pdf"
                    )
            else:
                entries.append(str(item))
    elif is_blank(raw):
        return parts, errors
    else:
        entries = re.split(r"[;\n]+", str(raw))

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        field, separator, filename = entry.partition("=")
        if not separator:
            # A bare name — the field stays at the default
            field, filename = DEFAULT_ATTACHMENT_FIELD, field

        filename, content_type = _split_content_type(filename)
        field = field.strip() or DEFAULT_ATTACHMENT_FIELD
        filename = filename.strip().strip('"').strip("'")

        if not filename:
            errors.append(
                f"{label + ': ' if label else ''}attachment field '{field}' has no "
                f"file name — add one, e.g. {field}=contract.pdf"
            )
            continue

        parts.append({"field": field, "filename": filename, "content_type": content_type})

    for part in parts:
        filename = part["filename"]
        if "${" in filename:
            continue  # resolved at run time; nothing to check yet
        if not attachment_exists(filename):
            errors.append(missing_attachment_message(filename, label))

    return parts, errors


def parse_body_mode(raw):
    """
    Read the Body-As cell into (mode, json_part_name).

    Blank or 'form' -> each payload key becomes its own text form field next to
    the file. 'json' -> the whole payload travels as one application/json part,
    named 'data' unless written as 'json:metadata'.
    """
    if is_blank(raw):
        return "form", DEFAULT_JSON_PART_NAME

    head, _separator, name = str(raw).strip().partition(":")
    if head.strip().lower() in BODY_AS_JSON_VALUES:
        return "json", (name.strip() or DEFAULT_JSON_PART_NAME)
    return "form", DEFAULT_JSON_PART_NAME


def format_body_mode(mode, json_part_name=DEFAULT_JSON_PART_NAME):
    """Render the body mode back into the Body-As cell text (for the export)."""
    if mode != "json":
        return ""
    if json_part_name and json_part_name != DEFAULT_JSON_PART_NAME:
        return f"json:{json_part_name}"
    return "json"


def format_attachment_spec(parts):
    """Render parts back into the Attachments cell text (for the export)."""
    entries = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        field = str(part.get("field") or "").strip() or DEFAULT_ATTACHMENT_FIELD
        filename = str(part.get("filename") or "").strip()
        if not filename:
            # A field read off a spec but not yet given a file: exported as
            # 'files=' so the sheet shows exactly what needs filling in.
            entries.append(f"{field}=")
            continue
        content_type = str(part.get("content_type") or "").strip()
        entries.append(f"{field}={filename}" + (f":{content_type}" if content_type else ""))
    return "; ".join(entries)


# ----------------------------------------------------------------------
# building the request
# ----------------------------------------------------------------------
def form_fields(payload):
    """
    Flatten a payload into multipart form fields.

    Form parts carry no type information, so every value goes out as text: a
    bool becomes 'true'/'false' rather than Python's 'True', and a nested
    object is JSON-encoded into its field. A list of scalars is kept as a list
    so requests repeats the field, which is how form data says "several values
    under one name". An API that needs real types wants Body-As: json instead.
    """
    if not isinstance(payload, dict):
        return {}

    fields = {}
    for key, value in payload.items():
        if value is None:
            continue  # an omitted field beats the text 'None'
        fields[key] = _form_value(value)
    return fields


def _form_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        if all(not isinstance(item, (dict, list, tuple)) for item in value):
            return [_form_value(item) for item in value if item is not None]
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def open_parts(parts):
    """
    Open every attachment for one request.

    Returns (files, handles, errors). files is a LIST of
    (field, (filename, handle, content_type)) tuples rather than a dict,
    because an endpoint accepting several files expects the same field name
    repeated, which a dict cannot express.

    The handles are the caller's to close once the response is back. A handle is
    consumed by the request that sends it, so anything issuing the same request
    repeatedly (a Locust run) must call this again rather than reuse them.
    """
    files, handles, errors = [], [], []

    for part in parts or []:
        filename = str(part.get("filename") or "").strip()
        if not filename:
            continue

        path = resolve_attachment_path(filename)
        if not os.path.isfile(path):
            errors.append(missing_attachment_message(filename))
            continue

        try:
            handle = open(path, "rb")
        except OSError as exc:
            errors.append(f"attachment '{filename}' could not be opened: {exc}")
            continue

        handles.append(handle)
        files.append((
            str(part.get("field") or "").strip() or DEFAULT_ATTACHMENT_FIELD,
            (os.path.basename(path), handle, guess_content_type(path, part.get("content_type"))),
        ))

    return files, handles, errors


def close_handles(handles):
    for handle in handles or []:
        try:
            handle.close()
        except Exception:
            pass  # a failed close must not mask the response we came for


def build_multipart(payload, parts, body_mode="form", json_part_name=DEFAULT_JSON_PART_NAME):
    """
    Turn a row's payload and attachments into the arguments requests needs.

    Returns (files, data, handles, errors); send it as
    requests.post(url, files=files, data=data, headers=without_content_type(h))
    and never set Content-Type yourself — requests has to write the multipart
    boundary into it.
    """
    files, handles, errors = open_parts(parts)

    data = {}
    if payload not in (None, "", {}, []):
        if body_mode == "json" or not isinstance(payload, dict):
            # A list or scalar body has no field names to spread across form
            # fields, so it can only travel as a JSON part whatever was asked.
            files.insert(0, (
                json_part_name,
                (None, json.dumps(payload, ensure_ascii=False), "application/json"),
            ))
        else:
            data = form_fields(payload)

    return files, data, handles, errors


def without_content_type(headers):
    """
    Headers for a multipart request.

    Content-Type is dropped so requests can set it together with the boundary it
    generates. The sheet's 'headers' cell says application/json, and sending
    that leaves the server unable to parse the body; a hand-typed
    'multipart/form-data' is no better, since it carries no boundary. Every
    other header — authorization included — passes through untouched.
    """
    return {
        name: value for name, value in (headers or {}).items()
        if str(name).strip().lower() != "content-type"
    }


FORM_URLENCODED_CONTENT_TYPE = "application/x-www-form-urlencoded"


def declared_content_type(headers):
    """
    The Content-Type the sheet asked for, lowercased and without parameters.

    Read by name-insensitive scan rather than headers.get(): a sheet may spell
    the column 'headers-content-type' in any case, and a missed match here means
    the body is silently encoded the wrong way.
    """
    for name, value in (headers or {}).items():
        if str(name).strip().lower() == "content-type":
            return str(value).split(";")[0].strip().lower()
    return ""


def is_form_urlencoded(headers):
    return declared_content_type(headers) == FORM_URLENCODED_CONTENT_TYPE


def build_form_data(payload):
    """
    Flatten a parsed body into the {name: value} dict requests form-encodes.

    Needed because a form body is not JSON: an OAuth token endpoint reading
    grant_type/client_id/client_secret expects 'a=1&b=2', so sending the JSON
    text of the same object under a form Content-Type gets it rejected before it
    ever looks at the credentials.

    Values become strings, since that is all a form body can carry: a bool is
    written as the lowercase 'true'/'false' every server parses (Python's 'True'
    is not), None as empty, and a nested object/array as its JSON text — there is
    no standard form spelling for one, and the APIs that accept it expect JSON.

    Returns (form_data, errors).
    """
    if not isinstance(payload, dict):
        return {}, [
            f"{FORM_URLENCODED_CONTENT_TYPE} needs a JSON object body, "
            f"got {type(payload).__name__} — a form body has no field names otherwise"
        ]

    form = {}
    for key, value in payload.items():
        name = str(key)
        if value is None:
            form[name] = ""
        elif isinstance(value, bool):
            form[name] = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            form[name] = json.dumps(value)
        else:
            form[name] = str(value)
    return form, []


def multipart_plan(payload, parts, body_mode="form", json_part_name=DEFAULT_JSON_PART_NAME):
    """
    A JSON-serialisable description of a multipart request, with absolute paths.

    Handed to the Locust worker through the environment: it cannot see the
    sheet, and passing paths rather than bytes keeps the variable small and lets
    the worker reopen every file on each iteration.
    """
    resolved = []
    for part in parts or []:
        filename = str(part.get("filename") or "").strip()
        if not filename:
            continue
        path = resolve_attachment_path(filename)
        resolved.append({
            "field": str(part.get("field") or "").strip() or DEFAULT_ATTACHMENT_FIELD,
            "path": path,
            "filename": os.path.basename(path),
            "content_type": guess_content_type(path, part.get("content_type")),
        })

    plan = {"files": resolved, "data": {}, "json_part": None}

    if payload not in (None, "", {}, []):
        if body_mode == "json" or not isinstance(payload, dict):
            plan["json_part"] = {
                "name": json_part_name,
                "value": json.dumps(payload, ensure_ascii=False),
            }
        else:
            plan["data"] = form_fields(payload)

    return plan


# ----------------------------------------------------------------------
# describing it, without the bytes
# ----------------------------------------------------------------------
def human_size(count):
    if count is None:
        return "unknown size"
    size = float(count)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def describe_multipart(files, data, limit=80):
    """
    One-line summary of a multipart request for the results grid and the report.

    Called while the handles are still open, and deliberately never touches the
    file contents: results are fed to the LLM analyser and written into HTML on
    disk, so raw upload bytes must not reach them.
    """
    pieces = [f"{name}={_preview(value, limit)}" for name, value in (data or {}).items()]

    for field, spec in files or []:
        filename, payload, content_type = spec
        if filename is None:
            pieces.append(f"{field}=<{content_type or 'text'} part, {len(payload)} chars>")
        else:
            pieces.append(f"{field}={filename} ({human_size(_handle_size(payload))}, {content_type})")

    return "; ".join(pieces)


def describe_parts(parts):
    """Summary of parsed parts, for a preview before anything is opened."""
    return ", ".join(
        f"{part.get('field') or DEFAULT_ATTACHMENT_FIELD}={part.get('filename')}"
        for part in parts or []
        if isinstance(part, dict)
    )


def _handle_size(handle):
    try:
        return os.fstat(handle.fileno()).st_size
    except Exception:
        return None


def _preview(value, limit=80):
    if isinstance(value, (list, tuple)):
        return ", ".join(_preview(item, limit) for item in value)
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ----------------------------------------------------------------------
# reading a file into the JSON body (the 'inline' encoding)
# ----------------------------------------------------------------------
def _readable_path(name):
    path = resolve_attachment_path(name)
    if not path:
        return ""
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"'{name}' not found — put the file in {ATTACHMENT_SUBFOLDER}{os.sep} "
            f"(looked in {path})"
        )
    size = os.path.getsize(path)
    if size > MAX_INLINE_FILE_BYTES:
        raise ValueError(
            f"'{name}' is {human_size(size)} — too large to inline in a JSON body "
            f"(limit {human_size(MAX_INLINE_FILE_BYTES)}); send it through the "
            f"Attachments column instead"
        )
    return path


def read_file_base64(name):
    """Base64 of an attachment — backs ${__fileBase64(contract.pdf)}."""
    path = _readable_path(name)
    if not path:
        return ""
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("ascii")


def read_file_text(name, encoding="utf-8"):
    """Text of an attachment — backs ${__fileText(body.json)}."""
    path = _readable_path(name)
    if not path:
        return ""
    with open(path, "r", encoding=encoding, errors="replace") as handle:
        return handle.read()


def attachment_basename(name):
    """Just the file name — backs ${__fileName(contract.pdf)}."""
    path = resolve_attachment_path(name)
    return os.path.basename(path) if path else ""
