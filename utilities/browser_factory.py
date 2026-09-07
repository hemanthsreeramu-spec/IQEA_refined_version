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
        driver = webdriver.Remote(
            command_executor=get_selenium_remote_url(),
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

    The exact path is Grid-version specific — confirm it against the Grid your
    DevOps team deploys before relying on it in the UI.
    """
    if not is_azure():
        return ""
    session_id = getattr(driver, "session_id", None)
    if not session_id:
        return ""
    return "%s?session=%s" % (get_novnc_path(), session_id)


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
