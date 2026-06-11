"""Emit the DeckEdit-style PPTX: full-bleed background picture per slide plus
solid-fill cover shapes carrying editable, style-matched text."""
from __future__ import annotations

from io import BytesIO

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from .models import ALIGN_CENTER, ALIGN_RIGHT, TextBlock

SLIDE_W_EMU = 12192000  # 13.333 in, matches the example deck
EMU_PER_PT = 12700
COVER_PAD_PX = 3     # expand cover box to hide anti-aliased fringe of raster text
LEADING_COMP = 0.20  # em: gap between a top-anchored frame's top and glyph ink

PP_ALIGN_MAP = {ALIGN_CENTER: PP_ALIGN.CENTER, ALIGN_RIGHT: PP_ALIGN.RIGHT}


class DeckBuilder:
    def __init__(self, page_w_pt: float, page_h_pt: float, font_name: str,
                 cover: bool = True):
        self.prs = Presentation()
        self.prs.slide_width = Emu(SLIDE_W_EMU)
        self.slide_h_emu = round(SLIDE_W_EMU * page_h_pt / page_w_pt)
        self.prs.slide_height = Emu(self.slide_h_emu)
        self.blank_layout = self.prs.slide_layouts[6]
        self.font_name = font_name
        self.cover = cover

    def add_slide(self, png_bytes: bytes, blocks: list[TextBlock],
                  img_w: int, img_h: int,
                  wipes: list[tuple[tuple, tuple]] | None = None) -> None:
        """wipes: [(bbox_px, rgb)] — text-less cover rectangles that blank
        out regions (e.g. the NotebookLM watermark) with the background
        color."""
        slide = self.prs.slides.add_slide(self.blank_layout)
        pic = slide.shapes.add_picture(
            BytesIO(png_bytes), 0, 0,
            self.prs.slide_width, self.prs.slide_height,
        )
        pic.name = "Image 0"

        def ex(px: float) -> int:
            return round(px * SLIDE_W_EMU / img_w)

        def ey(px: float) -> int:
            return round(px * self.slide_h_emu / img_h)

        for i, (bbox, rgb) in enumerate(wipes or []):
            x0, y0, x1, y1 = bbox
            shape = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Emu(max(0, ex(x0))), Emu(max(0, ey(y0))),
                Emu(ex(x1) - ex(x0)), Emu(ey(y1) - ey(y0)),
            )
            shape.name = f"Wipe {i}"
            shape.shadow.inherit = False
            shape.line.fill.background()
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor(*rgb)

        for i, block in enumerate(blocks):
            nudge = round(LEADING_COMP * block.style.font_pt * EMU_PER_PT)
            tilted = (len(block.lines) == 1 and block.lines[0].angle
                      and block.lines[0].center and block.lines[0].size)
            if tilted:
                # rotated shape: deskewed quad size centered on the quad
                # center; PowerPoint rotates around the shape center, and
                # both angles are clockwise-positive
                ln = block.lines[0]
                width = ex(ln.size[0] + 2 * COVER_PAD_PX)
                height = ey(ln.size[1] + 2 * COVER_PAD_PX)
                left = ex(ln.center[0]) - width // 2
                top = ey(ln.center[1]) - height // 2 - nudge
                height += nudge
            else:
                x0, y0, x1, y1 = block.bbox
                left = ex(x0 - COVER_PAD_PX)
                width = ex(x1 + COVER_PAD_PX) - left
                # cover height follows the glyph ink band, not the OCR box:
                # detector boxes carry large vertical slack that would paint
                # over diagram lines above/below the text. The text frame
                # top is decoupled from the cover top via a margin inset.
                if len(block.lines) == 1 and block.style.ink_bottom_px:
                    cov_h = block.style.ink_bottom_px - block.style.ink_top_px
                    pad_v = max(4.0, 0.08 * cov_h)
                    cov_y0 = block.style.ink_top_px - pad_v
                    cov_y1 = block.style.ink_bottom_px + pad_v
                else:
                    cov_y0, cov_y1 = y0 - COVER_PAD_PX, y1 + COVER_PAD_PX
                ink_top = ey(block.style.ink_top_px)
                text_top = ink_top - nudge
                top = min(text_top, ey(cov_y0))
                height = ey(cov_y1) - top
                margin_top = max(0, text_top - top)

            shape = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Emu(max(0, left)), Emu(max(0, top)),
                Emu(width), Emu(height),
            )
            if tilted:
                shape.rotation = block.lines[0].angle
                margin_top = 0
            shape.name = f"Text {i}"
            shape.shadow.inherit = False
            shape.line.fill.background()
            if self.cover and block.style.bg_rgb is not None:
                shape.fill.solid()
                shape.fill.fore_color.rgb = RGBColor(*block.style.bg_rgb)
            else:
                shape.fill.background()

            tf = shape.text_frame
            # single-line shapes must never wrap: a size estimate a hair too
            # large would otherwise break the line and wreck the layout
            tf.word_wrap = len(block.lines) > 1
            tf.auto_size = None
            tf.vertical_anchor = MSO_ANCHOR.TOP
            tf.margin_left = tf.margin_right = tf.margin_bottom = 0
            tf.margin_top = Emu(margin_top)

            for j, line in enumerate(block.lines):
                para = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                para.alignment = PP_ALIGN_MAP.get(block.align, PP_ALIGN.LEFT)
                pieces = None
                if len(block.lines) == 1 and block.style.runs:
                    pieces = _split_text_runs(line.text, block.style.runs)
                if pieces is None:
                    pieces = [(line.text, block.style.text_rgb)]
                for piece, rgb in pieces:
                    run = para.add_run()
                    run.text = piece
                    font = run.font
                    font.size = Pt(block.style.font_pt)
                    font.bold = block.style.bold
                    font.name = self.font_name  # sets <a:latin> only
                    font.color.rgb = RGBColor(*rgb)
                    _set_east_asian_font(run, self.font_name)

    def save(self, path: str) -> None:
        self.prs.save(path)


def _split_text_runs(text: str, runs) -> list[tuple[str, tuple]] | None:
    """Split the line text into (piece, rgb) runs. `runs` counts cover the
    space-stripped text; spaces and any trailing extras (recovered
    punctuation) attach to the current/last run."""
    total = sum(n for n, _ in runs)
    stripped_len = sum(1 for c in text if c != " ")
    if stripped_len < total:
        return None  # text was transformed past recognition; play safe

    bounds = []  # exclusive cumulative end index per run
    acc = 0
    for n, _ in runs:
        acc += n
        bounds.append(acc)

    pieces: list[tuple[str, tuple]] = []
    buf, seg, idx = [], 0, 0
    for ch in text:
        if ch != " ":
            while seg < len(runs) - 1 and idx >= bounds[seg]:
                pieces.append(("".join(buf), runs[seg][1]))
                buf = []
                seg += 1
            idx += 1
        buf.append(ch)
    if buf:
        pieces.append(("".join(buf), runs[seg][1]))
    return [(p, rgb) for p, rgb in pieces if p]


def _set_east_asian_font(run, typeface: str) -> None:
    """python-pptx has no API for <a:ea>; without it CJK text silently falls
    back to the theme font. Insert it right after <a:latin> (schema order)."""
    rPr = run._r.get_or_add_rPr()
    latin = rPr.find(qn("a:latin"))
    ea = rPr.makeelement(qn("a:ea"), {"typeface": typeface})
    if latin is not None:
        rPr.insert(list(rPr).index(latin) + 1, ea)
    else:
        rPr.append(ea)
