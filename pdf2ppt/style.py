"""Estimate text style (size, bold, colors) from the rendered page image.

All font sizes are computed in SLIDE point space (the PDF page may be any
physical size; the slide is fixed at 13.333 in wide), derived from the tight
ink bounds inside each OCR box — the detector's quads carry inconsistent
padding, so their raw height is a poor size signal.
"""
from __future__ import annotations

import re

import numpy as np

from .models import Line, Style

# trailing footnote reference marker, e.g. 佐證[1] (the literal markdown
# [^1] in a code block is not raised and is excluded by the ink check)
_SUPERSCRIPT_MARK = re.compile(r"\[\^?\d+\]$")

# Standard PowerPoint font sizes to snap to
FONT_SIZES = [8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 54, 60]

# Fraction of the em square the glyph ink occupies in Noto Sans TC
# (calibrated by rendering output via PowerPoint and re-measuring the ink)
CJK_INK_RATIO = 0.875
# latin ink extent depends on which letterforms appear: x-height base,
# plus ascenders/capitals, plus descenders (Z-Library spans ~0.94 em while
# Format spans ~0.74 — one fixed ratio mis-sizes one or the other)
_LATIN_X = 0.52
_LATIN_ASC = 0.22
_LATIN_DESC = 0.20
_ASC_CHARS = set("bdfhklt/()[]{}|!?'\"$")
_DESC_CHARS = set("gjpqy()[]{}|/$;,")


def latin_ink_ratio(text: str) -> float:
    ratio = _LATIN_X
    if any(c.isupper() or c.isdigit() or c in _ASC_CHARS for c in text):
        ratio += _LATIN_ASC
    if any(c in _DESC_CHARS for c in text):
        ratio += _LATIN_DESC
    return ratio
# the 72dpi source raster blurs glyph edges ~3px out on each side at the
# 200dpi render; subtract before the ratio or small text reads a size big
BLUR_PX = 6

RING_PX = 4            # background sampled from this ring around the bbox
BG_MIN_SHARE = 0.55    # below this dominance the ring is not a flat background
INK_DIST = 60        # Chebyshev distance from bg to count a pixel as ink
MIN_INK_ROW_PX = 3   # a row needs this many ink pixels to count toward height
MAX_INK_ROW_FRAC = 0.85  # rows nearly all "ink" are background outside a ribbon

# --- template-matched bold (>=16pt) ---
# Render the line's own text in YaHei Regular and Bold at the same ink
# height, blur like the upscaled source raster, cut the ink mask at the
# line's own contrast-relative threshold, and measure the same erosion
# stroke estimator. r = 0 means the observed stroke equals the Regular
# template, 1 the Bold template. Whole-document calibration 2026-06-12:
# at >=16pt regular tops out at r=0.09 and bold starts at 0.17 (the two
# stragglers Karpathy Wiki 模式 -0.01 and 4.批次整理 0.03 are rescued by
# the same-page cohort vote); below 16pt the blur noise dominates and
# all-caps Latin merges into blobs (PITCH DECK r=-2.4), keep stroke_rel.
# SIGMA shifts the whole r scale (1.0 -> +0.07, 1.5 -> -0.15) but keeps
# the ordering: the thresholds below are calibrated for SIGMA = 1.2.
TPL_SIGMA = 1.2          # gaussian blur on templates, px at 200 dpi
TPL_MIN_PT = 16          # template verdict is primary at/above this size
TPL_COMPUTE_PT = 14      # compute r down to this size (demote tiebreak)
TPL_MIN_CONTRAST = 75    # below this text/bg distance the cut is degenerate
BOLD_R_THRESH = 0.13     # midpoint of regular max 0.09 / bold min 0.17
TPL_MARGINAL_R = 0.22    # below this a template bold verdict is marginal:
#                          cohort votes and wrap groups may overturn it
#                          (人類輸入 r=0.25 is the lowest confirmed real
#                          emphasis; the noisiest false positive was
#                          為體系化… at 0.146)
TPL_FONT_REGULAR = r"C:\Windows\Fonts\msyh.ttc"
TPL_FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

# Rough advance widths (em) per character class, for the overflow clamp
_EM_CJK = 1.0
_EM_LATIN = 0.52
_EM_SPACE = 0.33

# Margin (slide pt) kept between rendered text and a hit obstruction, so a
# line clamped against a grid line / card border leaves visible breathing
# room instead of touching it (user request: p2, p8).
OBSTACLE_MARGIN_PT = 3.0


def is_pure_latin(text: str) -> bool:
    return all(ord(c) < 0x2E80 for c in text)


def text_width_em(text: str) -> float:
    total = 0.0
    for c in text:
        o = ord(c)
        if o >= 0x2E80:  # CJK + full-width forms
            total += _EM_CJK
        elif c == " ":
            total += _EM_SPACE
        else:
            total += _EM_LATIN
    return total


def width_tolerance(em_width: float) -> float:
    """How far the font may exceed the width-fit limit. Short lines keep
    headroom (the em estimate is noisy and overshoot stays inside the
    chip); long lines bind tightly (per-char error accumulates and the
    overflow visibly crosses cell/chip borders)."""
    if em_width <= 8:
        return 1.12
    if em_width >= 12:
        return 1.03
    return 1.12 - (em_width - 8) * (0.09 / 4)


def snap_font_size(pt: float, max_pt: float | None = None,
                   tol: float = 1.10) -> float:
    best = min(FONT_SIZES, key=lambda s: abs(s - pt))
    if max_pt is not None and best > max_pt * tol:
        smaller = [s for s in FONT_SIZES if s <= max_pt * tol]
        if smaller:
            best = smaller[-1]
    return best


_MEASURE_FONT: object = None
_MEASURE_FONT_LATIN: object = None
_MEASURE_FONT_NARROW: object = None

# Page titles emit their latin runs in Arial Narrow (user request: the
# source deck's latin is ~14% narrower than Arial and long mixed titles
# like p4 "Layer 0: 三層架構分工與 Karpathy 模式知識庫" ran visibly long;
# Narrow keeps the faithful point size instead of dropping a snap step).
NARROW_MIN_PT = 28


def _load_measure_font(paths):
    import os

    from PIL import ImageFont

    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, 100)
    return False


def _latin_measure_font(narrow: bool):
    global _MEASURE_FONT_LATIN, _MEASURE_FONT_NARROW
    if narrow:
        if _MEASURE_FONT_NARROW is None:
            _MEASURE_FONT_NARROW = _load_measure_font(
                (r"C:\Windows\Fonts\ARIALN.TTF",
                 r"C:\Windows\Fonts\arialn.ttf"))
        if _MEASURE_FONT_NARROW:
            return _MEASURE_FONT_NARROW
    if _MEASURE_FONT_LATIN is None:
        _MEASURE_FONT_LATIN = _load_measure_font(
            (r"C:\Windows\Fonts\arial.ttf",))
    return _MEASURE_FONT_LATIN


def _measure_em(text: str, narrow: bool = False) -> float | None:
    """Exact advance width of the text in em, measured with the real
    output font; None when no font file is available. Pure-latin lines
    are emitted in Arial (builder.LATIN_FONT), so multi-char pure-latin
    strings measure with Arial — single chars keep the CJK font: they are
    the per-char window mapping inside mixed lines, which is calibrated
    against the CJK font's advances. narrow=True measures latin with
    Arial Narrow (page titles >= NARROW_MIN_PT emit that face)."""
    global _MEASURE_FONT
    if _MEASURE_FONT is None:
        import os
        _MEASURE_FONT = _load_measure_font((
            r"C:\Windows\Fonts\msyh.ttc",
            os.path.expandvars(
                r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\NotoSansTC-Regular.ttf"),
            r"C:\Windows\Fonts\NotoSansTC-VF.ttf",
        ))
    # >= 3 chars: the width clamp on 2-char strings rides snap ties (the
    # p8 "98" chip jumped 20pt -> 24pt+bold when Arial's narrower digits
    # loosened max_pt by 7%), and at that length the metric difference is
    # invisible in the rendered output anyway
    if len(text) > 2 and is_pure_latin(text):
        latin_font = _latin_measure_font(narrow)
        if latin_font:
            return latin_font.getlength(text) / 100.0
    if not _MEASURE_FONT:
        return None
    # mixed line: the builder emits latin characters in Arial, which runs
    # narrower than YaHei's latin — measuring everything with YaHei
    # overestimates the width and the clamp squeezes true sizes (p5
    # "Git Hook 自動化": 7.57em YaHei vs 7.18em with Arial latin, clamped
    # 24pt -> 20pt). Sum per-script runs with each output font.
    if len(text) > 2 and any(ord(c) >= 0x2E80 for c in text) \
            and any(ord(c) < 0x2E80 for c in text):
        latin_font = _latin_measure_font(narrow)
        if latin_font:
            total, i = 0.0, 0
            while i < len(text):
                latin = ord(text[i]) < 0x2E80
                j = i
                while j < len(text) and (ord(text[j]) < 0x2E80) == latin:
                    j += 1
                font = latin_font if latin else _MEASURE_FONT
                total += font.getlength(text[i:j])
                i = j
            return total / 100.0
    return _MEASURE_FONT.getlength(text) / 100.0


def _dominant_color(pixels: np.ndarray) -> tuple[np.ndarray, float]:
    """Dominant color of an (N,3) uint8 pixel set and its share of the set."""
    q = (pixels >> 4) << 4  # quantize to 16 levels per channel
    colors, counts = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
    dom = colors[counts.argmax()]
    near = np.abs(pixels.astype(int) - dom.astype(int)).max(axis=1) < 32
    mean = pixels[near].mean(axis=0)
    return mean.round().astype(int), float(near.mean())


def _top_clusters(pixels: np.ndarray, k: int = 2):
    """Top-k color clusters of an (N,3) uint8 set as (mean_color, share),
    coarse-quantized then refined so a color straddling bin edges still
    aggregates into one cluster."""
    q = (pixels >> 5) << 5
    colors, counts = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
    order = counts.argsort()[::-1]
    out = []
    taken = np.zeros(len(pixels), dtype=bool)
    for idx in order:
        if len(out) >= k:
            break
        near = (np.abs(pixels.astype(int) - colors[idx].astype(int)).max(axis=1)
                < 40) & ~taken
        if near.sum() < max(20, 0.02 * len(pixels)):
            continue
        out.append((pixels[near].mean(axis=0).round().astype(int),
                    float(near.mean())))
        taken |= near
    return out


def _erode(mask: np.ndarray) -> np.ndarray:
    return (mask
            & np.roll(mask, 1, 0) & np.roll(mask, -1, 0)
            & np.roll(mask, 1, 1) & np.roll(mask, -1, 1))


def _dilate(mask: np.ndarray, times: int = 3) -> np.ndarray:
    for _ in range(times):
        mask = (mask
                | np.roll(mask, 1, 0) | np.roll(mask, -1, 0)
                | np.roll(mask, 1, 1) | np.roll(mask, -1, 1))
    return mask


def _core_color(inner: np.ndarray, mask: np.ndarray,
                bg_ref: np.ndarray) -> tuple[int, int, int]:
    """Mean of the masked pixels farthest from the background color —
    anti-aliasing drags stroke edges toward bg, the cores are the truth."""
    px = inner[mask].astype(int)
    diff = np.abs(px - bg_ref.astype(int)).max(axis=1)
    keep = diff >= np.percentile(diff, 70)
    src = px[keep] if keep.sum() >= 10 else px
    return tuple(int(v) for v in src.mean(axis=0).round())


def _survival(mask: np.ndarray) -> float:
    """Fraction of a 2D mask surviving two erosions: thin strokes die,
    solid blocks survive."""
    n = mask.sum()
    if n == 0:
        return 0.0
    return float(_erode(_erode(mask)).sum() / n)


def _band_stroke_px(ink: np.ndarray) -> tuple[float, np.ndarray] | None:
    """(stroke width px, band rows) from the heaviest glyph row-group of an
    ink mask — the same estimator estimate_style uses on the page crop."""
    row_counts = ink.sum(axis=1)
    row_w = max(1, ink.shape[1])
    rows = np.where((row_counts >= MIN_INK_ROW_PX)
                    & (row_counts <= MAX_INK_ROW_FRAC * row_w))[0]
    if not len(rows):
        return None
    splits = np.where(np.diff(rows) > 8)[0]
    if len(splits):
        groups = np.split(rows, splits + 1)
        rows = max(groups, key=lambda g: int(row_counts[g].sum()))
    band = ink[rows[0]:rows[-1] + 1]
    n = int(band.sum())
    if n < 30:
        return None
    survival1 = float(_erode(band).sum()) / n
    return 2.0 / max(0.05, 1.0 - survival1), rows


_TPL_RENDERABLE = None


def _tpl_text(text: str) -> str:
    """Strip characters we can't trust YaHei to render as real glyphs
    (arrows, roman numerals, dingbats become .notdef boxes = solid blobs
    that poison the stroke metric)."""
    keep = []
    for c in text:
        o = ord(c)
        if (0x20 <= o < 0x7F or 0x2E80 <= o <= 0x9FFF
                or 0x3000 <= o <= 0x30FF or 0xFF00 <= o <= 0xFFEF):
            keep.append(c)
    return "".join(keep).strip()


def _tpl_stroke_px(text: str, ink_h: float, bold: bool,
                   rel_thresh: float) -> float | None:
    """Stroke width of `text` rendered in YaHei (Regular/Bold), blurred
    like the upscaled source raster and cut at the line's own
    contrast-relative ink threshold, scaled so the glyph band matches
    ink_h. Measured with the same estimator as the page crop."""
    import os

    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    path = TPL_FONT_BOLD if bold else TPL_FONT_REGULAR
    if not os.path.exists(path):
        return None
    cut = 255.0 * (1.0 - min(0.95, rel_thresh))
    em = max(12, int(round(ink_h / 0.91)))
    result = None
    for _ in range(3):  # converge the band height onto ink_h
        font = ImageFont.truetype(path, em)
        l, t, r, b = font.getbbox(text)
        if r <= l or b <= t:
            return None
        im = Image.new("L", (int(r - l) + 20, int(b - t) + 20), 255)
        ImageDraw.Draw(im).text((10 - l, 10 - t), text, font=font, fill=0)
        im = im.filter(ImageFilter.GaussianBlur(TPL_SIGMA))
        ink = np.asarray(im) < cut
        got = _band_stroke_px(ink)
        if got is None:
            return None
        result, rows = got
        h = rows[-1] - rows[0] + 1
        if abs(h - ink_h) <= max(2, 0.04 * ink_h):
            break
        em = max(12, int(round(em * ink_h / h)))
    return result


def _template_bold_r(text: str, ink_h: float, w_obs: float,
                     contrast: float) -> float | None:
    """Template-matched weight score (see module constants). None when no
    trustworthy verdict exists."""
    text = _tpl_text(text)
    if sum(1 for c in text if c != " ") < 2:
        return None
    rel = INK_DIST / max(float(INK_DIST + 5), contrast)
    w_reg = _tpl_stroke_px(text, ink_h, False, rel)
    w_bold = _tpl_stroke_px(text, ink_h, True, rel)
    if not w_reg or not w_bold or w_bold <= w_reg:
        return None
    if w_reg > 2.5 * w_obs:  # template imploded into blobs (caps + blur)
        return None
    return (w_obs - w_reg) / (w_bold - w_reg)


def _crop(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    h, w = img.shape[:2]
    return img[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]


def _rectify(img: np.ndarray, line: Line, pad: int) -> np.ndarray:
    """Deskew a tilted line: map its (pad-expanded) rotated rect to a
    horizontal patch, so all color/ink sampling sees clean horizontal text
    surrounded by its true local background."""
    import math

    from PIL import Image

    cx, cy = line.center
    w, h = line.size
    a = math.radians(line.angle)
    ux, uy = math.cos(a), math.sin(a)      # along the text baseline
    vx, vy = -math.sin(a), math.cos(a)     # perpendicular, downward

    def corner(sx: float, sy: float) -> tuple[float, float]:
        return cx + ux * sx + vx * sy, cy + uy * sx + vy * sy

    hw, hh = w / 2 + pad, h / 2 + pad
    quad = (*corner(-hw, -hh), *corner(-hw, hh),
            *corner(hw, hh), *corner(hw, -hh))  # NW, SW, SE, NE
    out_size = (int(round(w + 2 * pad)), int(round(h + 2 * pad)))
    patch = Image.fromarray(img).transform(out_size, Image.QUAD, data=quad,
                                           resample=Image.BICUBIC)
    return np.asarray(patch)


RUN_JOIN_DIST = 45   # chars within this color distance join the same run
RUN_SPLIT_DIST = 60  # a line only splits into runs if colors differ this much


def _split_color_runs(img: np.ndarray, line: Line, bg_ref: np.ndarray):
    """Group the line's characters into same-color runs (e.g. a terracotta
    '⚠ 限制機制：' prefix followed by dark body text). Returns
    [(char_count, rgb), ...] or None when the line is one color."""
    if not line.char_boxes or len(line.char_boxes) < 2:
        return None
    colors = []
    for _, l, t, r, b in line.char_boxes:
        l, t, r, b = int(l), int(t), int(r), int(b)
        if r - l < 3 or b - t < 3:
            colors.append(None)
            continue
        crop = img[t:b, l:r]
        ink = np.abs(crop.astype(int) - bg_ref.astype(int)).max(axis=2) > INK_DIST
        if ink.sum() < 8:
            colors.append(None)
            continue
        colors.append(np.asarray(_core_color(crop, ink, bg_ref)))

    return _group_color_runs(colors)


def _group_color_runs(colors):
    """Group per-char colors (or None) into [(count, rgb), ...] runs, or
    None when the line is effectively one color."""
    segments: list[list] = []  # [count, color|None]
    for col in colors:
        if segments and (
                col is None or segments[-1][1] is None
                or np.abs(col - segments[-1][1]).max() <= RUN_JOIN_DIST):
            segments[-1][0] += 1
            if segments[-1][1] is None:
                segments[-1][1] = col
        else:
            segments.append([1, col])

    # a single-char segment between two same-color neighbors is CTC box
    # jitter, not emphasis: the final t of p4's "Idempotent(" sampled the
    # anti-aliasing grey (150,150,150) from a box landing half on the "("
    # gap and split the run mid-word. Genuine one-char emphasis between
    # two parts of the SAME color does not occur in these decks.
    i = 1
    while i < len(segments) - 1:
        prev_c, mid, next_c = segments[i - 1][1], segments[i], segments[i + 1][1]
        if (mid[0] == 1 and prev_c is not None and next_c is not None
                and np.abs(prev_c - next_c).max() <= RUN_JOIN_DIST):
            segments[i - 1][0] += mid[0] + segments[i + 1][0]
            del segments[i:i + 2]
        else:
            i += 1

    real = [s[1] for s in segments if s[1] is not None]
    if len(segments) < 2 or not real:
        return None
    spread = max(np.abs(a - b).max() for a in real for b in real)
    if spread < RUN_SPLIT_DIST:
        return None
    fallback = real[0]
    return [(s[0], tuple(int(v) for v in (s[1] if s[1] is not None else fallback)))
            for s in segments]


BG_SEG_MERGE = 26     # columns within this Chebyshev distance share a bg run
BG_SEG_STD = 16       # a clean flat fill's per-column color std stays below this
BG_SEG_DIST = 32      # adjacent fills must differ by at least this to stay split


def glyph_char_iou(img: np.ndarray, bbox, ch: str) -> float | None:
    """IoU between a box's glyph ink and the character `ch` rendered in
    YaHei, both tight-cropped and scaled to 64x64. A real glyph of `ch`
    overlaps its own rendering; an icon misread as `ch` does not (p14's CPU
    chip read as 尚: IoU 0.20 vs 0.35-0.65 for correctly read CJK chars).
    None when no font or the crop is too small."""
    import os

    from PIL import Image, ImageDraw, ImageFont

    if not os.path.exists(TPL_FONT_REGULAR):
        return None
    x0, y0, x1, y1 = (int(round(v)) for v in bbox)
    crop = _crop(img, x0, y0, x1, y1)
    if crop.shape[0] < 8 or crop.shape[1] < 8:
        return None
    edge = np.concatenate([crop[:4].reshape(-1, 3), crop[-4:].reshape(-1, 3),
                           crop[:, :4].reshape(-1, 3), crop[:, -4:].reshape(-1, 3)])
    bg = np.median(edge, axis=0)
    gm = np.abs(crop.astype(int) - bg).max(axis=2) > INK_DIST
    font = ImageFont.truetype(TPL_FONT_REGULAR, 200)
    l, t, r, b = font.getbbox(ch)
    if r <= l or b <= t:
        return None
    im = Image.new("L", (int(r - l) + 10, int(b - t) + 10), 0)
    ImageDraw.Draw(im).text((10 - l, 10 - t), ch, font=font, fill=255)
    cm = np.asarray(im) > 80

    def tight(m):
        rs, cs = np.where(m.any(1))[0], np.where(m.any(0))[0]
        return m[rs[0]:rs[-1] + 1, cs[0]:cs[-1] + 1] if len(rs) and len(cs) else None

    gm, cm = tight(gm), tight(cm)
    if gm is None or cm is None:
        return None
    gi = np.asarray(Image.fromarray(gm).resize((64, 64))) > 0.5
    ci = np.asarray(Image.fromarray(cm).resize((64, 64))) > 0.5
    return float((gi & ci).sum() / max(1, (gi | ci).sum()))


def _detect_bg_segments(inner: np.ndarray):
    """Run-length the box's per-column background color into flat fills.

    The background of each column is the median of its top+bottom edge rows
    (above/below the glyph band, so pure background regardless of glyph
    density — a full-column median is pulled dark by dense strokes, and a
    single-bg-ref ink mask inverts in a banner's far fill). Consecutive
    columns within BG_SEG_MERGE of a running mean form one fill. Handles a
    two-tone banner (dark|light, p2 BSD caption) AND an inline highlight
    (light|lavender|light, p2 `Perl` / `Email` code chips) the same way.
    Returns [(x0_local, x1_local, rgb), ...] (>=2 clean fills covering the
    width) or None for a uniform background or a smooth gradient — gradual
    columns merge into one run, and a run whose own columns vary more than
    BG_SEG_STD is rejected (a gradient/photo never resolves into flat
    blocks). Internal boundaries are refined to the per-channel mid-
    crossing so a fill edge lands in the inter-glyph gap, not inside a
    boundary glyph (the source never splits a glyph's own fill)."""
    h, w = inner.shape[:2]
    if w < 80 or h < 12:
        return None
    k = max(3, h // 8)
    edge = np.concatenate([inner[:k], inner[-k:]], axis=0).astype(float)
    colc = np.median(edge, axis=0)  # (w, 3) per-column background
    if w >= 5:
        ker = np.ones(5) / 5.0
        colc = np.stack([np.convolve(colc[:, i], ker, "same") for i in range(3)], 1)

    bounds, mean, n = [0], colc[0].copy(), 1
    for x in range(1, w):
        if np.abs(colc[x] - mean).max() <= BG_SEG_MERGE:
            mean = (mean * n + colc[x]) / (n + 1)
            n += 1
        else:
            bounds.append(x)
            mean, n = colc[x].copy(), 1
    bounds.append(w)
    segs = [[bounds[i], bounds[i + 1]] for i in range(len(bounds) - 1)]

    def seg_color(a, b):
        return np.median(edge[:, a:b].reshape(-1, 3), axis=0)

    minw = max(10, int(0.03 * w))
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i, (a, b) in enumerate(segs):
            if b - a >= minw:
                continue
            ci = seg_color(a, b)
            cand = []
            if i > 0:
                cand.append((float(np.abs(ci - seg_color(*segs[i - 1])).max()), i - 1))
            if i < len(segs) - 1:
                cand.append((float(np.abs(ci - seg_color(*segs[i + 1])).max()), i + 1))
            j = min(cand)[1]
            segs[min(i, j)] = [min(a, segs[j][0]), max(b, segs[j][1])]
            del segs[max(i, j)]
            changed = True
            break
    if len(segs) < 2:
        return None

    colors = [seg_color(a, b) for a, b in segs]
    for a, b in segs:
        if float(colc[a:b].std(axis=0).max()) > BG_SEG_STD:
            return None  # a fill must be flat; a gradient run fails this
    for i in range(len(segs) - 1):
        if np.abs(colors[i] - colors[i + 1]).max() < BG_SEG_DIST:
            return None  # neighboring fills too similar to be intentional

    out = [0]
    for i in range(len(segs) - 1):
        raw = segs[i][1]
        cA, cB = colors[i], colors[i + 1]
        ch = int(np.argmax(np.abs(cA - cB)))
        mid = (cA[ch] + cB[ch]) / 2.0
        win = max(4, int(0.04 * w))
        a0, b0 = max(out[-1] + 1, raw - win), min(w - 1, raw + win)
        out.append(a0 + int(np.argmin(np.abs(colc[a0:b0 + 1, ch] - mid))))
    out.append(w)
    return [(float(out[i]), float(out[i + 1]),
             tuple(int(v) for v in colors[i])) for i in range(len(segs))]


def _split_color_runs_segmented(img: np.ndarray, line: Line, segments):
    """Per-char color runs when the line spans two background fills: each
    char is measured against the background of the segment it sits in (by
    char-box center), so dark-on-light text on the light segment reads dark
    instead of sampling the bright fill as ink. `segments` is
    [(x0_px, x1_px, bg_rgb), ...]. Returns runs or None (one color)."""
    if not line.char_boxes or len(line.char_boxes) < 2:
        return None

    def seg_bg(cx: float) -> np.ndarray:
        for sx0, sx1, bg in segments:
            if sx0 <= cx < sx1:
                return np.asarray(bg)
        return np.asarray(segments[-1][2])

    colors = []
    for _, l, t, r, b in line.char_boxes:
        l, t, r, b = int(l), int(t), int(r), int(b)
        if r - l < 3 or b - t < 3:
            colors.append(None)
            continue
        bg = seg_bg((l + r) / 2.0)
        crop = img[t:b, l:r]
        ink = np.abs(crop.astype(int) - bg.astype(int)).max(axis=2) > INK_DIST
        if ink.sum() < 8:
            colors.append(None)
            continue
        colors.append(np.asarray(_core_color(crop, ink, bg)))
    return _group_color_runs(colors)


ROOM_MAX_FACTOR = 1.5   # scan at most this many line-heights of side room
ROOM_BG_DIST = 40       # a column is "free" if its pixels match the cover bg
ROOM_FREE_FRAC = 0.9
ROOM_THIN_PX = 8        # obstructions at most this wide may be seen through
ROOM_FAINT_DIST = 75    # ...but only when faint (decorative grid lines);
#                         card borders / leader dots are darker and still stop
#                         the scan (p5 Git Hook 自動化: a pale blueprint grid
#                         line 6px past the box froze the room at 6px and the
#                         width clamp squeezed a true 24pt header to 20pt)


def _chip_room_right(img: np.ndarray, line: Line, bg_rgb, rows,
                     y0: int) -> float | None:
    """How many pixels of unobstructed background extend past the box's
    right edge before any obstruction — the true space the rendered text
    may grow into. Returns inf when the whole scan range is free (nothing
    measured, the line may grow; the slide edge still caps), or None when
    there is no cover color or no measured rows."""
    if bg_rgb is None or not len(rows):
        return None
    h, w = img.shape[:2]
    x1 = int(round(line.bbox[2]))
    band_h = rows[-1] - rows[0] + 1
    r0 = y0 + rows[0] + band_h // 4
    r1 = y0 + rows[-1] - band_h // 4 + 1
    if r1 <= r0 or x1 >= w:
        return 0.0
    limit = min(w, x1 + int(ROOM_MAX_FACTOR * max(band_h, 1)))
    strip = img[r0:r1, x1:limit].astype(int)
    if strip.size == 0:
        return 0.0
    dist = np.abs(strip - np.asarray(bg_rgb)).max(axis=2)
    free = (dist < ROOM_BG_DIST).mean(axis=0) >= ROOM_FREE_FRAC
    faint = dist.max(axis=0) < ROOM_FAINT_DIST
    room, i = 0, 0
    while i < len(free):
        if free[i]:
            room = i + 1
            i += 1
            continue
        j = i
        while j < len(free) and not free[j]:
            j += 1
        # see through a thin, faint obstruction (decorative grid line);
        # anything wide or dark (chip border, leader dot) ends the room
        if j - i <= ROOM_THIN_PX and j < len(free) and faint[i:j].all():
            i = j
            continue
        return float(room)
    # the whole scanned strip is free: no border within 1.5 line-heights,
    # so nothing was measured — the line may grow freely (the slide edge
    # still caps it). Treating the scan limit as a ceiling squeezed p10
    # "AI 逆向掃描" (open page bg to its right) from 24pt to 20pt.
    return float("inf")


# Full-width punctuation whose ink does not span the em square — a line
# whose only CJK characters are these cannot anchor the band measurement
_CJK_LOW_INK = set("：；。、，·．！？…—～〜「」『』（）《》〈〉【】")


def _cjk_band_height(ink: np.ndarray, text: str,
                     min_extents: int = 1) -> float | None:
    """Glyph-band height measured per CJK character, with a consensus vote.

    Column ranges come from per-char advance widths mapped proportionally
    onto the box width (the real output font when available) — RapidOCR's
    CTC word boxes are too jittery for this (the boxes for 使用 in
    "graph.sh 使用" land half a char off and measured 33px instead of
    58px). Each char window is inset 0.2 em per side to absorb the
    residual mapping error, so a latin descender next to a CJK char can't
    bleed in.

    Each char's row extent is measured separately, then: when at least
    half the chars agree within 2% of the median, the band is the largest
    extent inside that cluster — this drops both junk-contaminated chars
    (a neighbor line's descenders under one char inflate it 14-29%) and
    single-char blur flukes (序/譜 read 61px where four siblings read
    58px, which is the 14pt->16pt snap boundary). Without a consensus
    (few chars, or noisy small text like 周郁凯 at 12pt whose extents
    spread 39-47px) it falls back to the largest extent, matching the
    plain union this measurement replaced. No MAX_INK_ROW_FRAC inside a
    window: a long horizontal stroke legitimately fills the whole narrow
    window (graph.sh 使用 lost mid-band rows to the 0.85 cap and measured
    8pt). Returns None when the line has no full-ink CJK glyph to anchor
    the band (e.g. the only CJK chars are punctuation)."""
    w = ink.shape[1]
    chars = text.strip()
    if not chars or w < 4:
        return None
    widths = []
    for c in chars:
        adv = _measure_em(c)
        if not adv:
            adv = (_EM_CJK if ord(c) >= 0x2E80
                   else _EM_SPACE if c == " " else _EM_LATIN)
        widths.append(adv)
    total = sum(widths)
    if total <= 0:
        return None
    scale = w / total
    extents = []
    pos = 0.0
    for c, adv in zip(chars, widths):
        # low-ink punctuation is excluded from the windows too, not just
        # from anchoring: a full-width （ descends below the glyph band
        # (定性 bug（Dict 排 measured 64px instead of 58px through it)
        if ord(c) >= 0x2E80 and c not in _CJK_LOW_INK:
            inset = 0.2 * scale
            a = max(0, int(round(pos * scale + inset)))
            b = min(w, int(round((pos + adv) * scale - inset)))
            if b > a:
                counts = ink[:, a:b].sum(axis=1)
                rows = np.where(counts >= MIN_INK_ROW_PX)[0]
                if len(rows):
                    # same blank-gap split as the full-line measurement:
                    # stray ink > 8 rows away (graph.sh 使用 has 3 junk
                    # rows above the band) must not stretch the extent.
                    # A glyph fragment isolated by the split (己's inset
                    # window splits into two strokes) lands outside the
                    # consensus cluster and is voted away.
                    splits = np.where(np.diff(rows) > 8)[0]
                    if len(splits):
                        rows = max(np.split(rows, splits + 1),
                                   key=lambda g: int(counts[g].sum()))
                    extents.append(float(rows[-1] - rows[0] + 1))
        pos += adv
    if len(extents) < max(1, min_extents):
        return None
    med = float(np.median(extents))
    # 4%: wide enough that normal glyph variance clusters (p14 轉化為的
    # at [80,75,93,75] — 2% left the cluster empty and the max() fallback
    # picked the 93px char whose window caught the line above's
    # descenders -> 24pt instead of 20pt), narrow enough to still exclude
    # the +5% blur flukes (序/譜 61px vs four 58px siblings) and junk
    cluster = [e for e in extents if abs(e - med) <= 0.04 * med]
    if 2 * len(cluster) >= len(extents):
        return max(cluster)
    return max(extents)


def _is_vertical_cjk(line: Line) -> bool:
    """Vertically-stacked CJK text: a tall, narrow box of N square CJK
    glyphs stacked top-to-bottom (p7 axis labels 純寫作 / 技術開發). Pure
    CJK only — a tall mixed/latin box is something else."""
    if line.angle or line.arc_sagitta:
        return False
    t = line.text.strip().replace(" ", "")
    if len(t) < 2 or any(ord(c) < 0x2E80 for c in t):
        return False
    w, h = line.bbox[2] - line.bbox[0], line.bbox[3] - line.bbox[1]
    if w <= 0 or h < 1.5 * w:
        return False
    cell = h / len(t)               # height of one stacked char
    return 0.55 <= cell / w <= 1.7  # roughly square glyphs


def _estimate_vertical(img: np.ndarray, line: Line,
                       px_to_slide_pt: float, bold_mode: str) -> Style:
    """Style for vertically-stacked CJK text. The font size comes from the
    char COLUMN width (each glyph is as wide as the column), not the
    stacked height; the cover spans the whole box; the builder renders it
    with an east-asian vertical text frame."""
    x0, y0, x1, y1 = (int(round(v)) for v in line.bbox)
    outer = _crop(img, x0 - RING_PX, y0 - RING_PX, x1 + RING_PX, y1 + RING_PX)
    inner = _crop(img, x0, y0, x1, y1)
    ring = np.concatenate([outer[:RING_PX].reshape(-1, 3),
                           outer[-RING_PX:].reshape(-1, 3),
                           outer[:, :RING_PX].reshape(-1, 3),
                           outer[:, -RING_PX:].reshape(-1, 3)])
    bg_ref, share = _dominant_color(ring)
    bg_rgb = tuple(int(v) for v in bg_ref) if share >= BG_MIN_SHARE else None
    ink = np.abs(inner.astype(int) - bg_ref.astype(int)).max(axis=2) > INK_DIST
    cols = np.where(ink.sum(axis=0) >= MIN_INK_ROW_PX)[0]
    ink_w = float(cols[-1] - cols[0] + 1) if len(cols) else float(x1 - x0)
    ink_w_eff = max(ink_w - BLUR_PX, ink_w * 0.6)
    font_pt = snap_font_size(ink_w_eff * px_to_slide_pt / CJK_INK_RATIO)
    if ink.sum() >= 10:
        text_rgb = _core_color(inner, ink, bg_ref)
    else:
        text_rgb = (0, 0, 0)
    if bold_mode == "always":
        bold = True
    elif bold_mode == "never":
        bold = False
    else:
        bold = font_pt >= 24
    return Style(
        font_pt=font_pt, bold=bold, est_pt=ink_w_eff * px_to_slide_pt / CJK_INK_RATIO,
        text_rgb=text_rgb, bg_rgb=bg_rgb,
        ink_top_px=float(y0), ink_bottom_px=float(y1), vertical=True,
    )


def estimate_style(img: np.ndarray, line: Line, px_to_slide_pt: float,
                   bold_mode: str = "auto") -> Style:
    """px_to_slide_pt: slide points per image pixel (960 / image_width).
    bold_mode: 'auto' | 'never' | 'always'.
    """
    if _is_vertical_cjk(line):
        return _estimate_vertical(img, line, px_to_slide_pt, bold_mode)

    x0, y0, x1, y1 = (int(round(v)) for v in line.bbox)
    chord_pt = (x1 - x0) * px_to_slide_pt

    # arc text: analyze only the middle third of the chord, at the arc's
    # own end of the box (locally flat, free of the parallel ribbon line
    # that interpenetrates the full bbox and poisons every color sample)
    if line.arc_sagitta:
        w_full, h_full = x1 - x0, y1 - y0
        x0 += w_full // 3
        x1 -= w_full // 3
        if line.arc_sagitta < 0:  # arch down: middle glyphs at the bottom
            y0 = y1 - round(0.5 * h_full)
        else:
            y1 = y0 + round(0.5 * h_full)

    # --- background color: ring around the box ---
    if line.angle and line.center and line.size:
        outer = _rectify(img, line, RING_PX)
        inner = outer[RING_PX:-RING_PX, RING_PX:-RING_PX]
    else:
        outer = _crop(img, x0 - RING_PX, y0 - RING_PX, x1 + RING_PX, y1 + RING_PX)
        inner = _crop(img, x0, y0, x1, y1)
    ring_parts = []
    oh, ow = outer.shape[:2]
    if oh > 2 * RING_PX and ow > 2 * RING_PX:
        ring_parts = [outer[:RING_PX].reshape(-1, 3),
                      outer[-RING_PX:].reshape(-1, 3),
                      outer[:, :RING_PX].reshape(-1, 3),
                      outer[:, -RING_PX:].reshape(-1, 3)]
    ring = np.concatenate(ring_parts) if ring_parts else outer.reshape(-1, 3)

    bg_rgb: tuple[int, int, int] | None = None
    text_rgb_override: tuple[int, int, int] | None = None
    bg_ref, share = _dominant_color(ring)
    if share >= BG_MIN_SHARE:
        bg_rgb = tuple(int(v) for v in bg_ref)
    else:
        # Ring is mixed: the text sits on a ribbon/chip whose edges run under
        # the OCR box, or on a gradient/photo. Cluster the box's vertical
        # middle band into its two main colors and erode each mask — text
        # strokes are thin and die, a ribbon is solid and survives. A clear
        # survival gap identifies the ribbon (cover color) vs the text.
        ih = inner.shape[0]
        mid = inner[ih // 4: max(ih // 4 + 1, 3 * ih // 4)]
        clusters = _top_clusters(mid.reshape(-1, 3))
        if len(clusters) == 2:
            masks = [
                np.abs(mid.astype(int) - c.astype(int)).max(axis=2) < 40
                for c, _ in clusters
            ]
            surv = [_survival(m) for m in masks]
            bg_i = 0 if surv[0] >= surv[1] else 1
            if surv[bg_i] - surv[1 - bg_i] > 0.2 and clusters[bg_i][1] >= 0.30:
                bg_ref = clusters[bg_i][0]
                bg_rgb = tuple(int(v) for v in bg_ref)
                # refine through the stroke cores, never the raw cluster
                # center: the text cluster mixes true strokes with the
                # much larger anti-aliasing / chip-outline population and
                # its center lands mid-grey (p8 Guardrail 1 painted
                # [171,171,169] instead of black)
                text_rgb_override = _core_color(mid, masks[1 - bg_i], bg_ref)
        if bg_rgb is None and clusters:
            # gradient/photo: no cover, but keep a reference color so the
            # ink mask below can still find the glyphs
            bg_ref = clusters[0][0]

    # --- ink mask ---
    ink = np.abs(inner.astype(int) - bg_ref.astype(int)).max(axis=2) > INK_DIST

    # the mixed-ring "text" cluster can be the anti-aliasing shell / chip
    # outline rather than the strokes (p8 Guardrail 1: outline + AA
    # clustered at grey ~[190] while the black strokes were too sparse to
    # form a cluster, painting the text [150,150,149]). When the ink mask
    # against the chosen bg holds a clearly farther core, trust the ink.
    if text_rgb_override is not None and ink.sum() >= 10:
        ink_core = _core_color(inner, ink, bg_ref)
        d_over = np.abs(np.array(text_rgb_override, dtype=int)
                        - bg_ref.astype(int)).max()
        d_core = np.abs(np.array(ink_core, dtype=int)
                        - bg_ref.astype(int)).max()
        if d_core >= d_over + 60:
            text_rgb_override = ink_core

    # --- pill/chip detection: when the box spills past a filled pill the
    # ring sees the outside color, so the whole pill registers as "ink"
    # (a solid blob, not strokes). Re-derive bg/text from the box's own
    # color clusters: the most solid cluster is the pill, the least solid
    # one is the glyph strokes. ---
    if text_rgb_override is None and ink.mean() >= 0.45 and _survival(ink) >= 0.45:
        clusters = _top_clusters(inner.reshape(-1, 3), k=3)
        if len(clusters) >= 2:
            masks = [np.abs(inner.astype(int) - c.astype(int)).max(axis=2) < 40
                     for c, _ in clusters]
            survs = [_survival(m) for m in masks]
            idx = range(len(clusters))
            bg_i = max(idx, key=lambda i: (clusters[i][1] >= 0.25, survs[i]))
            tx_i = min((i for i in idx if i != bg_i), key=lambda i: survs[i])
            # a real spilled pill re-derives a bg that DIFFERS from the
            # ring (that mismatch is the whole failure mode); when the
            # re-derived bg matches the ring this is just dense bold text
            # that crossed the ink.mean threshold (p15 把精力保留… at
            # ink.mean 0.46), and the least-solid cluster would be the
            # anti-aliasing shell — overriding paints the text grey
            if (survs[bg_i] - survs[tx_i] > 0.15
                    and np.abs(clusters[bg_i][0].astype(int)
                               - bg_ref.astype(int)).max() >= 40):
                bg_ref = clusters[bg_i][0]
                bg_rgb = tuple(int(v) for v in bg_ref)
                text_rgb_override = _core_color(inner, masks[tx_i], bg_ref)
                ink = (np.abs(inner.astype(int) - bg_ref.astype(int)).max(axis=2)
                       > INK_DIST)

    # --- tight ink bounds ---
    row_counts = ink.sum(axis=1)
    row_w = max(1, ink.shape[1])
    rows = np.where((row_counts >= MIN_INK_ROW_PX)
                    & (row_counts <= MAX_INK_ROW_FRAC * row_w))[0]
    if len(rows):
        # ink that crosses the box edge from the outside — a pill border
        # (page 9 "images/": rounded-corner rows at 0.67 width slip under
        # MAX_INK_ROW_FRAC, 16 blank rows away) or a neighboring line's
        # glyph edges (page 4 "graph.sh": the underscores of the line
        # above and the caps of the line below, 9 blank rows away) —
        # stretches the ink bounds, inflating the font and letting the
        # cover paint over the neighbor. The glyph band is one row-group;
        # split on blank gaps and keep the heaviest group. Real intra-line
        # gaps (i-dots) are <= ~4px at 200dpi, so 8 is safely above them.
        splits = np.where(np.diff(rows) > 8)[0]
        if len(splits):
            groups = np.split(rows, splits + 1)
            rows = max(groups, key=lambda g: int(row_counts[g].sum()))
        ink_h_px = float(rows[-1] - rows[0] + 1)
        ink_top_px = y0 + float(rows[0])
        ink_bottom_px = y0 + float(rows[-1] + 1)
    else:  # OCR found text the ink threshold can't see; fall back to box
        ink_h_px = float(y1 - y0)
        ink_top_px = float(y0)
        ink_bottom_px = float(y1)

    # --- no-cover rescue: the ring failed (p8's tilted green chips: the
    # axis-aligned box spans chip + page bg + neighbors, and the cluster
    # branch sees two SOLID surfaces with no survival gap) so bg stayed
    # None and the editable digits doubled over the raster. The glyphs
    # may still sit on a locally solid surface: sample the halo around
    # the ink band; a clearly dominant color is a usable cover. Gradient
    # or illustration backgrounds stay uncovered (dominant share low). ---
    if bg_rgb is None and len(rows) and ink.sum() >= 30:
        band_ink = np.zeros_like(ink)
        band_ink[rows[0]:rows[-1] + 1] = ink[rows[0]:rows[-1] + 1]
        near = _dilate(band_ink, 3)
        halo = _dilate(near, 3) & ~near
        if halo.sum() >= 60:
            halo_col, share = _dominant_color(inner[halo])
            if share >= 0.65:
                bg_rgb = tuple(int(v) for v in halo_col)

    # --- mixed-line CJK band (font size only): latin descenders (g/p/y,
    # parens, /) drop below the ideograph band and stretch the whole-line
    # ink union ~0.15 em, so CJK_INK_RATIO oversizes the font (page 4
    # "graph.sh 使用": 66px span vs 58px for its same-size pure-CJK
    # siblings -> 18pt instead of 14pt). Re-measure per CJK character and
    # take the consensus. Cover and positioning keep the full extent (the
    # raster descenders must stay painted over), only the em estimate
    # changes. A sparse-edge-row trim (count < 0.25x band median) was
    # tried first and over-trimmed: faint-but-real CJK edge rows scale
    # with line width while descender rows don't, so their relative
    # weights overlap across short and long lines (p2/p6 titles lost real
    # rows -> 44pt read 40pt, while the p4 fixes needed the full trim).
    # Gate: only lines whose latin part can actually descend (g/p/y,
    # parens, /) go through the consensus path. Widening it to every CJK
    # line was tried and reverted: the +-3px blur noise then flips OTHER
    # borderline lines down one snap step and breaks blocks that the
    # union measured consistently (p4's right annotation read 16/14/14pt
    # from one 16pt block; single-CJK-char lines like "2025 年" collapsed
    # to the lone char's band). Cross-line agreement is instead restored
    # by harmonize_font_sizes in blocks.py.
    ink_h_font_px = ink_h_px
    has_desc = any(c in _DESC_CHARS for c in line.text)
    has_latin = any(c.isascii() and c.isalnum() for c in line.text)
    if (len(rows) and not line.arc_sagitta and not is_pure_latin(line.text)
            and (has_desc or has_latin)):
        # descender lines may hang their consensus on a single CJK char
        # (跨 Viewer needs 跨 alone); other latin-mixed lines need >= 2
        # ideograph votes or single-CJK lines like "2025 年" collapse to
        # the lone char's band (p14 轉化為 AI 的 Guardrails: no descender
        # chars at all, but the line above's p/q stems bridged into the
        # union -> 24pt instead of 20pt, so desc-only gating is not enough)
        cjk_h = _cjk_band_height(ink, line.text,
                                 min_extents=1 if has_desc else 2)
        if cjk_h:
            ink_h_font_px = min(ink_h_px, cjk_h)

    # --- halo refinement: the cover color should match the pixels near the
    # glyphs, not the ring (which may lie on a different band, e.g. black
    # text on a near-white strip between grey strips). Skip the 3px closest
    # to the strokes: that's the anti-aliasing zone, tinted by the text. ---
    if bg_rgb is not None and text_rgb_override is None:
        near = _dilate(ink, 3)
        halo = _dilate(near, 3) & ~near
        if halo.sum() >= 60:
            halo_col, halo_share = _dominant_color(inner[halo])
            # only override when the ring clearly sat on a different
            # surface; for same-surface cases the ring color is purer
            if (halo_share >= BG_MIN_SHARE
                    and np.abs(halo_col.astype(int)
                               - np.asarray(bg_rgb)).max() >= 20):
                bg_rgb = tuple(int(v) for v in halo_col)

    # --- font size: ink height -> em, clamped so the line can't outgrow
    # the measured ink width (detector box widths are unreliable) ---
    # columns only from the text row band: box edges crossing a chip border
    # would otherwise pollute the width with non-glyph "ink"
    band = ink[rows[0]:rows[-1] + 1] if len(rows) else ink
    cols = np.where(band.sum(axis=0) >= 1)[0]
    ratio = (latin_ink_ratio(line.text) if is_pure_latin(line.text)
             else CJK_INK_RATIO)
    ink_h_eff = max(ink_h_font_px - BLUR_PX, ink_h_font_px * 0.6)
    font_pt = ink_h_eff * px_to_slide_pt / ratio
    em_width = (_measure_em(line.text, narrow=font_pt >= NARROW_MIN_PT)
                or text_width_em(line.text))
    max_pt, tol, cliff_ok = None, 1.10, True
    clamp_pt = None
    if line.arc_sagitta and em_width > 0:
        # arc text must fit its chord with margin: the chord segments
        # overlap slightly at their joints, so err small
        max_pt, tol = chord_pt / em_width, 0.85
    elif em_width > 0 and len(cols):
        room = _chip_room_right(img, line, bg_rgb, rows, y0)
        ink_w_pt = float(cols[-1] - cols[0] + 1) * px_to_slide_pt
        if room is not None and room != float("inf"):
            # an obstruction bounds growth: the measured free space LESS a
            # small margin (text sized to just touch a grid line / card
            # border reads as crowding — p2 John card body, p8 VS Code 內建
            # / Working Copy pressed their column rule; the user wants one
            # step down), and the snap cliff guard stays off. Relative
            # tolerances + cliff let 21-em card bodies stab 80px through
            # their card border (p13) and put Git Hook's 化 onto the leader
            # dot (user-rejected).
            avail_pt = ((x1 - x0) + room) * px_to_slide_pt - OBSTACLE_MARGIN_PT
            max_pt = avail_pt / em_width
            tol = 1.0
            cliff_ok = False
            clamp_pt = max_pt
        elif room is None:
            max_pt = ink_w_pt / em_width
            tol = width_tolerance(em_width)
        # room == inf: open space, no width ceiling (slide edge still
        # caps). A document-wide ink-footprint ceiling was tried and
        # reverted: the source deck's CJK tracking is uniformly ~10%
        # tighter than YaHei, so a tolerance tight enough to catch an
        # oversized title (footprint ratio 1.114) also strangles normal
        # body text (1.098) — 56 lines dropped a step.
    chord_ceil = max_pt * tol if max_pt else None
    # the slide edge is a hard wall: chip-room growth and generous short-
    # line tolerances may not push the rendered text off the 960pt slide
    # (p15 不再滿足於… grew to 32pt × 29em from x=49pt → right edge 977pt)
    slide_ceil = None
    if em_width > 0 and not line.angle and not line.arc_sagitta:
        slide_ceil = (960.0 - x0 * px_to_slide_pt - 3.0) / em_width
    ceils = [c for c in (chord_ceil, slide_ceil) if c is not None]
    eff_ceil = min(ceils) if ceils else None
    est_pt = min(font_pt, eff_ceil) if eff_ceil else font_pt
    font_pt = snap_font_size(est_pt, max_pt=eff_ceil, tol=1.0)
    # cliff guard: the snap table jumps 17% between 20 and 24pt, so a
    # marginal width-ceiling violation can drop a line two visual steps
    # (p5 Git Hook 自動化: source latin runs 14% narrower than Arial, the
    # leader dot sits 6px past the box, ceiling 23.62 → snapped to 20
    # beside its true-24pt row twins). When the nearest size overshoots
    # the SOFT chord ceiling by ≤3% — AND at most ~3pt of rendered width
    # (relative-only let 21-em card body lines stab 50px through their
    # card border: p13 當技術分析… at 16pt vs a 15.7pt ceiling) — and the
    # fallback loses >10%, keep the nearest size. The slide-edge ceiling
    # stays hard (p15 must not re-overflow).
    if chord_ceil is not None and cliff_ok:
        best = min(FONT_SIZES, key=lambda s: abs(s - est_pt))
        if (best > font_pt and font_pt < 0.9 * best
                and best <= chord_ceil * 1.03
                and (best - chord_ceil) * em_width <= 3.0
                and (slide_ceil is None or best <= slide_ceil)):
            font_pt = float(best)
    # title footprint check: page titles sit in open space (no ceiling)
    # and their height estimate rides snap midpoints — p8's title at est
    # 39 rounded up to 40 and rendered 21% wider than the raster ink,
    # its tail crowding the page edge while the raster sits centered.
    # When the snapped title renders >7% wider than the raster footprint
    # and one step down still covers >=90% of it, take the smaller size
    # (1.09 missed the p1 cover title at 1.072 — user-rejected; the doc's
    # un-flagged titles sit at <=1.07). Long titles only: body text
    # measures a uniform ~10% footprint surplus (tighter source
    # tracking) and a document-wide rule strangles it; the p15 quote
    # blocks (em 4-6) scatter +-8% within one true size, so short lines
    # are exempt.
    if (font_pt >= NARROW_MIN_PT and em_width >= 10 and len(cols)
            and not line.angle and not line.arc_sagitta):
        ink_w_pt = float(cols[-1] - cols[0] + 1) * px_to_slide_pt
        if font_pt * em_width > 1.07 * ink_w_pt:
            smaller = [s for s in FONT_SIZES if s < font_pt]
            if smaller and smaller[-1] * em_width >= 0.90 * ink_w_pt:
                font_pt = smaller[-1]
    # only the slide-edge ceiling propagates to wrap-groups (max_fit_pt):
    # the chord/ink ceiling is soft — a few percent of in-card overshoot
    # is survivable and the group majority legitimately overrides it
    # (p12 嚴格的格式約束… clamps a hair under 14pt; exporting that pulled
    # its three true-14pt wrap-mates down to 12)
    max_fit_pt = slide_ceil

    # --- text color: blur drags edge pixels toward the background, so
    # average only the stroke cores (the ink pixels farthest from bg) ---
    px_flat = inner.reshape(-1, 3).astype(int)
    ink_flat = ink.reshape(-1)
    if text_rgb_override is not None:
        text_rgb = text_rgb_override
    elif ink_flat.sum() >= 10:
        text_rgb = _core_color(inner, ink, bg_ref)
    else:
        lum = px_flat @ np.array([0.299, 0.587, 0.114])
        darkest = px_flat[lum.argsort()[: max(1, len(px_flat) // 10)]]
        text_rgb = tuple(int(v) for v in darkest.mean(axis=0).round())

    # --- bold: the 72dpi source blur erases the weight signal for small
    # text (ink-coverage and stroke-width discriminators both measured
    # fully overlapping distributions), so: large text is bold (titles in
    # these decks always are). Small text: at >=16pt the template-matched
    # score decides (the raw stroke_rel threshold cannot — its bold/thin
    # distributions overlap there: Layer 3 標題 0.108 bold vs 多模態輸入
    # 0.098 regular; the per-text template absorbs the content, size and
    # contrast-cut systematics that cause the overlap). Below 16pt the
    # templates are noise-dominated, keep the extreme-stroke rule. ---
    stroke_rel = 0.0
    bold_r = None
    if bold_mode == "always":
        bold = True
    elif bold_mode == "never":
        bold = False
    elif font_pt >= 24:
        bold = True
    else:
        stroke_w = 0.0
        if len(rows):
            band = ink[rows[0]:rows[-1] + 1]
            n = int(band.sum())
            if n >= 30:
                survival1 = float(_erode(band).sum()) / n
                stroke_w = 2.0 / max(0.05, 1.0 - survival1)
                stroke_rel = stroke_w / max(1.0, ink_h_px)
        bold = stroke_rel >= 0.13
        if (stroke_w > 0 and font_pt >= TPL_COMPUTE_PT and bg_rgb is not None
                and not line.arc_sagitta):
            contrast = float(np.abs(np.array(text_rgb, dtype=int)
                                    - bg_ref.astype(int)).max())
            if contrast >= TPL_MIN_CONTRAST:
                bold_r = _template_bold_r(line.text, ink_h_px, stroke_w,
                                          contrast)
        if bold_r is not None and font_pt >= TPL_MIN_PT:
            bold = bold_r >= BOLD_R_THRESH

    # two-tone banner: when the box runs across a sharp background step,
    # split it into per-fill cover segments and re-measure each char's
    # color against its own segment's background (so dark-on-light text
    # reads dark, not the bright fill sampled as ink). Only horizontal
    # boxes with usable per-char boxes and genuinely different text colors
    # across the step take this path; everything else keeps one fill.
    # --- trim the cover horizontally past a leading/trailing vivid-color
    # icon the box overhangs: p13's red ✗ sits just left of 'Not That' and
    # bleeds into the box's left padding, so the chip-colored cover paints
    # over the icon. The discriminator is color SATURATION (max-min channel
    # > 60): a red ✗ / green ✓ status icon is vividly saturated, while
    # tinted text (blue/purple links) is only mildly tinted (< 60), so the
    # icon is separable from colored text. Only when the line's own first/
    # last character is a real letter/CJK (the icon is NOT part of the OCR
    # text — else trimming would double a leading '×' glyph).
    #   The saturation discriminator only works when the TEXT itself is not
    # vivid. A vividly colored heading/label (p2 orange 現狀痛點 sat 110, the
    # brown chart caption 傳統 RAG sat 78) saturates every column, so the
    # edge-walk stops on a sparse stroke column inside the text and trims a
    # real edge glyph — 現狀痛點's trailing 點 was exposed, 傳統 RAG doubled
    # its leading 傳. Deck-wide every trim fired only on such vivid-text
    # lines (real icon cases like p13 内容矛盾 share the text's brown and
    # never satisfied the walk), so skip the trim when the text is vivid: an
    # icon cannot be separated from same-colored text by saturation. ---
    cover_x0_px = cover_x1_px = None
    text_vivid = max(text_rgb) - min(text_rgb) > 60
    if (len(rows) and not line.angle and not line.arc_sagitta and line.text
            and not text_vivid):
        band = ink[rows[0]:rows[-1] + 1]
        bpx = inner[rows[0]:rows[-1] + 1].astype(int)
        sat = band & ((bpx.max(axis=2) - bpx.min(axis=2)) > 60)
        col_ink = band.sum(axis=0) >= 1
        col_sat = sat.sum(axis=0) >= 2
        all_c = np.where(col_ink)[0]

        def text_ok(ch):
            return ch.isalnum() or ord(ch) >= 0x2E80

        # an icon is separated from the text by a blank gap (the column just
        # before the text resumes is ink-free); a colored first/last glyph
        # of the text itself has no such gap
        if len(all_c) and text_ok(line.text[0]):
            x = all_c[0]
            while x <= all_c[-1] and (col_sat[x] or not col_ink[x]):
                x += 1
            if (x - all_c[0] > 10 and all_c[-1] - x > 20
                    and not col_ink[x - 1]):
                cover_x0_px = float(x0 + int(x))
        if len(all_c) and text_ok(line.text[-1]):
            x = all_c[-1]
            while x >= all_c[0] and (col_sat[x] or not col_ink[x]):
                x -= 1
            if (all_c[-1] - x > 10 and x - all_c[0] > 20
                    and not col_ink[x + 1]):
                cover_x1_px = float(x0 + int(x) + 1)

    # --- strikethrough: a thin horizontal line through the glyph midline
    # covers a much larger width fraction than any character-stroke row
    # (p9 ~~作廢內容~~: the strike row covers 0.86 of the width vs <=0.51 for
    # the glyph rows). Coverage, not a continuous run — the line breaks at
    # the small inter-glyph gaps. Horizontal multi-char lines only. ---
    strikethrough = False
    if (len(rows) and not line.angle and not line.arc_sagitta
            and len(line.text.strip().replace(" ", "")) >= 2):
        rr0, rr1 = rows[0], rows[-1]
        rh, rw = rr1 - rr0 + 1, max(1, ink.shape[1])
        med = float(np.median(ink[rows].sum(axis=1) / rw))
        for r in range(int(rr0 + 0.35 * rh), int(rr0 + 0.65 * rh)):
            cov = float(ink[r].sum()) / rw
            if cov >= 0.75 and cov >= 1.5 * med:
                strikethrough = True
                break

    # --- trailing footnote marker rendered as superscript (p10
    # 需要出處佐證[1]: the [1] is smaller and raised). Verify against the ink
    # (the literal markdown [^1] in a code block is full size / not raised):
    # the marker's ink must sit clearly above the body baseline and be
    # shorter than the body glyphs. ---
    superscript_tail = 0
    if (line.char_boxes and len(rows) and not line.angle
            and not line.arc_sagitta):
        t = line.text.strip()
        m = _SUPERSCRIPT_MARK.search(t)
        stripped = t.replace(" ", "")
        if m and len(line.char_boxes) == len(stripped):
            nmark = len(m.group().replace(" ", ""))
            if 0 < nmark < len(stripped):
                mxl = int(line.char_boxes[len(stripped) - nmark][1]) - x0
                if 0 < mxl < ink.shape[1]:
                    br = np.where(ink[:, :mxl].sum(axis=1) >= 3)[0]
                    mr = np.where(ink[:, mxl:].sum(axis=1) >= 2)[0]
                    if len(br) and len(mr):
                        bh = br[-1] - br[0] + 1
                        mh = mr[-1] - mr[0] + 1
                        raised = (br[-1] - mr[-1]) / max(1, bh)
                        if raised >= 0.2 and mh <= 0.92 * bh:
                            superscript_tail = nmark

    bg_segments = None
    highlight_removed = False
    runs = _split_color_runs(img, line, bg_ref)
    if (bg_rgb is not None and not line.angle and not line.arc_sagitta):
        local = _detect_bg_segments(inner)
        if local is not None:
            ox = float(max(0, x0))
            segs = [(ox + a, (ox + b if i < len(local) - 1 else float(x1)),
                     c) for i, (a, b, c) in enumerate(local)]
            seg_runs = _split_color_runs_segmented(img, line, segs)
            if seg_runs is not None:
                # the text color changes across the fills (two-tone banner
                # white↔black, or a colored highlight word): the fills are
                # required — removing them would hide white-on-dark text
                # under the base, and the cover boundary tracks the text-
                # color boundary so it stays aligned. Reproduce them.
                bg_segments = segs
                runs = seg_runs
                bg_rgb = segs[-1][2]
            else:
                # one text color across all fills = an inline highlight box
                # (Perl/Email/Markdown). Reproduced at the SOURCE column it
                # drifts off the rendered text (the output font's advances
                # differ, and a mid-line word accumulates the offset), which
                # the user rejected. The dark text reads fine on the base
                # fill alone, so drop the boxes and cover the whole line in
                # the BASE (page) fill — the fill matching the ring
                # background, NOT the widest fill (a highlight wider than the
                # surrounding text, e.g. Markdown.pl 1.0.1, would otherwise
                # paint the whole line lavender) — hiding the highlight.
                bg_rgb = min(local, key=lambda s: float(
                    np.abs(np.asarray(s[2]) - bg_ref).max()))[2]
                highlight_removed = True

    return Style(
        font_pt=font_pt,
        bold=bold,
        est_pt=est_pt,
        stroke_rel=stroke_rel,
        bold_r=bold_r,
        max_fit_pt=max_fit_pt,
        clamp_pt=clamp_pt,
        text_rgb=text_rgb,
        bg_rgb=bg_rgb,
        ink_top_px=ink_top_px,
        ink_bottom_px=ink_bottom_px,
        cover_x0_px=cover_x0_px,
        cover_x1_px=cover_x1_px,
        runs=runs,
        bg_segments=bg_segments,
        highlight_removed=highlight_removed,
        strikethrough=strikethrough,
        superscript_tail=superscript_tail,
    )
