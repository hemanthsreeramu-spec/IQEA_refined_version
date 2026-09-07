"""
Engine 1 — deterministic visual comparison of two Power BI screenshots.

Compares a SOURCE (pre-migration) and TARGET (post-migration) screenshot and
reports, per visual, what changed: position, size, structure, colour, text,
chart shape, render failures and slicer selections.

Pipeline
    0. Normalise      — RGB, optional chrome crop, common canvas size
    1. Register       — phaseCorrelate (sub-pixel) / ORB + partial affine
    2. Segment        — Canny → morph-close → contours → NMS  ⇒ visual boxes
    3. Match          — IoU + centroid + size + pHash cost, Hungarian assignment
    4. Per-visual     — 11 checks (see _check_pair)
    5. Page-level     — counts, global SSIM, layout drift
    6. Artefacts      — side-by-side, annotated target, SSIM heatmap, crops

Libraries
    opencv      registration, segmentation, histograms, edge maps, templates
    scikit-image SSIM score + localised diff map
    imagehash   pHash/dHash/colourhash for region identity
    scipy       linear_sum_assignment (optimal 1:1 pairing)
    pytesseract OCR text/number diffing (optional — degrades gracefully)
    numpy/PIL   array maths, I/O, annotation
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import cv2
import imagehash
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import linear_sum_assignment
from skimage.metrics import structural_similarity as _ssim

# ── Optional OCR ──────────────────────────────────────────────────────────────
try:
    import pytesseract
    _PYTESSERACT_IMPORTED = True
except Exception:                                     # pragma: no cover
    _PYTESSERACT_IMPORTED = False

_OCR_PROBE: bool | None = None


def ocr_available() -> bool:
    """True only if pytesseract AND the Tesseract binary are both usable."""
    global _OCR_PROBE
    if _OCR_PROBE is None:
        if not _PYTESSERACT_IMPORTED:
            _OCR_PROBE = False
        else:
            try:
                # Honour [OCR] tesseract_cmd — in the container the binary is at
                # /usr/bin/tesseract rather than wherever PATH would find it.
                try:
                    from config.settings_reader import get_tesseract_cmd
                    _cmd = get_tesseract_cmd()
                    if _cmd:
                        pytesseract.pytesseract.tesseract_cmd = _cmd
                except Exception:
                    pass
                pytesseract.get_tesseract_version()
                _OCR_PROBE = True
            except Exception:
                _OCR_PROBE = False
    return _OCR_PROBE


# ── Severity ordering ─────────────────────────────────────────────────────────
SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "critical": 3}

_ERROR_PHRASES = (
    "no data available", "can't display this visual", "cant display this visual",
    "couldn't load", "couldnt load", "error loading", "see details",
    "something went wrong", "this visual has an error", "unable to load",
    "query has exceeded", "resource exceeded", "license required",
)


# ── Options ───────────────────────────────────────────────────────────────────
@dataclass
class DiffOptions:
    """Tolerances and switches. Every threshold the UI exposes lives here."""

    # geometry (px, measured on the normalised source canvas)
    pos_tol_px: float = 6.0
    pos_warn_px: float = 15.0
    size_tol_px: float = 6.0
    size_warn_px: float = 15.0

    # structural similarity
    ssim_pass: float = 0.95
    ssim_warn: float = 0.90

    # raw pixel difference (fraction of pixels beyond channel tolerance)
    pixel_channel_tol: int = 24
    pixel_diff_pass: float = 0.02
    pixel_diff_warn: float = 0.05

    # perceptual hash Hamming distance (0..64)
    phash_pass: int = 5
    phash_warn: int = 10

    # colour histogram correlation (1.0 == identical)
    hist_pass: float = 0.95
    hist_warn: float = 0.85

    # Canny edge-map IoU — edges land on the same pixels once registered, so
    # identical visuals score ~1.0 and a chart-type change drops sharply
    edge_pass: float = 0.70
    edge_warn: float = 0.50

    # blank / render-failure detection
    blank_std: float = 3.0

    # segmentation
    min_region_area_frac: float = 0.004
    max_region_area_frac: float = 0.70
    morph_kernel: int = 25
    rectangularity: float = 0.80
    max_regions: int = 60

    # matching
    match_cost_cutoff: float = 0.75

    # OCR
    enable_ocr: bool = True

    # chrome crop, as fractions of height/width
    crop_top: float = 0.0
    crop_bottom: float = 0.0
    crop_left: float = 0.0
    crop_right: float = 0.0

    # rects to blank out before any metric runs: (x, y, w, h) on source canvas
    ignore_regions: list = field(default_factory=list)

    # treat "major" findings as a page FAIL (migration = expect zero UI change)
    fail_on_major: bool = True


# ══════════════════════════════════════════════════════════════════════════════
# Step 0 — load & normalise
# ══════════════════════════════════════════════════════════════════════════════
def _to_rgb(img_bytes: bytes) -> np.ndarray:
    """Decode bytes → (H, W, 3) uint8 RGB. Alpha is composited onto white."""
    pil = Image.open(io.BytesIO(img_bytes))
    if pil.mode in ("RGBA", "LA", "P"):
        pil = pil.convert("RGBA")
        bg = Image.new("RGBA", pil.size, (255, 255, 255, 255))
        pil = Image.alpha_composite(bg, pil)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


def _crop(rgb: np.ndarray, o: DiffOptions) -> np.ndarray:
    h, w = rgb.shape[:2]
    t, b = int(h * o.crop_top), h - int(h * o.crop_bottom)
    l, r = int(w * o.crop_left), w - int(w * o.crop_right)
    if b - t < 32 or r - l < 32:            # refuse to crop away the report
        return rgb
    return rgb[t:b, l:r]


def _normalise(src: np.ndarray, tgt: np.ndarray, o: DiffOptions) -> tuple:
    """
    Crop chrome, then bring the target onto the source canvas size.

    Returns (src, tgt, notes) where notes are page-level findings about the
    capture itself — a resolution or aspect change is a finding in its own
    right because it means the two screenshots were not taken alike.
    """
    notes: list[dict] = []
    src, tgt = _crop(src, o), _crop(tgt, o)

    sh, sw = src.shape[:2]
    th, tw = tgt.shape[:2]

    if (sh, sw) != (th, tw):
        src_ar, tgt_ar = sw / sh, tw / th
        aspect_delta = abs(src_ar - tgt_ar) / src_ar
        notes.append({
            "category": "canvas_size_change",
            "severity": "major" if aspect_delta > 0.02 else "info",
            "check": "Canvas dimensions",
            "source_state": f"{sw}×{sh} px",
            "target_state": f"{tw}×{th} px",
            "metric": f"scale {tw / sw:.3f}× / {th / sh:.3f}×, "
                      f"aspect delta {aspect_delta * 100:.1f}%",
            "description": (
                "Source and target screenshots have different dimensions. "
                "The target was rescaled onto the source canvas before "
                "comparison; residual geometry findings may be capture noise "
                "rather than real migration defects."
                + (" Aspect ratio also changed, so the report canvas itself "
                   "is a different shape." if aspect_delta > 0.02 else "")
            ),
            "recommendation": (
                "Re-capture both screenshots on the same browser, window size "
                "and zoom level for px-accurate results."
            ),
        })
        tgt = cv2.resize(tgt, (sw, sh), interpolation=cv2.INTER_AREA)

    for (x, y, w, h) in (o.ignore_regions or []):
        x, y = max(0, int(x)), max(0, int(y))
        w, h = int(w), int(h)
        src[y:y + h, x:x + w] = 255
        tgt[y:y + h, x:x + w] = 255

    return src, tgt, notes


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — registration
# ══════════════════════════════════════════════════════════════════════════════
def _gray(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def _align(src: np.ndarray, tgt: np.ndarray) -> tuple:
    """
    Warp target onto source so a few px of global capture offset is not
    reported as "every visual moved".

    Returns (aligned_tgt, info) with info = {method, dx, dy, response}.
    """
    gs, gt = _gray(src), _gray(tgt)
    h, w = gs.shape

    # ── phaseCorrelate: sub-pixel pure translation, uses the whole image ──
    try:
        win = cv2.createHanningWindow((w, h), cv2.CV_32F)
        (dx, dy), response = cv2.phaseCorrelate(
            gs.astype(np.float32), gt.astype(np.float32), win)
    except Exception:
        dx = dy = 0.0
        response = 0.0

    if response > 0.10 and (abs(dx) > 0.3 or abs(dy) > 0.3) \
            and abs(dx) < w * 0.10 and abs(dy) < h * 0.10:
        # phaseCorrelate reports the shift OF target RELATIVE TO source, so
        # undo it with the negated translation.
        M = np.float32([[1, 0, -dx], [0, 1, -dy]])
        aligned = cv2.warpAffine(tgt, M, (w, h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
        return aligned, {"method": "phase_correlate", "dx": float(dx),
                         "dy": float(dy), "response": float(response)}

    if response > 0.10:                              # already aligned
        return tgt, {"method": "none", "dx": float(dx), "dy": float(dy),
                     "response": float(response)}

    # ── ORB + partial affine: handles translation + rotation + uniform scale ──
    # estimateAffinePartial2D (4 DOF) is deliberate: findHomography's 8 DOF
    # would fit a perspective warp to noisy chart features and distort things.
    try:
        orb = cv2.ORB_create(nfeatures=4000)
        k1, d1 = orb.detectAndCompute(gs, None)
        k2, d2 = orb.detectAndCompute(gt, None)
        if d1 is None or d2 is None or len(k1) < 12 or len(k2) < 12:
            raise ValueError("insufficient keypoints")
        matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
        matches = sorted(matches, key=lambda m: m.distance)[:600]
        if len(matches) < 12:
            raise ValueError("insufficient matches")
        p_src = np.float32([k1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        p_tgt = np.float32([k2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        # RANSAC discards genuinely-changed regions as outliers — align on what
        # is the same, then measure what is not.
        M, inl = cv2.estimateAffinePartial2D(p_tgt, p_src, method=cv2.RANSAC,
                                             ransacReprojThreshold=3.0)
        if M is None:
            raise ValueError("affine estimation failed")
        aligned = cv2.warpAffine(tgt, M, (w, h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
        return aligned, {"method": "orb_affine",
                         "dx": float(M[0, 2]), "dy": float(M[1, 2]),
                         "response": float(inl.mean()) if inl is not None else 0.0}
    except Exception:
        return tgt, {"method": "failed", "dx": 0.0, "dy": 0.0,
                     "response": float(response)}


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — segmentation into visual boxes
# ══════════════════════════════════════════════════════════════════════════════
def _nms_nested(boxes: list[dict]) -> list[dict]:
    """
    Keep only outermost boxes. PBI wraps a visual in several containers and a
    chart's own bars/columns also contour separately, so the same card is
    detected several times over — always keep the enclosing card and drop what
    sits inside it. Page/canvas wrappers are excluded earlier by area, not here.
    """
    def contains(a, b, pad=6):
        return (a["x"] - pad <= b["x"] and a["y"] - pad <= b["y"]
                and a["x"] + a["w"] + pad >= b["x"] + b["w"]
                and a["y"] + a["h"] + pad >= b["y"] + b["h"])

    return [b for b in boxes
            if not any(o is not b and contains(o, b)
                       and o["w"] * o["h"] > b["w"] * b["h"] for o in boxes)]


def _iou(a: dict, b: dict) -> float:
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union else 0.0


def _bg_color(rgb: np.ndarray) -> np.ndarray:
    """Modal colour of a downscaled copy — i.e. the report canvas background."""
    small = cv2.resize(rgb, (160, 90), interpolation=cv2.INTER_AREA)
    q = (small.reshape(-1, 3) // 16).astype(np.int32)
    codes = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    vals, counts = np.unique(codes, return_counts=True)
    c = int(vals[counts.argmax()])
    return np.array([(c // 256) * 16 + 8, ((c % 256) // 16) * 16 + 8,
                     (c % 16) * 16 + 8], dtype=np.int16)


def _candidate_masks(rgb: np.ndarray) -> list[tuple]:
    """
    Binary masks to contour, in preference order. Background-difference is the
    primary strategy for dashboards (white cards on a grey canvas separate
    cleanly); Canny and adaptive threshold cover low-contrast and dark themes.
    """
    gray = _gray(rgb)
    bg = _bg_color(rgb)
    diff = np.abs(rgb.astype(np.int16) - bg[None, None, :]).sum(axis=2)
    return [
        ("bgdiff", ((diff > 20).astype(np.uint8) * 255)),
        ("bgdiff_loose", ((diff > 8).astype(np.uint8) * 255)),
        ("canny", cv2.Canny(gray, 30, 110)),
        ("adaptive", cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                           cv2.THRESH_BINARY_INV, 25, 8)),
    ]


def _boxes_from_mask(mask: np.ndarray, kernel: int, o: DiffOptions,
                     shape: tuple) -> list[dict]:
    h, w = shape[:2]
    canvas = h * w
    kern = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel, kernel))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kern)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        if area < canvas * o.min_region_area_frac:
            continue
        if area > canvas * o.max_region_area_frac:
            continue
        if bw < 24 or bh < 24:
            continue
        found.append({"x": x, "y": y, "w": bw, "h": bh})
    return _nms_nested(found)


def _detect_regions(rgb: np.ndarray, o: DiffOptions) -> list[dict]:
    """
    mask → morph-close → contours → area filter → outermost-NMS ⇒ visual boxes.

    Several (mask, kernel) strategies are tried and scored by total canvas
    coverage. Coverage is the right selector because a card always covers more
    area than the sum of the bars inside it, so the strategy that resolves
    whole cards wins over one that fragments into chart elements.
    """
    h, w = rgb.shape[:2]
    canvas = h * w

    best: list[dict] = []
    best_score = -1.0
    for _name, mask in _candidate_masks(rgb):
        for kernel in (o.morph_kernel, max(9, o.morph_kernel // 2)):
            found = _boxes_from_mask(mask, kernel, o, rgb.shape)
            if not (2 <= len(found) <= o.max_regions):
                continue
            coverage = sum(b["w"] * b["h"] for b in found) / canvas
            if coverage > 0.95:            # everything merged into one slab
                continue
            if coverage > best_score:
                best_score, best = coverage, found

    candidates = best

    # reading order: top-to-bottom, then left-to-right within a band
    band = max(24, h // 24)
    candidates.sort(key=lambda b: (b["y"] // band, b["x"]))
    for i, b in enumerate(candidates, 1):
        b["id"] = i
    return candidates


def _grid_regions(shape: tuple, cols: int = 4, rows: int = 3) -> list[dict]:
    """Fallback tiling so localisation still works when segmentation fails."""
    h, w = shape[:2]
    cw, ch = w // cols, h // rows
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append({"id": len(out) + 1, "x": c * cw, "y": r * ch,
                        "w": cw, "h": ch, "grid": True})
    return out


def _is_slicer_like(box: dict, shape: tuple) -> bool:
    """Narrow/short controls at the canvas edge behave like slicers."""
    h, w = shape[:2]
    narrow = box["w"] < 0.22 * w
    short = box["h"] < 0.18 * h
    tall_thin = box["h"] > 1.2 * box["w"] and narrow
    return (narrow and short) or tall_thin


# ══════════════════════════════════════════════════════════════════════════════
# Region features & metrics
# ══════════════════════════════════════════════════════════════════════════════
def _sub(rgb: np.ndarray, box: dict) -> np.ndarray:
    y2 = min(rgb.shape[0], box["y"] + box["h"])
    x2 = min(rgb.shape[1], box["x"] + box["w"])
    return rgb[max(0, box["y"]):y2, max(0, box["x"]):x2]


def _hashes(region: np.ndarray) -> dict:
    pil = Image.fromarray(region)
    return {"phash": imagehash.phash(pil),
            "dhash": imagehash.dhash(pil),
            "chash": imagehash.colorhash(pil)}


def _common_size(a: np.ndarray, b: np.ndarray) -> tuple:
    """Resize both crops to a common box so SSIM/pixel maths is defined."""
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    h, w = max(h, 8), max(w, 8)
    return (cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA),
            cv2.resize(b, (w, h), interpolation=cv2.INTER_AREA))


def _ssim_pair(a: np.ndarray, b: np.ndarray) -> tuple:
    """SSIM score + diff map. win_size is clamped to fit tiny slicer crops."""
    a, b = _common_size(a, b)
    win = min(7, a.shape[0], a.shape[1])
    if win % 2 == 0:
        win -= 1
    if win < 3:
        return 1.0, np.zeros(a.shape[:2], dtype=np.float32)
    score, diff = _ssim(a, b, channel_axis=2, full=True,
                        win_size=win, data_range=255)
    return float(score), diff.mean(axis=2).astype(np.float32)


def _pixel_diff_ratio(a: np.ndarray, b: np.ndarray, tol: int) -> float:
    """Fraction of pixels differing beyond `tol` on any channel."""
    a, b = _common_size(a, b)
    # int cast is essential: uint8 subtraction wraps (5-10 → 251).
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    return float((d > tol).mean())


def _ink_mask(rgb: np.ndarray) -> np.ndarray:
    """Pixels that are not the region's own background — the chart's 'ink'."""
    bg = _bg_color(rgb)
    diff = np.abs(rgb.astype(np.int16) - bg[None, None, :]).sum(axis=2)
    return (diff > 40).astype(np.uint8) * 255


def _hist_scores(a: np.ndarray, b: np.ndarray) -> tuple:
    """
    HSV hue+saturation histogram compare, restricted to non-background pixels.

    HSV not RGB on purpose: it separates hue from brightness, so anti-aliasing
    and gamma noise barely move the score while a real palette change shifts it
    sharply. Masking to 'ink' is equally deliberate — a full-region histogram is
    dominated by the white card background, which hides a recoloured thin line
    or a small series entirely.
    """
    ha = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
    hb = cv2.cvtColor(b, cv2.COLOR_RGB2HSV)
    ma, mb = _ink_mask(a), _ink_mask(b)
    # Fall back to the whole region if either side has almost no ink.
    if ma.sum() < 255 * 40 or mb.sum() < 255 * 40:
        ma = mb = None
    h1 = cv2.calcHist([ha], [0, 1], ma, [36, 32], [0, 180, 0, 256])
    h2 = cv2.calcHist([hb], [0, 1], mb, [36, 32], [0, 180, 0, 256])
    cv2.normalize(h1, h1, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(h2, h2, 0, 1, cv2.NORM_MINMAX)
    return (float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)),
            float(cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA)))


def _edge_iou(a: np.ndarray, b: np.ndarray) -> float:
    """Canny edge-map overlap — catches bar→line even at identical palette."""
    a, b = _common_size(a, b)
    ea = cv2.Canny(_gray(a), 60, 160) > 0
    eb = cv2.Canny(_gray(b), 60, 160) > 0
    union = np.logical_or(ea, eb).sum()
    if union == 0:
        return 1.0
    return float(np.logical_and(ea, eb).sum() / union)


def _is_blank(region: np.ndarray, o: DiffOptions) -> bool:
    return float(region.std()) < o.blank_std


def _locate_template(full: np.ndarray, patch: np.ndarray) -> tuple:
    """
    Hunt a source crop across the whole target. Turns a vague "missing visual"
    into a precise "moved to (x, y)".
    """
    if patch.shape[0] >= full.shape[0] or patch.shape[1] >= full.shape[1]:
        return 0.0, (0, 0)
    res = cv2.matchTemplate(_gray(full), _gray(patch), cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    return float(maxv), (int(maxloc[0]), int(maxloc[1]))


# ── OCR ───────────────────────────────────────────────────────────────────────
_NUM_RE = re.compile(r"[-+(]?[$€£]?\s?\d[\d,\s]*\.?\d*\s?[%kKmMbB]?\)?")


def _ocr(region: np.ndarray, psm: int = 6) -> dict:
    """
    image_to_data (not image_to_string) so we get per-word boxes + confidence:
    lets us drop OCR garbage, spot truncation, and tell a title change from an
    axis-label change by where the word sits.
    """
    if not ocr_available():
        return {"text": "", "words": [], "ok": False}
    try:
        up = cv2.resize(region, None, fx=2.0, fy=2.0,
                        interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(up, cv2.COLOR_RGB2GRAY)
        df = pytesseract.image_to_data(
            gray, config=f"--psm {psm}",
            output_type=pytesseract.Output.DATAFRAME)
        df = df[(df.conf.astype(float) > 60) & df.text.notna()]
        words = [{"text": str(t).strip(), "conf": float(c),
                  "x": int(x), "y": int(y)}
                 for t, c, x, y in zip(df.text, df.conf, df.left, df.top)
                 if str(t).strip()]
        return {"text": " ".join(wd["text"] for wd in words),
                "words": words, "ok": True}
    except Exception:
        return {"text": "", "words": [], "ok": False}


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _tokens(s: str) -> tuple:
    """Split OCR text into (word_tokens, numeric_tokens)."""
    nums = [m.group(0).strip() for m in _NUM_RE.finditer(s)]
    words = [t for t in re.findall(r"[a-z][a-z'&/\-]*", s.lower()) if len(t) > 1]
    return words, nums


def _title_of(ocr: dict) -> str:
    """First OCR line = the visual title, near enough for report labelling."""
    if not ocr.get("words"):
        return ""
    top = min(w["y"] for w in ocr["words"])
    line = [w["text"] for w in sorted(ocr["words"], key=lambda w: w["x"])
            if w["y"] - top < 24]
    return re.sub(r"\s+", " ", " ".join(line)).strip()[:60]


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — matching
# ══════════════════════════════════════════════════════════════════════════════
def _match(src_boxes: list[dict], tgt_boxes: list[dict],
           src: np.ndarray, tgt: np.ndarray, o: DiffOptions) -> tuple:
    """
    Optimal 1:1 source→target pairing via the Hungarian algorithm.

    Greedy nearest-neighbour is not good enough here: two source visuals can
    both claim the same target, cascading into phantom missing/extra findings.
    linear_sum_assignment guarantees the globally minimum-cost assignment.
    """
    if not src_boxes or not tgt_boxes:
        return [], list(src_boxes), list(tgt_boxes)

    h, w = src.shape[:2]
    diag = float(np.hypot(w, h))

    s_feat = [_hashes(_sub(src, b)) for b in src_boxes]
    t_feat = [_hashes(_sub(tgt, b)) for b in tgt_boxes]

    cost = np.zeros((len(src_boxes), len(tgt_boxes)), dtype=np.float64)
    for i, sb in enumerate(src_boxes):
        sc = (sb["x"] + sb["w"] / 2, sb["y"] + sb["h"] / 2)
        for j, tb in enumerate(tgt_boxes):
            tc = (tb["x"] + tb["w"] / 2, tb["y"] + tb["h"] / 2)
            centroid = np.hypot(sc[0] - tc[0], sc[1] - tc[1]) / diag
            size = (abs(sb["w"] - tb["w"]) + abs(sb["h"] - tb["h"])) / (w + h)
            # pHash keeps all-pairs comparison affordable — SSIM here would be
            # far too slow, ORB slower still.
            phash = (s_feat[i]["phash"] - t_feat[j]["phash"]) / 64.0
            dhash = (s_feat[i]["dhash"] - t_feat[j]["dhash"]) / 64.0
            cost[i, j] = (0.34 * (1 - _iou(sb, tb))
                          + 0.22 * min(1.0, centroid * 3)
                          + 0.14 * min(1.0, size * 6)
                          + 0.20 * phash
                          + 0.10 * dhash)

    rows, cols = linear_sum_assignment(cost)
    pairs, used_s, used_t = [], set(), set()
    for i, j in zip(rows, cols):
        if cost[i, j] <= o.match_cost_cutoff:
            pairs.append({"src": src_boxes[i], "tgt": tgt_boxes[j],
                          "cost": float(cost[i, j]),
                          "phash_dist": int(s_feat[i]["phash"] - t_feat[j]["phash"]),
                          "chash_dist": int(s_feat[i]["chash"] - t_feat[j]["chash"])})
            used_s.add(i)
            used_t.add(j)

    pairs.sort(key=lambda p: p["src"]["id"])
    unmatched_src = [b for i, b in enumerate(src_boxes) if i not in used_s]
    unmatched_tgt = [b for j, b in enumerate(tgt_boxes) if j not in used_t]
    return pairs, unmatched_src, unmatched_tgt


# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — per-visual checks
# ══════════════════════════════════════════════════════════════════════════════
def _sev(value: float, pass_at: float, warn_at: float, higher_is_better: bool,
         warn_sev: str = "minor", fail_sev: str = "major") -> str:
    if higher_is_better:
        if value >= pass_at:
            return "info"
        return warn_sev if value >= warn_at else fail_sev
    if value <= pass_at:
        return "info"
    return warn_sev if value <= warn_at else fail_sev


def _check_pair(pair: dict, src: np.ndarray, tgt: np.ndarray,
                o: DiffOptions, vid: str, name: str) -> tuple:
    """Run every per-visual check. Returns (findings, metrics_row, ssim_map)."""
    sb, tb = pair["src"], pair["tgt"]
    a, b = _sub(src, sb), _sub(tgt, tb)
    findings: list[dict] = []
    m: dict = {"Visual": vid, "Name": name or "(untitled)",
               "Kind": "Slicer" if sb.get("slicer_like") else "Visual"}

    def add(cat, sev, check, s_state, t_state, metric, desc, rec=""):
        if sev == "info":
            return
        findings.append({"visual_id": vid, "visual_name": name, "category": cat,
                         "severity": sev, "check": check,
                         "source_state": s_state, "target_state": t_state,
                         "metric": metric, "description": desc,
                         "recommendation": rec})

    tight = 0.6 if sb.get("slicer_like") else 1.0   # slicers get tighter tolerance

    # ── 1. Position ───────────────────────────────────────────────────────────
    dx, dy = tb["x"] - sb["x"], tb["y"] - sb["y"]
    shift = float(np.hypot(dx, dy))
    m["Δx px"], m["Δy px"], m["Shift px"] = dx, dy, round(shift, 1)
    sev = _sev(shift, o.pos_tol_px * tight, o.pos_warn_px * tight, False)
    add("slicer_position_change" if sb.get("slicer_like") else "position_change",
        sev, "Position",
        f"({sb['x']}, {sb['y']})", f"({tb['x']}, {tb['y']})",
        f"Δx={dx:+d}px, Δy={dy:+d}px (|Δ|={shift:.1f}px)",
        f"Visual moved {shift:.1f}px after migration "
        f"({shift / src.shape[1] * 100:.2f}% of canvas width).",
        "Compare the visual's X/Y in the report layout between the two "
        "workspaces; a migration should not reposition visuals.")

    # ── 2. Size ───────────────────────────────────────────────────────────────
    dw, dh = tb["w"] - sb["w"], tb["h"] - sb["h"]
    resize = float(max(abs(dw), abs(dh)))
    m["Δw px"], m["Δh px"] = dw, dh
    sev = _sev(resize, o.size_tol_px * tight, o.size_warn_px * tight, False)
    add("size_change", sev, "Size",
        f"{sb['w']}×{sb['h']} px", f"{tb['w']}×{tb['h']} px",
        f"Δw={dw:+d}px, Δh={dh:+d}px",
        f"Visual was resized by {dw:+d}×{dh:+d}px.",
        "Check the visual's width/height properties; resizing can also clip "
        "labels or change how many rows a table shows.")

    # ── 10. Render failure (checked early — it explains everything else) ──────
    blank_src, blank_tgt = _is_blank(a, o), _is_blank(b, o)
    m["Blank"] = "Target" if blank_tgt and not blank_src else (
        "Both" if blank_tgt and blank_src else "No")
    if blank_tgt and not blank_src:
        add("render_error", "critical", "Render",
            "rendered", "blank / empty",
            f"target std={b.std():.2f}",
            "Visual is present in the source but renders blank in the target "
            "— it most likely failed to load after migration.",
            "Check the dataset binding, credentials and RLS for this visual "
            "in the target workspace.")

    # ── 4/5/6/7/9. Content metrics ────────────────────────────────────────────
    # These five signals are strongly correlated — one changed chart trips all
    # of them. Compute them all into the metrics table, but emit at most ONE
    # consolidated content finding per visual, classified by whichever signal
    # is most diagnostic. Five findings per visual would bury the real report.
    ssim_score, ssim_map = _ssim_pair(a, b)
    pdr = _pixel_diff_ratio(a, b, o.pixel_channel_tol)
    ph = pair["phash_dist"]
    corr, bhat = _hist_scores(*_common_size(a, b))
    eiou = _edge_iou(a, b)

    m["SSIM"] = round(ssim_score, 4)
    m["Pixel diff %"] = round(pdr * 100, 2)
    m["pHash dist"] = ph
    m["Hue corr"] = round(corr, 4)
    m["Edge IoU"] = round(eiou, 3)

    sev_ssim = _sev(ssim_score, o.ssim_pass, o.ssim_warn, True)
    sev_pdr = _sev(pdr, o.pixel_diff_pass, o.pixel_diff_warn, False)
    sev_ph = _sev(ph, o.phash_pass, o.phash_warn, False)
    sev_hist = _sev(corr, o.hist_pass, o.hist_warn, True)
    sev_edge = _sev(eiou, o.edge_pass, o.edge_warn, True)
    if blank_src or blank_tgt:
        sev_hist = sev_edge = "info"

    worst_content = max(
        (SEVERITY_RANK[s] for s in (sev_ssim, sev_pdr, sev_ph, sev_hist, sev_edge)),
        default=0)

    if worst_content > 0 and not (blank_tgt and not blank_src):
        # localise the change inside the region for a more useful description
        where = ""
        bad = (ssim_map < 0.5)
        if bad.any():
            ys, xs = np.nonzero(bad)
            vy = ys.mean() / max(1, ssim_map.shape[0])
            vx = xs.mean() / max(1, ssim_map.shape[1])
            where = (f" Change concentrated in the "
                     f"{'top' if vy < 0.34 else 'bottom' if vy > 0.66 else 'middle'}-"
                     f"{'left' if vx < 0.34 else 'right' if vx > 0.66 else 'centre'} "
                     f"of the visual.")

        # Classify: edge topology is the strongest chart-type signal; a colour
        # shift with intact edges is a theme change; otherwise generic content.
        if SEVERITY_RANK[sev_edge] >= 2:
            cat, check = "chart_type_change", "Shape / chart structure"
            desc = ("Edge topology differs substantially — the chart type or "
                    "its plotted geometry appears to have changed "
                    "(e.g. bar → line).")
            rec = ("Open both visuals and confirm the visualisation type and "
                   "field wells match.")
        elif SEVERITY_RANK[sev_hist] >= 2 and SEVERITY_RANK[sev_edge] == 0:
            cat, check = "color_theme_change", "Colour / theme"
            desc = ("Colour distribution changed while the shape stayed intact "
                    "— report theme, series palette or a conditional-formatting "
                    "rule may not have carried over.")
            rec = ("Compare the report theme and conditional formatting rules "
                   "on this visual between source and target.")
        else:
            cat, check = "visual_content_change", "Visual content"
            desc = f"Visual content differs from the source.{where}"
            rec = "Inspect the cropped before/after pair in the report artefacts."

        add(cat, ["info", "minor", "major", "critical"][worst_content], check,
            "reference",
            f"SSIM {ssim_score:.4f}, {pdr * 100:.2f}% px differ",
            f"SSIM={ssim_score:.4f} (pass ≥{o.ssim_pass}) · "
            f"pixel_diff={pdr * 100:.2f}% (pass ≤{o.pixel_diff_pass * 100:.0f}%) · "
            f"pHash={ph}/64 (pass ≤{o.phash_pass}) · "
            f"hue_corr={corr:.4f} (pass ≥{o.hist_pass}) · "
            f"bhattacharyya={bhat:.4f} · "
            f"edge_iou={eiou:.3f} (pass ≥{o.edge_pass})",
            desc + where if cat != "visual_content_change" else desc, rec)

    # ── 8. Text content (OCR) + 11. slicer selection ──────────────────────────
    m["Text Δ"] = ""
    m["Numbers Δ"] = ""
    if o.enable_ocr and ocr_available():
        psm = 6 if sb.get("slicer_like") else 11
        oa, ob = _ocr(a, psm), _ocr(b, psm)
        wa, na = _tokens(oa["text"])
        wb, nb = _tokens(ob["text"])

        # words: a UI finding
        if wa or wb:
            ratio = SequenceMatcher(None, wa, wb).ratio()
            gone = [t for t in wa if t not in wb][:6]
            new = [t for t in wb if t not in wa][:6]
            m["Text Δ"] = f"{ratio:.2f}"
            if ratio < 0.98 and (gone or new):
                sev = "major" if ratio < 0.75 else "minor"
                add("slicer_selection_change" if sb.get("slicer_like")
                    else "title_text_change",
                    sev, "Text content (OCR)",
                    " ".join(gone) or "(none)", " ".join(new) or "(none)",
                    f"token similarity={ratio:.2f}",
                    ("Slicer selection or label text changed."
                     if sb.get("slicer_like") else
                     "Visible text changed — a title, legend entry or axis "
                     "label was renamed, truncated or removed."),
                    "Verify field names and captions; a truncated label often "
                    "means the visual was resized.")

        # numbers: a DATA finding, deliberately kept in a separate bucket
        if na or nb:
            nra = SequenceMatcher(None, na, nb).ratio()
            m["Numbers Δ"] = f"{nra:.2f}"
            if nra < 0.98:
                add("value_change", "major", "Displayed values (OCR)",
                    ", ".join(na[:8]) or "(none)",
                    ", ".join(nb[:8]) or "(none)",
                    f"numeric token similarity={nra:.2f}",
                    "Displayed numbers differ. This is a DATA finding, not a "
                    "layout one — the visual renders in the same place but "
                    "shows different values.",
                    "Validate the underlying dataset/measures via Steps 1-3 "
                    "of the PBI Validator rather than treating it as a UI bug.")

        # error text in the target
        low = _norm_text(ob["text"])
        if any(p in low for p in _ERROR_PHRASES):
            add("render_error", "critical", "Render",
                "rendered", ob["text"][:80],
                "error text detected by OCR",
                "The target visual shows a Power BI error/empty-state message.",
                "Check dataset refresh, gateway and permissions in the target "
                "workspace.")

    # ── 3. Overlap with neighbours ────────────────────────────────────────────
    m["Verdict"] = "PASS"
    worst = max((SEVERITY_RANK[f["severity"]] for f in findings), default=0)
    m["Verdict"] = ("FAIL" if worst >= (2 if o.fail_on_major else 3)
                    else "WARN" if worst == 1 else "PASS")
    m["Findings"] = len(findings)
    return findings, m, ssim_map


# ══════════════════════════════════════════════════════════════════════════════
# Artefacts
# ══════════════════════════════════════════════════════════════════════════════
def _font(size: int = 15):
    for path in ("arial.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


_COLOR = {"PASS": (34, 160, 70), "WARN": (240, 160, 20), "FAIL": (214, 40, 40),
          "MISSING": (150, 30, 160), "NEW": (30, 110, 200)}


def _draw_boxes(rgb: np.ndarray, items: list[tuple]) -> bytes:
    """items = [(box, label, status)]"""
    pil = Image.fromarray(rgb.copy())
    d = ImageDraw.Draw(pil)
    f = _font(15)
    for box, label, status in items:
        c = _COLOR.get(status, (120, 120, 120))
        d.rectangle([box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]],
                    outline=c, width=3)
        tw = d.textlength(label, font=f)
        d.rectangle([box["x"], max(0, box["y"] - 20),
                     box["x"] + tw + 10, max(0, box["y"] - 20) + 20], fill=c)
        d.text((box["x"] + 5, max(0, box["y"] - 19)), label, fill="white", font=f)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def _side_by_side(src: np.ndarray, tgt: np.ndarray,
                  s_items: list, t_items: list) -> bytes:
    a = Image.open(io.BytesIO(_draw_boxes(src, s_items)))
    b = Image.open(io.BytesIO(_draw_boxes(tgt, t_items)))
    gap = 14
    out = Image.new("RGB", (a.width + b.width + gap, max(a.height, b.height)),
                    (235, 235, 235))
    out.paste(a, (0, 0))
    out.paste(b, (a.width + gap, 0))
    d = ImageDraw.Draw(out)
    f = _font(20)
    d.text((10, 6), "SOURCE", fill=(20, 20, 20), font=f)
    d.text((a.width + gap + 10, 6), "TARGET", fill=(20, 20, 20), font=f)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def _heatmap(tgt: np.ndarray, ssim_map: np.ndarray) -> bytes:
    """JET-coloured (1 - SSIM) blended over the target."""
    inv = np.clip((1.0 - ssim_map) * 255.0, 0, 255).astype(np.uint8)
    inv = cv2.resize(inv, (tgt.shape[1], tgt.shape[0]))
    heat = cv2.applyColorMap(inv, cv2.COLORMAP_JET)
    heat = cv2.cvtColor(heat, cv2.COLOR_BGR2RGB)
    return _png(cv2.addWeighted(tgt, 0.55, heat, 0.45, 0))


def _crop_pair(src: np.ndarray, tgt: np.ndarray, pair: dict, label: str) -> bytes:
    a = Image.fromarray(_sub(src, pair["src"]))
    b = Image.fromarray(_sub(tgt, pair["tgt"]))
    gap, head = 12, 26
    out = Image.new("RGB", (a.width + b.width + gap,
                            max(a.height, b.height) + head), (245, 245, 245))
    out.paste(a, (0, head))
    out.paste(b, (a.width + gap, head))
    d = ImageDraw.Draw(out)
    f = _font(14)
    d.text((2, 5), f"{label} — SOURCE", fill=(30, 30, 30), font=f)
    d.text((a.width + gap + 2, 5), f"{label} — TARGET", fill=(30, 30, 30), font=f)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════════════════
def compare_screenshots(src_bytes: bytes, tgt_bytes: bytes,
                        options: DiffOptions | None = None) -> dict:
    """
    Compare two PBI screenshots deterministically.

    Returns a dict with: verdict, page_metrics, findings[], visual_table[],
    artifacts{}, warnings[].
    """
    o = options or DiffOptions()
    warnings: list[str] = []

    src0, tgt0 = _to_rgb(src_bytes), _to_rgb(tgt_bytes)
    src, tgt, notes = _normalise(src0, tgt0, o)
    findings: list[dict] = []
    for n in notes:
        findings.append({"visual_id": "PAGE", "visual_name": "Page", **n})

    # ── register ──────────────────────────────────────────────────────────────
    tgt_aligned, align_info = _align(src, tgt)
    if align_info["method"] == "failed":
        warnings.append("Global alignment failed — geometry findings may be "
                        "noisy. Re-capture both screenshots identically.")

    # ── segment ───────────────────────────────────────────────────────────────
    s_boxes = _detect_regions(src, o)
    t_boxes = _detect_regions(tgt_aligned, o)
    if len(s_boxes) < 2 or len(t_boxes) < 2:
        warnings.append(
            f"Visual segmentation found only {len(s_boxes)}/{len(t_boxes)} "
            "region(s) — falling back to a 4×3 grid, so findings are "
            "localised by tile rather than by visual.")
        s_boxes = _grid_regions(src.shape)
        t_boxes = _grid_regions(tgt_aligned.shape)

    for b in s_boxes:
        b["slicer_like"] = _is_slicer_like(b, src.shape)
    for b in t_boxes:
        b["slicer_like"] = _is_slicer_like(b, tgt_aligned.shape)

    # ── match ─────────────────────────────────────────────────────────────────
    pairs, un_src, un_tgt = _match(s_boxes, t_boxes, src, tgt_aligned, o)

    # ── per-visual checks ─────────────────────────────────────────────────────
    visual_table: list[dict] = []
    crops: list[dict] = []
    status_src: dict[int, str] = {}
    status_tgt: dict[int, str] = {}
    names: dict[int, str] = {}
    # region-id → report id, so the annotated images and the findings table use
    # the same label and a user can trace a finding back to the picture
    label_src: dict[int, str] = {}
    label_tgt: dict[int, str] = {}

    for idx, pair in enumerate(pairs, 1):
        vid = f"V{idx:02d}"
        name = ""
        if o.enable_ocr and ocr_available():
            name = _title_of(_ocr(_sub(src, pair["src"]), psm=6))
        names[pair["src"]["id"]] = name
        f_list, row, _ = _check_pair(pair, src, tgt_aligned, o, vid, name)
        findings.extend(f_list)
        visual_table.append(row)
        status_src[pair["src"]["id"]] = row["Verdict"]
        status_tgt[pair["tgt"]["id"]] = row["Verdict"]
        label_src[pair["src"]["id"]] = vid
        label_tgt[pair["tgt"]["id"]] = vid
        if row["Verdict"] != "PASS":
            crops.append({"visual_id": vid, "name": name,
                          "verdict": row["Verdict"],
                          "png": _crop_pair(src, tgt_aligned, pair,
                                            f"{vid} {name}".strip())})

    # ── missing visuals (with template-match rescue) ───────────────────────────
    for k, b in enumerate(un_src, 1):
        vid = f"M{k:02d}"
        name = (_title_of(_ocr(_sub(src, b), psm=6))
                if o.enable_ocr and ocr_available() else "")
        conf, loc = _locate_template(tgt_aligned, _sub(src, b))
        status_src[b["id"]] = "MISSING"
        label_src[b["id"]] = vid
        if conf > 0.90:
            # not gone — relocated. Report precisely instead of vaguely.
            dx, dy = loc[0] - b["x"], loc[1] - b["y"]
            findings.append({
                "visual_id": vid, "visual_name": name,
                "category": "position_change", "severity": "major",
                "check": "Position (template match)",
                "source_state": f"({b['x']}, {b['y']})",
                "target_state": f"({loc[0]}, {loc[1]})",
                "metric": f"template confidence={conf:.3f}, Δ=({dx:+d}, {dy:+d})",
                "description": "Visual was not matched in place but was found "
                               f"elsewhere in the target, moved by "
                               f"({dx:+d}, {dy:+d})px.",
                "recommendation": "Check the report layout ordering/anchoring "
                                  "in the target workspace.",
            })
        else:
            findings.append({
                "visual_id": vid, "visual_name": name,
                "category": "missing_visual", "severity": "critical",
                "check": "Visual inventory",
                "source_state": f"present at ({b['x']}, {b['y']}), "
                                f"{b['w']}×{b['h']} px",
                "target_state": "not found",
                "metric": f"best template confidence={conf:.3f}",
                "description": "A visual present in the source has no "
                               "counterpart anywhere in the target.",
                "recommendation": "Confirm the visual exists on the migrated "
                                  "report page and is not hidden behind a "
                                  "bookmark, filter or selection pane setting.",
            })
        visual_table.append({"Visual": vid, "Name": name or "(untitled)",
                             "Kind": "Slicer" if b.get("slicer_like") else "Visual",
                             "Verdict": "FAIL", "Findings": 1,
                             "SSIM": None, "Pixel diff %": None})

    for k, b in enumerate(un_tgt, 1):
        vid = f"N{k:02d}"
        name = (_title_of(_ocr(_sub(tgt_aligned, b), psm=6))
                if o.enable_ocr and ocr_available() else "")
        status_tgt[b["id"]] = "NEW"
        label_tgt[b["id"]] = vid
        findings.append({
            "visual_id": vid, "visual_name": name,
            "category": "extra_visual", "severity": "critical",
            "check": "Visual inventory",
            "source_state": "not present",
            "target_state": f"present at ({b['x']}, {b['y']}), "
                            f"{b['w']}×{b['h']} px",
            "metric": "unmatched target region",
            "description": "The target has a visual with no counterpart in "
                           "the source.",
            "recommendation": "Confirm whether this visual was intentionally "
                              "added during migration.",
        })
        visual_table.append({"Visual": vid, "Name": name or "(untitled)",
                             "Kind": "Slicer" if b.get("slicer_like") else "Visual",
                             "Verdict": "FAIL", "Findings": 1,
                             "SSIM": None, "Pixel diff %": None})

    # ── page-level ────────────────────────────────────────────────────────────
    page_ssim, page_map = _ssim_pair(src, tgt_aligned)
    page_pdr = _pixel_diff_ratio(src, tgt_aligned, o.pixel_channel_tol)
    drift = (float(np.mean([np.hypot(p["tgt"]["x"] - p["src"]["x"],
                                     p["tgt"]["y"] - p["src"]["y"])
                            for p in pairs])) if pairs else 0.0)

    # Only report the count delta when it is NOT already explained by the
    # missing/extra findings above — otherwise it is the same fact twice.
    if len(s_boxes) != len(t_boxes) and not un_src and not un_tgt:
        findings.append({
            "visual_id": "PAGE", "visual_name": "Page",
            "category": "visual_count_change",
            "severity": "critical", "check": "Visual count",
            "source_state": f"{len(s_boxes)} visuals detected",
            "target_state": f"{len(t_boxes)} visuals detected",
            "metric": f"Δ={len(t_boxes) - len(s_boxes):+d}",
            "description": "The number of detected visuals differs between "
                           "source and target.",
            "recommendation": "Reconcile the visual inventory on the migrated "
                              "report page.",
        })

    sev_counts = {k: 0 for k in SEVERITY_RANK}
    for f in findings:
        sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1

    worst = max((SEVERITY_RANK[f["severity"]] for f in findings), default=0)
    fail_at = 2 if o.fail_on_major else 3
    verdict = ("FAIL" if worst >= fail_at
               else "PASS_WITH_WARNINGS" if worst >= 1 else "PASS")

    page_metrics = {
        "Source size": f"{src.shape[1]}×{src.shape[0]} px",
        "Target size": f"{tgt.shape[1]}×{tgt.shape[0]} px",
        "Visuals (source)": len(s_boxes),
        "Visuals (target)": len(t_boxes),
        "Matched pairs": len(pairs),
        "Missing visuals": len(un_src),
        "New visuals": len(un_tgt),
        "Page SSIM": round(page_ssim, 4),
        "Page pixel diff %": round(page_pdr * 100, 2),
        "Layout drift (avg px)": round(drift, 1),
        "Alignment": f"{align_info['method']} "
                     f"(dx={align_info['dx']:.1f}, dy={align_info['dy']:.1f})",
        "OCR": "enabled" if (o.enable_ocr and ocr_available()) else "disabled",
    }
    if o.enable_ocr and not ocr_available():
        warnings.append("OCR checks were skipped: the Tesseract binary is not "
                        "available. Text and displayed-value changes will not "
                        "be detected by the Python engine.")

    s_items = [(b, label_src.get(b["id"], f"?{b['id']}"),
                status_src.get(b["id"], "PASS")) for b in s_boxes]
    t_items = [(b, label_tgt.get(b["id"], f"?{b['id']}"),
                status_tgt.get(b["id"], "PASS")) for b in t_boxes]

    return {
        "engine": "python",
        "verdict": verdict,
        "severity_counts": sev_counts,
        "page_metrics": page_metrics,
        "findings": findings,
        "visual_table": visual_table,
        "warnings": warnings,
        "artifacts": {
            "side_by_side": _side_by_side(src, tgt_aligned, s_items, t_items),
            "annotated_target": _draw_boxes(tgt_aligned, t_items),
            "heatmap": _heatmap(tgt_aligned, page_map),
            "crops": crops,
        },
    }
