"""
Engine 2 — LLM vision comparison of two Power BI screenshots.

Two modes:

  two_pass  (default, more reliable)
      Pass A — inventory each screenshot SEPARATELY into structured JSON
               (title, chart type, grid position, bbox %, key text, values).
      Pass B — diff the two inventories as TEXT.
      Models read a single image well but compare coordinates across two
      images badly, so turning the visual task into a text task materially
      improves accuracy.

  one_shot
      Both images in a single call. Fewer tokens, faster, less reliable on
      layout; useful as a cross-check.

Findings use the same schema as utils.visual_diff so the two engines merge
into one report.
"""
from __future__ import annotations

import base64
import io
import json
import re

from PIL import Image

VALID_CATEGORIES = (
    "missing_visual", "extra_visual", "position_change", "size_change",
    "chart_type_change", "title_text_change", "value_change",
    "color_theme_change", "slicer_selection_change", "slicer_position_change",
    "legend_axis_change", "render_error", "truncation", "visual_count_change",
    "canvas_size_change", "other",
)
VALID_SEVERITIES = ("critical", "major", "minor", "info")

DEFAULT_MODEL = "gpt-5-mini"


# ── Image prep ────────────────────────────────────────────────────────────────
def _downscale_b64(img_bytes: bytes, max_dim: int = 1600) -> tuple:
    """Resize so the long edge is <= max_dim, return (b64, (w, h), (ow, oh))."""
    pil = Image.open(io.BytesIO(img_bytes))
    if pil.mode != "RGB":
        pil = pil.convert("RGB")
    ow, oh = pil.size
    if max(ow, oh) > max_dim:
        scale = max_dim / max(ow, oh)
        pil = pil.resize((int(ow * scale), int(oh * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    pil.save(buf, format="PNG", optimize=True)
    return (base64.b64encode(buf.getvalue()).decode("utf-8"),
            pil.size, (ow, oh))


def _img_block(b64: str) -> dict:
    return {"type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}",
                          "detail": "high"}}


# ── LLM plumbing ──────────────────────────────────────────────────────────────
def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _call_json(client, model: str, content: list, max_tokens: int = 8000,
               retries: int = 1) -> dict:
    """Chat completion that must return a JSON object. Retries once on parse error."""
    last_err = None
    msgs = [{"role": "user", "content": content}]
    for attempt in range(retries + 1):
        resp = client.chat.completions.create(
            model=model, messages=msgs, max_tokens=max_tokens, timeout=600)
        raw = _strip_fences(resp.choices[0].message.content or "")
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            return {"_list": data}
        except Exception as exc:
            last_err = exc
            # Feed the bad output back and insist on plain JSON.
            msgs = [
                {"role": "user", "content": content},
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content":
                    "That was not valid JSON. Return ONLY the JSON object, "
                    "no prose and no markdown fences."},
            ]
    raise ValueError(f"LLM did not return valid JSON: {last_err}")


# ── Prompts ───────────────────────────────────────────────────────────────────
_INVENTORY_PROMPT = """You are a Power BI report layout analyst.

Inventory EVERY element visible on this Power BI report screenshot.

Return ONLY a JSON object:
{
  "page_title": "<report/page title if visible, else ''>",
  "visuals": [
    {
      "id": 1,
      "title": "<visual title exactly as shown, '' if none>",
      "type": "card|kpi|bar_chart|column_chart|line_chart|area_chart|pie_chart|donut_chart|scatter|table|matrix|map|gauge|funnel|treemap|slicer|filter_pane|text_box|image|shape|other",
      "grid": "row <n>, col <n>",
      "bbox_pct": {"x": <0-100>, "y": <0-100>, "w": <0-100>, "h": <0-100>},
      "key_text": ["<axis labels, legend entries, column headers, captions>"],
      "displayed_values": ["<every number/metric shown, exactly as displayed>"],
      "dominant_colors": ["<plain colour names of the data series>"],
      "selected_values": "<for slicers only: currently selected value(s); '' otherwise>",
      "state": "rendered|empty|error"
    }
  ]
}

Rules:
- bbox_pct is the element's position/size as a PERCENTAGE of the whole image.
- Order visuals top-to-bottom, then left-to-right.
- Include slicers, filter panes, text boxes, logos and images as visuals.
- state='empty' if the visual shows no data; 'error' if it shows a Power BI
  error or "No data available" message.
- Copy numbers EXACTLY as displayed, including $ , % K M suffixes.
- Return ONLY the JSON object, no markdown fences, no commentary."""


_DIFF_PROMPT = """You are validating a Power BI report MIGRATION (platform A to
platform B). The report is supposed to be IDENTICAL after migration — the data
source moved, but NOTHING about the UI should change.

Below are two structured inventories of the same report page, extracted from
screenshots taken BEFORE (source) and AFTER (target) the migration.

Compare them and report every difference. Because no UI change is expected,
ANY genuine difference is a finding.

Match visuals across the two inventories by title first, then type, then
position. Do NOT assume the `id` numbers correspond.

Return ONLY a JSON object:
{
  "page_verdict": "PASS|PASS_WITH_WARNINGS|FAIL",
  "summary": "<2-3 sentence plain-English summary for a QA report>",
  "visual_count_source": <int>,
  "visual_count_target": <int>,
  "findings": [
    {
      "visual_name": "<visual title, or a description if untitled>",
      "category": "missing_visual|extra_visual|position_change|size_change|chart_type_change|title_text_change|value_change|color_theme_change|slicer_selection_change|slicer_position_change|legend_axis_change|render_error|truncation|visual_count_change|other",
      "severity": "critical|major|minor|info",
      "source_state": "<what the source shows>",
      "target_state": "<what the target shows>",
      "description": "<what changed and why it matters>",
      "recommendation": "<what the QA engineer should check>"
    }
  ]
}

Severity guidance:
- critical : a visual is missing, added, or shows an error/empty state
- major    : chart type changed, a visual clearly moved or resized, displayed
             values differ, a slicer's selection differs
- minor    : small position/size differences (<2% of canvas), colour shade
             differences, minor text/caption differences
- info     : cosmetic observations that are almost certainly capture noise

CRITICAL RULE ABOUT bbox_pct — READ CAREFULLY:
The bbox_pct values in these inventories were ESTIMATED BY EYE from screenshots
and are only accurate to about ±5 percentage points. They are NOT measurements.
Therefore:
- Do NOT raise a 'position_change' or 'size_change' finding merely because the
  bbox_pct numbers differ. They almost always differ slightly by estimation
  noise alone.
- Only report 'position_change' if the visual's `grid` cell changed AND the
  bbox x or y differs by more than 8 percentage points.
- Only report 'size_change' if the bbox w or h differs by more than 10
  percentage points.
- If a visual moved only because a neighbouring visual was added or removed,
  report the added/removed visual and do NOT also report the neighbour as
  moved.
- When in doubt about geometry, say nothing. A separate pixel-accurate engine
  measures geometry; your value here is semantic (chart types, titles, text,
  values, colours, error states), not coordinates.

Other rules:
- IGNORE screenshot-capture artefacts (mouse cursor, tooltip, focus ring,
  scrollbar position).
- Treat a changed NUMBER as category 'value_change' — a data issue, not a
  layout issue — and say so in the description.
- verdict FAIL if any critical or major finding exists; PASS_WITH_WARNINGS if
  only minor; PASS if none.
- Return ONLY the JSON object, no markdown fences.

SOURCE INVENTORY (before migration):
{src_json}

TARGET INVENTORY (after migration):
{tgt_json}"""


_ONE_SHOT_PROMPT = """You are validating a Power BI report MIGRATION (platform A
to platform B). The report should look IDENTICAL after migration — only the
data source moved, so NOTHING about the UI should change.

You have been given two screenshots:
  IMAGE 1 = SOURCE (before migration)
  IMAGE 2 = TARGET (after migration)

Compare them thoroughly and report every difference: missing or added visuals,
visuals that moved or were resized, chart types that changed, titles/labels that
changed or were truncated, displayed values that differ, colour/theme changes,
slicer selections that differ, and any visual showing an error or empty state.

Also check the position and selected values of every slicer.

Return ONLY a JSON object:
{
  "page_verdict": "PASS|PASS_WITH_WARNINGS|FAIL",
  "summary": "<2-3 sentence plain-English summary for a QA report>",
  "visual_count_source": <int>,
  "visual_count_target": <int>,
  "findings": [
    {
      "visual_name": "<visual title, or a description if untitled>",
      "category": "missing_visual|extra_visual|position_change|size_change|chart_type_change|title_text_change|value_change|color_theme_change|slicer_selection_change|slicer_position_change|legend_axis_change|render_error|truncation|visual_count_change|other",
      "severity": "critical|major|minor|info",
      "source_state": "<what IMAGE 1 shows>",
      "target_state": "<what IMAGE 2 shows>",
      "description": "<what changed and why it matters>",
      "recommendation": "<what the QA engineer should check>"
    }
  ]
}

Severity guidance:
- critical : a visual is missing, added, or shows an error/empty state
- major    : chart type changed, a visual clearly moved or resized, displayed
             values differ, a slicer's selection differs
- minor    : small position/size differences, colour shade differences, minor
             text differences
- info     : cosmetic observations that are almost certainly capture noise

Rules:
- IGNORE screenshot-capture artefacts (mouse cursor, tooltip, focus ring,
  scrollbar position).
- Treat a changed NUMBER as 'value_change' — a data issue, not a layout issue.
- Only report 'position_change' or 'size_change' when the shift is large and
  obvious to the eye — roughly a tenth of the canvas or more. You cannot
  measure pixels reliably, and a separate pixel-accurate engine handles
  geometry; your value here is semantic (chart types, titles, text, values,
  colours, error states).
- If a visual appears to have moved only because a neighbouring visual was
  added or removed, report the added/removed visual and not the neighbour.
- If nothing changed, return an empty findings array and verdict PASS.
- Return ONLY the JSON object, no markdown fences."""


# ── Normalisation ─────────────────────────────────────────────────────────────
def _normalise_findings(raw_findings: list) -> list:
    out = []
    for i, f in enumerate(raw_findings or [], 1):
        if not isinstance(f, dict):
            continue
        cat = str(f.get("category", "other")).strip().lower()
        if cat not in VALID_CATEGORIES:
            cat = "other"
        sev = str(f.get("severity", "minor")).strip().lower()
        if sev not in VALID_SEVERITIES:
            sev = "minor"
        out.append({
            "engine": "llm",
            "visual_id": f"L{i:02d}",
            "visual_name": str(f.get("visual_name", "") or "")[:80],
            "category": cat,
            "severity": sev,
            "check": "LLM visual comparison",
            "source_state": str(f.get("source_state", "") or "")[:300],
            "target_state": str(f.get("target_state", "") or "")[:300],
            "metric": "LLM judgement",
            "description": str(f.get("description", "") or "")[:800],
            "recommendation": str(f.get("recommendation", "") or "")[:400],
        })
    return out


def _inventory_table(inv: dict, side: str) -> list:
    rows = []
    for v in (inv.get("visuals") or []):
        bb = v.get("bbox_pct") or {}
        rows.append({
            "Side": side,
            "ID": v.get("id"),
            "Title": str(v.get("title", "") or "(untitled)")[:50],
            "Type": v.get("type", ""),
            "Grid": v.get("grid", ""),
            "x%": bb.get("x"), "y%": bb.get("y"),
            "w%": bb.get("w"), "h%": bb.get("h"),
            "State": v.get("state", ""),
            "Selected": str(v.get("selected_values", "") or "")[:60],
            "Values": ", ".join(str(x) for x in (v.get("displayed_values") or []))[:80],
            "Colors": ", ".join(str(x) for x in (v.get("dominant_colors") or []))[:40],
        })
    return rows


# ── Public entry point ────────────────────────────────────────────────────────
def compare_screenshots_llm(src_bytes: bytes, tgt_bytes: bytes, client,
                            model: str = DEFAULT_MODEL,
                            mode: str = "two_pass",
                            max_dim: int = 1600,
                            progress=None) -> dict:
    """
    Compare two PBI screenshots with an LLM.

    mode      "two_pass" (inventory each, then diff as text) or "one_shot"
    progress  optional callable(str) for UI status updates

    Returns the same result shape as utils.visual_diff.compare_screenshots:
    verdict, findings[], page_metrics, warnings[], plus 'summary' and
    'inventory_table' when two_pass was used.
    """
    def say(msg):
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    warnings: list[str] = []
    s_b64, s_size, s_orig = _downscale_b64(src_bytes, max_dim)
    t_b64, t_size, t_orig = _downscale_b64(tgt_bytes, max_dim)

    if s_orig != t_orig:
        warnings.append(
            f"Source ({s_orig[0]}×{s_orig[1]}) and target ({t_orig[0]}×"
            f"{t_orig[1]}) screenshots have different dimensions — the LLM was "
            "told to ignore capture artefacts, but re-capturing both at the "
            "same resolution gives cleaner results.")

    page_metrics = {
        "Engine mode": mode,
        "Model": model,
        "Source size": f"{s_orig[0]}×{s_orig[1]} px (sent {s_size[0]}×{s_size[1]})",
        "Target size": f"{t_orig[0]}×{t_orig[1]} px (sent {t_size[0]}×{t_size[1]})",
    }
    inventory_table: list = []
    summary = ""

    if mode == "one_shot":
        say("Comparing both screenshots in a single LLM call…")
        # Label each image in its own text block — models reliably confuse
        # which image is which when both are dumped in without labels.
        content = [
            {"type": "text", "text": "IMAGE 1 = SOURCE (before migration):"},
            _img_block(s_b64),
            {"type": "text", "text": "IMAGE 2 = TARGET (after migration):"},
            _img_block(t_b64),
            {"type": "text", "text": _ONE_SHOT_PROMPT},
        ]
        data = _call_json(client, model, content)

    else:
        say("Pass A · inventorying the SOURCE screenshot…")
        src_inv = _call_json(client, model, [
            {"type": "text", "text": "This is the SOURCE Power BI report "
                                     "screenshot (before migration)."},
            _img_block(s_b64),
            {"type": "text", "text": _INVENTORY_PROMPT},
        ])

        say("Pass A · inventorying the TARGET screenshot…")
        tgt_inv = _call_json(client, model, [
            {"type": "text", "text": "This is the TARGET Power BI report "
                                     "screenshot (after migration)."},
            _img_block(t_b64),
            {"type": "text", "text": _INVENTORY_PROMPT},
        ])

        inventory_table = (_inventory_table(src_inv, "SOURCE")
                           + _inventory_table(tgt_inv, "TARGET"))
        page_metrics["Visuals (source)"] = len(src_inv.get("visuals") or [])
        page_metrics["Visuals (target)"] = len(tgt_inv.get("visuals") or [])

        say("Pass B · diffing the two inventories…")
        prompt = (_DIFF_PROMPT
                  .replace("{src_json}", json.dumps(src_inv, indent=1)[:24000])
                  .replace("{tgt_json}", json.dumps(tgt_inv, indent=1)[:24000]))
        data = _call_json(client, model,
                          [{"type": "text", "text": prompt}], max_tokens=8000)

    findings = _normalise_findings(data.get("findings"))
    summary = str(data.get("summary", "") or "")

    if "visual_count_source" in data:
        page_metrics.setdefault("Visuals (source)", data.get("visual_count_source"))
        page_metrics.setdefault("Visuals (target)", data.get("visual_count_target"))

    # Trust our own severity rules over the model's page_verdict.
    from utils.visual_diff import SEVERITY_RANK
    worst = max((SEVERITY_RANK[f["severity"]] for f in findings), default=0)
    verdict = ("FAIL" if worst >= 2
               else "PASS_WITH_WARNINGS" if worst >= 1 else "PASS")
    model_verdict = str(data.get("page_verdict", "") or "").upper()
    if model_verdict and model_verdict != verdict:
        warnings.append(
            f"The model reported page verdict {model_verdict}; recomputed "
            f"{verdict} from the individual finding severities.")

    sev_counts = {k: 0 for k in ("info", "minor", "major", "critical")}
    for f in findings:
        sev_counts[f["severity"]] += 1

    return {
        "engine": "llm",
        "verdict": verdict,
        "summary": summary,
        "severity_counts": sev_counts,
        "page_metrics": page_metrics,
        "findings": findings,
        "visual_table": [],
        "inventory_table": inventory_table,
        "warnings": warnings,
        "artifacts": {},
    }
