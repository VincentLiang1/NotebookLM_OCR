"""Command-line interface and pipeline orchestration."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pymupdf

from .blocks import (clamp_row_neighbors, drop_illegible_lines, harmonize_bold, sync_clamped_twins,
                     harmonize_font_sizes, lines_to_blocks)
from .builder import DeckBuilder
from .ocr import OcrEngine
from .render import render_page
from .style import estimate_style


def is_watermark(line, style, img_w: int, img_h: int) -> bool:
    """The NotebookLM watermark: logo + 'NotebookLM' in the bottom-right
    corner (OCR sometimes merges the logo into the text as a stray char)."""
    text = line.text.replace(" ", "")
    if not text.endswith("NotebookLM") or len(text) > 13:
        return False
    x0, y0, x1, y1 = line.bbox
    return (y0 > 0.85 * img_h and x1 > 0.65 * img_w
            and style.bg_rgb is not None)


def watermark_wipe(line, style) -> tuple[tuple, tuple]:
    """Cover box for the watermark: extend left to also hide the logo icon
    that sits before the text."""
    x0, y0, x1, y1 = line.bbox
    h = y1 - y0
    return (x0 - 1.8 * h, y0 - 0.3 * h, x1 + 0.3 * h, y1 + 0.3 * h), style.bg_rgb


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
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

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
    ap.add_argument("--no-cover", action="store_true", help="no solid fills; text overlays the image")
    ap.add_argument("--keep-watermark", action="store_true",
                    help="keep the bottom-right NotebookLM watermark instead of wiping it")
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

    print("Loading OCR engine...")
    engine = OcrEngine(lang=args.lang, fast=args.fast, s2t=not args.no_s2t,
                       device=args.device)
    print(f"Inference device: {engine.device}")

    first = doc[page_indices[0]]
    builder = DeckBuilder(first.rect.width, first.rect.height,
                          font_name=args.font, cover=not args.no_cover)

    debug_dump = []
    t0 = time.time()
    for n, idx in enumerate(page_indices, 1):
        page = doc[idx]
        img, png = render_page(page, args.dpi)
        px_to_slide_pt = 960.0 / img.shape[1]  # slide is fixed at 960 pt wide
        lines = engine.recognize(img, min_score=args.min_score)
        styles = [estimate_style(img, ln, px_to_slide_pt, bold_mode)
                  for ln in lines]

        wipes = []
        if not args.keep_watermark:
            kept_lines, kept_styles = [], []
            for ln, st in zip(lines, styles):
                if is_watermark(ln, st, img.shape[1], img.shape[0]):
                    wipes.append(watermark_wipe(ln, st))
                else:
                    kept_lines.append(ln)
                    kept_styles.append(st)
            lines, styles = kept_lines, kept_styles

        n_tiny = 0
        if not args.keep_tiny_text:
            lines, styles, n_tiny = drop_illegible_lines(lines, styles)

        # size first: wrap-mates unified into their true size leave the
        # same-size bold cohorts cleaner (SKILL.md belongs to 自動產出's
        # 18pt chip, not to the 16pt 步驟 headers it was born sized as)
        harmonize_font_sizes(lines, styles)
        sync_clamped_twins(lines, styles)
        if bold_mode == "auto":
            harmonize_bold(lines, styles)
        clamp_row_neighbors(lines, styles, px_to_slide_pt)
        blocks = lines_to_blocks(lines, styles, merge=args.merge_lines)
        builder.add_slide(png, blocks, img.shape[1], img.shape[0],
                          wipes=wipes, img=img)
        print(f"page {idx + 1} ({n}/{len(page_indices)}): {len(lines)} lines, "
              f"{len(blocks)} shapes"
              + (f", {n_tiny} tiny/blurry left as image" if n_tiny else "")
              + (f", {len(wipes)} watermark wiped" if wipes else ""))

        if args.debug:
            debug_dump.append({
                "page": idx + 1,
                "lines": [{"text": ln.text, "bbox": ln.bbox, "score": ln.score,
                           "font_pt": st.font_pt, "bold": st.bold,
                           "stroke_rel": round(st.stroke_rel, 4),
                           "est_pt": round(st.est_pt, 2),
                           "bold_r": (round(st.bold_r, 4)
                                      if st.bold_r is not None else None),
                           "text_rgb": st.text_rgb, "bg_rgb": st.bg_rgb}
                          for ln, st in zip(lines, styles)],
            })
            _write_debug_overlay(img, lines, out_path, idx + 1)

    builder.save(str(out_path))
    print(f"Saved {out_path} ({len(page_indices)} slides, "
          f"{time.time() - t0:.1f}s)")

    if args.debug:
        dbg = out_path.with_suffix(".debug.json")
        dbg.write_text(json.dumps(debug_dump, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"Debug data: {dbg}")
    return 0


def _write_debug_overlay(img, lines, out_path: Path, page_no: int) -> None:
    from PIL import Image, ImageDraw

    im = Image.fromarray(img).convert("RGB")
    draw = ImageDraw.Draw(im)
    for ln in lines:
        draw.rectangle(ln.bbox, outline=(255, 0, 0), width=2)
    im.save(out_path.with_name(f"{out_path.stem}.debug.p{page_no:02d}.png"))
