"""Shared data structures for the pdf2ppt pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Line:
    """One OCR-recognized text line, in rendered-image pixel coordinates."""

    text: str
    bbox: tuple[float, float, float, float]  # axis-aligned x0, y0, x1, y1 in px
    score: float
    # tilted text (detector returned a rotated quad): clockwise degrees plus
    # the quad's center and deskewed (width, height); 0/None for horizontal
    angle: float = 0.0
    center: tuple[float, float] | None = None
    size: tuple[float, float] | None = None
    # per-character boxes (char, l, t, r, b) in image px for the
    # space-stripped text; None when word boxes were unusable
    char_boxes: list[tuple[str, float, float, float, float]] | None = None
    # arc text (ribbon banners): vertical deviation of the line's edges vs
    # its middle in px; positive = arch up, 0 = straight
    arc_sagitta: float = 0.0

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]


@dataclass
class Style:
    font_pt: float  # in slide point space (slide is fixed at 13.333 in wide)
    bold: bool
    text_rgb: tuple[int, int, int]
    bg_rgb: tuple[int, int, int] | None  # None => no cover fill (gradient/photo)
    # pre-snap size estimate (after the width clamp); lets the wrap-line
    # harmonizer judge whether two lines truly measured alike
    est_pt: float = 0.0
    # relative stroke width from the bold discriminator (0 when the
    # >=24pt rule decided); lets the bold harmonizer spot coin-flip
    # values near the 0.13 threshold
    stroke_rel: float = 0.0
    # template-matched weight score: 0 = the line's own text rendered in
    # YaHei Regular, 1 = YaHei Bold, at matched ink height / blur /
    # contrast cut. None when no template verdict (small text, unknown
    # bg, low contrast, unrenderable text). Primary bold signal >= 16pt.
    bold_r: float | None = None
    # hard width ceiling in pt (chord / chip-room / slide-edge fit, with
    # tolerance applied); None when nothing binds. Wrap-group unification
    # must not exceed any member's ceiling.
    max_fit_pt: float | None = None
    # obstacle-derived width ceiling in pt (a real grid line / card border
    # the room scan hit). Unlike max_fit_pt this is NOT the slide edge, but
    # the wrap-group harmonizer caps its unified size by it so a body block
    # constrained by its card can't be re-rounded up past the card boundary
    # (p2 John Gruber card body). None when no obstacle bounded the line.
    clamp_pt: float | None = None
    ink_top_px: float = 0.0     # top of the actual glyph ink, image px
    ink_bottom_px: float = 0.0  # bottom of the actual glyph ink, image px
    # horizontal cover bounds trimmed past a leading/trailing adjacent
    # graphic of a different color the OCR box overhangs (p13: the red ✗
    # left of 'Not That'); None means use the box edge as usual
    cover_x0_px: float | None = None
    cover_x1_px: float | None = None
    # multi-color lines: [(char_count, rgb), ...] over the space-stripped
    # text; None when the whole line is one color
    runs: list[tuple[int, tuple[int, int, int]]] | None = None
    # two-tone banner: the line runs across a sharp background step (p2's
    # BSD caption: dark-bg/white-text left, light-bg/dark-text right).
    # [(x0_px, x1_px, bg_rgb), ...] in image px; None for a single fill.
    bg_segments: list[tuple[float, float, tuple[int, int, int]]] | None = None
    # an inline highlight box was detected but dropped (it drifts off the
    # rendered text); cover the FULL OCR box vertically so the source
    # highlight is hidden cleanly rather than leaking past the glyph band
    highlight_removed: bool = False
    # vertically-stacked CJK text (p7 axis labels 純寫作 / 技術開發): the
    # box is tall & narrow with N square chars stacked; render with an
    # east-asian vertical text frame and size from the char (column) width
    vertical: bool = False


# Paragraph alignment markers (mirrors PP_ALIGN without importing pptx here)
ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"


@dataclass
class TextBlock:
    """One output shape: one or more lines sharing position and style."""

    lines: list[Line]
    style: Style
    align: str = ALIGN_LEFT
    _bbox: tuple[float, float, float, float] | None = field(default=None, repr=False)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        if self._bbox is None:
            self._bbox = (
                min(ln.bbox[0] for ln in self.lines),
                min(ln.bbox[1] for ln in self.lines),
                max(ln.bbox[2] for ln in self.lines),
                max(ln.bbox[3] for ln in self.lines),
            )
        return self._bbox
