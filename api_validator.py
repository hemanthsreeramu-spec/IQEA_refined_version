
import os
import json
import hashlib
from datetime import datetime
import pandas as pd
import streamlit as st
import urllib3
import configparser
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -------------------------------------------
# Import API utilities
# -------------------------------------------
from utilities.API_Utils import api_core_model as api_utils
from utilities.API_Utils import swaggerhub as swagger_utils
from utilities.API_Utils import api_runner
from utilities.API_Utils import api_report
from utilities.API_Utils.api_context import ApiContext, find_variables, parse_extract_spec
import allure

swagger_utils.init_allure_results()

if "swagger_apis" not in st.session_state:
    st.session_state.swagger_apis = []
if "api_response_analysis" not in st.session_state:
    st.session_state.api_response_analysis=[]
if "api_performance_analysis" not in st.session_state:
    st.session_state.api_performance_analysis=[]
if "locust_convert_response" not in st.session_state:
    st.session_state.locust_convert_response=[]
# -------------------------------------------
# FOLDER CONFIG
# -------------------------------------------
current_path = os.getcwd()
input_folder = os.path.join(current_path, "Input")
output_folder = os.path.join(current_path, "output")
api_template_file = os.path.join(input_folder, "Api_template.xlsx")
REPORT_DIR = os.path.join(os.getcwd(), "tests_results", "Api_llm_results")
os.makedirs(REPORT_DIR, exist_ok=True)

os.makedirs(input_folder, exist_ok=True)
os.makedirs(output_folder, exist_ok=True)
ini_file_path = os.path.join(input_folder, "locust_config.ini")
locust_config = configparser.ConfigParser()
locust_config.read(ini_file_path)
performance_config = {
    "ramp_users": locust_config.get("api-performance", "ramp_users"),
    "spawn_rate": locust_config.get("api-performance", "spawn_rate"),
    "run_time": locust_config.get("api-performance", "run_time"),
    "stop_time": locust_config.get("api-performance", "stop_time")
}
# -------------------------------------------
# STREAMLIT CONFIG
# -------------------------------------------
st.set_page_config(
    page_title="TigerQE AI iQEA",
    page_icon="🤖",
    layout="centered"
)

if "api_data" not in st.session_state:
    st.session_state.api_data = None

# ------------------------------------------------------------------
# RESULT CACHE  —  compute once on run, render in tabs (survives reruns)
# ------------------------------------------------------------------
for _k, _v in {
    "api_val_results": [], "api_val_perf_paths": [],
    "api_val_resp_html": None, "api_val_perf_html": None, "api_val_ran": False,
    "api_val_chain_vars": {}, "api_val_notes": [],
}.items():
    st.session_state.setdefault(_k, _v)

st.markdown(
    "<style>.stButton>button[kind=\"primary\"]{background:#F47B20;border-color:#F47B20;}</style>",
    unsafe_allow_html=True,
)

st.title("🤖 TigerQE AI Platform - API Validator")
st.caption("Validate, benchmark and analyse APIs — each concern in its own panel, no long scroll.")


# ==================================================================
# COMPUTE  —  Document flow
# ==================================================================
def _run_document(performance_flag, recommendation_flag):
    api_list = st.session_state.api_data or []
    runnable = [row for row in api_list if row.get("validate") or row.get("performance")]
    if not runnable:
        st.warning("No rows are marked Validate? = Y (or Performance? = Y).")
        return

    progress = st.progress(0)
    status_text = st.empty()

    def _on_progress(done, total, label):
        status_text.markdown(f"**Running {done} / {total}** — `{label}`")
        progress.progress(done / total if total else 1.0)

    try:
        results, performance_result, context, notes = api_runner.run_suite(
            api_list,
            mode="file",
            context=ApiContext(),
            validate_fn=api_runner.document_validate,
            on_progress=_on_progress,
            performance=performance_flag,
            global_headers=_global_headers(),
        )
    except ValueError as exc:  # circular dependency between test cases
        progress.empty()
        status_text.empty()
        st.error(str(exc))
        return

    status_text.markdown(f"**Completed {len(results)} API call(s)**")
    progress.progress(1.0)

    st.session_state.api_val_chain_vars = context.as_dict()
    st.session_state.api_val_notes = notes

    resp_html = None
    if recommendation_flag:
        # Feed the compact report rows, not raw bodies — smaller prompt, and the
        # model sees exactly the columns the report shows.
        api_response_analysis_prompt = swagger_utils.api_response_prompt(
            api_report.report_rows(results))
        st.session_state.api_response_analysis = swagger_utils.get_queries_from_ai_updated(api_response_analysis_prompt)
        resp_html = swagger_utils.save_html_report(st.session_state.api_response_analysis, REPORT_DIR, "Api_Response")

    perf_html = None
    if performance_result:
        performance_extracted_data = swagger_utils.collect_locust_csv_from_paths(performance_result)
        locust_covert_prompt = swagger_utils.locust_convert_prompt(performance_extracted_data, performance_config)
        st.session_state.locust_convert_response = swagger_utils.get_queries_from_ai_updated(locust_covert_prompt)
        perf_html = swagger_utils.save_html_report(st.session_state.locust_convert_response, REPORT_DIR,
                                                   "Api_Performance_Response")

    st.session_state.api_val_results = results
    st.session_state.api_val_perf_paths = performance_result
    st.session_state.api_val_resp_html = resp_html
    st.session_state.api_val_perf_html = perf_html
    st.session_state.api_val_ran = True


# ==================================================================
# COMPUTE  —  Swagger flow
# ==================================================================
def _run_swagger():
    apis_to_run = [
        api for api in st.session_state.swagger_apis
        if api.get("Validate?") or api.get("Performance?")
    ]
    if not apis_to_run:
        st.warning("Select at least one API to validate.")
        return

    progress_bar = st.progress(0)
    status_text = st.empty()

    def _on_progress(done, total, label):
        status_text.markdown(f"**Running {done} / {total}** — `{label}`")
        progress_bar.progress(done / total if total else 1.0)

    try:
        results, performance_result, context, notes = api_runner.run_suite(
            apis_to_run,
            mode="Swegger",
            context=ApiContext(),
            on_progress=_on_progress,
            performance=any(api.get("Performance?") for api in apis_to_run),
            global_headers=_global_headers(),
        )
    except ValueError as exc:  # circular dependency
        progress_bar.empty()
        status_text.empty()
        st.error(str(exc))
        return

    status_text.markdown(f"**Completed {len(results)} API call(s)**")
    progress_bar.progress(1.0)

    st.session_state.api_val_chain_vars = context.as_dict()
    st.session_state.api_val_notes = notes

    api_response_analysis_prompt = swagger_utils.api_response_prompt(results)
    st.session_state.api_response_analysis = swagger_utils.get_queries_from_ai_updated(api_response_analysis_prompt)
    resp_html = swagger_utils.save_html_report(st.session_state.api_response_analysis, REPORT_DIR, "Api_Response")

    perf_html = None
    if performance_result:
        performance_extracted_data = swagger_utils.collect_locust_csv_from_paths(performance_result)
        locust_covert_prompt = swagger_utils.locust_convert_prompt(performance_extracted_data)
        st.session_state.locust_convert_response = swagger_utils.get_queries_from_ai_updated(locust_covert_prompt)
        api_performance_analysis_prompt = swagger_utils.api_performace_reponse_prompt(
            st.session_state.locust_convert_response, performance_config)
        st.session_state.api_performance_analysis = swagger_utils.get_queries_from_ai_updated(
            api_performance_analysis_prompt)
        perf_html = swagger_utils.save_html_report(st.session_state.api_performance_analysis, REPORT_DIR,
                                                   "Api_Performance_Response")

    st.session_state.api_val_results = results
    st.session_state.api_val_perf_paths = performance_result
    st.session_state.api_val_resp_html = resp_html
    st.session_state.api_val_perf_html = perf_html
    st.session_state.api_val_ran = True


# ==================================================================
# SWAGGER SELECTION GRID  (+ chaining inputs)
# ==================================================================
# Rendering every widget for a large spec (the agentflow spec has 465
# endpoints) makes the page crawl, so the per-API chaining inputs are only
# rendered for APIs that are actually selected to run.
MAX_ROWS_RENDERED = 150


def _is_selected(api):
    return bool(api.get("Validate?") or api.get("Performance?"))


def _global_headers():
    """
    Headers applied to every API in a run.

    Read fresh from session_state at run time rather than copied onto rows when a
    button is pressed — copying meant a row selected afterwards silently missed
    the header and came back 401.
    """
    headers = {}
    for slot in (1, 2):
        name = (st.session_state.get(f"swagger_global_hdr_name_{slot}") or "").strip()
        value = st.session_state.get(f"swagger_global_hdr_value_{slot}")
        if name and value and str(value).strip():
            headers[name] = value
    return headers


def _render_global_header_inputs():
    """Paste-once headers. Shared by both flows — the token problem is identical."""
    st.markdown(
        "**Global headers** — added to every API you run, including ones you select or upload "
        "later. A row that sets the same header keeps its own value, and the API that "
        "*produces* a referenced value never receives it."
    )
    for slot in (1, 2):
        g1, g2 = st.columns([2, 5])
        g1.text_input(
            f"Header name {slot}",
            value="Authorization" if slot == 1 else "",
            key=f"swagger_global_hdr_name_{slot}",
        )
        g2.text_input(
            f"Header value {slot}",
            placeholder="Bearer eyJhbGciOi…   (paste the token, or Bearer ${token} to chain it)",
            key=f"swagger_global_hdr_value_{slot}",
        )

    active = _global_headers()
    if active:
        st.caption("Will be sent with every API in this run: " + ", ".join(f"`{k}`" for k in active))
    else:
        st.caption("No global header set — authenticated endpoints will return 401.")


def _set_selection(apis, value):
    """
    Bulk set the Validate flag. The checkbox widget state is dropped so each box
    re-initialises from the dict on the next run (assigning the widget key
    directly would clash with the widget's own default).
    """
    for api in apis:
        api["Validate?"] = value
        st.session_state.pop(f"swagger_validate_{api['__id__']}", None)
        if not value:
            api["Performance?"] = False
            st.session_state.pop(f"swagger_perf_{api['__id__']}", None)


def _render_swagger_grid(all_apis):
    st.markdown("**API Selection**")

    c1, c2, c3 = st.columns([4, 2, 2])
    search = c1.text_input(
        "Filter endpoints",
        placeholder="Filter by method or path, e.g. 'post prompts'",
        label_visibility="collapsed",
        key="swagger_search",
    )
    selected_only = c2.toggle("Selected only", key="swagger_selected_only")
    selected_count = sum(1 for api in all_apis if _is_selected(api))
    c3.markdown(f"**{selected_count} selected** / {len(all_apis)}")

    # ---- chaining help + bulk header ----
    with st.expander("🔗 Chaining — how to feed one API's response into another"):
        st.markdown(
            "Give an API an **Extract** rule to capture values from its response, then reference "
            "them as `${name}` in any later API's path params, query params, headers or payload.\n\n"
            "```\n"
            "POST /auth/token      Extract: token=$.access_token\n"
            "GET  /prompts/list    Header:  Authorization = Bearer ${token}\n"
            "                      Extract: prompt_id=$.data[0].id\n"
            "GET  /prompts/{id}     Path:    id = ${prompt_id}\n"
            "```\n"
            "One value can feed **any number** of later APIs — extract it once:\n\n"
            "```\n"
            "POST /agents/save_draft    Extract: agent_id=$.agent_id|int   Order 1\n"
            "POST /agents/create_draft  Payload: \"agent_id\": \"${agent_id}\"   Order 2\n"
            "PUT  /agents/update        Payload: \"agent_id\": \"${agent_id}\"   Order 3\n"
            "```\n"
            "Execution order is inferred automatically — an API that uses `${token}` runs after the "
            "one that extracts it. Set **Order** only to sequence APIs that consume the same value.\n\n"
            "Extract sources: `$.json.path`, `header:Set-Cookie`, `$status`, `$body`. Add `|int` "
            "(or `|float`, `|str`, `|bool`, `|json`) to cast — needed when an API returns an id as a "
            "string but the next API declares that field as an integer.\n\n"
            "Not sure of the path? Run the producing API on its own once and read its body under "
            "**Results → Response bodies**, then write the Extract rule.\n\n"
            "**Generated values** (no Extract needed — useful when a create API needs a unique "
            "name each run): `${__uuid}`, `${__timestamp}`, `${__time(YMDHMS)}`, `${__datetime}`, "
            "`${__randomInt(1,999)}`, `${__randomString(8)}`, `${__counter}`, `${__threadNum}`.\n\n"
            "In a JSON payload always quote the placeholder (`\"connector_id\": \"${conn_id}\"`) — "
            "if the stored value is a number it is substituted back as a number, not a string."
        )

        st.markdown("---")
        _render_global_header_inputs()

    # ---- filter ----
    needle = (search or "").strip().lower()
    visible = [
        api for api in all_apis
        if not needle or all(tok in f"{api['httpMethod']} {api['endpoint']}".lower() for tok in needle.split())
    ]
    if selected_only:
        visible = [api for api in visible if _is_selected(api)]

    # Cap the render, but never hide something that is going to run
    shown = visible[:MAX_ROWS_RENDERED]
    shown_ids = {api["__id__"] for api in shown}
    shown += [api for api in visible[MAX_ROWS_RENDERED:] if _is_selected(api) and api["__id__"] not in shown_ids]
    hidden = len(visible) - len(shown)

    if not visible:
        st.info("No endpoints match the filter.")
        return

    # ---- select all / clear all (acts on the filtered set) ----
    scope_label = "matching" if needle or selected_only else "all"
    b1, b2, _sp = st.columns([2, 2, 4])
    if b1.button(f"☑ Select {scope_label} ({len(visible)})", use_container_width=True):
        _set_selection(visible, True)
        st.rerun()
    if b2.button("☐ Clear selection", use_container_width=True):
        _set_selection(all_apis, False)
        st.rerun()

    if hidden > 0:
        st.caption(f"Showing {len(shown)} of {len(visible)} matching endpoints — narrow the filter to see the rest.")

    head = st.columns([7, 1.2, 1.4])
    head[0].markdown("**Endpoint**")
    head[1].markdown("**Validate**")
    head[2].markdown("**Perf**")

    for api in shown:
        api_id = api["__id__"]
        cols = st.columns([7, 1.2, 1.4])
        cols[0].write(f"`{api['httpMethod']}` {api['endpoint']}")

        api["Validate?"] = cols[1].checkbox(
            "Validate", value=bool(api.get("Validate?")),
            key=f"swagger_validate_{api_id}", label_visibility="collapsed",
        )
        api["Performance?"] = cols[2].checkbox(
            "Performance", value=bool(api.get("Performance?")),
            key=f"swagger_perf_{api_id}", label_visibility="collapsed",
        )

        if _is_selected(api):
            _render_api_detail(api)


def _render_api_detail(api):
    api_id = api["__id__"]
    extract_summary = f" · extracts {', '.join(n for n, _ in parse_extract_spec(api.get('extract')))}" \
        if api.get("extract") else ""

    with st.expander(f"⚙️ {api['httpMethod']} {api['endpoint']}{extract_summary}"):
        # ---- test case name ----
        api["test_case_name"] = st.text_input(
            "Test case name",
            value=api.get("test_case_name") or "",
            key=f"swagger_tcname_{api_id}",
            help="Shown in the result report and used by Depends-On. Defaults to a name "
                 "generated from the method and path.",
        )

        # ---- order ----
        order_value = st.number_input(
            "Execution order (0 = auto)",
            min_value=0, step=1,
            value=int(api.get("order") or 0),
            key=f"swagger_order_{api_id}",
            help="Ties are broken by this number. Dependencies inferred from ${vars} always win.",
        )
        api["order"] = order_value or None

        # ---- path params ----
        path_params = api.get("pathParams") or []
        if path_params:
            st.markdown("**Path parameters**")
            for param in path_params:
                param["value"] = st.text_input(
                    f"{param['name']} (path)",
                    value=str(param.get("value") or ""),
                    placeholder="literal value or ${var}",
                    key=f"swagger_path_{api_id}_{param['name']}",
                    help=param.get("description") or None,
                )

        # ---- query params ----
        query_params = api.get("queryParams") or []
        if query_params:
            st.markdown("**Query parameters**")
            for param in query_params:
                label = f"{param['name']} (query)" + (" *" if param.get("required") else "")
                param["value"] = st.text_input(
                    label,
                    value=str(param.get("value") if param.get("value") is not None else ""),
                    placeholder="leave blank to omit",
                    key=f"swagger_query_{api_id}_{param['name']}",
                    help=param.get("description") or None,
                )

        # ---- headers ----
        headers_key = f"swagger_headers_{api_id}"
        headers_text = st.text_area(
            "Headers (JSON)",
            value=json.dumps(api.get("headers") or {}, indent=2),
            height=110,
            key=headers_key,
        )
        try:
            api["headers"] = json.loads(headers_text) if headers_text.strip() else {}
            api.pop("_headers_error", None)
        except Exception as exc:
            # Flag it on the row: without this the last value that DID parse stays
            # in place and gets sent silently on the next Run.
            api["_headers_error"] = f"Headers JSON is invalid: {exc}"
            st.warning(f"⚠ Invalid headers JSON — this API will not be sent: {exc}")

        # ---- payload ----
        if api["httpMethod"] in ("POST", "PUT", "PATCH"):
            payload_key = f"swagger_payload_text_{api_id}"
            payload_text = st.text_area(
                "Payload (JSON)",
                value=json.dumps(api.get("payload") or {}, indent=2),
                height=180,
                key=payload_key,
            )
            try:
                api["payload"] = json.loads(payload_text) if payload_text.strip() else {}
                api.pop("_payload_error", None)
            except Exception as exc:
                api["_payload_error"] = f"Payload JSON is invalid: {exc}"
                st.warning(f"⚠ Invalid JSON payload — this API will not be sent: {exc}")

        # ---- chaining ----
        api["extract"] = st.text_input(
            "Extract from response",
            value=api.get("extract") or "",
            placeholder="token=$.access_token; user_id=$.data[0].id",
            key=f"swagger_extract_{api_id}",
            help="name=source pairs, ';' separated. Sources: $.json.path, header:Name, $status, $body",
        )
        api["dependsOn"] = st.text_input(
            "Depends on (optional)",
            value=api.get("dependsOn") or "",
            placeholder="POST /auth/token",
            key=f"swagger_depends_{api_id}",
            help="Usually unnecessary — order is inferred from ${vars}. Use for ordering with no data flow.",
        )

        expected = st.number_input(
            "Expected status code",
            min_value=100, max_value=599,
            value=int(api.get("Expected-StatusCode") or 200),
            key=f"swagger_expected_{api_id}",
        )
        api["Expected-StatusCode"] = expected


def _render_swagger_export(all_apis):
    """
    Export the fetched endpoints as a filled-in copy of the Excel template, so a
    Swagger fetch can be handed over to the Document flow (and edited, reviewed
    or committed as a test suite) instead of being re-typed by hand.
    """
    with st.expander("⬇️ Export to Excel template — continue in the Document flow"):
        # ---- optionally build on top of a sheet exported earlier ----
        previous = st.file_uploader(
            "Add to a previously exported sheet (optional)",
            type=["xlsx"],
            key="swagger_export_base",
            help="Upload an earlier export to append the endpoints you select now. "
                 "Re-selecting the same endpoint with a different payload is kept as a separate test case.",
        )

        base_frame, base_notes = None, []
        if previous is not None:
            base_frame, base_error = swagger_utils.read_template_frame(previous)
            if base_error:
                st.error(base_error)
                base_frame = None
            else:
                st.success(f"Loaded {len(base_frame)} existing row(s) — new endpoints are appended below.")

        selected = [api for api in all_apis if _is_selected(api)]
        scope_selected = st.radio(
            "What to export",
            options=(f"Selected only ({len(selected)})", f"All fetched endpoints ({len(all_apis)})"),
            index=0 if selected else 1,
            horizontal=True,
            key="swagger_export_scope",
        )
        rows = selected if scope_selected.startswith("Selected") else all_apis

        if not rows and base_frame is None:
            st.info("Nothing to export — select at least one endpoint, or switch to “All fetched endpoints”.")
            return

        warnings = []
        if rows:
            new_frame, warnings = swagger_utils.swagger_rows_to_template(rows)
        else:
            new_frame = None
            st.info("No endpoints selected — you can still edit and re-download the uploaded sheet.")

        if base_frame is not None and new_frame is not None:
            frame, base_notes = swagger_utils.merge_template_frames(base_frame, new_frame)
            st.caption(f"{len(base_frame)} existing + {len(new_frame)} new = **{len(frame)} row(s)**")
        elif base_frame is not None:
            frame = base_frame
            st.caption(f"{len(frame)} row(s) from the uploaded sheet")
        else:
            frame = new_frame
            st.caption(
                f"{len(frame)} row(s) · path and query values, payloads, headers, Extract rules, "
                "Depends-On and Order are all carried over."
            )

        for note in base_notes:
            st.info(note)
        for warning in warnings:
            st.warning(warning)

        # ---- editable before download ----
        st.markdown("**Review and edit** — change any cell, or use the ➕ row at the bottom to add one.")
        # Reset the editor when the underlying set of rows changes, otherwise it
        # would keep showing edits made against a different selection.
        signature = hashlib.md5(
            ("|".join(map(str, frame.get("Test_Case_Name", []))) + f"|{len(frame.columns)}").encode()
        ).hexdigest()[:10]

        yes_no = st.column_config.SelectboxColumn(options=["Y", "N"], width="small")
        edited = st.data_editor(
            frame,
            key=f"swagger_export_editor_{signature}",
            num_rows="dynamic",
            use_container_width=True,
            height=320,
            column_config={
                "BodyFormat": st.column_config.TextColumn("BodyFormat", width="large"),
                "endPoint": st.column_config.TextColumn("endPoint", width="medium"),
                "Extract-Values": st.column_config.TextColumn("Extract-Values", width="medium"),
                "Validate?": yes_no,
                "Performance?": yes_no,
            },
        )

        edited = edited.where(pd.notna(edited), "")
        for problem in swagger_utils.validate_template_frame(edited):
            st.warning(problem)

        try:
            payload = swagger_utils.template_dataframe_to_bytes(edited)
        except Exception as exc:
            st.error(f"Could not build the Excel file: {exc}")
            return

        st.download_button(
            f"⬇ Download API_Details.xlsx ({len(edited)} row(s))",
            data=payload,
            file_name="API_Details.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
        st.caption(
            "Switch to **📄 Document (Excel)** and upload this file to run it — or bring it back here "
            "later to append more endpoints."
        )


def _render_result_downloads(results):
    """One consolidated HTML and Excel report per run, failures in red."""
    stats = api_report.summarise(api_report.report_rows(results))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary = st.columns(5)
    summary[0].metric("Total", stats["total"])
    summary[1].metric("Passed", stats["passed"])
    summary[2].metric("Failed", stats["failed"])
    summary[3].metric("Skipped", stats["skipped"])
    summary[4].metric("Pass rate", f"{stats['pass_rate']}%")

    try:
        html_report = api_report.results_to_html(results)
        excel_report = api_report.results_to_excel_bytes(results)
    except Exception as exc:
        st.error(f"Could not build the result report: {exc}")
        return

    left, right = st.columns(2)
    left.download_button(
        "⬇ Download HTML report",
        data=html_report.encode("utf-8"),
        file_name=f"API_Test_Report_{stamp}.html",
        mime="text/html",
        use_container_width=True,
    )
    right.download_button(
        "⬇ Download Excel report",
        data=excel_report,
        file_name=f"API_Test_Report_{stamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    with st.expander("📋 Consolidated report preview", expanded=stats["failed"] > 0):
        st.components.v1.html(html_report, height=460, scrolling=True)


# ==================================================================
# RESULT TABS  (Validation / Performance / AI Insights)
# ==================================================================
def _render_result_tabs():
    st.subheader("Results")
    if not st.session_state.api_val_ran:
        st.info("Configure a source above and run a validation — results appear here.")
        return

    tab_v, tab_p, tab_ai = st.tabs(["🧪 Validation", "⚡ Performance", "🤖 AI Insights"])

    with tab_v:
        results = st.session_state.api_val_results or []
        if results:
            df = pd.DataFrame(results)

            palette = {
                "PASS": "background-color: #c8f7c5",
                "SKIP": "background-color: #fdf0c2",
            }

            def color_rows(row):
                return [palette.get(row["Result"], "background-color: #f7c5c5")] * len(row)

            # Request/response detail is shown separately below — it would make
            # every row of the table unreadably tall.
            table_df = df.drop(
                columns=["Actual Response", "Request URL", "Request Headers", "Request Body"],
                errors="ignore",
            )
            st.dataframe(table_df.style.apply(color_rows, axis=1), use_container_width=True)

            _render_result_downloads(results)

            for note in st.session_state.api_val_notes or []:
                st.warning(note)

            chain_vars = st.session_state.api_val_chain_vars or {}
            if chain_vars:
                with st.expander(f"🔗 Chained values captured ({len(chain_vars)})"):
                    st.json({k: v for k, v in chain_vars.items()})

            detailed = [r for r in results if r.get("Actual Response") or r.get("Request URL")]
            if detailed:
                with st.expander(
                    f"🔍 Request / response detail ({len(detailed)}) — "
                    "check what was actually sent, and build Extract paths"
                ):
                    for r in detailed:
                        st.markdown(f"**{r['Method']} {r['Endpoint']}** → `{r['Status']}`")
                        req_col, resp_col = st.columns(2)

                        with req_col:
                            st.caption("Sent")
                            if r.get("Request URL"):
                                st.code(r["Request URL"], language="text")
                            if r.get("Request Headers"):
                                st.code(r["Request Headers"], language="json")
                            if r.get("Request Body"):
                                st.code(r["Request Body"], language="json")

                        with resp_col:
                            st.caption("Received")
                            body = r.get("Actual Response") or ""
                            try:
                                st.json(json.loads(body))
                            except Exception:
                                st.code(body or "(empty)")
                        st.divider()
        else:
            st.info("No validation results.")

    with tab_p:
        paths = st.session_state.api_val_perf_paths or []
        if paths:
            api_utils.Apicore().show_locust_report(paths)
            if st.session_state.api_val_perf_html:
                api_utils.Apicore().show_llm_response(st.session_state.api_val_perf_html, "Performance_response")
        else:
            st.info("No performance run — enable **Performance** before validating.")

    with tab_ai:
        if st.session_state.api_val_resp_html:
            api_utils.Apicore().show_llm_response(st.session_state.api_val_resp_html, "API_response")
        else:
            st.info("No AI analysis — enable **AI recommendation** (Document) before validating.")


# ==================================================================
# INPUT  —  source selector + mode-specific inputs
# ==================================================================
mode = st.segmented_control(
    "API Source",
    ["📄 Document (Excel)", "🌐 Swagger / OpenAPI"],
    default="📄 Document (Excel)",
    label_visibility="collapsed",
    key="api_source_mode",
)
mode = mode or "📄 Document (Excel)"
is_swagger = "Swagger" in mode

with st.container(border=True):
    # ------------------------------------------------------------------
    # DOCUMENT MODE
    # ------------------------------------------------------------------
    if not is_swagger:
        col1, col2 = st.columns([3, 1])
        with col1:
            uploaded_file = st.file_uploader("Upload API Details Excel document", type=["xlsx"])
        with col2:
            with open(api_template_file, "rb") as f:
                st.download_button("⬇ Download Template", f, file_name="API_Test_Template.xlsx",
                                   use_container_width=True)

        f1, f2 = st.columns(2)
        performance_flag = f1.toggle("⚡ Performance test")
        recommendation_flag = f2.toggle("🤖 AI recommendation")

        with st.expander("🔗 Chaining & auth — pass one API's response into another"):
            st.markdown(
                "Add `Extract-Values` to the row that produces a value, then reference it as "
                "`${name}` in any later row's `endPoint`, `BodyFormat` or `headers-*` cell.\n\n"
                "```\n"
                "TC_01_save_draft    Extract-Values: agent_id=$.data.agent_id|int   Execution-Order 1\n"
                "TC_02_create_draft  BodyFormat: {\"agent_id\": \"${agent_id}\"}         Execution-Order 2\n"
                "TC_03_update        BodyFormat: {\"agent_id\": \"${agent_id}\"}         Execution-Order 3\n"
                "```\n"
                "Order is inferred from `${vars}` — set `Execution-Order` only to sequence rows "
                "that consume the same value. `Depends-On` takes `Test_Case_Name`s for ordering "
                "with no data flow.\n\n"
                "Extract sources: `$.json.path`, `header:Set-Cookie`, `$status`, `$body`, with an "
                "optional `|int` / `|float` / `|str` / `|bool` / `|json` cast. Generated values need "
                "no Extract: `${__uuid}`, `${__time(YMDHMS)}`, `${__randomInt(1,999)}`.\n\n"
                "Add any header as a `headers-<Name>` column (e.g. `headers-x-api-key`).\n\n"
                "**Expected-Message** runs only once the status code matches. Comma-separated, "
                "quotes optional:\n\n"
                "```\n"
                "agent_id:10877, message:Created, \"Agent Created & Secured\"\n"
                "```\n"
                "`key:value` finds that field anywhere in the response (including inside `data`) and "
                "matches **partially, case-insensitively** — `message:Created` passes against "
                "\"Agent Created & Secured\". A bare value with no key must appear somewhere in the "
                "response. Numbers and booleans are compared by value, so `id:3` will not pass "
                "against `13243`."
            )
            st.markdown("---")
            _render_global_header_inputs()

        if uploaded_file:
            api_list, read_errors = swagger_utils.read_excel_input(uploaded_file)
            st.session_state.api_data = api_list

            for problem in read_errors:
                st.error(problem)

            if api_list:
                st.success(f"Loaded {len(api_list)} row(s) from the document")
                preview = pd.DataFrame([
                    {
                        "Test Case": row["test_case_name"],
                        "Method": row["method"],
                        "URL": f"{row['baseUrl']}{row['endpoint']}",
                        "Headers": ", ".join(row["headers"].keys()) or "-",
                        "Payload": (json.dumps(row["payload"])[:60] + "…")
                        if len(json.dumps(row["payload"])) > 60 else json.dumps(row["payload"]),
                        "Extract": row["extract"] or "-",
                        "Depends On": row["dependsOn"] or "-",
                        "Order": row["order"] or "auto",
                        "Validate": "Y" if row["validate"] else "N",
                        "Perf": "Y" if row["performance"] else "N",
                    }
                    for row in api_list
                ])
                st.dataframe(preview, use_container_width=True)
            else:
                st.warning("No usable rows found in the document.")

        if st.button("▶️ Validate APIs", type="primary"):
            if not st.session_state.api_data:
                st.error("Upload API Excel file")
            else:
                _run_document(performance_flag, recommendation_flag)
                st.success("API Testing Completed")

    # ------------------------------------------------------------------
    # SWAGGER MODE
    # ------------------------------------------------------------------
    else:
        col1, col2 = st.columns([4, 1])
        with col1:
            swagger_url = st.text_input(
                "Swagger / OpenAPI URL",
                placeholder="https://virtserver.swaggerhub.com/xxx/1.0.0/swagger.json",
                label_visibility="collapsed",
            )
        with col2:
            fetch_clicked = st.button("Fetch APIs", use_container_width=True)

        if fetch_clicked:
            if not swagger_url:
                st.error("Please enter Swagger URL")
            else:
                try:
                    spec = swagger_utils.load_openapi_spec(swagger_url)
                    api_details = swagger_utils.extract_api_details(spec)
                    base_url = swagger_utils.get_base_url(swagger_url, spec)
                    api_list = swagger_utils.build_data_dictionary(api_details, base_url, spec)

                    taken_names = set()
                    for idx, api in enumerate(api_list):
                        # Nothing is selected by default — a large spec would
                        # otherwise fire hundreds of requests on the first click.
                        api["Validate?"] = False
                        api["Performance?"] = False
                        api["__id__"] = f"{api['httpMethod']}_{api['endpoint']}_{idx}"
                        # Give every endpoint a real test case name so results and
                        # exports are labelled by name, not by URL.
                        api["test_case_name"] = swagger_utils.make_test_case_name(
                            api, idx + 1, taken_names)

                    st.session_state.swagger_apis = api_list
                    st.success(f"Loaded {len(api_list)} APIs from Swagger")
                except Exception as e:
                    st.error(f"Failed to load Swagger APIs: {e}")

        # ---- API selection grid ----
        if st.session_state.swagger_apis:
            all_apis = st.session_state.swagger_apis
            _render_swagger_grid(all_apis)

            if st.button("▶️ Run Selected Swagger APIs", type="primary"):
                _run_swagger()
                st.success("Swagger APIs completed")

            _render_swagger_export(all_apis)

st.divider()

# ==================================================================
# RESULTS
# ==================================================================
_render_result_tabs()

# ============================================================
# FOOTER
# ============================================================
st.divider()
st.markdown("""
    ### Contact Us
    - Reach us at [QE Core Team](mailto:sahil.gupta@tigeranalytics.com)
""")
