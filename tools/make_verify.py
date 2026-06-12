"""Stack PDF render (top) and exported slide PNG (bottom) into verify/ images."""
import sys
from pathlib import Path

import pymupdf
from PIL import Image

pdf_path, slides_dir, out_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
pages = [int(p) for p in sys.argv[4].split(",")]
out_dir.mkdir(exist_ok=True)
doc = pymupdf.open(pdf_path)
for pno in pages:
    pix = doc[pno - 1].get_pixmap(dpi=100)
    top = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    bot = Image.open(slides_dir / f"slide{pno}.png").convert("RGB")
    bot = bot.resize((top.width, round(bot.height * top.width / bot.width)))
    canvas = Image.new("RGB", (top.width, top.height + bot.height + 8), "red")
    canvas.paste(top, (0, 0))
    canvas.paste(bot, (0, top.height + 8))
    canvas.save(out_dir / f"p{pno:02d}.png")
    print(f"verify/p{pno:02d}.png")
