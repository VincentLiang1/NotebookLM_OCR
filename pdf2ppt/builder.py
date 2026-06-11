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
WARP_DROP_RATIO = 0.13  # arch warp: rendered drop per unit of frame height

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
                  wipes: list[tuple[tuple, tuple]] | None = None,
                  img=None) -> None:
        """wipes: [(bbox_px, rgb)] — text-less cover rectangles that blank
        out regions (e.g. the NotebookLM watermark) with the background
        color. img: the page render (numpy RGB), used to clamp arc cover
        strips to their ribbon."""
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

        # arc covers go in first: two arc lines on the same ribbon
        # interpenetrate, and a later line's cover strips must not paint
        # over an earlier line's text segments
        arc_blocks = [(i, b) for i, b in enumerate(blocks)
                      if len(b.lines) == 1 and b.lines[0].arc_sagitta]
        for i, block in arc_blocks:
            self._add_arc_cover(slide, block, i, ex, ey,
                                px_per_pt=img_w / 960.0, img=img)

        for i, block in enumerate(blocks):
            if len(block.lines) == 1 and block.lines[0].arc_sagitta:
                self._add_arc_segments(slide, block, i, ex, ey,
                                       px_per_pt=img_w / 960.0)
                continue
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

            fill = self.cover and block.style.bg_rgb is not None
            if not tilted and fill and text_top < ey(cov_y0):
                # the leading-compensation zone above the ink would carry
                # the fill onto the previous line's descenders in tight
                # rows; split into a cover rect plus a transparent text box
                cover = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, Emu(max(0, left)),
                    Emu(max(0, ey(cov_y0))),
                    Emu(width), Emu(ey(cov_y1) - ey(cov_y0)),
                )
                cover.name = f"Text {i} bg"
                cover.shadow.inherit = False
                cover.line.fill.background()
                cover.fill.solid()
                cover.fill.fore_color.rgb = RGBColor(*block.style.bg_rgb)
                fill = False
                top = text_top
                height = ey(cov_y1) - top
                margin_top = 0

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
            if fill:
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

    @staticmethod
    def _arc_geometry(block, px_per_pt: float):
        ln = block.lines[0]
        x0, y0, x1, y1 = ln.bbox
        glyph_h = min(block.style.font_pt * 1.2 * px_per_pt, (y1 - y0) * 0.8)
        if ln.arc_sagitta > 0:  # arch up: middle at top, edges at bottom
            y_mid, y_edge = y0 + glyph_h / 2, y1 - glyph_h / 2
        else:                   # arch down
            y_mid, y_edge = y1 - glyph_h / 2, y0 + glyph_h / 2
        return ln, x0, y0, x1, y1, glyph_h, y_mid, y_edge

    def _add_arc_cover(self, slide, block, i: int, ex, ey,
                       px_per_pt: float, img=None) -> None:
        """Cover strips tracing the arc band (drawn before ALL arc text)."""
        import numpy as np

        ln, x0, y0, x1, y1, glyph_h, y_mid, y_edge = \
            self._arc_geometry(block, px_per_pt)
        style = block.style

        if not (self.cover and style.bg_rgb is not None):
            return

        bg = np.asarray(style.bg_rgb, dtype=int)

        def on_ribbon(px_x: float, px_y: float) -> bool:
            if img is None:
                return True
            h_img, w_img = img.shape[:2]
            xi = min(max(int(px_x), 0), w_img - 1)
            yi = min(max(int(px_y), 0), h_img - 1)
            return int(np.abs(img[yi, xi].astype(int) - bg).max()) < 70

        # cover strips along the arc rather than one blocky rectangle:
        # reconstruct the parabola from the box (edges hold the glyphs at
        # one end of the box, the middle at the other)
        n = 12
        xc, half_w = (x0 + x1) / 2, (x1 - x0) / 2
        for s in range(n):
            sx0 = x0 + (x1 - x0) * s / n
            sx1 = x0 + (x1 - x0) * (s + 1) / n
            t = ((sx0 + sx1) / 2 - xc) / half_w
            yc = y_mid + (y_edge - y_mid) * t * t
            pad = max(COVER_PAD_PX, 0.5 * glyph_h)
            # shrink the strip's edges until they sit on the ribbon: a
            # rectangle staircase that pokes past the ribbon boundary onto
            # the page background reads as jagged red teeth
            xs = tuple(sx0 + (sx1 - sx0) * f for f in (0.12, 0.5, 0.88))
            top = yc - glyph_h / 2 - pad
            while (top < yc - glyph_h * 0.25
                   and not all(on_ribbon(x, top) for x in xs)):
                top += 1
            bot = yc + glyph_h / 2 + pad
            while (bot > yc + glyph_h * 0.25
                   and not all(on_ribbon(x, bot) for x in xs)):
                bot -= 1
            # the ribbon is shaded, one global color shows as a patch —
            # fill each strip with its own local ribbon color
            fill_rgb = style.bg_rgb
            if img is not None:
                region = img[max(0, int(top)):max(1, int(bot)),
                             max(0, int(sx0)):max(1, int(sx1))]
                if region.size:
                    px = region.reshape(-1, 3).astype(int)
                    near = np.abs(px - bg).max(axis=1) < 70
                    if near.sum() >= 30:
                        fill_rgb = tuple(int(v) for v in
                                         np.median(px[near], axis=0))
            strip = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Emu(max(0, ex(sx0 - 1))), Emu(max(0, ey(top))),
                Emu(ex(sx1 + 1) - ex(sx0 - 1)), Emu(ey(bot) - ey(top)),
            )
            strip.name = f"Text {i} cover {s}"
            strip.shadow.inherit = False
            strip.line.fill.background()
            strip.fill.solid()
            strip.fill.fore_color.rgb = RGBColor(*fill_rgb)

    def _add_arc_segments(self, slide, block, i: int, ex, ey,
                          px_per_pt: float) -> None:
        """The arc text: chord segments along the parabola, each a small
        rotated shape at the local tangent. PowerPoint's prstTxWarp arch
        was tried first and abandoned — its drop/frame scaling is opaque
        and uncontrollable (see git history for the calibration attempts)."""
        import math

        ln, x0, y0, x1, y1, glyph_h, y_mid_t, y_edge_t = \
            self._arc_geometry(block, px_per_pt)
        style = block.style
        xc, half_w = (x0 + x1) / 2, (x1 - x0) / 2
        n_seg = max(3, min(6, round((x1 - x0) / (3.0 * max(glyph_h, 1)))))
        text = ln.text
        # split by accumulated advance width (mixed CJK/latin) and snap to
        # a nearby space so words like PDF are not cut in half
        adv = [1.0 if ord(c) >= 0x2E80 else (0.33 if c == " " else 0.52)
               for c in text]
        total = sum(adv) or 1.0
        bounds = [0]
        acc, target_idx = 0.0, 1
        for idx, a in enumerate(adv):
            acc += a
            while target_idx < n_seg and acc >= total * target_idx / n_seg:
                cut = idx + 1
                for off in (0, 1, -1, 2, -2):
                    j = cut + off
                    if 0 < j < len(text) and text[j - 1] == " ":
                        cut = j
                        break
                bounds.append(max(cut, bounds[-1]))
                target_idx += 1
        bounds.append(len(text))
        # pack segments by their actual text width, centered on the chord:
        # spreading them across the full chord turns the font-cap slack
        # into visible gaps between segments
        font_px = style.font_pt * px_per_pt
        em_at = [0.0]
        for s in range(n_seg):
            seg_em_s = sum(adv[bounds[s]:bounds[s + 1]])
            em_at.append(em_at[-1] + seg_em_s)
        em_total = em_at[-1] or 1.0
        span = min(x1 - x0, em_total * font_px * 1.0)
        sx_origin = xc - span / 2
        for s in range(n_seg):
            seg_text = text[bounds[s]:bounds[s + 1]].strip()
            if not seg_text:
                continue
            em_mid = (em_at[s] + em_at[s + 1]) / 2
            cx_seg = sx_origin + span * em_mid / em_total
            t = (cx_seg - xc) / half_w
            yc = y_mid_t + (y_edge_t - y_mid_t) * t * t
            slope = 2 * (y_edge_t - y_mid_t) * t / half_w
            ang = math.degrees(math.atan(slope))
            seg_em = sum(1.0 if ord(c) >= 0x2E80 else
                         (0.33 if c == " " else 0.52) for c in seg_text)
            width = Emu(round(seg_em * style.font_pt * EMU_PER_PT * 1.06))
            height = Emu(ey(yc + glyph_h / 2) - ey(yc - glyph_h / 2))
            left = Emu(ex(cx_seg) - width // 2)
            top = Emu(ey(yc) - height // 2)
            seg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top,
                                         width, height)
            seg.name = f"Text {i}.{s}"
            seg.rotation = ang
            seg.shadow.inherit = False
            seg.line.fill.background()
            seg.fill.background()
            tf = seg.text_frame
            tf.word_wrap = False
            tf.auto_size = None
            tf.margin_left = tf.margin_right = 0
            tf.margin_top = tf.margin_bottom = 0
            para = tf.paragraphs[0]
            para.alignment = PP_ALIGN.CENTER
            run = para.add_run()
            run.text = seg_text
            font = run.font
            font.size = Pt(style.font_pt)
            font.bold = style.bold
            font.name = self.font_name
            font.color.rgb = RGBColor(*style.text_rgb)
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
