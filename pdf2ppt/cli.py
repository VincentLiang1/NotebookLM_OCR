"""Command-line interface and pipeline orchestration."""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pymupdf

from .blocks import (clamp_row_neighbors, drop_illegible_lines, drop_unreproducible,
                     harmonize_across_dropped, harmonize_bold, harmonize_code_block_latin,
                     harmonize_chip_bg, harmonize_row_twin_bold,
                     merge_row_title_fragments, propagate_column_clamp,
                     propagate_row_clamp, reeval_clamped_bold,
                     sync_clamped_twins, harmonize_font_sizes,
                     harmonize_stacked_overlap_size, lines_to_blocks)
from .builder import DeckBuilder
from .ocr import OcrEngine
from .render import render_page
from .style import estimate_style


# The product renames itself and old exports keep the old mark, so this is a
# list rather than one literal: 'NotebookLM' up to mid-2026, 'Gemini Notebook'
# after it (spelled without the space because the match runs on de-spaced
# text). Compared case-folded: the mark is set small and light, where the rec
# model's casing is the least trustworthy part of an otherwise easy read.
# Exit code for a run that produced a deck but had to degrade at least one
# page. Neither 0 nor 1 is honest here: 0 makes the GUI announce plain success
# over a page that lost its text, and 1 reports failure over a file that is
# perfectly usable. ⚠️ pdf2ppt_gui_2.py carries its own copy of this number
# (a test pins it to this one).
PARTIAL_RC = 3

WATERMARK_MARKS = ("notebooklm", "gemininotebook")
WATERMARK_STRAY_MAX = 6  # chars OCR may glue on ahead of the mark


def is_watermark(line, style, img_w: int, img_h: int) -> bool:
    """The export watermark: logo + brand name in the bottom-right corner.

    Keyed on the brand name because the corner gate alone cannot carry it — a
    full-width caption band reaches into the same corner. OCR sometimes merges
    the logo AND the faint page-id stamp into the text ('P92F2NotebookLM'), so
    a few leading stray chars are allowed before the mark."""
    text = line.text.replace(" ", "").casefold()
    mark = next((m for m in WATERMARK_MARKS if text.endswith(m)), None)
    if mark is None or len(text) - len(mark) > WATERMARK_STRAY_MAX:
        return False
    x0, y0, x1, y1 = line.bbox
    return (y0 > 0.85 * img_h and x1 > 0.65 * img_w
            and style.bg_rgb is not None)


WIPE_PAD_PX = 2       # absolute pad for the anti-aliased fringe of the pill
WIPE_INK_DIST = 40    # per-channel distance from bg that counts as ink (the
                      # pill is faint, so this is looser than style.INK_DIST)
WIPE_INK_FRAC = 0.05  # columns of the strip a row needs inked to count as part
                      # of the mark: a page rule crossing the strip inks 1-2%
                      # of them, the mark's thinnest row (logo tips) inks 10%
WIPE_COL_FRAC = 0.10  # the same test the other way round, over the band the
                      # row walk just measured
# Blank rows/columns, relative to the box height, that separate the mark from
# unrelated page content. Left is loosest: it must bridge the word space ahead
# of the brand name should the logo fall outside the box. Right is tightest:
# nothing of the mark follows the last glyph, and the page's right rule runs
# 8px past it.
WIPE_GAP_FRAC, WIPE_GAP_L_FRAC, WIPE_GAP_R_FRAC = 0.15, 0.35, 0.10
WIPE_GAP_MIN_PX = 4
WIPE_SHRINK_FRAC = 0.3  # how far inside the OCR box a measured edge may pull:
                        # the box overshoots the glyphs, far enough on both
                        # decks measured to land on the page rule beside them


def _contiguous_ink(inked, seed: int, gap: int) -> tuple[int, int]:
    """Extent of the mark along one axis: walk outward from a row/column known
    to be on it and stop at the first run of `gap` blank ones.

    Taking the outermost inked row of the window instead would swallow
    whatever else happens to sit near the corner — a card edge 14 rows above
    the mark, the page's bottom rule 16 rows below it — and the clamp would
    then paint over it. The mark's own parts (logo, text, pill) have no blank
    row between them, so a small gap separates the two cases."""
    lo = hi = seed
    while True:
        above = np.flatnonzero(inked[max(0, lo - gap):lo])
        if not above.size:
            break
        lo = max(0, lo - gap) + int(above[0])
    while True:
        below = np.flatnonzero(inked[hi + 1:hi + 1 + gap])
        if not below.size:
            break
        hi = hi + 1 + int(below[-1])
    return lo, hi


def watermark_wipe(line, style, img=None) -> tuple[tuple, tuple]:
    """Cover box for the watermark: the logo icon ahead of the brand name, the
    name itself, and the faint pill behind them.

    The extent is MEASURED on the render, not taken as a multiple of the OCR
    box: detector padding is inconsistent (CLAUDE.md's box-padding invariant)
    and the logo can overshoot the box, so nothing about the box predicts the
    mark. Each edge is clamped into [tight, wide] so a failed scan degrades to
    known-good behaviour instead of eating slide content — see CLAUDE.md
    浮水印遮擋範圍 for the calibration."""
    x0, y0, x1, y1 = line.bbox
    h = max(1.0, y1 - y0)
    tight_t, tight_b = y0 - 0.05 * h, y1 + 0.12 * h
    wide_t, wide_b = y0 - 0.35 * h, y1 + 0.40 * h
    wide_l, wide_r = x0 - 1.8 * h, x1 + 0.3 * h
    shrink_l, shrink_r = x0 + WIPE_SHRINK_FRAC * h, x1 - WIPE_SHRINK_FRAC * h
    ink_t, ink_b = tight_t, tight_b
    ink_l, ink_r = wide_l, wide_r

    if img is not None and style.bg_rgb is not None:
        ih, iw = img.shape[:2]
        xs0, xs1 = max(0, int(wide_l)), min(iw, int(wide_r))
        win_t, win_b = max(0, int(wide_t)), min(ih, int(wide_b))
        if xs1 - xs0 >= 4 and win_b - win_t >= 4:
            strip = img[win_t:win_b, xs0:xs1].astype(int)
            bg = np.asarray(style.bg_rgb, dtype=int)
            ink = np.abs(strip - bg).max(axis=2) > WIPE_INK_DIST
            rows_inked = ink.sum(axis=1) > max(1, int(WIPE_INK_FRAC * (xs1 - xs0)))
            # seed the walk in the middle 60% of the OCR box, which is the
            # text band: the box edges are where foreign ink creeps in
            b0 = min(max(0, int(y0 + 0.2 * h) - win_t), rows_inked.size)
            b1 = min(max(b0, int(y1 - 0.2 * h) - win_t), rows_inked.size)
            rows = np.flatnonzero(rows_inked[b0:b1])
            if rows.size:
                seed = b0 + int(rows[rows.size // 2])
                lo, hi = _contiguous_ink(rows_inked, seed,
                                         max(WIPE_GAP_MIN_PX, int(WIPE_GAP_FRAC * h)))
                ink_t = win_t + lo - WIPE_PAD_PX
                ink_b = win_t + hi + WIPE_PAD_PX

                # ...then the same walk sideways, over the band just measured
                band = ink[lo:hi + 1]
                cols_inked = band.sum(axis=0) > max(1, int(WIPE_COL_FRAC * len(band)))
                c0 = min(max(0, int(x0) - xs0), cols_inked.size)
                c1 = min(max(c0, int(x1) - xs0), cols_inked.size)
                cols = np.flatnonzero(cols_inked[c0:c1])
                if cols.size:
                    left = _contiguous_ink(cols_inked, c0 + int(cols[0]),
                                           max(WIPE_GAP_MIN_PX, int(WIPE_GAP_L_FRAC * h)))[0]
                    right = _contiguous_ink(cols_inked, c0 + int(cols[-1]),
                                            max(WIPE_GAP_MIN_PX, int(WIPE_GAP_R_FRAC * h)))[1]
                    ink_l = xs0 + left - WIPE_PAD_PX
                    ink_r = xs0 + right + WIPE_PAD_PX

    # the clamp is an identity on the tight fallback, so one exit covers both
    top = min(tight_t, max(wide_t, ink_t))
    bot = max(tight_b, min(wide_b, ink_b))
    lft = min(shrink_l, max(wide_l, ink_l))
    rgt = max(shrink_r, min(wide_r, ink_r))
    return (lft, top, rgt, bot), style.bg_rgb


def parse_pages(spec: str, page_count: int) -> list[int]:
    """'1-5,8' -> zero-based page indices."""
    indices: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            indices.extend(range(int(a) - 1, int(b)))
        else:
            indices.append(int(part) - 1)
    return [i for i in indices if 0 <= i < page_count]


def main(argv: list[str] | None = None) -> int:
    # line_buffering as well as the encoding: stdout is block-buffered when it
    # is not a console (`pdf2ppt … > run.txt`), while the OCR engine logs to
    # stderr unbuffered, so the captured file interleaves the two wrongly --
    # warnings raised on page 7 land above the 'page 1' line, which is exactly
    # the file someone reads to find out which page went wrong. One line per
    # page makes the flush free. (The GUI is unaffected: it routes both
    # streams through one queue.)
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except (AttributeError, ValueError, OSError):
        pass    # pythonw with no handle at all, or a stand-in stream

    ap = argparse.ArgumentParser(
        prog="pdf2ppt",
        description="OCR an image-only PDF slide deck into an editable PPTX "
                    "(background image + style-matched editable text boxes).",
    )
    ap.add_argument("input", help="input PDF path")
    ap.add_argument("-o", "--output", help="output PPTX path (default: input stem + .pptx)")
    ap.add_argument("--dpi", type=int, default=200, help="render DPI (default 200)")
    ap.add_argument("--lang", default=None, help="RapidOCR rec language (default: chinese+english)")
    ap.add_argument("--fast", action="store_true",
                    help="use the mobile recognition model (faster, less accurate on Traditional Chinese)")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "dml", "cuda"],
                    help="inference device (default auto: DirectML > CUDA > CPU by availability)")
    ap.add_argument("--no-s2t", action="store_true",
                    help="keep OCR output as-is instead of normalizing simplified strays to Traditional Chinese")
    ap.add_argument("--pages", default=None, help="page selection, e.g. 1-5,8")
    ap.add_argument("--min-score", type=float, default=0.5, help="drop OCR lines below this confidence")
    # A real pair, not a flag plus an inert twin: an accepted-but-unread
    # --cover made `--no-cover --cover` silently mean no-cover, and it also
    # stole the --c/--co abbreviations from the flag that does something.
    #
    # --no-cover is the DEFAULT since 2026-08-24. The two modes were measured
    # against each other on all 15 pages of `guard` (PowerPoint COM export,
    # per-pixel diff): the worst page differs on 0.22% of its pixels by >8
    # levels, all of it hairline background rule at the cover's top edge
    # (the no-cover band runs 0.20em taller). Visually it is a wash, so the
    # decision falls to editing: no-cover emits 255 shapes where cover emits
    # 463, and all 227 text lines behave alike -- under --cover, 19 of them
    # keep their own fill anyway (two-tone banners, inline highlight, arcs),
    # so the user cannot tell by looking which lines take one click to
    # recolor and which take two. See docs/spec/06 for the full comparison.
    cov = ap.add_mutually_exclusive_group()
    cov.add_argument("--no-cover", dest="no_cover", action="store_true",
                     help="carry each block's fill on its own text shape "
                          "instead of a separate cover rectangle, so the "
                          "background travels with the text when you move it "
                          "in PowerPoint (the default). Two-tone banner lines "
                          "keep their own cover rects either way (one shape "
                          "cannot hold two fills), and lines with no usable "
                          "background estimate stay transparent")
    cov.add_argument("--cover", dest="no_cover", action="store_false",
                     help="separate cover rectangles under transparent text "
                          "boxes; deleting a text box then leaves the cover "
                          "behind, still hiding the raster underneath")
    ap.set_defaults(no_cover=True)
    ap.add_argument("--keep-watermark", action="store_true",
                    help="keep the bottom-right export watermark (NotebookLM "
                         "/ Gemini Notebook) instead of wiping it")
    ap.add_argument("--keep-tiny-text", action="store_true",
                    help="convert tiny/blurry OCR lines (chart and diagram "
                         "innards) to text instead of leaving them in the image")
    ap.add_argument("--merge-lines", action="store_true", help="merge adjacent lines into one shape")
    bold = ap.add_mutually_exclusive_group()
    bold.add_argument("--no-bold", action="store_true", help="never mark text bold")
    bold.add_argument("--force-bold", action="store_true", help="mark all text bold")
    ap.add_argument("--font", default="Microsoft YaHei", help='font name (default "Microsoft YaHei")')
    ap.add_argument("--debug", action="store_true", help="write OCR overlay PNGs + JSON next to output")
    args = ap.parse_args(argv)

    in_path = Path(args.input)
    if not in_path.is_file():
        ap.error(f"input not found: {in_path}")
    out_path = Path(args.output) if args.output else in_path.with_suffix(".pptx")
    bold_mode = "never" if args.no_bold else "always" if args.force_bold else "auto"

    doc = pymupdf.open(in_path)
    page_indices = (parse_pages(args.pages, len(doc)) if args.pages
                    else list(range(len(doc))))
    if not page_indices:
        ap.error("no pages selected")

    # says why the first run stops here for minutes: the engine's own
    # "Initiating download" line is one of the INFO lines we silence
    print("Loading OCR engine... (first run downloads ~90MB of OCR models)")
    engine = OcrEngine(lang=args.lang, fast=args.fast, s2t=not args.no_s2t,
                       device=args.device)
    # Replaces the engine's own 12-line banner (silenced in OcrEngine) with
    # the part that answers a question about the output: which rec model read
    # the page, on what device, at what resolution.
    print(f"OCR: PP-OCRv5 rec={'mobile (--fast)' if args.fast else 'server'}"
          f", device={engine.device}, dpi={args.dpi}"
          + (f", lang={args.lang}" if args.lang else ""))

    first = doc[page_indices[0]]
    builder = DeckBuilder(first.rect.width, first.rect.height,
                          font_name=args.font, cover=not args.no_cover)

    debug_dump = []
    failed: list[tuple[int, str]] = []
    t0 = time.time()
    for n, idx in enumerate(page_indices, 1):
        t_page = time.time()
        page = doc[idx]
        head = f"page {idx + 1} ({n}/{len(page_indices)})"
        try:
            img, png = render_page(page, args.dpi)
        except Exception as e:
            # no raster means no slide at all -- a blank stand-in would shift
            # every page number after it without saying so
            traceback.print_exc()
            print(f"{head}: render failed ({type(e).__name__}), "
                  f"page dropped from the deck")
            failed.append((idx + 1, "dropped"))
            continue

        n_before = len(builder.prs.slides)
        try:
            res = _convert_page(engine, builder, args, bold_mode, img, png)
        except Exception as e:
            # The raster is already in hand, so the page still goes into the
            # deck -- just without editable text over it. The traceback goes
            # out in full: a page failing on someone else's machine is exactly
            # the case where the run log is the only evidence there will be.
            traceback.print_exc()
            how = _fallback_slide(builder, img, png, n_before)
            print(f"{head}: {type(e).__name__}, left as {how}"
                  f", {time.time() - t_page:.1f}s")
            failed.append((idx + 1, how))
            if args.debug:
                debug_dump.append({"page": idx + 1,
                                   "error": f"{type(e).__name__}: {e}"})
            continue

        lines, styles, page_fixes = res["lines"], res["styles"], res["fixes"]
        n_tiny, n_unrepr, wipes = res["n_tiny"], res["n_unrepr"], res["wipes"]
        print(f"{head}: {len(lines)} lines, {len(res['blocks'])} shapes"
              + (f", {n_tiny} tiny/blurry left as image" if n_tiny else "")
              + (f", {n_unrepr} unreproducible left as image" if n_unrepr else "")
              + (f", {len(wipes)} watermark wiped" if wipes else "")
              # per page, not just a total: one line sent through the rotation
              # rescue costs seven OCR passes, and a total of 36s says nothing
              # about which page paid for it
              + f", {time.time() - t_page:.1f}s")
        # the corrections are invisible in the PPTX by design (the text just
        # comes out right), so --debug is where they get an outlet
        if args.debug and page_fixes:
            print("  fixes: " + ", ".join(f"{k} {v}" for k, v
                                          in sorted(page_fixes.items())))

        if args.debug:
            debug_dump.append({
                "page": idx + 1,
                "fixes": page_fixes,
                "lines": [{"text": ln.text, "bbox": ln.bbox, "score": ln.score,
                           "font_pt": st.font_pt, "bold": st.bold,
                           "stroke_rel": round(st.stroke_rel, 4),
                           "est_pt": round(st.est_pt, 2),
                           "bold_r": (round(st.bold_r, 4)
                                      if st.bold_r is not None else None),
                           "text_rgb": st.text_rgb, "bg_rgb": st.bg_rgb,
                           "glow_px": st.glow_px}
                          for ln, st in zip(lines, styles)],
            })
            _write_debug_overlay(img, lines, out_path, idx + 1)

    builder.save(str(out_path))
    # count the slides that exist, not the pages asked for: a page whose
    # raster could not be produced is not in the file
    print(f"Saved {out_path} ({len(builder.prs.slides)} slides, "
          f"{time.time() - t0:.1f}s)")
    if failed:
        # deliberately the last line printed: 'Saved …' above reads like
        # unqualified success, and this is the one thing the user has to know
        # before opening the file
        print("WARNING: " + ", ".join(f"page {q} {how}" for q, how in failed))

    if args.debug:
        dbg = out_path.with_suffix(".debug.json")
        dbg.write_text(json.dumps(debug_dump, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"Debug data: {dbg}")
    # a run where every single page failed is a failed run, whatever landed on
    # disk; anything less still produced a deck worth opening, but it must not
    # come back as an unqualified success either
    if len(failed) == len(page_indices):
        return 1
    return PARTIAL_RC if failed else 0


def _fallback_slide(builder, img, png, n_before: int) -> str:
    """Carry a page whose conversion blew up as its bare raster.

    Returns what the user actually ends up with on that page, for the run
    log -- the three outcomes are not equally bad and the difference is not
    visible from outside."""
    if len(builder.prs.slides) > n_before:
        # add_slide broke partway: the slide is already there holding
        # whatever it managed to place, and adding a second one would
        # duplicate the page rather than repair it
        return "partial slide"
    try:
        builder.add_slide(png, [], img.shape[1], img.shape[0])
    except Exception:
        traceback.print_exc()
        return "dropped"
    return "image only"


def _convert_page(engine, builder, args, bold_mode, img, png) -> dict:
    """One rendered page -> one slide, plus the numbers the run log prints.

    Lifted out of main() so that a page which blows up costs one page instead
    of the whole run: a 15-page deck failing on page 14 used to throw away the
    thirteen that had already worked. The caller catches around this call.
    ⚠️ **The only thing in here that touches the deck is the add_slide at the
    very end** -- that is what makes the fallback safe, so keep it that way.
    """
    px_to_slide_pt = 960.0 / img.shape[1]  # slide is fixed at 960 pt wide
    lines = engine.recognize(img, min_score=args.min_score)
    # read it now: the next recognize() resets it
    page_fixes = engine.last_fixes
    styles = [estimate_style(img, ln, px_to_slide_pt, bold_mode)
              for ln in lines]

    wipes = []
    if not args.keep_watermark:
        kept_lines, kept_styles = [], []
        for ln, st in zip(lines, styles):
            if is_watermark(ln, st, img.shape[1], img.shape[0]):
                wipes.append(watermark_wipe(ln, st, img))
            else:
                kept_lines.append(ln)
                kept_styles.append(st)
        lines, styles = kept_lines, kept_styles

    # icons-as-letters, markup strikethroughs and sub/superscript
    # formulas can't be rendered as faithful text — leave the raster
    before_drop = lines
    lines, styles, n_unrepr = drop_unreproducible(lines, styles, img)

    n_tiny = 0
    if not args.keep_tiny_text:
        lines, styles, n_tiny = drop_illegible_lines(lines, styles)
    # n_unrepr is NOT folded into n_tiny: drop_unreproducible is not
    # controlled by --keep-tiny-text, and its lines (icons read as
    # letters, markup strikethroughs, sub/superscript formulas) are
    # neither tiny nor blurry — reporting them as such told users the
    # flag they had just passed had not taken effect
    kept_ids = {id(ln) for ln in lines}
    dropped_lines = [ln for ln in before_drop if id(ln) not in kept_ids]

    # merge detector-shattered title fragments into one line before
    # harmonizing (p6 釐清「方言」：markdown 的規格體系)
    lines, styles = merge_row_title_fragments(lines, styles, img)

    # stacked same-card labels measured at split sizes -> one size,
    # BEFORE harmonize_font_sizes re-groups a corrected size back up
    # (p8 單一/主專案, p14 啟動【…】/全力建構/重啟計量)
    harmonize_stacked_overlap_size(lines, styles)
    # size first: wrap-mates unified into their true size leave the
    # same-size bold cohorts cleaner (SKILL.md belongs to 自動產出's
    # 18pt chip, not to the 16pt 步驟 headers it was born sized as)
    harmonize_font_sizes(lines, styles)
    harmonize_code_block_latin(lines, styles)
    sync_clamped_twins(lines, styles)
    propagate_column_clamp(lines, styles)
    # parallel card stacks in one row share a size: the card whose lines
    # are all short escapes the width clamp and snaps two steps up (p13)
    propagate_row_clamp(lines, styles)
    if bold_mode == "auto":
        reeval_clamped_bold(lines, styles)
        harmonize_bold(lines, styles)
        # parallel labels on one row are one design element: the
        # cohort vote can't reach a split pair whose page-mates are
        # genuine body text (p13 Phase 1 / Phase 2)
        harmonize_row_twin_bold(lines, styles)
    # match a paragraph tail stranded by a raster line in its middle to
    # the body line's size/weight (p13 會變成… → Alerts… line)
    harmonize_across_dropped(lines, styles, dropped_lines)
    clamp_row_neighbors(lines, styles, px_to_slide_pt)
    harmonize_chip_bg(lines, styles)
    blocks = lines_to_blocks(lines, styles, merge=args.merge_lines)
    builder.add_slide(png, blocks, img.shape[1], img.shape[0],
                      wipes=wipes, img=img)
    return {"lines": lines, "styles": styles, "blocks": blocks,
            "wipes": wipes, "n_tiny": n_tiny, "n_unrepr": n_unrepr,
            "fixes": page_fixes}


def _write_debug_overlay(img, lines, out_path: Path, page_no: int) -> None:
    from PIL import Image, ImageDraw

    im = Image.fromarray(img).convert("RGB")
    draw = ImageDraw.Draw(im)
    for ln in lines:
        draw.rectangle(ln.bbox, outline=(255, 0, 0), width=2)
    im.save(out_path.with_name(f"{out_path.stem}.debug.p{page_no:02d}.png"))
