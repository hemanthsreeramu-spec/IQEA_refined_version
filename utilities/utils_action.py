# utils_action.py
import time
import re
import os
import json
from collections import defaultdict
from urllib.parse import urlparse
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
load_dotenv()
from utilities.db_utils.models import Screenshot

JS_action_listeners = """(function (statusKey) {
    if (window.__listenersInjected) return;
    window.__listenersInjected = true;

    // --- Action persistence ---
    if (!window.__recordedActions) {
        window.__recordedActions = JSON.parse(localStorage.getItem("recordedActions") || "[]");
    }

    function saveAction(action) {
        const existing = JSON.parse(localStorage.getItem("recordedActions") || "[]");
        const last = existing.length > 0 ? existing[existing.length - 1] : null;

        // ✅ Skip duplicate (same action+label+url+value)
        if (last &&
            last.action === action.action &&
            last.label === action.label &&
            last.url === action.url &&
            (!action.value || action.value === last.value)) {
            console.log("⏭️ Duplicate action skipped:", action);
            return;
        }

        existing.push(action);
        localStorage.setItem("recordedActions", JSON.stringify(existing));
        window.__recordedActions.push(action);

        try {
            window.dispatchEvent(new CustomEvent("__action_recorded", { detail: action }));
            if (window.opener && window.opener !== window) {
                window.opener.postMessage({ __relay: true, payload: action }, "*");
            }
        } catch (err) {
            console.warn("Relay failed:", err);
        }
    }

    // --- Focus listener ---
    window.addEventListener("focus", () => {
        localStorage.setItem("lastFocusedWindow", window.location.href);
    });

    // --- XPath helper ---
    function getXPath(el) {
        const getPos = e => {
            let pos = 1;
            while (e.previousElementSibling) { e = e.previousElementSibling; pos++; }
            return pos;
        };
        const parts = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            let index = getPos(el);
            parts.unshift(el.tagName.toLowerCase() + '[' + index + ']');
            el = el.parentNode;
        }
        return '/' + parts.join('/');
    }

    // --- Record action ---
    function recordAction(type, target) {
        // ⛔ Skip if still in grace period (reinjection)
        if (Date.now() - (window.__reinjectionGrace || 0) < 800) return;
        if (!target || ["script", "style"].includes(target.tagName?.toLowerCase())) return;

        const xpath = getXPath(target);
        const label = target.getAttribute("aria-label") ||
                      target.name || target.id ||
                      target.innerText || target.placeholder ||
                      target.value || target.type ||
                      target.getAttribute('alt') || target.getAttribute('class');
        const value = (["input","change","input_others"].includes(type))
                        ? target.value || target.innerText || "" : "";
        const currentUrl = window.location.href;
        const actionObj = {
            action: type,
            xpath,
            label: label?.trim(),
            value,
            url: currentUrl,
            windowId: window.name || statusKey,
            timestamp: new Date().toISOString()
        };

        // ✅ If last recorded action was only a "switch", replace it with this real action
        const last = window.__recordedActions.length > 0 ? window.__recordedActions[window.__recordedActions.length - 1] : null;
        if (last && last.action === "switch" && last.windowId === actionObj.windowId) {
            window.__recordedActions.pop();
            let existing = JSON.parse(localStorage.getItem("recordedActions") || "[]");
            existing.pop();
            localStorage.setItem("recordedActions", JSON.stringify(existing));
        }

        saveAction(actionObj);
        console.log("Recorded:", actionObj);
    }

    // --- Attach listeners ---
    function attachListeners() {
        if (window.__listenersAttached) return;
        window.__listenersAttached = true;

        document.addEventListener('click', e => recordAction('click', e.target), true);
        document.addEventListener('change', e => {
            if (e.target.type === 'checkbox' || e.target.type === 'radio')
                recordAction('input_others', e.target);
            else
                recordAction('input', e.target);
        }, true);
        document.addEventListener('focusout', e => {
            const tag = e.target.tagName.toLowerCase();
            if (tag !== 'button' && tag !== 'input' && tag !== 'textarea')
                recordAction('change', e.target);
        }, true);
    }

    // --- Relay handler ---
    window.addEventListener("message", function(event) {
        if (event.data && event.data.__relay && event.data.payload) {
            saveAction(event.data.payload);
            if (window.opener && window.opener !== window) {
                window.opener.postMessage(event.data, "*");
            }
        }
    });

    if (document.readyState === "complete") attachListeners();
    else window.addEventListener('load', attachListeners, { once:true });

    console.log("✅ Action listeners bound with key:", statusKey);
})(STATUS_KEY_PLACEHOLDER);
"""
JS_action_listeners_1 = """(function (statusKey) {
    if (window.__listenersInjected) return;
    window.__listenersInjected = true;

    // --- Action persistence ---
    if (!window.__recordedActions) {
        window.__recordedActions = JSON.parse(localStorage.getItem("recordedActions") || "[]");
    }

    function saveAction(action) {
        const existing = JSON.parse(localStorage.getItem("recordedActions") || "[]");
        existing.push(action);
        localStorage.setItem("recordedActions", JSON.stringify(existing));

        window.__recordedActions.push(action);

        try {
            window.dispatchEvent(new CustomEvent("__action_recorded", { detail: action }));
            if (window.opener && window.opener !== window) {
                window.opener.postMessage({ __relay: true, payload: action }, "*");
            }
        } catch (err) {
            console.warn("Relay failed:", err);
        }
    }

    // --- Focus listener ---
    window.addEventListener("focus", () => {
        localStorage.setItem("lastFocusedWindow",  window.location.href);
    });

    // --- XPath helper ---
    function getXPath(el) {
        const getPos = e => {
            let pos = 1;
            while (e.previousElementSibling) { e = e.previousElementSibling; pos++; }
            return pos;
        };
        const parts = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            let index = getPos(el);
            parts.unshift(el.tagName.toLowerCase() + '[' + index + ']');
            el = el.parentNode;
        }
        return '/' + parts.join('/');
    }

    // --- Record action ---
    function recordAction(type, target) {
        // ⛔ Skip if still in grace period (800ms default)
        if (Date.now() - (window.__reinjectionGrace || 0) < 800) return;
        if (!target || ["script", "style"].includes(target.tagName?.toLowerCase())) return;

        const xpath = getXPath(target);
        const label = target.getAttribute("aria-label") || target.name || target.id || target.innerText || target.placeholder || target.value || target.type || target.getAttribute('alt') || target.getAttribute('class');
        const value = (["input","change","input_others"].includes(type)) ? target.value || target.innerText || "" : "";

        const actionObj = {
            action: type,
            xpath,
            label: label?.trim(),
            value,
            url: window.location.href,
            windowId: window.name || statusKey,
            timestamp: new Date().toISOString()
        };

        saveAction(actionObj);
        console.log("Recorded:", actionObj);
    }

    // --- Attach listeners ---
    function attachListeners() {
        if (window.__listenersAttached) return;
        window.__listenersAttached = true;

        document.addEventListener('click', e => recordAction('click', e.target), true);
        document.addEventListener('change', e => {
            if (e.target.type === 'checkbox' || e.target.type === 'radio')
                recordAction('input_others', e.target);
            else
                recordAction('input', e.target);
        }, true);
        document.addEventListener('focusout', e => {
            const tag = e.target.tagName.toLowerCase();
            if (tag !== 'button' && tag !== 'input' && tag !== 'textarea')
                recordAction('change', e.target);
        }, true);
    }

    // --- Relay handler ---
    window.addEventListener("message", function(event) {
        if (event.data && event.data.__relay && event.data.payload) {
            saveAction(event.data.payload);
            if (window.opener && window.opener !== window) {
                window.opener.postMessage(event.data, "*");
            }
        }
    });

    if (document.readyState === "complete") attachListeners();
    else window.addEventListener('load', attachListeners, { once:true });

    console.log("✅ Action listeners bound with key:", statusKey);
})(STATUS_KEY_PLACEHOLDER);
"""

def injection_script_updated_fixed():
    return f"""
    (function() {{
        if (window.__recorderInjected) return;
        window.__recorderInjected = true;

        // Ensure a stable windowId
        if (!window.name || window.name.trim() === "") {{
            window.name = "recorder_" + Math.random().toString(36).substr(2, 9);
        }}
        const windowId = window.name;

        const statusKey = "recorder_status_" + windowId;

        function updateStatus(alive = true) {{
            localStorage.setItem(statusKey, JSON.stringify({{
                windowId: windowId,
                alive: alive,
                url: window.location.href,
                ts: Date.now()
            }}));
        }}

        // Initial write
        updateStatus(true);

        // Refresh every 2s
        setInterval(() => updateStatus(true), 2000);

        // Mark as dead when page unloads
        window.addEventListener("beforeunload", () => updateStatus(false));

        // ---- Inject listeners with SAME statusKey ----
        {JS_action_listeners
            .replace("STATUS_KEY_PLACEHOLDER", "statusKey")
            .replace("WINDOW_ID_PLACEHOLDER", "windowId")}
        // ✅ Reinjection grace flag
        window.__reinjectionGrace = Date.now();    

        console.log("✅ Recorder JS injected + heartbeat + listeners active (aligned key)");
    }})();
    """

FINAL_JS_ACTION_LISTENER="""(function () {
    if (!window.__recordedActions) {
        window.__recordedActions = JSON.parse(localStorage.getItem("recordedActions") || "[]");
    }

    function saveAction(action) {
        const existing = JSON.parse(localStorage.getItem("recordedActions") || "[]");
        existing.push(action);
        localStorage.setItem("recordedActions", JSON.stringify(existing));
    }

    function getXPath(el) {
        const getPos = e => {
            let pos = 1;
            while (e.previousElementSibling) { e = e.previousElementSibling; pos++; }
            return pos;
        };
        const parts = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            let index = getPos(el);
            parts.unshift(el.tagName.toLowerCase() + '[' + index + ']');
            el = el.parentNode;
        }
        return '/' + parts.join('/');
    }

    function recordAction(type, target) {
        if (!target || ["script", "style"].includes(target.tagName?.toLowerCase())) return;
        const xpath = getXPath(target);
        const label = target.getAttribute("aria-label") || target.name || target.id || target.innerText || target.placeholder || target.value || target.type || target.getAttribute('alt') || target.getAttribute('class');
        const value = (["input","change","input_others"].includes(type)) ? target.value || target.innerText || "" : "";
        const url = window.location.href;
        const actionObj = {
            action: type,
            xpath,
            label: label?.trim(),
            value,
            url,
            windowId: window.name || window.location.href,
            timestamp: new Date().toISOString()
        };

        window.__recordedActions.push(actionObj);
        saveAction(actionObj);

        // 🔑 Always try to bubble the event up to the root window
        if (window.opener && window.opener !== window) {
            window.opener.postMessage({ __relay: true, payload: actionObj }, "*");
        }

        console.log("Recorded:", actionObj);
    }

    function attachListeners() {
        if (window.__listenersAttached) return;
        window.__listenersAttached = true;

        document.addEventListener('click', e => recordAction('click', e.target), true);
        document.addEventListener('change', e => {
            if(e.target.type === 'checkbox' || e.target.type === 'radio') recordAction('input_others', e.target);
            else recordAction('input', e.target);
        }, true);
        document.addEventListener('focusout', e => {
            const tag = e.target.tagName.toLowerCase();
            if(tag !== 'button' && tag !== 'input' && tag !== 'textarea') recordAction('change', e.target);
        }, true);
    }

    // 🔑 Relay + root collector
    window.addEventListener("message", function(event) {
        if (event.data && event.data.__relay && event.data.payload) {
            // Save locally
            saveAction(event.data.payload);

            // If this window also has an opener, keep bubbling up until root
            if (window.opener && window.opener !== window) {
                window.opener.postMessage(event.data, "*");
            }
        }
    });

    if (document.readyState === "complete") attachListeners();
    else window.addEventListener('load', attachListeners, {once:true});

    console.log("✅ Multi-window action recording active...");
})();
"""
FINAL_JS_ACTION_LISTENER_old1= """
(function () {
    // Prevent duplicate injection across reloads/navigations
    if (localStorage.getItem("__recorderInjected") === "true") {
        console.log("ℹ️ Recorder already injected, skipping...");
        return;
    }
    localStorage.setItem("__recorderInjected", "true");
    window.__recorderInjected = true;

    // Initialize global action store
    if (!window.recordedActions) {
        window.recordedActions = JSON.parse(localStorage.getItem("recordedActions") || "[]");
    }

    function saveAction(action) {
        const existing = JSON.parse(localStorage.getItem("recordedActions") || "[]");
        existing.push(action);
        localStorage.setItem("recordedActions", JSON.stringify(existing));
    }

    function getXPath(el) {
        const getPos = e => {
            let pos = 1;
            while (e.previousElementSibling) {
                e = e.previousElementSibling;
                pos++;
            }
            return pos;
        };

        const parts = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            let index = getPos(el);
            let tag = el.nodeName.toLowerCase();
            parts.unshift(`${tag}[${index}]`);
            el = el.parentNode;
        }
        return '/' + parts.join('/');
    }

    function recordAction(type, target) {
        if (!target || ["script", "style"].includes(target.tagName?.toLowerCase())) return;
        const xpath = getXPath(target);
        const label = target.getAttribute("aria-label") || target.name || target.id || target.innerText || target.placeholder || target.value || target.getAttribute('alt') || target.getAttribute('class') || target.getAttribute('type');
        const value = (["input", "change", "input_others"].includes(type)) ? target.value || target.innerText || "" : "";
        const url = window.location.href;
        const actionObj = { 
            action: type, 
            xpath, 
            label: label?.trim(), 
            value, 
            url,
            windowId: window.name || window.location.href, 
            timestamp: new Date().toISOString()
        };

        // Save locally
        window.recordedActions.push(actionObj);
        saveAction(actionObj);

        // Send to parent if this is a popup/child window
        if (window.opener) {
            window.opener.postMessage(actionObj, "*");
        }
        console.log("Recorded:", actionObj);
    }

    function attachListeners() {    
        if (window.__listenersAttached) return; // prevent duplicates
        window.__listenersAttached = true;

        document.addEventListener('click', e => recordAction('click', e.target), true);

        document.addEventListener('change', e => {
            if (e.target.type === 'checkbox' || e.target.type === 'radio') {
                recordAction('input_others', e.target);
            } else if (e.target.type !== 'submit') {
                recordAction('input', e.target);
            }
        });

        document.addEventListener('focusout', e => {
            const tag = e.target.tagName.toLowerCase();
            if(tag !== 'button' && tag !== 'input' && tag !== 'textarea') {
                recordAction('change', e.target);
            }
        });
    }

    // Listen to messages from child windows
    window.addEventListener("message", function(event) {
        if (event.data && event.data.action) {
            saveAction(event.data);
        }
    });

    if (document.readyState === "complete") {
        attachListeners();
    } else {
        window.addEventListener('load', attachListeners, { once: true });
    }

    // Minimal observer: don’t reattach global listeners
    const observer = new MutationObserver(() => {
        // If new inputs/buttons appear dynamically, they’ll still work
        // since we attach at the document level
    });
    observer.observe(document.body, { childList: true, subtree: true });

    console.log("✅ Recording actions (multi-window safe)...");
})();
"""


FINAL_JS_ACTION_LISTENER_old= """ 
(function () {
    // Initialize recordedActions from localStorage or empty array
    window.recordedActions = JSON.parse(localStorage.getItem("recordedActions") || "[]");

    function saveAction(action) {
        const existing = JSON.parse(localStorage.getItem("recordedActions") || "[]");
        existing.push(action);
        localStorage.setItem("recordedActions", JSON.stringify(existing));
    }

    function getXPath(el) {
        const getPos = e => {
            let pos = 1;
            while (e.previousElementSibling) {
                e = e.previousElementSibling;
                pos++;
            }
            return pos;
        };

        const parts = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            let index = getPos(el);
            let tag = el.nodeName.toLowerCase();
            parts.unshift(`${tag}[${index}]`);
            el = el.parentNode;
        }
        return '/' + parts.join('/');
    }

    function recordAction(type, target) {
        if (!target || ["script", "style"].includes(target.tagName?.toLowerCase())) return;

        const xpath = getXPath(target);
        const label = target.getAttribute("aria-label") || target.name || target.id || target.innerText || target.placeholder || target.value || target.type;
        const value = (type === "input" || type === "change") ? target.value || "" : "";
        const url = window.location.href;

        //const exists = window.recordedActions.some(action => action.xpath === xpath && action.action === type && action.value === value);
        //if (!exists) {
            const actionObj = { action: type, xpath, label: label?.trim(), value, url };
            window.recordedActions.push(actionObj);
            saveAction(actionObj);
            console.log("Recorded:", actionObj);
        //}
    }

    function attachListeners() {
        document.addEventListener('click', e => {
            recordAction('click', e.target);
        });

        document.addEventListener('change', e => {
            recordAction('change', e.target);
        });

        document.addEventListener('blur', e => {
            const tag = e.target.tagName.toLowerCase();
            if (tag === 'input' || tag === 'textarea') {
                recordAction('input', e.target);
            }
        }, true);
    }

    if (document.readyState === "complete") {
        attachListeners();
    } else {
        window.addEventListener('load', attachListeners);
    }

    // Observe DOM changes to reattach listeners if needed (optional)
    const observer = new MutationObserver(() => {
        attachListeners();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    console.log("Recording actions...");
})();
"""


injection_script = f"""
var script = document.createElement('script');
script.type = 'text/javascript';
script.text = {json.dumps(FINAL_JS_ACTION_LISTENER)};
document.documentElement.appendChild(script);
"""
# in action_utils.py (or wherever)
def injection_script_updated():
    # keep this definition in your file as you posted earlier
    return f"""
        if (!document.getElementById("recorder_script")) {{
            var script = document.createElement('script');
            script.type = 'text/javascript';
            script.id = 'recorder_script';
            script.text = {json.dumps(FINAL_JS_ACTION_LISTENER)};
            document.documentElement.appendChild(script);
            console.log("✅ Recorder injected");
        }} else {{
            console.log("ℹ️ Recorder already present, skipping reinjection");
        }}
    """
def injection_script_updated_old():
    return f"""
        if (!document.getElementById("recorder_script")) {{
            var script = document.createElement('script');
            script.type = 'text/javascript';
            script.id = 'recorder_script';
            script.text = {json.dumps(FINAL_JS_ACTION_LISTENER)};
            document.documentElement.appendChild(script);
            console.log("✅ Recorder injected");
        }} else {{
            console.log("ℹ️ Recorder already present, skipping reinjection");
        }}
    """
def start_recording(driver):
    driver.execute_script(injection_script_updated())
    ####domain change handled action
def get_new_actions(driver):
    return driver.execute_script("""
        const actions = window.__recordedActions || [];
        window.__recordedActions = []; // clear after reading
        return actions;
    """)
def get_recorded_actions(driver):
    """
    Collect recorded actions from all windows, merge by timestamp.
    injected_windows: dict of {window_handle: True}
    """
    all_actions = []
    handles = driver.window_handles
    # Iterate through all known windows
    for handle in handles:
        try:
            driver.switch_to.window(handle)

            # Fetch actions from this window's localStorage
            actions = driver.execute_script("""
                return JSON.parse(localStorage.getItem('recordedActions') || '[]');
            """)
            if actions:
                all_actions.extend(actions)

        except Exception as e:
            print(f"⚠ Error fetching actions from window {handle}: {e}")

    # Sort all actions by timestamp
    all_actions.sort(key=lambda x: x.get('timestamp', ''))
    return all_actions

def get_recorded_actions_old(driver):
    # return driver.execute_script("return window.recordedActions || []")
    raw_actions = driver.execute_script("return localStorage.getItem('recordedActions') || '[]';")
    print("------------------recorder raw action--------------------")
    print(raw_actions)
    driver.execute_script("return localStorage.setItem('recordedActions','[]');")
    return json.loads(raw_actions) if raw_actions else []

def wait_for_url_change(driver, initial_url, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if driver.current_url != initial_url:
            return True
        time.sleep(1)
    return False

def generate_workflow(actions):
    # Access the variables
    print("*************Recorded Action *****************")
    print(actions)
    print("****************Recorded Action end**************")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

    # Set the environment variables explicitly if needed
    os.environ["AZURE_OPENAI_API_KEY"] = api_key
    os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint

    model = AzureChatOpenAI(
        openai_api_version="2023-05-15",
        azure_deployment="qepracticekey",
    )
    #
    prompt = f"""
    You are an expert test automation assistant. 
    Convert the raw recorded actions into a clean, deduplicated, and human-readable workflow 
    that can directly be used for writing test cases, scripts, and Gherkin feature files.

    Input Actions:
    {actions}

    Transformation Rules:
    1. **Deduplication**
       - Remove repeated actions on the same element (keep only the latest meaningful step).
       - If the same text input occurs multiple times in sequence, keep only the final input.
       - Ignore duplicate clicks when nothing changes.

    2. **Noise Filtering**
       - Ignore technical IDs (e.g., "a-xxxx", "ketch-*", "mx-auto", cryptic auto-generated IDs).
       - Skip redundant "Change the value to…" lines when already captured as "Enter…" or "Select…".
       - Remove empty clicks like `Click on ""`.

    3. **Action Normalization**
       - Merge "Click" + "Change the value" into a single meaningful action (e.g., `Select "Alabama" from "State" dropdown`).
       - Replace cryptic field names with human-readable labels using this mapping:
         - "first_name[0][value]" → "First Name"
         - "last_name[0][value]" → "Last Name"
         - "field_company[0][value]" → "Company"
         - "mail" → "Email"
         - "phoneNumber" → "Phone Number"
         - "dateOfBirthMasked" → "Date of Birth"
         - "addressLine1" → "Address Line 1"
         - "addressLine2" → "Address Line 2"
         - "cityName" → "City"
         - "zipCode" → "Zip Code"
         - "saveConsumer" → "Save"
         - "terms-of-use" → "Terms of Use"
         - "op" → "Submit"
       - If an element is not in the mapping, keep its best human-readable form.

    4. **Window Management**
       - Start with: `User opened page: [URL]`.
       - For new windows: `Switched to new window: [URL]`.
       - For revisits: `Switched to window: [URL]`.

    5. **Output Format**
       - Numbered steps.
       - Each step on its own line.
       - Use consistent phrasing:
         - Click → `Click the "LABEL" button` or `Click the "LABEL" link`
         - Input → `Enter "VALUE" in "LABEL" field`
         - Select → `Select "VALUE" from "LABEL" dropdown`
         - Checkbox → `Select "LABEL"`
       - No explanations, only the cleaned workflow.

    Output:
    - A perfectly cleaned workflow with numbered steps, 
    ready to be used for test case and feature file creation.
    """

    message = HumanMessage(content=prompt)
    output_value = model([message])
    print(output_value)
    return output_value.content
def generate_workflow_manual(actions):
    """
    Convert recorded actions into human-readable workflow suitable for AI feature/test case generation.
    Handles multiple windows and avoids duplicate window messages.
    """
    print("************Actions***************")
    print(actions)
    workflow_lines = []
    current_window = None
    seen_windows = set()

    for act in actions:
        window_id = act.get("windowId", "MainWindow")
        url = act.get("url", "Unknown")

        # Detect window switch or new window
        if window_id != current_window:
            if window_id in seen_windows:
                workflow_lines.append(f'Switched to window: [{url}]')
            else:
                if window_id == "MainWindow":
                    workflow_lines.append(f'User opened page: [{url}]')
                else:
                    workflow_lines.append(f'Switched to new window: [{url}]')
                seen_windows.add(window_id)

            current_window = window_id

        # Human-readable action
        readable = humanize_action(act)
        if readable:
            workflow_lines.append(f'{readable} (URL: {url})')
    print("*********workflow_lines************")
    print(workflow_lines)
    print("*********workflow_lines ends************")
   # generate_workflow(workflow_lines)
    return workflow_lines


def humanize_action(action_dict):
    """
    Converts a recorded action into a human-readable sentence suitable for AI consumption.
    """
    action_type = action_dict.get("action")
    tag = (action_dict.get("tag") or "").lower()
    label = (action_dict.get("label") or "").strip()
    value = (action_dict.get("value") or "").strip()
    placeholder = (action_dict.get("placeholder") or "").strip()
    element_id = (action_dict.get("id") or "").strip()

    display_label = label or placeholder or element_id.replace("-", " ").replace("_", " ").title()

    if action_type == "click":
        if tag == "button" or "btn" in element_id.lower():
            return f'Click the "{display_label}" button'
        elif tag == "a":
            return f'Click the "{display_label}" link'
        else:
            return f'Click on "{display_label}"'

    elif action_type == "input_others":
        return f'Select "{value}" in the "{display_label}" field'

    elif action_type == "select":
        return f'Select "{value}" from the "{display_label}" dropdown'

    elif action_type == "input":
        return f'Enter "{value}" in the "{display_label}" field'

    elif action_type == "change":
        return f'Change the value to "{value}" in "{display_label}"'

    elif action_type == "navigate":
        return f'Navigate to "{display_label}" page'

    elif action_type:
        return f'{action_type.capitalize()} on "{display_label}"'
    elif action_type == "scroll":
        return f'Scroll the page'

    elif action_type == "hover":
        return f'Hover over "{display_label}"'

    elif action_type == "keypress":
        return f'Press key in "{display_label}" field'

    elif action_type == "ajax":
        return f'Wait for page load/update triggered by "{display_label}"'

    else:
        return f'Perform action on "{display_label}"'



# def generate_workflow(actions):
#     print("------------------recorder raw action--------------------")
#     print(actions)
#     workflow_lines = []
#     recorded = set()
#     prev_url = None
#     prev_window = None
#
#     for act in actions:
#         url = act.get("url", "Unknown")
#         window_id = act.get("windowId", "MainWindow")
#
#         # Group by window and URL
#         if url != prev_url or window_id != prev_window:
#             workflow_lines.append(f"\nWindow: [{window_id}] | Page: [{url}]")
#             prev_url, prev_window = url, window_id
#
#         readable = humanize_action(act)
#         if readable and (window_id, readable) not in recorded:
#             workflow_lines.append(f"- {readable}")
#             recorded.add((window_id, readable))
#
#     return workflow_lines

def generate_workflow_old(actions):
    print("------------------recorder raw action--------------------")
    print(actions)
    workflow_lines = []
    recorded = set()
    prev_url = None

    for act in actions:
        url = act.get("url", "Unknown")

        # Only add "Page:" line if URL changes from previous
        if url != prev_url:
            workflow_lines.append(f"Page: [{url}]")
            prev_url = url

        readable = humanize_action(act)
        if readable and readable not in recorded:
            workflow_lines.append(f"- {readable}")
            recorded.add(readable)

    return workflow_lines
# def generate_workflow(actions):
#     grouped = defaultdict(list)
#     for act in actions:
#         url = act.get("url", "Unknown")
#         grouped[url].append(act)
#
#     workflow_lines = []
#     for url, acts in grouped.items():
#         workflow_lines.append(f"Page: [{url}]")
#         recorded = set()
#
#         for act in acts:
#             readable=humanize_action(act)
#             if readable and readable not in recorded:
#                 workflow_lines.append(f"- {readable}")
#                 recorded.add(readable)
#
#             # action = act.get("action", "").strip()
#             # label = act.get("label", "").strip()
#             #
#             # if not action or not label:
#             #     continue
#             #
#             # if action == 'click':
#             #     line = f"Click {label}"
#             # elif action == 'input':
#             #     line = f"Enter {label}"
#             # elif action == 'change':
#             #     line = f"Change {label}"
#             # else:
#             #     line = f"{action.capitalize()} {label}"
#             #
#             # if line and line not in recorded:
#             #     workflow_lines.append(f"- {line}")
#             #     recorded.add(line)
#
#         workflow_lines.append("")  # separate pages with blank line
#
#     return workflow_lines

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def take_screenshot(driver, folder):
    url = driver.current_url
    parsed_url = urlparse(url)
    page_name = sanitize_filename(parsed_url.path.strip("/")) or "home"
    file_path = os.path.join(folder, f"{page_name}.png")
    driver.save_screenshot(file_path)
    return file_path
# def humanize_action(action_dict):
#     action_type = action_dict.get("action")
#     tag = (action_dict.get("tag") or "").lower()
#
#     label = (action_dict.get("label") or "").strip()
#     value = (action_dict.get("value") or "").strip()
#     placeholder = (action_dict.get("placeholder") or "").strip()
#     element_id = (action_dict.get("id") or "").strip()
#
#     # Fallback label
#     display_label = label or placeholder or element_id.replace("-", " ").replace("_", " ").title()
#
#     # Add window info for clarity
#     window_id = action_dict.get("windowId", "MainWindow")
#
#     if action_type == "click":
#         if tag == "button" or "btn" in element_id.lower():
#             return f'[{window_id}] Click the "{display_label}" button'
#         elif tag == "a":
#             return f'[{window_id}] Click the "{display_label}" link'
#         else:
#             return f'[{window_id}] Click on "{display_label}"'
#
#     elif action_type == "input_others":
#         return f'[{window_id}] Select "{value}" in the "{display_label}" field'
#
#     elif action_type == "select":
#         return f'[{window_id}] Select "{value}" from the "{display_label}" dropdown'
#
#     elif action_type == "input":
#         return f'[{window_id}] Enter "{value}" in the "{display_label}" field'
#
#     elif action_type == "change":
#         return f'[{window_id}] Change the {value} in "{display_label}"'
#
#     elif action_type == "navigate":
#         return f'[{window_id}] Navigate to "{display_label}" page'
#
#     # Fallback
#     if action_type:
#         return f'[{window_id}] {action_type.capitalize()} on "{display_label}"'
#     else:
#         return f'[{window_id}] Perform action on "{display_label}"'

def humanize_action_old(action_dict):

    action_type = action_dict.get("action")
    tag = (action_dict.get("tag") or "").lower()

    label = action_dict.get("label")
    label = label.strip() if isinstance(label, str) else ""

    value = action_dict.get("value")
    value = value.strip() if isinstance(value, str) else ""

    placeholder = action_dict.get("placeholder")
    placeholder = placeholder.strip() if isinstance(placeholder, str) else ""

    element_id = action_dict.get("id")
    element_id = element_id.strip() if isinstance(element_id, str) else ""

    # Fallback-friendly label logic
    display_label = label or placeholder or element_id.replace("-", " ").replace("_", " ").title()

    if action_type == "click":
        if tag == "button" or "btn" in element_id.lower():
            return f'Click the "{display_label}" button'
        elif tag == "a":
            return f'Click the "{display_label}" link'
        else:
            return f'Click on "{display_label}"'

    elif action_type == "input":
        return f'Enter "{value}" in the "{display_label}" field'

    elif action_type == "change":
        return f'Change the value in "{display_label}"'

    elif action_type == "select":
        return f'Select "{value}" from the "{display_label}" dropdown'

    elif action_type == "navigate":
        return f'Navigate to "{display_label}" page'

    # Safeguard for unknown or missing action_type
    if action_type:
        return f'{action_type.capitalize()} on "{display_label}"'
    else:
        return f'Perform action on "{display_label}"'

