"""Estimate text style (size, bold, colors) from the rendered page image.

All font sizes are computed in SLIDE point space (the PDF page may be any
physical size; the slide is fixed at 13.333 in wide), derived from the tight
ink bounds inside each OCR box — the detector's quads carry inconsistent
padding, so their raw height is a poor size signal.
"""
from __future__ import annotations

import numpy as np

from .models import Line, Style

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

# Rough advance widths (em) per character class, for the overflow clamp
_EM_CJK = 1.0
_EM_LATIN = 0.52
_EM_SPACE = 0.33


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


def _measure_em(text: str) -> float | None:
    """Exact advance width of the text in em, measured with the real
    output font (Microsoft YaHei, Noto fallback); None when no font file
    is available."""
    global _MEASURE_FONT
    if _MEASURE_FONT is None:
        import os

        from PIL import ImageFont

        for path in (
            r"C:\Windows\Fonts\msyh.ttc",
            os.path.expandvars(
                r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\NotoSansTC-Regular.ttf"),
            r"C:\Windows\Fonts\NotoSansTC-VF.ttf",
        ):
            if os.path.exists(path):
                _MEASURE_FONT = ImageFont.truetype(path, 100)
                break
        else:
            _MEASURE_FONT = False
    if not _MEASURE_FONT:
        return None
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


ROOM_MAX_FACTOR = 1.5   # scan at most this many line-heights of side room
ROOM_BG_DIST = 40       # a column is "free" if its pixels match the cover bg
ROOM_FREE_FRAC = 0.9


def _chip_room_right(img: np.ndarray, line: Line, bg_rgb, rows,
                     y0: int) -> float | None:
    """How many pixels of unobstructed background extend past the box's
    right edge before a border/edge — the true space the rendered text may
    grow into. None when there is no cover color or no measured rows."""
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
    free = (np.abs(strip - np.asarray(bg_rgb)).max(axis=2)
            < ROOM_BG_DIST).mean(axis=0) >= ROOM_FREE_FRAC
    room = 0
    for ok in free:
        if not ok:
            break
        room += 1
    return float(room)


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


def estimate_style(img: np.ndarray, line: Line, px_to_slide_pt: float,
                   bold_mode: str = "auto") -> Style:
    """px_to_slide_pt: slide points per image pixel (960 / image_width).
    bold_mode: 'auto' | 'never' | 'always'.
    """
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
                text_rgb_override = tuple(int(v) for v in clusters[1 - bg_i][0])
        if bg_rgb is None and clusters:
            # gradient/photo: no cover, but keep a reference color so the
            # ink mask below can still find the glyphs
            bg_ref = clusters[0][0]

    # --- ink mask ---
    ink = np.abs(inner.astype(int) - bg_ref.astype(int)).max(axis=2) > INK_DIST

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
    em_width = _measure_em(line.text) or text_width_em(line.text)
    max_pt, tol = None, 1.10
    if line.arc_sagitta and em_width > 0:
        # arc text must fit its chord with margin: the chord segments
        # overlap slightly at their joints, so err small
        max_pt, tol = chord_pt / em_width, 0.85
    elif em_width > 0 and len(cols):
        room = _chip_room_right(img, line, bg_rgb, rows, y0)
        if room is not None:
            # measured space before the chip/cell border binds directly
            avail_pt = ((x1 - x0) + room) * px_to_slide_pt
            max_pt, tol = avail_pt / em_width, 1.02
        else:
            ink_w_pt = float(cols[-1] - cols[0] + 1) * px_to_slide_pt
            max_pt = ink_w_pt / em_width
            tol = width_tolerance(em_width)
    est_pt = min(font_pt, max_pt * tol) if max_pt else font_pt
    font_pt = snap_font_size(est_pt, max_pt=max_pt, tol=tol)

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
    # these decks always are), small text only when strokes are extreme ---
    stroke_rel = 0.0
    if bold_mode == "always":
        bold = True
    elif bold_mode == "never":
        bold = False
    elif font_pt >= 24:
        bold = True
    else:
        if len(rows):
            band = ink[rows[0]:rows[-1] + 1]
            n = int(band.sum())
            if n >= 30:
                survival1 = float(_erode(band).sum()) / n
                stroke_w = 2.0 / max(0.05, 1.0 - survival1)
                stroke_rel = stroke_w / max(1.0, ink_h_px)
        bold = stroke_rel >= 0.13

    return Style(
        font_pt=font_pt,
        bold=bold,
        est_pt=est_pt,
        stroke_rel=stroke_rel,
        text_rgb=text_rgb,
        bg_rgb=bg_rgb,
        ink_top_px=ink_top_px,
        ink_bottom_px=ink_bottom_px,
        runs=_split_color_runs(img, line, bg_ref),
    )
