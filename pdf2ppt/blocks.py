"""Group OCR lines into text blocks.

Default behavior (like DeckEdit) is one shape per line; merging adjacent
lines into multi-paragraph shapes is opt-in via --merge-lines.
"""
from __future__ import annotations

import re

import numpy as np

from . import style as style_mod
from .models import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, Line, Style, TextBlock
from .style import (FONT_SIZES, _measure_em, snap_font_size, text_width_em)

_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")

# Tiny raster text (charts, flowcharts, terminal mockups) is near the 72dpi
# legibility floor: OCR output is mostly garbage and a cover + wrong text is
# worse than leaving the raster untouched. Thresholds calibrated on the
# sample deck (p11 zodiac wheel / terminal: 44 junk lines vs p9 timestamps,
# p5 pyramid chips, p8 isometric labels that must survive).
TINY_PT = 9              # at/below: drop unless provably clean
TINY_CJK_KEEP = 0.85     # clean small CJK chips (p5 基礎/進階 0.89–0.93)
TINY_LATIN_KEEP = 0.94   # clean small latin/digits (p9 timestamps 0.94+)
SMALL_PT = 14
SMALL_MIN_SCORE = 0.72   # small + this blurry is a misread (p3 <小> 0.57)
GLYPH_MIN_SCORE = 0.75   # short non-CJK soup at any size (p14 di 0.53)


def _rotated_decor_pair(a: Line, b: Line) -> bool:
    """Two steeply rotated latin-only quads that interpenetrate."""
    import math

    if not (a.angle and b.angle and abs(a.angle) >= 15 and abs(b.angle) >= 15):
        return False
    if not (a.center and b.center and a.size and b.size):
        return False
    if _CJK_RE.search(a.text) or _CJK_RE.search(b.text):
        return False
    th = math.radians(a.angle)
    dx, dy = b.center[0] - a.center[0], b.center[1] - a.center[1]
    u = dx * math.cos(th) + dy * math.sin(th)
    v = -dx * math.sin(th) + dy * math.cos(th)
    return (abs(u) < (a.size[0] + b.size[0]) / 2
            and abs(v) < (a.size[1] + b.size[1]) / 2)


def _is_illegible(line: Line, style: Style) -> bool:
    text = line.text.replace(" ", "")
    n_cjk = len(_CJK_RE.findall(text))
    if style.font_pt <= TINY_PT:
        if (n_cjk == len(text) and 2 <= len(text) <= 4
                and line.score >= TINY_CJK_KEEP):
            return False
        return line.score < TINY_LATIN_KEEP
    if style.font_pt <= SMALL_PT and line.score < SMALL_MIN_SCORE:
        return True
    return n_cjk == 0 and len(text) <= 3 and line.score < GLYPH_MIN_SCORE


def drop_illegible_lines(lines: list[Line], styles: list[Style],
                         ) -> tuple[list[Line], list[Style], int]:
    """Drop tiny/blurry junk lines so the raster stays visible.

    Three passes: per-line thresholds first, then a junk-neighborhood
    flood for the survivors the thresholds can't judge — isolated glyphs
    inside an illustration (p11 zodiac symbols read as m/Ⅱ/10 at score
    0.96+, or 'Python' 0.93 inside the garbled terminal block). A weak
    line (tiny, or a ≤2-char non-CJK glyph ≤20pt) sitting next to dropped
    junk with no strong kept line nearby belongs to the same illustration.
    Real small text survives because its neighbors are clean (p9
    timestamps) or it hugs a strong line (p8 'IP' under 'Attacker').

    Last, twin consistency: dropping half a set of sibling chips looks
    worse than either extreme (p9 BSP stack: 商業策略/資訊策略 scored
    0.60–0.69 and dropped while 應用系統/技術基礎 scored 0.77+ and
    survived — half covers, half raster on one illustration). A kept
    small line that is a twin of a dropped one (same font size, stacked
    in the same column, similar height, vertically adjacent) joins it."""
    n = len(lines)
    drop = [_is_illegible(ln, st) for ln, st in zip(lines, styles)]

    # steeply rotated latin pairs whose quads interpenetrate are book-spine
    # / billboard decoration (p10 VENDOR PITCH DECK at -28°: the detector
    # split it into two overlapping quads and one cover wipes the other
    # line's raster glyphs; VENDO is a truncated misread anyway). Editable
    # value is nil, raster fidelity wins — drop both. CJK chips are
    # exempt: rotated pyramid-band chips are real content.
    for i in range(n):
        for j in range(i + 1, n):
            if drop[i] and drop[j]:
                continue
            if _rotated_decor_pair(lines[i], lines[j]):
                drop[i] = drop[j] = True

    def weak(i: int) -> bool:
        text = lines[i].text.replace(" ", "")
        if styles[i].font_pt <= TINY_PT:
            return True
        return (styles[i].font_pt <= 20 and len(text) <= 2
                and not _CJK_RE.search(text))

    def near(i: int, j: int) -> bool:
        x0, y0, x1, y1 = lines[i].bbox
        pad = 2.0 * (y1 - y0)
        bx0, by0, bx1, by1 = lines[j].bbox
        return (bx0 < x1 + pad and bx1 > x0 - pad
                and by0 < y1 + pad and by1 > y0 - pad)

    def twin(i: int, j: int) -> bool:
        if styles[i].font_pt != styles[j].font_pt:
            return False
        xi0, yi0, xi1, yi1 = lines[i].bbox
        xj0, yj0, xj1, yj1 = lines[j].bbox
        hi, hj = yi1 - yi0, yj1 - yj0
        if abs(hi - hj) > 0.3 * max(hi, hj):
            return False
        if (min(xi1, xj1) - max(xi0, xj0)
                < 0.6 * min(xi1 - xi0, xj1 - xj0)):
            return False
        return max(yi0, yj0) - min(yi1, yj1) <= 0.8 * max(hi, hj)

    changed = True
    while changed:
        changed = False
        for i in range(n):
            if drop[i]:
                continue
            if weak(i):
                has_junk = any(drop[j] and near(i, j) for j in range(n))
                has_strong = any(not drop[j] and j != i and not weak(j)
                                 and near(i, j) for j in range(n))
                if has_junk and not has_strong:
                    drop[i] = True
                    changed = True
                    continue
            if (styles[i].font_pt <= SMALL_PT
                    and any(drop[j] and twin(i, j) for j in range(n))):
                drop[i] = True
                changed = True

    kept_lines = [ln for ln, d in zip(lines, drop) if not d]
    kept_styles = [st for st, d in zip(styles, drop) if not d]
    return kept_lines, kept_styles, sum(drop)


def lines_to_blocks(lines: list[Line], styles: list[Style],
                    merge: bool = False) -> list[TextBlock]:
    if not merge:
        return [TextBlock(lines=[ln], style=st, align=ALIGN_LEFT)
                for ln, st in zip(lines, styles)]

    groups: list[list[int]] = []
    for i, ln in enumerate(lines):
        target = None
        for g in groups:
            last = lines[g[-1]]
            if _belongs(last, ln) and styles[g[-1]].font_pt == styles[i].font_pt:
                target = g
                break
        if target is None:
            groups.append([i])
        else:
            target.append(i)

    blocks = []
    for g in groups:
        blocks.append(TextBlock(
            lines=[lines[i] for i in g],
            style=styles[g[0]],
            align=_detect_align([lines[i] for i in g]),
        ))
    return blocks


def _tpl_marginal_bold(st: Style) -> bool:
    """Template-decided bold whose r sits in the overturnable band."""
    return (st.bold and st.bold_r is not None
            and st.font_pt >= style_mod.TPL_MIN_PT
            and st.bold_r < style_mod.TPL_MARGINAL_R)


def harmonize_font_sizes(lines: list[Line], styles: list[Style],
                         ) -> None:
    """Wrapped lines of one paragraph must share a font size.

    The band measurement carries ~±3px of 72dpi blur noise, and the
    14/16pt snap boundary sits inside that noise: p10's "CB 詢圈案例/…"
    measured 12.6pt while its wrap-mate "法規或生辰八字" measured 14.1pt
    from visually identical glyphs. Per-line estimation cannot resolve
    this (widening the per-char consensus to all CJK lines just moved the
    flips elsewhere), so: group vertical neighbors that share style and
    whose pre-snap estimates differ within noise (12%), and when such a
    group snapped to two adjacent FONT_SIZES steps, unify — majority
    wins, ties re-snap the group's median estimate."""
    n = len(lines)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def ok(i: int) -> bool:
        return (not lines[i].angle and not lines[i].arc_sagitta
                and styles[i].est_pt > 0)

    for i in range(n):
        if not ok(i):
            continue
        for j in range(n):
            if j == i or not ok(j):
                continue
            a, b = (i, j) if lines[i].bbox[1] <= lines[j].bbox[1] else (j, i)
            la, lb = lines[a], lines[b]
            sa, sb = styles[a], styles[b]
            h = min(la.height, lb.height)
            gap = lb.bbox[1] - la.bbox[3]
            if not (-0.6 * h < gap < 0.45 * h):
                continue
            ox = min(la.bbox[2], lb.bbox[2]) - max(la.bbox[0], lb.bbox[0])
            if ox < 0.4 * min(la.width, lb.width):
                continue
            if sa.bold != sb.bold:
                # a marginal template-bold verdict must not break a wrap
                # group: 為體系化的高價值資產。 (14pt wrap tail, born
                # snapped 16 / r=0.146 barely over threshold) was locked
                # out of its 14pt regular wrap-mates, stranding it at
                # 16pt bold. Adjacency + matched style outweighs a
                # marginal r; the group majority then settles both size
                # and weight below.
                if not _tpl_marginal_bold(sa if sa.bold else sb):
                    continue
            if (sa.bg_rgb is None) != (sb.bg_rgb is None):
                continue
            # 25, not 16: photo-panel gradients drift the bg estimate
            # between wrap-mates (p7 成果/零/研究 measured 180/160/153 and
            # the trio snapped 18/20/20); cross-chip pairs are still
            # blocked by the adjacency gates above
            if sa.bg_rgb is not None and max(
                    abs(x - y) for x, y in zip(sa.bg_rgb, sb.bg_rgb)) > 25:
                continue
            if max(abs(x - y) for x, y in zip(sa.text_rgb, sb.text_rgb)) > 45:
                continue
            # 14%: p11's wrap pair V1 輿 V2 同時回 (11.8) / AI 要求比對
            # 差距 (13.5) differs 12.6%; a true 12-vs-14 pair differs ~19%
            if abs(sa.est_pt - sb.est_pt) > 0.14 * max(sa.est_pt, sb.est_pt):
                continue
            parent[find(i)] = find(j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    for g in groups.values():
        # marginal template-bold members follow a strict regular majority
        # of their wrap group (1v1 pairs stay untouched: 人類專屬：精選
        # at r=0.219 keeps its bold lead-in over its regular wrap tail)
        bold_n = sum(1 for i in g if styles[i].bold)
        if 0 < bold_n * 2 < len(g):
            for i in g:
                if _tpl_marginal_bold(styles[i]):
                    styles[i].bold = False
        sizes = sorted({styles[i].font_pt for i in g})
        if len(sizes) < 2:
            continue
        idx = sorted(FONT_SIZES.index(s) for s in sizes if s in FONT_SIZES)
        if len(idx) != len(sizes) or idx[-1] - idx[0] > len(sizes) - 1:
            continue  # only adjacent snap steps qualify as the same size
        counts = {s: sum(1 for i in g if styles[i].font_pt == s)
                  for s in sizes}
        best = max(counts.values())
        leaders = [s for s, c in counts.items() if c == best]
        if len(leaders) == 1:
            target = leaders[0]
        else:
            med = float(np.median([styles[i].est_pt for i in g]))
            target = snap_font_size(med)
        # a width-clamped member's ceiling is a physical constraint: the
        # unified size must fit every wrap-mate or the clamped line
        # overflows again (p15: 不再滿足於… capped at 31.3pt by the slide
        # edge; the tie-break median re-snapped the pair to 32 and pushed
        # it back off the slide — both lines belong at 28)
        ceil = min((styles[i].max_fit_pt for i in g
                    if styles[i].max_fit_pt is not None), default=None)
        if ceil is not None and target > ceil:
            smaller = [s for s in FONT_SIZES if s <= ceil]
            if smaller:
                target = smaller[-1]
        for i in g:
            styles[i].font_pt = target


def sync_clamped_twins(lines: list[Line], styles: list[Style]) -> None:
    """A width-clamped header drags its same-style page twins down one
    snap step. p5: Git Hook 自動化 wants 24pt (est 23.6) but a leader dot
    sits 6px past its box — rendering 24pt puts 化 onto the dot
    (user-rejected), so it clamps to 20. Its design twins 規則演化 (免疫
    力) / 跨頁連動修復 sit in open space at 24 — mixed 20/24 across one
    header family looks broken, and the user prefers the family at the
    clamped size. Gates are tight: bold headers only, est within 10%,
    same text color / background surface, similar line length, exactly
    one snap step apart."""
    n = len(lines)
    for i in range(n):
        si = styles[i]
        if not si.bold or si.est_pt <= 0:
            continue
        want = snap_font_size(si.est_pt)
        if (want not in FONT_SIZES or si.font_pt not in FONT_SIZES
                or FONT_SIZES.index(want) - FONT_SIZES.index(si.font_pt) != 1):
            continue
        emi = _measure_em(lines[i].text) or text_width_em(lines[i].text)
        for j in range(n):
            sj = styles[j]
            if j == i or not sj.bold or sj.font_pt != want or sj.est_pt <= 0:
                continue
            if abs(si.est_pt - sj.est_pt) > 0.10 * max(si.est_pt, sj.est_pt):
                continue
            if max(abs(a - b)
                   for a, b in zip(si.text_rgb, sj.text_rgb)) > 45:
                continue
            if (si.bg_rgb is None) != (sj.bg_rgb is None):
                continue
            if si.bg_rgb is not None and max(
                    abs(a - b) for a, b in zip(si.bg_rgb, sj.bg_rgb)) > 25:
                continue
            emj = _measure_em(lines[j].text) or text_width_em(lines[j].text)
            if emi and emj and not (0.6 <= emi / emj <= 1.6):
                continue
            sj.font_pt = si.font_pt


def clamp_row_neighbors(lines: list[Line], styles: list[Style],
                        px_to_slide_pt: float) -> None:
    """A line's rendered text must not run into its same-row right
    neighbor. estimate_style's width clamp only sees the line's own ink
    width with a generous tolerance, so a detector-split title renders
    wider than its raster and crowds the next box (p14: 'AI 協作的黃金
    法則' at 40pt is ~336pt wide but only 323pt exist before
    '(流程與資產篇)' starts). Bind the size to the neighbor's left edge,
    and when the neighbor is a near-touching same-style twin (one split
    headline), give it the same clamped size so the title stays uniform."""
    n = len(lines)
    order = sorted(range(n), key=lambda i: lines[i].bbox[0])
    for ai, i in enumerate(order):
        li, si = lines[i], styles[i]
        if li.angle or li.arc_sagitta:
            continue
        nb = None
        for j in order[ai + 1:]:
            lj = lines[j]
            if lj.angle or lj.arc_sagitta or lj.bbox[0] <= li.bbox[2]:
                continue
            ov = (min(li.bbox[3], lj.bbox[3])
                  - max(li.bbox[1], lj.bbox[1]))
            if ov < 0.5 * min(li.height, lj.height):
                continue
            if nb is None or lj.bbox[0] < lines[nb].bbox[0]:
                nb = j
        if nb is None:
            continue
        em = (_measure_em(li.text,
                          narrow=si.font_pt >= style_mod.NARROW_MIN_PT)
              or text_width_em(li.text))
        if em <= 0:
            continue
        avail_pt = (lines[nb].bbox[0] - li.bbox[0]) * px_to_slide_pt
        if si.font_pt * em <= avail_pt * 1.02:
            continue
        old = si.font_pt
        fit = [s for s in FONT_SIZES if s * em <= avail_pt * 1.02]
        if not fit:
            continue
        si.font_pt = fit[-1]
        sj = styles[nb]
        gap_px = lines[nb].bbox[0] - li.bbox[2]
        if (sj.font_pt == old and sj.bold == si.bold
                and gap_px * px_to_slide_pt < 0.5 * old
                and max(abs(a - b) for a, b in
                        zip(sj.text_rgb, si.text_rgb)) <= 45):
            sj.font_pt = si.font_pt


def _bold_promote_ok(st: Style) -> bool:
    """May a cohort vote flip this regular line to bold? Template-decided
    lines promote from r >= -0.05 (Karpathy Wiki 模式 measured -0.01 amid
    seven bold siblings; regular text in bold-majority cohorts hasn't
    measured above -0.05); stroke-decided lines keep the 0.115 band."""
    if st.bold_r is not None and st.font_pt >= style_mod.TPL_MIN_PT:
        return st.bold_r >= -0.05
    return st.stroke_rel >= 0.115


def _bold_demote_ok(st: Style) -> bool:
    """May a cohort vote strip this bold line? Template-decided lines
    demote only up to r = 0.22 (人類輸入 at 0.25 is real emphasis sitting
    alone among eight body lines). Stroke-decided lines keep the 0.15
    band, but a template second opinion of r >= 0.28 vetoes the strip —
    the 14pt card titles 1.先寫規則 (rel 0.144, r 0.43) and 3.人類給骨架
    (rel 0.133, r 0.31) are real bold drowned in a 17-line body cohort."""
    if st.bold_r is not None and st.font_pt >= style_mod.TPL_MIN_PT:
        return st.bold_r < style_mod.TPL_MARGINAL_R
    if st.bold_r is not None and st.bold_r >= 0.28:
        return False
    return st.stroke_rel <= 0.15


def harmonize_bold(lines: list[Line], styles: list[Style]) -> None:
    """Same-size stroke-decided lines on a page are one type family; the
    weight discriminators wobble near their thresholds (the measured
    stroke_rel spread of p5's four identical pyramid headings is
    0.123-0.140). Vote within each (page, font_pt) cohort — text color is
    deliberately NOT part of the key, the p5 headings are four different
    colors. Flip only measurements inside the per-metric ambiguity bands
    (_bold_promote_ok/_bold_demote_ok): clearly thick emphasis keeps bold
    (SKILL 0.185, 永遠不要覆蓋！ 0.175) and clearly thin text keeps
    regular. Promoting needs a 2/3 bold majority; demoting needs the bold
    share down at 1/5 — a same-size cohort often mixes box headers with
    body text (p10: Input:/OutputA at 4/12 bold are real headers; p11
    步驟 2 at 1/3 matches the other 步驟 headers), and stripping those
    would break真 emphasis, so only clearly isolated false positives
    demote."""
    groups: dict[float, list[int]] = {}
    for i, st in enumerate(styles):
        # stroke_rel == 0 -> decided by the >=24pt rule or --bold flag
        if st.stroke_rel > 0 and st.font_pt < 24:
            groups.setdefault(st.font_pt, []).append(i)
    for idxs in groups.values():
        if len(idxs) < 3:
            continue
        n = len(idxs)
        bold_n = sum(1 for i in idxs if styles[i].bold)
        if bold_n * 3 >= n * 2:
            for i in idxs:
                if not styles[i].bold and _bold_promote_ok(styles[i]):
                    styles[i].bold = True
        elif bold_n * 5 <= n:  # 1/5: p7's Before sat at 2/11 after the
            # size pass moved a member out of the cohort; the protected
            # header cases (p10 Input:/OutputA 4/12, p11 步驟 2 at 1/3)
            # stay well above this
            for i in idxs:
                if styles[i].bold and _bold_demote_ok(styles[i]):
                    styles[i].bold = False


def _belongs(a: Line, b: Line) -> bool:
    if a.angle or b.angle:  # tilted lines keep their own rotated shapes
        return False
    h = min(a.height, b.height)
    if not (0.75 <= b.height / max(a.height, 1e-6) <= 1.33):
        return False
    if b.bbox[1] - a.bbox[3] >= 0.7 * h:
        return False
    # x-ranges must overlap
    if b.bbox[0] > a.bbox[2] or a.bbox[0] > b.bbox[2]:
        return False
    left_aligned = abs(a.bbox[0] - b.bbox[0]) < 1.0 * h
    ca = (a.bbox[0] + a.bbox[2]) / 2
    cb = (b.bbox[0] + b.bbox[2]) / 2
    center_aligned = abs(ca - cb) < 1.0 * h
    return left_aligned or center_aligned


def _detect_align(lines: list[Line]) -> str:
    if len(lines) < 2:
        return ALIGN_LEFT
    lefts = np.array([ln.bbox[0] for ln in lines])
    rights = np.array([ln.bbox[2] for ln in lines])
    centers = (lefts + rights) / 2
    variances = {ALIGN_LEFT: lefts.var(), ALIGN_CENTER: centers.var(),
                 ALIGN_RIGHT: rights.var()}
    return min(variances, key=variances.get)
