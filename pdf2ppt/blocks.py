"""Group OCR lines into text blocks.

Default behavior (like DeckEdit) is one shape per line; merging adjacent
lines into multi-paragraph shapes is opt-in via --merge-lines.
"""
from __future__ import annotations

import numpy as np

from .models import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, Line, Style, TextBlock


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
