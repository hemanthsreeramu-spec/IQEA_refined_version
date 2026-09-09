"""
Single place where every Chrome instance in IQEA is created.

Why profiles
------------
Before this module there were eight `webdriver.Chrome(options=...)` call sites,
each with its own flag list. Collapsing them onto one shared flag set would have
silently changed local behaviour for most of them. So each call site keeps its
own PROFILE, and under execution_type=local the profile replays that call site's
original flags EXACTLY — same order, same values, same service. Local runs are
therefore unchanged; see test_browser_factory_parity() at the bottom.

local vs azure
--------------
local : `webdriver.Chrome(...)` on this machine, exactly as before.
azure : `webdriver.Remote(...)` against a Selenium Grid Hub. Chrome runs HEADED
        on a virtual display (Xvfb) inside a Grid node so the user can watch and
        drive it through noVNC — headless would start fine but leave nothing to
        interact with, which is the whole point of the recorder.

Grid handles session->node routing and idle-session cleanup, so there is no pool
to manage here. The per-session screen is reachable at
    <hub>/session/<session_id>/se/vnc
which is why only the Hub needs to be exposed publicly.
"""

import os
import uuid

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from config.settings_reader import (get_novnc_path, get_selenium_remote_url,
                                    get_window_size, is_azure)

# ── Original per-call-site flags. DO NOT reorder or "tidy" these: they are the
#    local contract. Each list is copied verbatim from the call site named above
#    it, so `git blame` on the original line still explains every flag.
_RECORDER_ARGS = [
    # action_new_xpath_subway_TMT.py (User Workflow Recorder)
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--remote-debugging-port=9222",
    "--no-sandbox",
    "--remote-allow-origins=*",
    "--disable-dev-shm-usage",
]

_LOCATOR_ARGS = [
    # chatbot/services/locator_service.py — same six flags as the recorder
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--remote-debugging-port=9222",
    "--no-sandbox",
    "--remote-allow-origins=*",
    "--disable-dev-shm-usage",
]

_SELF_HEALING_ARGS = [
    # Self_healing_web_application/Self_healing_streamlet.py — only three flags
    "--remote-debugging-port=9222",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

_XPATH_PAGE_ARGS = [
    # accelerator/pages/3_..._Xpath_..._Page_File_Generator.py (legacy app).
    # Same three flags as self_healing, kept as its own profile so a change to
    # one call site cannot silently alter the other.
    "--remote-debugging-port=9222",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

_PBI_ARGS = [
    # pbi_validator/utils/pbi_browser.py — anti-automation-detection set
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-extensions",
]

PROFILES = {
    "recorder":     _RECORDER_ARGS,
    "locator":      _LOCATOR_ARGS,
    "self_healing": _SELF_HEALING_ARGS,
    "xpath_page":   _XPATH_PAGE_ARGS,
    "pbi":          _PBI_ARGS,
}

# Flags that cannot survive in a container.
#   --remote-debugging-port=9222 is a FIXED port. Locally one user means one
#   Chrome, so it never collides. In Azure many people record at once, and the
#   second Chrome to claim 9222 exits immediately with the same
#   "session not created: Chrome instance exited" error we set out to fix.
_AZURE_DROP_PREFIXES = ("--remote-debugging-port",)

# Flags every containerised Chrome needs.
#   --no-sandbox            : Chrome's sandbox needs user namespaces a container restricts
#   --disable-dev-shm-usage : /dev/shm defaults to 64 MB in Docker; Chrome crashes without this
#   --disable-gpu           : no GPU on the node
_AZURE_REQUIRED = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


def build_options(profile="recorder", headless=False):
    """Build ChromeOptions for a profile under the active execution type."""
    if profile not in PROFILES:
        raise ValueError("Unknown browser profile %r. Known: %s"
                         % (profile, ", ".join(sorted(PROFILES))))

    options = Options()
    args = list(PROFILES[profile])

    if is_azure():
        args = [a for a in args
                if not a.startswith(_AZURE_DROP_PREFIXES)]
        for required in _AZURE_REQUIRED:
            if required not in args:
                args.append(required)

        # No window manager has sized the window at first paint, so say it
        # explicitly — otherwise screenshots come back at the default 800x600
        # and Power BI extraction silently scrapes a cramped layout.
        width, height = get_window_size()
        args.append("--window-size=%d,%d" % (width, height))

        # A unique profile dir per session. Chrome cannot share one, and a
        # container's HOME is often read-only, which alone kills startup.
        args.append("--user-data-dir=/tmp/chrome-%s" % uuid.uuid4().hex)

        # NOTE: deliberately NOT headless. The user has to see this browser.

    elif headless:
        # Local headless stays opt-in and behaves as it did in pbi_browser.py.
        args.insert(0, "--headless=new")

    for arg in args:
        options.add_argument(arg)

    if profile == "pbi":
        # Preserved from pbi_browser.start_browser()
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

    return options


def get_driver(profile="recorder", url=None, headless=False):
    """
    Create a Chrome driver for `profile`.

    Navigation, maximising and page-load waits stay at the call sites so their
    existing behaviour is untouched; pass `url` only if you want the convenience.
    """
    options = build_options(profile, headless=headless)

    if is_azure():
        target = get_selenium_remote_url()
        # Preflight: a wrong address otherwise surfaces as a urllib3
        # "Connection refused" with no hint about what to change.
        ok, detail = check_grid_reachable(target)
        if not ok:
            raise RuntimeError(_grid_unreachable_message(target, detail))
        driver = webdriver.Remote(
            command_executor=target,
            options=options,
        )
    else:
        driver = _local_driver(profile, options)

    if url:
        driver.get(normalize_url(url))
    return driver


def _local_driver(profile, options):
    """Local Chrome, constructed exactly as the original call site did."""
    if profile == "pbi":
        # pbi_browser.py resolved its driver through webdriver_manager. Kept for
        # local parity only — in Azure the driver ships inside the Grid node, and
        # a runtime download would fail on restricted egress or fetch a version
        # that does not match the node's Chrome.
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                                options=options)
    return webdriver.Chrome(options=options)


def check_grid_reachable(url=None, timeout=5):
    """
    Can we actually reach the Selenium Grid? Returns (ok: bool, detail: str).

    Probes the Grid's /status endpoint. Called before creating a remote session
    so a misconfigured address produces an explanatory message instead of a raw
    "Connection refused" traceback from deep inside urllib3.
    """
    import json
    import urllib.error
    import urllib.request

    target = url or get_selenium_remote_url()
    # /status lives at the Grid root, not under /wd/hub
    base = target.split("/wd/hub")[0].rstrip("/")
    status_url = base + "/status"
    try:
        with urllib.request.urlopen(status_url, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        value = body.get("value", {})
        ready = value.get("ready")
        nodes = value.get("nodes") or []
        slots = sum(len(n.get("slots") or []) for n in nodes)
        return bool(ready), ("ready=%s nodes=%d slots=%d — %s"
                             % (ready, len(nodes), slots,
                                value.get("message", "").strip() or "ok"))
    except urllib.error.HTTPError as exc:
        return False, "HTTP %s from %s" % (exc.code, status_url)
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)


def check_novnc_reachable(timeout=5):
    """
    Is the live-browser panel actually going to show a browser?

    Checks two hops separately, because they fail for different reasons:
      1. direct  -> NOVNC_UPSTREAM (the Chrome container's noVNC on :7900)
      2. proxied -> our own nginx at novnc_path

    Hop 2 has a specific trap: Streamlit is a single-page app that answers ANY
    unknown path with its own index.html. So if nginx is not routing /vnc/ (or
    nginx is not in the request path at all, e.g. WEBSITES_PORT points straight
    at Streamlit), the panel does not error — it renders IQEA inside itself.
    We detect that by looking for Streamlit's markers in the response body.

    Returns (ok: bool, detail: str).
    """
    import urllib.request

    upstream = os.environ.get("NOVNC_UPSTREAM", "127.0.0.1:7900")
    notes = []

    # Hop 1: the Chrome container's noVNC
    direct_ok = False
    try:
        with urllib.request.urlopen("http://%s/vnc.html" % upstream,
                                    timeout=timeout) as resp:
            body = resp.read(4096).decode("utf-8", "replace")
        direct_ok = resp.status == 200 and "noVNC" in body
        notes.append("direct http://%s/vnc.html -> %s%s"
                     % (upstream, resp.status,
                        "" if direct_ok else " (not a noVNC page)"))
    except Exception as exc:
        notes.append("direct http://%s/vnc.html -> %s: %s"
                     % (upstream, type(exc).__name__, exc))

    # Hop 2: through our nginx, the path the browser actually requests
    path = get_novnc_path()
    if not path.endswith("/"):
        path += "/"
    proxied_url = "http://127.0.0.1:8000%svnc.html" % path
    proxied_ok = False
    try:
        with urllib.request.urlopen(proxied_url, timeout=timeout) as resp:
            body = resp.read(8192).decode("utf-8", "replace")
        if "noVNC" in body:
            proxied_ok = True
            notes.append("proxied %s -> %s (noVNC)" % (proxied_url, resp.status))
        elif "streamlit" in body.lower() or "stAppViewContainer" in body:
            notes.append(
                "proxied %s -> %s but returned the STREAMLIT APP, not noVNC. "
                "nginx is not routing this path, so the panel renders IQEA "
                "inside itself." % (proxied_url, resp.status))
        else:
            notes.append("proxied %s -> %s (unrecognised body)"
                         % (proxied_url, resp.status))
    except Exception as exc:
        notes.append("proxied %s -> %s: %s"
                     % (proxied_url, type(exc).__name__, exc))

    return (direct_ok and proxied_ok), " | ".join(notes)


def _grid_unreachable_message(target, detail):
    """The actionable version of 'Connection refused'."""
    host = target.split("//")[-1].split("/")[0]
    loopback = host.startswith(("127.0.0.1", "localhost", "[::1]"))
    lines = [
        "Selenium Grid is not reachable at %s" % target,
        "  probe: %s" % detail,
        "",
    ]
    if loopback:
        lines += [
            "SELENIUM_REMOTE_URL points at loopback (%s)." % host,
            "Loopback only works where the app and the Grid SHARE a network",
            "namespace — i.e. Azure App Service sidecars. In Docker Compose, "
            "plain",
            "`docker run`, Kubernetes or Container Apps, each container has its "
            "own",
            "loopback, so 127.0.0.1 resolves to the APP container, where nothing",
            "listens on 4444. That is this error.",
            "",
            "Fix — address the Grid by name and make sure both are on one network:",
            "  Docker Compose : SELENIUM_REMOTE_URL=http://chrome:4444/wd/hub",
            "                   GRID_UPSTREAM=chrome:4444",
            "  docker run     : put both on the same --network, then use the",
            "                   Selenium container's name as the host",
            "  Container Apps : SELENIUM_REMOTE_URL=http://<grid-app-name>/wd/hub",
            "  Grid on the host, app in a container:",
            "                   SELENIUM_REMOTE_URL=http://host.docker.internal:4444/wd/hub",
        ]
    else:
        lines += [
            "Check that: the Grid container is running and healthy; '%s' resolves"
            % host,
            "from inside the app container; both are attached to the same network;",
            "and the port matches the Grid's published port.",
            "",
            "Verify from inside the app container:",
            "  curl -sS http://%s/status" % host,
        ]
    lines += [
        "",
        "Set execution_type=local in config/settings.ini to run Chrome on this "
        "machine instead.",
    ]
    return "\n".join(lines)


def normalize_url(url):
    """
    Turn what a user types into something Chrome will actually navigate to.

    `driver.get()` requires an absolute URL. Handed "google.com", or anything
    with stray whitespace from a copy-paste, Chrome rejects it with a bare
        InvalidArgumentException: Message: invalid argument
    which says nothing about the cause. Returns '' for empty input so callers
    can show a proper message instead of navigating nowhere.
    """
    clean = (url or "").strip().strip('"').strip("'")
    if not clean:
        return ""
    if not clean.startswith(("http://", "https://", "file://", "about:", "data:")):
        clean = "https://" + clean
    return clean


def safe_maximize(driver):
    """
    Maximise the window, tolerating the states where Chrome refuses.

    Chrome restores the window state from the user profile, so a browser can
    open ALREADY maximised — and calling maximize_window() then fails with
        "failed to change window state to 'normal', current state is 'maximized'"
    which used to abort "Open Browser" entirely. The window is already the size
    we wanted, so there is nothing to recover from.

    Headless/container Chrome has no window manager at all, where the call is
    equally meaningless — size comes from --window-size instead.
    """
    if driver is None:
        return False
    try:
        driver.maximize_window()
        return True
    except Exception as exc:
        print("[browser] maximize skipped (%s)" % str(exc).splitlines()[0])
        return False


def get_novnc_url(driver):
    """
    URL of the live screen for this driver's session, for embedding in Streamlit.

    Selenium Grid proxies each session's VNC under the Hub, keyed by session id,
    so only the Hub needs to be publicly reachable. Returns '' locally, where the
    browser is already on the user's own screen.

    Uses the noVNC web client that selenium's images serve on port 7900 (nginx
    proxies it at novnc_path). `autoconnect` skips the connect button and
    `resize=scale` fits the remote 1920x1080 desktop into the panel.

    A VNC password (SE_VNC_PASSWORD) has to reach the client somehow; noVNC
    accepts it as a query parameter. Prefer leaving the password off
    (SE_VNC_NO_PASSWORD=true) and putting Azure Easy Auth in front of the app,
    so the screen is protected by real identity rather than a shared string in
    a URL.
    """
    if not is_azure():
        return ""
    base = get_novnc_path()
    if not base.endswith("/"):
        base += "/"
    url = base + "vnc.html?autoconnect=1&resize=scale"
    password = os.environ.get("SE_VNC_PASSWORD", "").strip()
    if password:
        from urllib.parse import quote
        url += "&password=" + quote(password)
    return url


def quit_driver(driver):
    """
    Release a driver and its Grid node. Safe to call on an already-dead session.

    Matters much more in Azure than locally: an un-quit session keeps a whole
    Chrome node busy, so abandoned tabs would starve other users. Grid's own
    SE_SESSION_TIMEOUT is the backstop when this never runs.
    """
    if driver is None:
        return
    try:
        driver.quit()
    except Exception as exc:
        print("[browser] quit failed (session probably already gone): %s" % exc)


def test_browser_factory_parity():
    """
    Assert the LOCAL flag list for every profile still matches what the original
    call site passed. Run this after touching PROFILES:

        python -c "from utilities.browser_factory import test_browser_factory_parity as t; t()"
    """
    from config.settings_reader import get_execution_type
    assert get_execution_type() == "local", (
        "parity check must run with execution_type=local (got %r)"
        % get_execution_type())

    expected = {
        "recorder":     _RECORDER_ARGS,
        "locator":      _LOCATOR_ARGS,
        "self_healing": _SELF_HEALING_ARGS,
        "xpath_page":   _XPATH_PAGE_ARGS,
        "pbi":          _PBI_ARGS,
    }
    for profile, want in expected.items():
        got = build_options(profile).arguments
        assert got == want, ("profile %r drifted from its original flags:\n"
                             "  expected: %s\n  actual:   %s" % (profile, want, got))
    print("browser_factory parity OK — all %d profiles match their "
          "original call-site flags" % len(expected))


def diagnose():
    """
    Print how this process will reach a browser, and whether it can.

    Run INSIDE the app container — that is the only place the answer is
    meaningful, because container networking is what usually breaks:

        python -m utilities.browser_factory
    """
    import os
    from config.settings_reader import get_execution_type

    print("IQEA browser diagnostics")
    print("-" * 60)
    print("  execution_type        : %s" % get_execution_type())
    print("  (env IQEA_EXECUTION_TYPE = %r)"
          % os.environ.get("IQEA_EXECUTION_TYPE"))

    if not is_azure():
        print("  mode                  : LOCAL — Chrome launches on this machine")
        print("  Grid is not used. Nothing further to check.")
        return 0

    target = get_selenium_remote_url()
    print("  mode                  : AZURE — remote WebDriver")
    print("  SELENIUM_REMOTE_URL   : %s" % target)
    print("  GRID_UPSTREAM (nginx) : %s"
          % os.environ.get("GRID_UPSTREAM", "<unset -> 127.0.0.1:4444>"))
    print("  noVNC path            : %s" % get_novnc_path())
    print()

    ok, detail = check_grid_reachable(target)
    if ok:
        print("  GRID REACHABLE        : yes")
        print("  %s" % detail)
        print()
        print("  If a node has 0 slots, no Chrome node has registered with the "
              "Hub yet.")
        # WebDriver working does not mean the user can SEE the browser — that is
        # a separate port and a separate nginx route.
        vok, vdetail = check_novnc_reachable()
        print("  LIVE VIEW (noVNC)     : %s" % ("yes" if vok else "NO"))
        for part in vdetail.split(" | "):
            print("    %s" % part)
        if not vok:
            print()
            print("  The recorder will work but the user cannot see or click the")
            print("  browser. Check, in order:")
            print("    - the Chrome sidecar has SE_START_VNC=true and is listening")
            print("      on 7900 (noVNC is a DIFFERENT port from WebDriver's 4444)")
            print("    - NOVNC_UPSTREAM=127.0.0.1:7900 is set")
            print("    - WEBSITES_PORT=8000 so traffic goes through OUR nginx.")
            print("      If it points at 8501, requests hit Streamlit directly,")
            print("      nginx never runs, and /vnc/ returns the IQEA app itself.")
        return 0 if vok else 1

    print("  GRID REACHABLE        : NO")
    print()
    print(_grid_unreachable_message(target, detail))
    return 1


if __name__ == "__main__":
    raise SystemExit(diagnose())
