
import os
import json
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
    results = []
    performance_result = []
    api_list = st.session_state.api_data
    progress = st.progress(0)

    for i, api_data in enumerate(api_list):
        if not str(api_data.get("Validate?")):
            continue

        api_response, combined_url, http_method = api_utils.Apicore().makeapicall(api_data, "file")

        if not api_response:
            results.append({
                "Method": http_method, "Endpoint": combined_url, "Status": "NO RESPONSE",
                "Actual Response": "", "Expected Response": "", "Result": "FAIL",
            })
            continue

        http_method = http_method.upper()

        if http_method == "GET":
            expected_output = api_data.get("expected_message", "")
            result = api_utils.Apicore().validate_api_result(api_response, expected_output)
        elif http_method in ["POST", "PUT"]:
            request_payload = api_data.get("payload", {})
            if isinstance(request_payload, str):
                request_payload = json.loads(request_payload)
            result = api_utils.Apicore().validate_post_response(api_response, request_payload)
        elif http_method in ["PATCH", "DELETE"]:
            result = "PASS" if api_response.status_code < 400 else "FAIL"
        else:
            result = "FAIL"

        results.append({
            "Method": http_method, "Endpoint": combined_url, "Status": api_response.status_code,
            "Actual Response": api_response.text,
            "Expected Response": api_data.get("expected_message", ""), "Result": result,
        })

        if performance_flag and str(api_data.get("Performance?")):
            report_path, locust_csv_path = api_utils.Apicore().makeperformancecall(api_data, "file")
            performance_result.append(report_path)

        progress.progress((i + 1) / len(api_list))

    resp_html = None
    if recommendation_flag:
        api_response_analysis_prompt = swagger_utils.api_response_prompt(results)
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
    results = []
    performance_result = []

    apis_to_run = [
        api for api in st.session_state.swagger_apis
        if api.get("Validate?") or api.get("Performance?")
    ]
    total = len(apis_to_run)
    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, api in enumerate(apis_to_run):
        endpoint_label = f"{api.get('httpMethod', '')} {api.get('endpoint', '')}"
        status_text.markdown(f"**Running {idx + 1} / {total}** — `{endpoint_label}`")
        progress_bar.progress((idx + 1) / total)

        if api.get("Validate?"):
            response, combined_url, http_method = api_utils.Apicore().makeapicall(api, "Swegger")
            if response:
                status = response.status_code
                expected_status = api.get("Expected-StatusCode", 200)
                result = "PASS" if response.status_code == expected_status else "FAIL"
            else:
                status = "NO RESPONSE"
                result = "FAIL"
            results.append({
                "Method": http_method, "Endpoint": combined_url, "Status": status, "Result": result,
            })

        if api.get("Performance?"):
            path, locust_csv_path = api_utils.Apicore().makeperformancecall(api, "Swegger")
            if path:
                performance_result.append(path)

    status_text.markdown(f"**Completed {total} / {total} APIs**")
    progress_bar.progress(1.0)

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

            def color_rows(row):
                return [
                    "background-color: #c8f7c5" if row["Result"] == "PASS"
                    else "background-color: #f7c5c5"
                ] * len(row)

            st.dataframe(df.style.apply(color_rows, axis=1), use_container_width=True)
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

        if uploaded_file:
            api_list = swagger_utils.read_excel_input(uploaded_file)
            st.session_state.api_data = api_list
            st.success("API file uploaded successfully")
            st.dataframe(pd.DataFrame(api_list), use_container_width=True)

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
                    base_url = swagger_utils.get_base_url(api_details, spec)
                    api_list = swagger_utils.build_data_dictionary(api_details, base_url, spec)

                    for idx, api in enumerate(api_list):
                        api["Validate?"] = True
                        api["Performance?"] = False
                        api["__id__"] = f"{api['httpMethod']}_{api['endpoint']}_{idx}"

                    st.session_state.swagger_apis = api_list
                    st.success(f"Loaded {len(api_list)} APIs from Swagger")
                except Exception as e:
                    st.error(f"Failed to load Swagger APIs: {e}")

        # ---- API selection grid ----
        if st.session_state.swagger_apis:
            st.markdown("**API Selection**")
            header = st.columns([4, 2, 2, 4])
            header[0].markdown("**Endpoint**")
            header[1].markdown("**Validate**")
            header[2].markdown("**Performance**")
            header[3].markdown("**Payload (POST/PUT)**")

            for api in st.session_state.swagger_apis:
                cols = st.columns([4, 2, 2, 4])
                cols[0].write(f"{api['httpMethod']} {api['endpoint']}")

                validate_key = f"swagger_validate_{api['__id__']}"
                perf_key = f"swagger_perf_{api['__id__']}"
                payload_key = f"swagger_payload_{api['__id__']}"

                if validate_key not in st.session_state:
                    st.session_state[validate_key] = api["Validate?"]
                if perf_key not in st.session_state:
                    st.session_state[perf_key] = api["Performance?"]
                if payload_key not in st.session_state:
                    if api["httpMethod"] in ["POST", "PUT"]:
                        sample_payload = api['payload']
                        st.session_state[payload_key] = sample_payload
                        api["payload"] = sample_payload
                    else:
                        st.session_state[payload_key] = {}

                api["Validate?"] = cols[1].checkbox("", key=validate_key)
                api["Performance?"] = cols[2].checkbox("", key=perf_key)

                if api["httpMethod"] in ["POST", "PUT"]:
                    updated_payload = cols[3].text_area(
                        "Edit Payload",
                        value=json.dumps(st.session_state[payload_key], indent=2),
                        height=150,
                        key=f"payload_text_{api['__id__']}",
                    )
                    try:
                        api["payload"] = json.loads(updated_payload)
                        st.session_state[payload_key] = api["payload"]
                    except Exception as e:
                        st.warning(f"Invalid JSON payload: {e}")

            if st.button("▶️ Run Selected Swagger APIs", type="primary"):
                _run_swagger()
                st.success("Swagger APIs completed")

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
