import json
import re
from io import BytesIO

import docx2txt
import pandas as pd
import PyPDF2


def read_requirements_file(uploaded_file) -> str:
    """
    Read an uploaded Streamlit file (Word / PDF / Excel / TXT) and return its text.
    """
    filename = uploaded_file.name.lower()
    content = uploaded_file.read()

    if filename.endswith(".docx"):
        return docx2txt.process(BytesIO(content))

    if filename.endswith(".pdf"):
        reader = PyPDF2.PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(BytesIO(content))
        return df.to_string(index=False)

    # TXT or any other format
    return content.decode("utf-8", errors="ignore")


_BATCH_SIZE = 25   # KPIs per LLM call — keeps output well within token budget
_MAX_TOKENS  = 8000


def _build_prompt(requirements_text: str, schema_section: str, kpi_lines: str) -> str:
    return f"""You are a SQL expert helping to validate a Power BI report against its database.

Requirements Document:
{requirements_text}
{schema_section}

KPIs extracted from the Power BI report UI:
{kpi_lines}

Task:
For each KPI listed above, write a SQL SELECT query that retrieves the SAME value
shown in the Power BI report. Each query must return a SINGLE scalar value so it
can be compared directly to the UI value.

Return ONLY a valid JSON array with no markdown code fences and no extra text.
Each element must have these exact keys:
  - "kpi_name"    : exact KPI name from the list
  - "visual_name" : the visual name from the list
  - "ui_value"    : the UI value from the list
  - "sql_query"   : a SQL SELECT statement returning one scalar value
  - "description" : one sentence explaining what the query measures

Example output (do not include this line):
[{{"kpi_name":"Total Revenue","visual_name":"Revenue Card","ui_value":"$1.2M",
  "sql_query":"SELECT SUM(amount) FROM sales WHERE YEAR(date)=2024",
  "description":"Total sales amount for the current year"}}]

Return ONLY the JSON array."""


def _call_llm(prompt: str, client) -> list:
    """Call LLM and parse JSON, with clear error messages on failure."""
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=_MAX_TOKENS,   # max_tokens works on this Azure endpoint;
        timeout=600,              # max_completion_tokens silently returns empty
    )

    raw = response.choices[0].message.content or ""

    if not raw.strip():
        finish = response.choices[0].finish_reason
        raise ValueError(
            f"LLM returned an empty response (finish_reason='{finish}'). "
            "The KPI batch may still be too large. Try reducing _BATCH_SIZE in sql_generator.py."
        )

    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$",          "", raw)
    raw = raw.strip()

    if not raw:
        raise ValueError(
            "LLM returned only empty code fences with no JSON content inside. "
            "Check that the requirements document loaded correctly."
        )

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Response may have been truncated — try to salvage complete objects
        last_obj = raw.rfind("},")
        if last_obj > 0:
            try:
                return json.loads("[" + raw.lstrip("[")[:last_obj + 1] + "]")
            except json.JSONDecodeError:
                pass
        raise ValueError(
            f"LLM response was not valid JSON.\n"
            f"finish_reason: {response.choices[0].finish_reason}\n"
            f"First 400 chars of raw response: {raw[:400]}"
        )


def generate_sql_for_kpis(kpi_list: list, requirements_text: str,
                           db_schema: str, client) -> list:
    """
    Use LLM to generate a SQL query for each KPI extracted from PBI.
    KPIs are processed in batches of _BATCH_SIZE to stay within token limits.

    kpi_list  : list of dicts with keys visual_name, kpi_name, value, value_type
    returns   : list of dicts with keys kpi_name, visual_name, ui_value,
                sql_query, description
    """
    schema_section = (
        f"\nDatabase Schema (for reference):\n{db_schema.strip()}"
        if db_schema and db_schema.strip()
        else ""
    )

    all_results: list = []

    for batch_start in range(0, len(kpi_list), _BATCH_SIZE):
        batch = kpi_list[batch_start: batch_start + _BATCH_SIZE]

        kpi_lines = "\n".join(
            f"  - KPI: \"{item['kpi_name']}\" | "
            f"Visual: \"{item.get('visual_name', 'N/A')}\" | "
            f"UI Value: \"{item.get('value', '')}\""
            for item in batch
        )

        prompt = _build_prompt(requirements_text, schema_section, kpi_lines)
        batch_results = _call_llm(prompt, client)
        all_results.extend(batch_results)

    return all_results
