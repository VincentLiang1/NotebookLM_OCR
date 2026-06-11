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
    ink_top_px: float = 0.0  # top of the actual glyph ink, image px
    # multi-color lines: [(char_count, rgb), ...] over the space-stripped
    # text; None when the whole line is one color
    runs: list[tuple[int, tuple[int, int, int]]] | None = None


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
