from locust import HttpUser, task, between
import os
import json


def _load_json_env(name, default):
    """os.getenv's default only applies when the var is ABSENT. The caller sets
    LOCUST_DATA to "" for GET/DELETE, so guard against empty/invalid values too."""
    raw = os.environ.get(name, "")
    if not raw or not raw.strip():
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        print(f"Could not parse {name} as JSON; using default")
        return default


def _open_multipart(plan):
    """
    Build the files/data arguments for one multipart request.

    Called per iteration, never once up front: a file handle is consumed by the
    request that sends it, so a shared handle would upload correctly on the
    first sample and send an empty part for every one after it — a load test
    that passes while proving nothing.

    Returns (files, data, handles); the caller closes the handles once the
    sample is done. files is a list so one field can carry several files.
    """
    files, handles = [], []

    json_part = plan.get("json_part")
    if json_part:
        files.append((json_part.get("name") or "data",
                      (None, json_part.get("value") or "", "application/json")))

    for part in plan.get("files") or []:
        path = part.get("path")
        if not path or not os.path.isfile(path):
            print(f"Attachment missing, skipping part: {path}")
            continue
        handle = open(path, "rb")
        handles.append(handle)
        files.append((
            part.get("field") or "files",
            (part.get("filename") or os.path.basename(path), handle,
             part.get("content_type") or "application/octet-stream"),
        ))

    return files, plan.get("data") or {}, handles


def _close(handles):
    for handle in handles:
        try:
            handle.close()
        except Exception:
            pass


class LocustApiUser(HttpUser):
    wait_time = between(1, 3)  # Simulate real-user wait time

    @task()
    def make_api_request(self):
        """ Make API request using Locust """
        print("going inside the actual performance")
        # The caller (makeperformancecall) exports LOCUST_ENDPOINT, not LOCUST_HOST.
        endpoint = os.environ.get("LOCUST_ENDPOINT") or "/"
        print(endpoint)
        method = (os.environ.get("LOCUST_METHOD") or "GET").upper()
        print(method)
        # LOCUST_DATA holds the request body itself, not a {"json": ...} wrapper.
        request_details = _load_json_env("LOCUST_DATA", None)
        headers = _load_json_env("LOCUST_AUTH", {})
        print("request_details", request_details)
        print("headers", headers)
        #data = os.getenv("LOCUST_DATA")  # Default to empty JSON
        # headers = {
        #     "Content-Type": "application/json"
        # }

        # for api in api_list:
        #     method = api.get("method", "GET").upper()
        #     url = api.get("url", "")
        #     headers = api.get("headers", {})
        #     body = api.get("body", {})
        #
        #     if not url:
        #         print("⚠️ No API URL provided. Skipping test.")
        #         continue  # Move to the next API
        #     if method == "GET":
        #         self.client.get(url, headers=headers)
        # name= keeps every sample grouped under one row in the report instead of
        # one row per generated URL.
        common = {"headers": headers, "verify": False, "name": f"{method} {endpoint}"}

        # An upload row: send the same multipart body the functional run sent.
        multipart = _load_json_env("LOCUST_MULTIPART", None)
        # A form-encoded row, already flattened to {field: text} by the caller.
        form_body = _load_json_env("LOCUST_FORM", None)

        sender = {
            "GET": self.client.get,
            "POST": self.client.post,
            "PUT": self.client.put,
            "PATCH": self.client.patch,
            "DELETE": self.client.delete,
        }.get(method)

        if sender is None:
            print(f"Unsupported method: {method}")
            return

        if method in ("GET", "DELETE"):
            sender(endpoint, **common)
            return

        if multipart:
            files, data, handles = _open_multipart(multipart)
            try:
                sender(endpoint, files=files, data=data, **common)
            finally:
                _close(handles)
            return

        # data= rather than json=: the Content-Type in LOCUST_AUTH promises a
        # form body, and a JSON one under that header is rejected on encoding.
        if form_body is not None:
            sender(endpoint, data=form_body, **common)
            return

        sender(endpoint, json=request_details, **common)

