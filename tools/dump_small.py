"""List small/low-score debug lines per page to calibrate the tiny-text filter."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "generated.debug.json"
max_pt = float(sys.argv[2]) if len(sys.argv) > 2 else 14.0
data = json.load(open(path, encoding="utf-8"))
for page in data:
    rows = [l for l in page["lines"] if l["font_pt"] <= max_pt or l["score"] < 0.8]
    if not rows:
        continue
    print(f"--- page {page['page']} ({len(rows)}/{len(page['lines'])}) ---")
    for l in rows:
        x0, y0, x1, y1 = (round(v) for v in l["bbox"])
        print(f"  {l['font_pt']:>5.1f}pt s={l['score']:.2f} "
              f"[{x0},{y0},{x1},{y1}] {l['text'][:46]!r}")
