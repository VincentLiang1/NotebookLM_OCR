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
CJK_INK_RATIO = 0.91
LATIN_INK_RATIO = 0.72  # cap height + descender for a typical latin line

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


def snap_font_size(pt: float, max_pt: float | None = None) -> float:
    best = min(FONT_SIZES, key=lambda s: abs(s - pt))
    if max_pt is not None and best > max_pt:
        smaller = [s for s in FONT_SIZES if s <= max_pt]
        if smaller:
            best = smaller[-1]
    return best


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

    real = [s[1] for s in segments if s[1] is not None]
    if len(segments) < 2 or not real:
        return None
    spread = max(np.abs(a - b).max() for a in real for b in real)
    if spread < RUN_SPLIT_DIST:
        return None
    fallback = real[0]
    return [(s[0], tuple(int(v) for v in (s[1] if s[1] is not None else fallback)))
            for s in segments]


def estimate_style(img: np.ndarray, line: Line, px_to_slide_pt: float,
                   bold_mode: str = "auto") -> Style:
    """px_to_slide_pt: slide points per image pixel (960 / image_width).
    bold_mode: 'auto' | 'never' | 'always'.
    """
    x0, y0, x1, y1 = (int(round(v)) for v in line.bbox)

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
            if survs[bg_i] - survs[tx_i] > 0.15:
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
        ink_h_px = float(rows[-1] - rows[0] + 1)
        ink_top_px = y0 + float(rows[0])
    else:  # OCR found text the ink threshold can't see; fall back to box
        ink_h_px = float(y1 - y0)
        ink_top_px = float(y0)

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
    cols = np.where(ink.sum(axis=0) >= 1)[0]
    ratio = LATIN_INK_RATIO if is_pure_latin(line.text) else CJK_INK_RATIO
    font_pt = ink_h_px * px_to_slide_pt / ratio
    em_width = text_width_em(line.text)
    max_pt = None
    if em_width > 0 and len(cols):
        ink_w_pt = float(cols[-1] - cols[0] + 1) * px_to_slide_pt
        max_pt = ink_w_pt / em_width * 1.05
    font_pt = snap_font_size(min(font_pt, max_pt) if max_pt else font_pt,
                             max_pt=max_pt)

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

    # --- bold: ink coverage over the tight ink bbox ---
    if bold_mode == "always":
        bold = True
    elif bold_mode == "never":
        bold = False
    else:
        if len(rows) and len(cols):
            tight = ink[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
            ink_ratio = float(tight.mean())
        else:
            ink_ratio = 0.0
        # calibrated on the example deck: bold CJK labels measure >=0.33,
        # regular latin labels <=0.29 (tiny blurry text reads high — accepted)
        threshold = 0.32 if is_pure_latin(line.text) else 0.28
        bold = ink_ratio > threshold

    return Style(
        font_pt=font_pt,
        bold=bold,
        text_rgb=text_rgb,
        bg_rgb=bg_rgb,
        ink_top_px=ink_top_px,
        runs=_split_color_runs(img, line, bg_ref),
    )
