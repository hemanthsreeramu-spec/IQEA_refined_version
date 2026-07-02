import re
from io import BytesIO

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# ── Value normalisation ────────────────────────────────────────────────────────

def normalize_value(raw):
    """
    Convert a display string to a float so two values can be compared numerically.

    Examples:
        "$1.2M"   → 1_200_000.0
        "94.3%"   → 94.3
        "1,234"   → 1_234.0
        "12.5K"   → 12_500.0
        "3.1B"    → 3_100_000_000.0
        "N/A"     → None
    """
    if raw is None:
        return None

    s = str(raw).strip()

    # Remove currency symbols
    s = re.sub(r"[$€£¥₹]", "", s)
    # Remove commas and spaces
    s = s.replace(",", "").replace(" ", "")

    is_pct = s.endswith("%")
    s = s.rstrip("%")

    multiplier = 1
    upper = s.upper()
    if upper.endswith("B"):
        multiplier = 1_000_000_000
        s = s[:-1]
    elif upper.endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]
    elif upper.endswith("K"):
        multiplier = 1_000
        s = s[:-1]

    try:
        return float(s) * multiplier
    except (ValueError, TypeError):
        return None


# ── Comparison ─────────────────────────────────────────────────────────────────

def compare_values(ui_value: str, db_value, tolerance_pct: float = 0.1) -> tuple:
    """
    Compare a UI display value against the DB result.

    Returns (status, reason) where status is "PASS", "FAIL", or "ERROR".
    tolerance_pct is the acceptable percentage difference (default 0.1 %).
    """
    if db_value is None:
        return "FAIL", "DB query returned no result"

    ui_norm = normalize_value(ui_value)
    db_norm = normalize_value(db_value)

    # ── String comparison when neither side parses as a number ──────────────
    if ui_norm is None and db_norm is None:
        if str(ui_value).strip().lower() == str(db_value).strip().lower():
            return "PASS", "Exact text match"
        return "FAIL", f"Text mismatch — UI: '{ui_value}'  DB: '{db_value}'"

    if ui_norm is None:
        return "ERROR", f"Cannot parse UI value '{ui_value}' as a number"

    if db_norm is None:
        return "ERROR", f"Cannot parse DB value '{db_value}' as a number"

    # ── Both zero ────────────────────────────────────────────────────────────
    if ui_norm == 0 and db_norm == 0:
        return "PASS", "Both values are zero"

    if ui_norm == 0:
        return "FAIL", f"UI value is 0 but DB returned {db_norm}"

    diff_pct = abs(ui_norm - db_norm) / abs(ui_norm) * 100

    if diff_pct <= tolerance_pct:
        return "PASS", f"Within {tolerance_pct}% tolerance (diff = {diff_pct:.4f}%)"

    return (
        "FAIL",
        f"Diff {diff_pct:.2f}% exceeds {tolerance_pct}% tolerance  "
        f"(UI ≈ {ui_norm:,.2f}  |  DB ≈ {db_norm:,.2f})"
    )


# ── Report helpers ─────────────────────────────────────────────────────────────

def build_validation_df(results: list) -> pd.DataFrame:
    """
    Build a tidy DataFrame from the list of validation result dicts.
    Each dict must have: visual_name, kpi_name, ui_value, sql_query,
                         db_value, status, reason
    """
    rows = [
        {
            "Visual Name": r.get("visual_name", ""),
            "KPI Name":    r.get("kpi_name", ""),
            "UI Value":    r.get("ui_value", ""),
            "SQL Query":   r.get("sql_query", ""),
            "DB Value":    r.get("db_value", ""),
            "Status":      r.get("status", ""),
            "Reason":      r.get("reason", ""),
        }
        for r in results
    ]
    return pd.DataFrame(rows)


def export_to_excel(df: pd.DataFrame) -> bytes:
    """
    Render the validation DataFrame to an in-memory Excel workbook with
    colour-coded rows (green = PASS, red = FAIL, yellow = ERROR).
    Returns the raw bytes ready for st.download_button.
    """
    output = BytesIO()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PBI Validation Report"

    # ── Styles ────────────────────────────────────────────────────────────
    header_fill  = PatternFill("solid", fgColor="E8650A")
    header_font  = Font(bold=True, color="FFFFFF", size=11)
    pass_fill    = PatternFill("solid", fgColor="C6EFCE")
    fail_fill    = PatternFill("solid", fgColor="FFC7CE")
    error_fill   = PatternFill("solid", fgColor="FFEB9C")
    thin         = Side(style="thin")
    border       = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap_center  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    wrap_top     = Alignment(wrap_text=True, vertical="top")

    # ── Header row ────────────────────────────────────────────────────────
    for col_idx, col_name in enumerate(df.columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill      = header_fill
        cell.font      = header_font
        cell.alignment = wrap_center
        cell.border    = border

    # ── Data rows ─────────────────────────────────────────────────────────
    for row_idx, row in enumerate(df.itertuples(index=False), 2):
        status   = str(getattr(row, "Status", ""))
        row_fill = pass_fill if status == "PASS" else (
                   fail_fill if status == "FAIL" else error_fill)

        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx,
                           value=str(value) if value is not None else "")
            cell.fill      = row_fill
            cell.alignment = wrap_top
            cell.border    = border

    # ── Column widths ─────────────────────────────────────────────────────
    target_widths = [22, 28, 14, 60, 14, 10, 45]
    for i, w in enumerate(target_widths, 1):
        if i <= ws.max_column:
            ws.column_dimensions[get_column_letter(i)].width = w

    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"

    wb.save(output)
    return output.getvalue()
