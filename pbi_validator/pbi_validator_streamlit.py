import os
import sys
import time

import openai
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# ── Path setup so sibling utilities are importable ────────────────────────────
_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
for _p in (_THIS_DIR, _PARENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

load_dotenv(os.path.join(_PARENT_DIR, ".env"))

from utils.pbi_browser   import (extract_kpis_via_llm, is_driver_alive,
                                  start_browser, take_screenshot,
                                  try_show_as_table)
from utils.sql_generator  import generate_sql_for_kpis, read_requirements_file
from utils.db_connector   import build_connection_string, execute_query, test_connection
from utils.comparator     import (build_validation_df, compare_values,
                                  export_to_excel)

# ── Output folder ─────────────────────────────────────────────────────────────
_OUTPUT_DIR = os.path.join(_THIS_DIR, "output", "reports")
os.makedirs(_OUTPUT_DIR, exist_ok=True)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="PBI Validator", page_icon="📊", layout="wide")

# ── Session state defaults ────────────────────────────────────────────────────
_DEFAULTS = {
    "pbi_driver":             None,
    "pbi_extracted_kpis":     [],
    "pbi_screenshot_b64":     None,
    "pbi_screenshot_bytes":   None,
    "pbi_sql_mapping":        [],
    "pbi_validation_results": [],
    "pbi_conn_string":        "",
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── LLM factory ───────────────────────────────────────────────────────────────
def _get_llm():
    return openai.OpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        base_url=os.getenv("AZURE_OPENAI_ENDPOINT"),
    )


# ── Shared styles ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
.pbi-header {
    padding: 20px 0 14px 0;
}
.pbi-header h1 {
    font-size: 30px;
    font-weight: 900;
    color: #1B2A4A;
    margin-bottom: 4px;
}
.pbi-header p {
    font-size: 15px;
    color: #666;
    font-weight: 500;
    margin: 0;
}
.step-badge {
    display: inline-block;
    background: #F47B20;
    color: white;
    border-radius: 50%;
    width: 28px;
    height: 28px;
    line-height: 28px;
    text-align: center;
    font-weight: 800;
    font-size: 14px;
    margin-right: 8px;
}
.section-title {
    font-size: 18px;
    font-weight: 700;
    color: #1B2A4A;
    margin: 16px 0 8px 0;
}
.info-box {
    background: #FFF8F3;
    border-left: 4px solid #F47B20;
    padding: 10px 14px;
    border-radius: 4px;
    font-size: 14px;
    color: #444;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="pbi-header">
    <h1>📊 PBI Data Validator</h1>
    <p>Extract KPIs from Power BI UI &nbsp;→&nbsp; Generate SQL from Requirements
       &nbsp;→&nbsp; Validate UI vs Database</p>
    <hr style="border:2px solid #F47B20; width:60px; margin:10px 0 0 0;">
</div>
""", unsafe_allow_html=True)


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "🌐  Step 1 · Extract KPIs",
    "🧠  Step 2 · Generate SQL",
    "✅  Step 3 · Validate",
])


# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — EXTRACT KPIs
# ════════════════════════════════════════════════════════════════════════════════
with tab1:
    # ── Load KPIs from a previous session ─────────────────────────────────────
    with st.expander("📂 Load KPIs from a previous extraction", expanded=False):
        st.caption("Upload a CSV saved from an earlier session to skip re-extraction.")
        prev_kpi_file = st.file_uploader(
            "KPI CSV file",
            type=["csv"],
            key="pbi_prev_kpi_file",
            label_visibility="collapsed",
        )
        if prev_kpi_file is not None:
            try:
                df_prev = pd.read_csv(prev_kpi_file)
                st.dataframe(df_prev, use_container_width=True, height=180)
                if st.button("✅ Use this data", type="primary", key="pbi_load_prev_kpis_btn"):
                    st.session_state.pbi_extracted_kpis = df_prev.to_dict("records")
                    st.success(f"✅ Loaded {len(df_prev)} KPIs from file.")
                    st.rerun()
            except Exception as exc:
                st.error(f"Could not read file: {exc}")

    st.markdown('<p class="section-title">1 · Open Power BI Report</p>', unsafe_allow_html=True)

    col_url, col_btn = st.columns([4, 1])
    with col_url:
        pbi_url = st.text_input(
            "Power BI Report URL",
            placeholder="https://app.powerbi.com/reportEmbed?reportId=...",
            label_visibility="collapsed",
            key="pbi_url_input",
        )
    with col_btn:
        open_btn = st.button("🌐 Open Browser", use_container_width=True)

    if open_btn:
        if not pbi_url:
            st.warning("Please enter a Power BI report URL first.")
        else:
            with st.spinner("Launching Chrome..."):
                try:
                    if st.session_state.pbi_driver and is_driver_alive(st.session_state.pbi_driver):
                        st.session_state.pbi_driver.quit()
                    st.session_state.pbi_driver = start_browser(pbi_url)
                    st.success(
                        "✅ Browser is open. **Log into Power BI** in the browser window, "
                        "navigate to the report page you want to validate, then come back here."
                    )
                except Exception as exc:
                    st.error(f"Could not open browser: {exc}")

    # Show status badge
    if st.session_state.pbi_driver and is_driver_alive(st.session_state.pbi_driver):
        st.markdown(
            '<div class="info-box">🟢 Browser is active. '
            'Make sure the report is fully loaded before extracting.</div>',
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown('<p class="section-title">2 · Extract KPIs from Current View</p>',
                    unsafe_allow_html=True)

        extraction_mode = st.radio(
            "Extraction method",
            [
                "📸  Screenshot + LLM  (best for KPI cards & trend tiles)",
                "📋  Show as Table  (best for charts, bar graphs, tables)",
            ],
            horizontal=True,
            key="pbi_extraction_mode",
        )

        col_ext, col_ss = st.columns(2)
        with col_ext:
            extract_btn = st.button(
                "🔍 Extract KPIs Now", type="primary",
                use_container_width=True, key="pbi_extract_btn"
            )
        with col_ss:
            screenshot_btn = st.button(
                "📷 Refresh Screenshot Only",
                use_container_width=True, key="pbi_ss_btn"
            )

        if screenshot_btn:
            try:
                png, b64 = take_screenshot(st.session_state.pbi_driver)
                st.session_state.pbi_screenshot_b64   = b64
                st.session_state.pbi_screenshot_bytes = png
                st.rerun()
            except Exception as exc:
                st.error(f"Screenshot failed: {exc}")

        if extract_btn:
            try:
                with st.spinner("Taking screenshot..."):
                    png, b64 = take_screenshot(st.session_state.pbi_driver)
                    st.session_state.pbi_screenshot_b64   = b64
                    st.session_state.pbi_screenshot_bytes = png

                kpis = []

                if "Show as Table" in extraction_mode:
                    with st.spinner("Extracting tables from each visual (opens Focus Mode per visual)..."):
                        table_results = try_show_as_table(st.session_state.pbi_driver)

                    if table_results:
                        seen_kpi_names = set()  # dedup guard — skip KPIs already collected

                        for tbl in table_results:
                            cols           = tbl.get("headers") or tbl.get("columns", [])
                            rows           = tbl.get("rows", [])
                            visual_name    = tbl.get("visual_title", "Table")
                            has_row_header = tbl.get("has_row_header", True)

                            for row in rows:
                                if not row:
                                    continue

                                if has_row_header and len(cols) > 1:
                                    # Chart table: col[0] = dimension label, col[1..] = metrics
                                    # row[0] = dimension value (e.g. "Africa"), row[1..] = values
                                    row_id = row[0] if row else ""
                                    for col_idx in range(1, len(cols)):
                                        if col_idx < len(row) and row[col_idx]:
                                            kpi_name = f"{cols[col_idx]} [{row_id}]"
                                            if kpi_name not in seen_kpi_names:
                                                seen_kpi_names.add(kpi_name)
                                                kpis.append({
                                                    "visual_name": visual_name,
                                                    "kpi_name":    kpi_name,
                                                    "value":       row[col_idx],
                                                    "value_type":  "number",
                                                })

                                elif not has_row_header and cols:
                                    # Pure-metric table (KPI cards): every column IS a metric
                                    # row[0] aligns with cols[0] — no offset, no shift
                                    for col_idx in range(len(cols)):
                                        if col_idx < len(row) and row[col_idx]:
                                            kpi_name = cols[col_idx]
                                            if kpi_name not in seen_kpi_names:
                                                seen_kpi_names.add(kpi_name)
                                                kpis.append({
                                                    "visual_name": visual_name,
                                                    "kpi_name":    kpi_name,
                                                    "value":       row[col_idx],
                                                    "value_type":  "number",
                                                })

                                else:
                                    # Single-column or fallback
                                    kpi_name = cols[0] if cols else "Value"
                                    if kpi_name not in seen_kpi_names:
                                        seen_kpi_names.add(kpi_name)
                                        kpis.append({
                                            "visual_name": visual_name,
                                            "kpi_name":    kpi_name,
                                            "value":       row[0] if row else "",
                                            "value_type":  "number",
                                        })

                        st.success(f"✅ Extracted {len(kpis)} KPIs from visual tables.")
                    else:
                        st.info("No 'Show as table' option found — falling back to Screenshot + LLM.")
                        with st.spinner("LLM reading KPIs from screenshot..."):
                            kpis = extract_kpis_via_llm(b64, _get_llm())
                        st.success(f"✅ LLM extracted {len(kpis)} KPIs from screenshot.")

                else:
                    with st.spinner("LLM reading KPIs from screenshot (this may take ~15 s)..."):
                        kpis = extract_kpis_via_llm(b64, _get_llm())
                    st.success(f"✅ LLM extracted {len(kpis)} KPIs from screenshot.")

                st.session_state.pbi_extracted_kpis = kpis
                st.rerun()

            except Exception as exc:
                st.error(f"Extraction failed: {exc}")

        # Show screenshot preview
        if st.session_state.pbi_screenshot_bytes:
            with st.expander("📷 Current Screenshot", expanded=False):
                st.image(st.session_state.pbi_screenshot_bytes, use_container_width=True)

        # Show / edit extracted KPIs
        if st.session_state.pbi_extracted_kpis:
            st.markdown("---")
            st.markdown(
                f'<p class="section-title">3 · Review Extracted KPIs '
                f'({len(st.session_state.pbi_extracted_kpis)} found)</p>',
                unsafe_allow_html=True,
            )
            st.caption("Edit, add, or delete rows before proceeding to SQL generation.")

            edited_df = st.data_editor(
                pd.DataFrame(st.session_state.pbi_extracted_kpis),
                num_rows="dynamic",
                use_container_width=True,
                key="pbi_kpi_editor",
            )

            col_save, col_clear, col_dl, _ = st.columns([1, 1, 1, 1])
            with col_save:
                if st.button("💾 Save & Proceed →", type="primary",
                             use_container_width=True, key="pbi_save_kpis"):
                    st.session_state.pbi_extracted_kpis = edited_df.to_dict("records")
                    st.success("✅ KPIs saved. Head to **Step 2** to generate SQL.")
            with col_clear:
                if st.button("🗑️ Clear All", use_container_width=True, key="pbi_clear_kpis"):
                    st.session_state.pbi_extracted_kpis = []
                    st.rerun()
            with col_dl:
                csv_bytes = pd.DataFrame(
                    st.session_state.pbi_extracted_kpis
                ).to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Save as CSV",
                    data=csv_bytes,
                    file_name="kpi_extraction.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="pbi_dl_kpis",
                )

    else:
        st.markdown(
            '<div class="info-box">Enter a Power BI report URL above and click '
            '<strong>Open Browser</strong> to get started.</div>',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — GENERATE SQL
# ════════════════════════════════════════════════════════════════════════════════
with tab2:
    # ── Load SQL mapping from a previous session — always visible ─────────────
    with st.expander("📂 Load SQL mapping from a previous session", expanded=False):
        st.caption("Upload a SQL mapping CSV saved from an earlier session to skip re-generation.")
        prev_sql_file = st.file_uploader(
            "SQL mapping CSV file",
            type=["csv"],
            key="pbi_prev_sql_file",
            label_visibility="collapsed",
        )
        if prev_sql_file is not None:
            try:
                df_sql_prev = pd.read_csv(prev_sql_file)
                st.dataframe(df_sql_prev, use_container_width=True, height=180)
                if st.button("✅ Use this mapping", type="primary", key="pbi_load_prev_sql_btn"):
                    st.session_state.pbi_sql_mapping = df_sql_prev.to_dict("records")
                    st.success(f"✅ Loaded {len(df_sql_prev)} SQL queries from file.")
                    st.rerun()
            except Exception as exc:
                st.error(f"Could not read file: {exc}")

    # ── SQL generation — only when KPIs are in session ────────────────────────
    if not st.session_state.pbi_extracted_kpis:
        if not st.session_state.pbi_sql_mapping:
            st.markdown(
                '<div class="info-box">⚠️ No KPIs extracted yet. '
                'Complete <strong>Step 1</strong> or load a previous SQL mapping above.</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f'<p class="section-title">'
            f'{len(st.session_state.pbi_extracted_kpis)} KPIs ready for SQL generation'
            f'</p>',
            unsafe_allow_html=True,
        )

        with st.expander("📋 Extracted KPIs (read-only preview)", expanded=False):
            st.dataframe(
                pd.DataFrame(st.session_state.pbi_extracted_kpis),
                use_container_width=True,
            )

        st.markdown("---")
        st.markdown('<p class="section-title">Upload Requirements Document</p>',
                    unsafe_allow_html=True)

        col_file, col_text = st.columns(2)
        with col_file:
            uploaded_req = st.file_uploader(
                "Requirements file (Word / PDF / Excel / TXT)",
                type=["docx", "pdf", "xlsx", "xls", "txt"],
                key="pbi_req_upload",
            )
        with col_text:
            manual_req = st.text_area(
                "Or paste requirements directly",
                height=160,
                placeholder=(
                    "Describe the KPIs, their business logic, and which tables/columns "
                    "they come from…"
                ),
                key="pbi_manual_req",
            )

        st.markdown('<p class="section-title">Database Schema (optional but recommended)</p>',
                    unsafe_allow_html=True)
        db_schema_text = st.text_area(
            "Paste relevant table and column definitions",
            height=110,
            placeholder="e.g.  sales(id, amount, date, region_id)  |  products(id, name, price)",
            key="pbi_db_schema",
        )

        st.markdown("---")
        gen_btn = st.button("🧠 Generate SQL Queries", type="primary", key="pbi_gen_sql")

        if gen_btn:
            requirements_text = ""
            if uploaded_req:
                with st.spinner("Reading requirements document..."):
                    try:
                        requirements_text = read_requirements_file(uploaded_req)
                    except Exception as exc:
                        st.error(f"Could not read file: {exc}")

            if manual_req and manual_req.strip():
                requirements_text += "\n" + manual_req

            if not requirements_text.strip():
                st.warning("Please upload a requirements file or paste requirements text.")
            else:
                with st.spinner("LLM generating SQL — this may take ~20 s…"):
                    try:
                        sql_mapping = generate_sql_for_kpis(
                            st.session_state.pbi_extracted_kpis,
                            requirements_text,
                            db_schema_text or "",
                            _get_llm(),
                        )
                        st.session_state.pbi_sql_mapping = sql_mapping
                        st.success(f"✅ SQL generated for {len(sql_mapping)} KPIs.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"SQL generation failed: {exc}")

    # ── SQL mapping editor — visible whenever mapping is in session ───────────
    if st.session_state.pbi_sql_mapping:
        st.markdown("---")
        st.markdown(
            f'<p class="section-title">Review & Edit SQL Mapping '
            f'({len(st.session_state.pbi_sql_mapping)} queries)</p>',
            unsafe_allow_html=True,
        )
        st.caption("Each query must return exactly ONE value. Edit directly in the table below.")

        edited_sql = st.data_editor(
            pd.DataFrame(st.session_state.pbi_sql_mapping),
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "sql_query":   st.column_config.TextColumn("SQL Query",   width="large"),
                "description": st.column_config.TextColumn("Description", width="medium"),
                "ui_value":    st.column_config.TextColumn("UI Value",    width="small"),
            },
            key="pbi_sql_editor",
        )

        col_save_sql, col_dl_sql, _ = st.columns([1, 1, 3])
        with col_save_sql:
            if st.button("💾 Save SQL Mapping", type="primary",
                         use_container_width=True, key="pbi_save_sql"):
                st.session_state.pbi_sql_mapping = edited_sql.to_dict("records")
                st.success("✅ SQL mapping saved. Head to **Step 3** to run validation.")
        with col_dl_sql:
            sql_csv_bytes = pd.DataFrame(
                st.session_state.pbi_sql_mapping
            ).to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Save as CSV",
                data=sql_csv_bytes,
                file_name="sql_mapping.csv",
                mime="text/csv",
                use_container_width=True,
                key="pbi_dl_sql",
            )


# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — VALIDATE
# ════════════════════════════════════════════════════════════════════════════════
with tab3:
    if not st.session_state.pbi_sql_mapping:
        st.markdown(
            '<div class="info-box">⚠️ No SQL mapping found. '
            'Complete <strong>Steps 1 &amp; 2</strong> first.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<p class="section-title">Database Connection</p>',
                    unsafe_allow_html=True)

        col_db1, col_db2, col_db3 = st.columns(3)
        with col_db1:
            db_type = st.selectbox(
                "DB Type",
                ["postgresql", "mysql", "mssql", "sqlite", "databricks"],
                key="pbi_db_type",
            )

        is_databricks = db_type == "databricks"

        with col_db1:
            if is_databricks:
                db_host = st.text_input(
                    "Server Hostname",
                    placeholder="adb-1234567890.7.azuredatabricks.net",
                    key="pbi_db_host",
                )
            else:
                db_host = st.text_input("Host", value="localhost", key="pbi_db_host")
                db_port = st.text_input("Port", value="5432",      key="pbi_db_port")

        with col_db2:
            if is_databricks:
                db_http_path = st.text_input(
                    "HTTP Path",
                    placeholder="/sql/1.0/warehouses/abc123...",
                    key="pbi_db_http_path",
                )
                db_pass = st.text_input(
                    "Access Token",
                    type="password",
                    placeholder="dapi...",
                    key="pbi_db_pass",
                )
                db_catalog = st.text_input(
                    "Catalog (optional)",
                    placeholder="hive_metastore",
                    key="pbi_db_catalog",
                )
                db_schema  = st.text_input(
                    "Schema (optional)",
                    placeholder="default",
                    key="pbi_db_schema_name",
                )
                # unused for databricks but keep variables defined
                db_name = ""
                db_user = ""
                db_port = ""
            else:
                db_name = st.text_input("Database Name", key="pbi_db_name")
                db_user = st.text_input("Username",      key="pbi_db_user")
                db_pass = st.text_input("Password", type="password", key="pbi_db_pass")
                db_http_path = ""
                db_catalog   = ""
                db_schema    = ""

        with col_db3:
            tolerance = st.number_input(
                "Tolerance (%)",
                min_value=0.0, max_value=10.0, value=0.1, step=0.05,
                help="Max acceptable % difference between UI and DB value.",
                key="pbi_tolerance",
            )
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔌 Test Connection", use_container_width=True, key="pbi_test_conn"):
                conn_str = build_connection_string(
                    db_type, db_host, db_port, db_name, db_user, db_pass,
                    http_path=db_http_path, catalog=db_catalog, schema=db_schema,
                )
                ok, msg = test_connection(conn_str)
                if ok:
                    st.session_state.pbi_conn_string = conn_str
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")

        st.markdown("---")
        st.markdown(
            f'<p class="section-title">'
            f'Ready to validate {len(st.session_state.pbi_sql_mapping)} KPIs'
            f'</p>',
            unsafe_allow_html=True,
        )

        run_btn = st.button("▶️ Run Validation", type="primary", key="pbi_run_val")

        if run_btn:
            # Build connection string from current form values if not already stored
            if not st.session_state.pbi_conn_string:
                st.session_state.pbi_conn_string = build_connection_string(
                    db_type, db_host, db_port, db_name, db_user, db_pass,
                    http_path=db_http_path, catalog=db_catalog, schema=db_schema,
                )

            total   = len(st.session_state.pbi_sql_mapping)
            results = []
            progress_bar = st.progress(0)
            status_txt   = st.empty()

            for i, item in enumerate(st.session_state.pbi_sql_mapping):
                kpi_name = item.get("kpi_name", f"KPI_{i+1}")
                ui_val   = item.get("ui_value", "")
                sql      = item.get("sql_query", "").strip()

                status_txt.text(f"Validating {i + 1}/{total}: {kpi_name}")

                if not sql:
                    results.append({
                        **item,
                        "db_value": "",
                        "status":   "ERROR",
                        "reason":   "No SQL query defined",
                    })
                else:
                    ok, db_val, err = execute_query(st.session_state.pbi_conn_string, sql)
                    if not ok:
                        results.append({
                            **item,
                            "db_value": "",
                            "status":   "ERROR",
                            "reason":   err,
                        })
                    else:
                        status, reason = compare_values(
                            ui_val, db_val, tolerance_pct=tolerance
                        )
                        results.append({
                            **item,
                            "db_value": str(db_val) if db_val is not None else "",
                            "status":   status,
                            "reason":   reason,
                        })

                progress_bar.progress((i + 1) / total)

            st.session_state.pbi_validation_results = results
            progress_bar.empty()
            status_txt.text("Validation complete!")
            time.sleep(0.5)
            status_txt.empty()
            st.rerun()

        # ── Results ────────────────────────────────────────────────────────────
        if st.session_state.pbi_validation_results:
            results = st.session_state.pbi_validation_results
            total   = len(results)
            passed  = sum(1 for r in results if r["status"] == "PASS")
            failed  = sum(1 for r in results if r["status"] == "FAIL")
            errors  = sum(1 for r in results if r["status"] == "ERROR")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total KPIs",  total)
            m2.metric("✅ Passed",    passed)
            m3.metric("❌ Failed",    failed)
            m4.metric("⚠️ Errors",   errors)

            st.markdown("---")
            st.markdown('<p class="section-title">Validation Results</p>',
                        unsafe_allow_html=True)

            df_results = build_validation_df(results)

            def _row_color(row):
                s = row["Status"]
                color = (
                    "#C6EFCE" if s == "PASS" else
                    "#FFC7CE" if s == "FAIL" else
                    "#FFEB9C"
                )
                return [f"background-color: {color}"] * len(row)

            st.dataframe(
                df_results.style.apply(_row_color, axis=1),
                use_container_width=True,
                height=420,
            )

            st.markdown("---")
            col_dl, col_clear_res, _ = st.columns([1, 1, 3])
            with col_dl:
                excel_bytes = export_to_excel(df_results)
                st.download_button(
                    "📥 Download Excel Report",
                    data=excel_bytes,
                    file_name="pbi_validation_report.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet"
                    ),
                    type="primary",
                    key="pbi_download",
                )
            with col_clear_res:
                if st.button("🔄 Clear Results", use_container_width=True,
                             key="pbi_clear_results"):
                    st.session_state.pbi_validation_results = []
                    st.rerun()
