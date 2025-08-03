# utils_action.py
import time
import re
import os
from collections import defaultdict
from urllib.parse import urlparse
from utilities.db_utils.models import Screenshot

JS_EVENT_LISTENER_allsite="""(function () {
    if (!window.recordedActions) {
        window.recordedActions = [];
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

        const exists = window.recordedActions.some(action => action.xpath === xpath && action.action === type);
        if (!exists) {
            window.recordedActions.push({ action: type, xpath, label: label?.trim(), value, url });
            console.log("Recorded:", { action: type, xpath, label, value });
        }
    }

    function attachListeners() {
        document.addEventListener('click', e => {
            recordAction('click', e.target);
        });

        document.addEventListener('change', e => {
            recordAction('change', e.target);
        });

        document.addEventListener('blur', e => {
            if (e.target.tagName.toLowerCase() === 'input' || e.target.tagName.toLowerCase() === 'textarea') {
                recordAction('input', e.target);
            }
        }, true);
    }

    if (document.readyState === "complete") {
        attachListeners();
    } else {
        window.addEventListener('load', attachListeners);
    }

    // Optionally observe DOM changes
    const observer = new MutationObserver(() => {
        attachListeners();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    console.log("Recording actions...");
})();
"""

JS_EVENT_LISTENER="""(function () {
    if (!window.recordedActions) {
        window.recordedActions = [];
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
        const xpath = getXPath(target);
        const label = target.getAttribute("aria-label") || target.name || target.id || target.innerText || target.placeholder || target.value || target.type;
        const value = (type === "input" || type === "change") ? target.value || "" : "";
        const url = window.location.href;

        // Prevent duplicates
        const exists = window.recordedActions.some(action => action.xpath === xpath && action.action === type);
        if (!exists) {
            window.recordedActions.push({ action: type, xpath, label: label?.trim(), value, url });
        }
    }

    document.addEventListener('click', e => {
        recordAction('click', e.target);
    });

    document.addEventListener('change', e => {
        recordAction('change', e.target);
    });

    // On blur, capture final input value
    document.addEventListener('blur', e => {
        if (e.target.tagName.toLowerCase() === 'input' || e.target.tagName.toLowerCase() === 'textarea') {
            recordAction('input', e.target);
        }
    }, true);  // useCapture = true to catch blur bubbling up

    console.log("Recording actions...");
})();
"""

JS_EVENT_LISTENER_1 = """(function() {
    if (!window.recordedActions) {
        window.recordedActions = [];
    }

    function getXPath(element) {
        const getPos = el => {
            let pos = 1;
            while (el.previousElementSibling) {
                el = el.previousElementSibling;
                pos++;
            }
            return pos;
        };

        const parts = [];
        while (element && element.nodeType === Node.ELEMENT_NODE) {
            let index = getPos(element);
            let tag = element.nodeName.toLowerCase();
            parts.unshift(`${tag}[${index}]`);
            element = element.parentNode;
        }
        return '/' + parts.join('/');
    }

    function record(action, target) {
        const xpath = getXPath(target);
        const label = target.getAttribute("aria-label") || target.placeholder || target.name || target.id || target.innerText || target.value || target.type;
        const url = window.location.href;
        window.recordedActions.push({ action, xpath, label: label.trim(), url: url });
    }

    document.addEventListener('click', event => { record('click', event.target); });
    document.addEventListener('input', event => { record('input', event.target); });
    document.addEventListener('change', event => { record('change', event.target); });

    console.log("Recording actions...");
})();"""

def start_recording(driver):
    driver.execute_script(JS_EVENT_LISTENER_allsite)

def get_recorded_actions(driver):
    return driver.execute_script("return window.recordedActions || []")

def wait_for_url_change(driver, initial_url, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if driver.current_url != initial_url:
            return True
        time.sleep(1)
    return False


def generate_workflow(actions):
    grouped = defaultdict(list)
    for act in actions:
        url = act.get("url", "Unknown")
        grouped[url].append(act)

    workflow_lines = []
    for url, acts in grouped.items():
        workflow_lines.append(f"Page: [{url}]")
        recorded = set()

        for act in acts:
            readable=humanize_action(act)
            if readable and readable not in recorded:
                workflow_lines.append(f"- {readable}")
                recorded.add(readable)

            # action = act.get("action", "").strip()
            # label = act.get("label", "").strip()
            #
            # if not action or not label:
            #     continue
            #
            # if action == 'click':
            #     line = f"Click {label}"
            # elif action == 'input':
            #     line = f"Enter {label}"
            # elif action == 'change':
            #     line = f"Change {label}"
            # else:
            #     line = f"{action.capitalize()} {label}"
            #
            # if line and line not in recorded:
            #     workflow_lines.append(f"- {line}")
            #     recorded.add(line)

        workflow_lines.append("")  # separate pages with blank line

    return workflow_lines

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def take_screenshot(driver, folder):
    url = driver.current_url
    parsed_url = urlparse(url)
    page_name = sanitize_filename(parsed_url.path.strip("/")) or "home"
    file_path = os.path.join(folder, f"{page_name}.png")
    driver.save_screenshot(file_path)
    return file_path

def humanize_action(action_dict):
    action_type = action_dict.get("action")
    tag = action_dict.get("tag", "").lower()
    label = action_dict.get("label", "").strip()
    value = action_dict.get("value", "").strip()
    placeholder = action_dict.get("placeholder", "").strip()
    element_id = action_dict.get("id", "").strip()

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

