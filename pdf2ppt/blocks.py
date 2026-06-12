"""Group OCR lines into text blocks.

Default behavior (like DeckEdit) is one shape per line; merging adjacent
lines into multi-paragraph shapes is opt-in via --merge-lines.
"""
from __future__ import annotations

import numpy as np

from .models import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, Line, Style, TextBlock
from .style import FONT_SIZES, snap_font_size


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
                continue
            if (sa.bg_rgb is None) != (sb.bg_rgb is None):
                continue
            if sa.bg_rgb is not None and max(
                    abs(x - y) for x, y in zip(sa.bg_rgb, sb.bg_rgb)) > 16:
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
        for i in g:
            styles[i].font_pt = target


def harmonize_bold(lines: list[Line], styles: list[Style]) -> None:
    """Same-size stroke-decided lines on a page are one type family; the
    stroke-width discriminator coin-flips near its 0.13 threshold (the
    measured spread of p5's four identical pyramid headings is
    0.123-0.140). Vote within each (page, font_pt) cohort — text color is
    deliberately NOT part of the key, the p5 headings are four different
    colors. Flip only measurements inside the ambiguity band: clearly
    thick emphasis keeps bold (SKILL 0.185, 永遠不要覆蓋！ 0.175) and
    clearly thin text keeps regular. Promoting needs a 2/3 bold majority;
    demoting needs the bold share down at 1/6 — a same-size cohort often
    mixes box headers with body text (p10: Input:/OutputA at 4/12 bold
    are real headers; p11 步驟 2 at 1/3 matches the other 步驟 headers),
    and stripping those would break真 emphasis, so only clearly isolated
    false positives demote."""
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
                if not styles[i].bold and styles[i].stroke_rel >= 0.115:
                    styles[i].bold = True
        elif bold_n * 5 <= n:  # 1/5: p7's Before sat at 2/11 after the
            # size pass moved a member out of the cohort; the protected
            # header cases (p10 Input:/OutputA 4/12, p11 步驟 2 at 1/3)
            # stay well above this
            for i in idxs:
                if styles[i].bold and styles[i].stroke_rel <= 0.15:
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
