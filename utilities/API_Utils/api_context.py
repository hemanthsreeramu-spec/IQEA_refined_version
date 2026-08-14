"""
Runtime variable store for API chaining.

One ApiContext lives for the duration of a single validation run. Values pulled
out of an API response are stored here, and later APIs reference them with
${name} placeholders in any field — endpoint, headers, payload, path/query
params.

Deliberately in-memory and per-run: a persistent store (e.g. an INI on disk)
leaks stale tokens into later runs and cannot hold non-string values.
"""

import copy
import json
import random
import re
import string
import uuid
from datetime import datetime

from jsonpath_ng import parse

# ${name} or ${name(args)} — also tolerates ${ name } and dotted names
VAR_PATTERN = re.compile(r"\$\{\s*([A-Za-z_][A-Za-z0-9_.\-]*)\s*(?:\(([^()]*)\))?\s*\}")

# A string that is *exactly* one placeholder, e.g. "${connector_id}".
# These are replaced with the stored value keeping its native type.
WHOLE_VALUE_PATTERN = re.compile(
    r"^\s*\$\{\s*([A-Za-z_][A-Za-z0-9_.\-]*)\s*(?:\(([^()]*)\))?\s*\}\s*$"
)

# Named time formats, including the JMeter spelling people paste in
TIME_FORMATS = {
    "YMDHMS": "%Y%m%d%H%M%S",
    "YMD": "%Y%m%d",
    "HMS": "%H%M%S",
    "YMDHMS_DASH": "%Y-%m-%d_%H-%M-%S",
    "ISO": "%Y-%m-%dT%H:%M:%S",
}


def _now_formatted(args):
    fmt = (args or "").strip()
    now = datetime.now()
    if not fmt:
        return now.strftime(TIME_FORMATS["YMDHMS"])
    if fmt in TIME_FORMATS:
        return now.strftime(TIME_FORMATS[fmt])
    if fmt.lower() in ("ms", "millis"):
        return int(now.timestamp() * 1000)
    return now.strftime(fmt)  # anything else treated as a strftime pattern


def _random_int(args):
    parts = [p.strip() for p in (args or "").split(",") if p.strip()]
    low, high = (0, 1_000_000)
    if len(parts) == 1:
        high = int(parts[0])
    elif len(parts) >= 2:
        low, high = int(parts[0]), int(parts[1])
    return random.randint(low, high)


def _random_string(args):
    length = int((args or "8").strip() or 8)
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


# Generators usable as ${__name} / ${__name(args)}. These produce a fresh value
# at request time rather than reading one out of the store, so payloads that
# need to be unique per run (new agent names, ids) work without chaining.
BUILTINS = {
    "__uuid": lambda a: str(uuid.uuid4()),
    "__timestamp": lambda a: int(datetime.now().timestamp()),
    "__time": _now_formatted,
    "__datetime": _now_formatted,
    "__randomInt": _random_int,
    "__randomString": _random_string,
    # JMeter compatibility: a functional run is single-threaded
    "__threadNum": lambda a: 1,
    # __counter is handled on the context so it can keep per-run state
    "__counter": lambda a: None,
}


class MissingVariableError(Exception):
    """Raised when a ${var} is referenced but was never extracted."""

    def __init__(self, name, field=None, produced_by=None):
        self.name = name
        self.field = field
        message = f"${{{name}}} was never set"
        if produced_by:
            message += f" — expected from '{produced_by}'"
        else:
            message += " — check the Extract value of the API that should produce it"
        if field:
            message += f" (referenced in '{field}')"
        super().__init__(message)


def find_variables(obj):
    """
    Return the set of ${var} names referenced anywhere inside obj.

    Built-in generators are excluded — they produce their own value, so they are
    neither a dependency on another API nor a missing variable.
    """
    found = set()

    def walk(node):
        if isinstance(node, str):
            found.update(
                name for name, _args in VAR_PATTERN.findall(node) if name not in BUILTINS
            )
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(obj)
    return found


CASTS = {
    "int": int,
    "float": float,
    "str": str,
    "bool": lambda v: str(v).strip().lower() in ("1", "true", "yes", "y"),
    "json": lambda v: json.loads(v) if isinstance(v, str) else v,
}


def split_cast(source):
    """
    Split a trailing '|cast' off an extract source.

    'agent_id=$.agent_id|int' captures the id and stores it as an integer —
    needed when an API returns an id as a string but a downstream API declares
    that field as an integer.
    """
    if "|" in source:
        head, _, tail = source.rpartition("|")
        cast = tail.strip().lower()
        if cast in CASTS:
            return head.strip(), cast
    return source, None


def parse_extract_spec(spec):
    """
    Parse an extraction spec into [(name, source), ...].

    Accepted forms, separated by ';' or newlines:
        token=$.access_token
        user_id=$.data[0].id ; name=$.data[0].first_name
        session=header:Set-Cookie
        code=$status
        agent_id=$.agent_id|int      (cast: int, float, str, bool, json)

    A bare source with no '=' (the legacy 'Extract-token' column) is named
    after the last path segment, so '$.access_token' becomes 'access_token'.
    """
    if not spec:
        return []

    if isinstance(spec, dict):
        return [(str(k), str(v)) for k, v in spec.items() if v]

    pairs = []
    for chunk in re.split(r"[;\n]+", str(spec)):
        chunk = chunk.strip()
        if not chunk:
            continue

        if "=" in chunk:
            # Split on the FIRST '=' only — jsonpath filters can contain '=='
            name, source = chunk.split("=", 1)
            name, source = name.strip(), source.strip()
        else:
            source = chunk
            # Derive a name from the trailing path segment
            name = re.split(r"[.\[\]]+", chunk.rstrip("]"))[-1] or "value"
            name = name.strip().lstrip("$").strip() or "value"

        if name and source:
            pairs.append((name, source))

    return pairs


class ApiContext:
    def __init__(self, initial=None):
        self._values = dict(initial or {})
        # name -> label of the API that produced it (for error messages)
        self._producers = {}
        self._counter = 0

    # ------------------------------------------------------------------
    # store
    # ------------------------------------------------------------------
    def set(self, name, value, produced_by=None):
        self._values[name] = value
        if produced_by:
            self._producers[name] = produced_by

    def get(self, name, default=None):
        return self._values.get(name, default)

    def has(self, name):
        return name in self._values

    def as_dict(self):
        return dict(self._values)

    def missing(self, obj):
        """Names referenced in obj that are not in the store yet."""
        return sorted(n for n in find_variables(obj) if n not in self._values)

    # ------------------------------------------------------------------
    # resolve
    # ------------------------------------------------------------------
    def resolve(self, obj, field=None, strict=True):
        """
        Deep-copy obj with every ${var} substituted.

        A string that is exactly one placeholder keeps the stored value's
        native type ("${conn_id}" -> 0). A placeholder inside a longer string
        is interpolated ("Bearer ${token}" -> "Bearer eyJ...").

        strict=False leaves unknown placeholders untouched instead of raising.
        """
        return self._resolve_node(copy.deepcopy(obj), field, strict)

    def _resolve_node(self, node, field, strict):
        if isinstance(node, str):
            return self._resolve_string(node, field, strict)

        if isinstance(node, dict):
            return {
                self._resolve_node(k, field, strict): self._resolve_node(v, f"{field}.{k}" if field else str(k), strict)
                for k, v in node.items()
            }

        if isinstance(node, list):
            return [self._resolve_node(item, field, strict) for item in node]

        return node

    def _builtin(self, name, args, field):
        """Evaluate a built-in generator. Returns (handled, value)."""
        if name not in BUILTINS:
            return False, None
        if name == "__counter":
            self._counter += 1
            return True, self._counter
        try:
            return True, BUILTINS[name](args)
        except Exception as exc:
            raise ValueError(f"${{{name}}} could not be evaluated: {exc}"
                             + (f" (in '{field}')" if field else ""))

    def _resolve_string(self, text, field, strict):
        whole = WHOLE_VALUE_PATTERN.match(text)
        if whole:
            name, args = whole.group(1), whole.group(2)
            handled, value = self._builtin(name, args, field)
            if handled:
                return value
            if name in self._values:
                return self._values[name]  # native type preserved
            if strict:
                raise MissingVariableError(name, field, self._producers.get(name))
            return text

        def substitute(match):
            name, args = match.group(1), match.group(2)
            handled, value = self._builtin(name, args, field)
            if not handled:
                if name in self._values:
                    value = self._values[name]
                elif strict:
                    raise MissingVariableError(name, field, self._producers.get(name))
                else:
                    return match.group(0)
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return "" if value is None else str(value)

        return VAR_PATTERN.sub(substitute, text)

    # ------------------------------------------------------------------
    # extract
    # ------------------------------------------------------------------
    def extract(self, response, spec, produced_by=None):
        """
        Pull values out of a response and store them.

        Returns (extracted_dict, failures_list). Never raises — a failed
        extraction is reported so the row can be flagged, while any values
        that did resolve are still stored for downstream APIs.
        """
        extracted = {}
        failures = []

        pairs = parse_extract_spec(spec)
        if not pairs:
            return extracted, failures

        body = None
        body_parsed = False

        for name, raw_source in pairs:
            source, cast = split_cast(raw_source)
            try:
                if source.lower().startswith("header:"):
                    header_name = source.split(":", 1)[1].strip()
                    value = (response.headers or {}).get(header_name)
                    if value is None:
                        failures.append(f"{name}: header '{header_name}' not in response")
                        continue

                elif source.strip() in ("$status", "$statusCode", "$status_code"):
                    value = response.status_code

                elif source.strip() == "$body":
                    value = response.text

                else:
                    if not body_parsed:
                        body = self._response_json(response)
                        body_parsed = True
                    if body is None:
                        failures.append(f"{name}: response is not valid JSON")
                        continue
                    value = self._json_path(body, source)
                    if value is _NO_MATCH:
                        # Name what IS in the response — the whole point of the
                        # first run is usually to discover the right path.
                        failures.append(
                            f"{name}: no match for '{source}'{self._describe_shape(body)}"
                        )
                        continue

                if cast:
                    try:
                        value = CASTS[cast](value)
                    except Exception:
                        failures.append(f"{name}: cannot cast {value!r} to {cast}")
                        continue

                self.set(name, value, produced_by)
                extracted[name] = value

            except Exception as exc:  # a bad jsonpath shouldn't kill the run
                failures.append(f"{name}: {exc}")

        return extracted, failures

    @staticmethod
    def _describe_shape(body, limit=12):
        """Human hint about what the response actually contains."""
        if isinstance(body, dict):
            keys = list(body.keys())
            shown = ", ".join(keys[:limit])
            more = f" (+{len(keys) - limit} more)" if len(keys) > limit else ""
            return f" — response keys: {shown}{more}" if keys else " — response object is empty"
        if isinstance(body, list):
            if body and isinstance(body[0], dict):
                return f" — response is a list of {len(body)}; item keys: {', '.join(list(body[0].keys())[:limit])}"
            return f" — response is a list of {len(body)}"
        return f" — response is a {type(body).__name__}"

    @staticmethod
    def _response_json(response):
        try:
            return response.json()
        except Exception:
            try:
                return json.loads(response.text)
            except Exception:
                return None

    @staticmethod
    def _json_path(body, source):
        expression = source if source.strip().startswith("$") else f"$.{source.strip()}"
        matches = [m.value for m in parse(expression).find(body)]
        if not matches:
            return _NO_MATCH
        return matches[0]


class _NoMatch:
    def __repr__(self):
        return "<no match>"


_NO_MATCH = _NoMatch()
