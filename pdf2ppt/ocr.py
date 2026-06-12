"""RapidOCR wrapper returning Line objects in image pixel coordinates.

The recognition model drops most spaces. They are restored two ways:
- real gaps between latin characters (from per-char word boxes) become spaces
- a space is always inserted at CJK ideograph <-> latin alphanumeric
  boundaries ("pangu" spacing, matching the source decks' typography)
"""
from __future__ import annotations

import math
import re
from statistics import median

import numpy as np

from .models import Line

_CJK = "㐀-䶿一-鿿豈-﫿"
_RE_CJK_TO_LAT = re.compile(f"([{_CJK}])([A-Za-z0-9])")
_RE_LAT_TO_CJK = re.compile(f"([A-Za-z0-9])([{_CJK}])")
LATIN_GAP_FACTOR = 0.33  # space if gap > this fraction of median char width

RESCUE_SCORE = 0.75      # lines below this confidence get the rotation rescue
RESCUE_ANGLES = (0, -3, 3, -6, 6, -9, 9)  # degrees, for tilted-ribbon text
RESCUE_MARGIN = 0.05     # a candidate must beat the original by this much
MIN_TILT_DEG = 2.0       # rescue-path tilt below this is noise (OCR-verified)
QUAD_TILT_DEG = 5.0      # detector quads jitter up to ~3.2 deg on short
                         # labels; real slanted band text measures 26+

# trailing punctuation the detector tends to crop off line ends
TRAIL_PUNCT = set("。．.，,、；;：:！!？?）)」』】%…")


def _is_latin_alnum(c: str) -> bool:
    return c.isascii() and c.isalnum()


def _quad_bounds(quad) -> tuple[float, float, float, float] | None:
    try:
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        return float(min(xs)), float(max(xs)), float(min(ys)), float(max(ys))
    except (TypeError, IndexError):
        return None


def _gap_is_blank(img: np.ndarray, gx0: float, gx1: float,
                  gy0: float, gy1: float) -> bool:
    """A real word space contains no glyph ink; a CTC word-box artifact
    (the rec model splitting e.g. KEEP between the Es) overlaps strokes.
    Word-box edges are sloppy, so only the middle half of the gap is
    sampled (measured: real spaces 0.00-0.10 ink, artifact 0.24)."""
    gw = gx1 - gx0
    strip = img[int(gy0):int(gy1),
                int(gx0 + 0.25 * gw):int(gx1 - 0.25 * gw) + 1]
    if strip.size == 0:
        return False
    med = np.median(strip.reshape(-1, 3), axis=0)
    ink = np.abs(strip.astype(int) - med).max(axis=2) > 60
    return float(ink.mean()) < 0.15


def _restore_latin_gaps(text: str, words, img: np.ndarray):
    """words: per-char (char, score, quad) tuples for one OCR line.
    Returns (text, char_boxes) where char_boxes is [(char, l, t, r, b)] for
    the space-stripped text, or None when word boxes were unusable."""
    if not words:
        return text, None
    chars, geoms = [], []
    for w in words:
        ch, quad = str(w[0]), (w[2] if len(w) > 2 else None)
        chars.append(ch)
        geoms.append(_quad_bounds(quad) if quad is not None else None)
    # safety: only trust word boxes if they spell the same text
    if "".join(chars).replace(" ", "") != text.replace(" ", ""):
        return text, None

    def boxes():
        out = []
        for ch, g in zip(chars, geoms):
            for c in ch:
                if c != " ":
                    out.append((c, g[0], g[2], g[1], g[3]) if g
                               else (c, 0.0, 0.0, 0.0, 0.0))
        return out

    latin_widths = [g[1] - g[0] for ch, g in zip(chars, geoms)
                    if g and len(ch) == 1 and _is_latin_alnum(ch) and g[1] > g[0]]
    if not latin_widths:
        return text, boxes()
    med_w = median(latin_widths)

    # walk the ORIGINAL text so spaces the rec model itself emitted are
    # preserved (word boxes never carry them); gap analysis only ADDS spaces
    flat_chars: list[str] = []
    flat_geoms = []
    for ch, g in zip(chars, geoms):
        for c in ch:
            flat_chars.append(c)
            flat_geoms.append(g)

    out = []
    ci = 0
    for ch in text:
        if ch == " ":
            if out and out[-1] != " ":
                out.append(" ")
            continue
        g = flat_geoms[ci]
        p = flat_geoms[ci - 1] if ci else None
        if (out and out[-1] != " " and g and p
                and _is_latin_alnum(flat_chars[ci - 1])
                and _is_latin_alnum(flat_chars[ci])
                and g[0] - p[1] > LATIN_GAP_FACTOR * med_w
                and _gap_is_blank(img, p[1], g[0],
                                  min(p[2], g[2]), max(p[3], g[3]))):
            out.append(" ")
        out.append(ch)
        ci += 1
    return "".join(out), boxes()


ARC_MIN_BOX_H = 80   # only boxes at least this tall can hold a visible arc
ARC_MIN_SAG = 12.0   # px; smaller fitted sagittas are fragment jitter


def _arc_from_fragments(frags, box_h: float) -> float:
    """Sagitta from the rescue's OCR-verified fragments (their quads can't
    contain a neighboring line — the center-band filter removed it).
    Positive = arch up. Pure-image arc tracking was tried and abandoned:
    interleaved ribbon lines pollute each other's boxes and even flip the
    fitted sign."""
    if len(frags) < 3:
        return 0.0
    pts = sorted((float(f[3][:, 0].mean()), float(f[3][:, 1].mean()))
                 for f in frags)
    span = pts[-1][0] - pts[0][0]
    if span < 4 * box_h:
        return 0.0
    mid_x = (pts[0][0] + pts[-1][0]) / 2
    mid = min(pts[1:-1], key=lambda p: abs(p[0] - mid_x))
    edge_y = (pts[0][1] + pts[-1][1]) / 2
    sag = edge_y - mid[1]  # y-down: middle higher => positive => arch up
    if abs(sag) < ARC_MIN_SAG:
        return 0.0
    return float(sag)


def _looks_like_warning_icon(img: np.ndarray, box) -> bool:
    """A ⚠ triangle icon is recognized as 'A'. Discriminator: the icon's
    base is one continuous ink bar (measured 0.93 of box width) while a
    real letter A ends in two separate legs (measured 0.24)."""
    _, l, t, r, b = box
    l, t, r, b = int(l), int(t), int(r), int(b)
    if r - l < 8 or b - t < 8:
        return False
    crop = img[t:b, l:r].astype(int)
    med = np.median(crop.reshape(-1, 3), axis=0)
    ink = np.abs(crop - med).max(axis=2) > 60
    rows = np.where(ink.sum(axis=1) >= 2)[0]
    if not len(rows):
        return False
    h = rows[-1] - rows[0] + 1
    band = ink[rows[-1] - max(1, h // 6):rows[-1] + 1].any(axis=0)
    best = cur = 0
    for v in band:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best / max(1, r - l) >= 0.6


def _looks_like_filled_icon(img: np.ndarray, bbox) -> bool:
    """A text glyph is strokes of ONE color; a filled icon (p15's green
    refresh arrows -> 'S') splits its ink into two strong color clusters
    (fill + outline). Background is the box's own dominant color — a ring
    around the tight icon bbox lands ON the icon and lies about the bg."""
    x0, y0, x1, y1 = (int(round(v)) for v in bbox)
    h, w = img.shape[:2]
    inner = img[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
    if inner.size == 0:
        return False
    px = inner.reshape(-1, 3).astype(int)
    q = (px >> 5) << 5
    bins, bcounts = np.unique(q, axis=0, return_counts=True)
    bg = bins[bcounts.argmax()]
    near_bg = np.abs(px - bg).max(axis=1) < 40
    bg = px[near_bg].mean(axis=0) if near_bg.any() else bg
    ink = px[np.abs(px - bg).max(axis=1) > 60]
    if len(ink) < 100:
        return False
    q = (ink >> 5) << 5
    colors, counts = np.unique(q, axis=0, return_counts=True)
    order = counts.argsort()[::-1]
    clusters = []
    taken = np.zeros(len(ink), dtype=bool)
    for idx in order[:6]:
        near = (np.abs(ink - colors[idx]).max(axis=1) < 40) & ~taken
        share = float(near.mean())
        if share >= 0.25:
            clusters.append(ink[near].mean(axis=0))
            taken |= near
        if len(clusters) >= 2:
            break
    if len(clusters) < 2 or np.abs(clusters[0] - clusters[1]).max() < 60:
        return False
    # anti-aliasing also forms a second cluster, but it lies ON the
    # bg<->glyph color line; an icon's fill color is off that line
    # (green is not a blend of cream and the dark outline)
    a, b = np.asarray(bg, float), clusters[0]
    p = clusters[1]
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / max(1e-6, np.dot(ab, ab)), 0.0, 1.0)
    residual = float(np.linalg.norm(p - (a + t * ab)))
    return residual >= 45.0


def _fix_warning_icon(text: str, char_boxes, img: np.ndarray):
    """Replace a line-leading 'A' that is actually a warning triangle."""
    if (char_boxes and text[:1] == "A"
            and (len(text) == 1 or text[1] == " " or ord(text[1]) >= 0x2E80)
            and _looks_like_warning_icon(img, char_boxes[0])):
        c = char_boxes[0]
        char_boxes[0] = ("⚠", c[1], c[2], c[3], c[4])
        rest = text[1:]
        if rest and rest[0] != " ":
            rest = " " + rest
        return "⚠" + rest
    return text


def _fix_trailing_degree(text: str) -> str:
    """The rec model misreads a line-final ideographic full stop 。 as a
    degree sign ° (same small circle, but rendered top-aligned). A real
    degree is preceded by a digit; anything else gets the full stop."""
    if text.endswith("°") and len(text) >= 2 and not text[-2].isdigit():
        return text[:-1].rstrip() + "。"
    return text


def _pangu_spacing(text: str) -> str:
    text = _RE_CJK_TO_LAT.sub(r"\1 \2", text)
    text = _RE_LAT_TO_CJK.sub(r"\1 \2", text)
    return re.sub(r" {2,}", " ", text)


def resolve_device(device: str = "auto") -> str:
    """'auto' picks the best available onnxruntime provider: DirectML
    (any DX12 GPU on Windows, e.g. Intel Arc) > CUDA > CPU. An explicit
    'dml'/'cuda'/'cpu' is honored as given."""
    if device != "auto":
        return device
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
    except ImportError:
        return "cpu"
    if "DmlExecutionProvider" in providers:
        return "dml"
    if "CUDAExecutionProvider" in providers:
        return "cuda"
    return "cpu"


class OcrEngine:
    def __init__(self, lang: str | None = None, fast: bool = False,
                 s2t: bool = True, device: str = "auto"):
        # heavy imports deferred until needed
        from rapidocr import ModelType, OCRVersion, RapidOCR

        # PP-OCRv5 server rec is markedly better on Traditional Chinese than
        # the default v4 mobile model ('攝'→'撬' class errors disappear)
        params = {
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
        }
        if not fast:
            params["Rec.model_type"] = ModelType.SERVER
        if lang:
            from rapidocr import LangRec

            params["Rec.lang_type"] = LangRec(lang)
        self.device = resolve_device(device)
        if self.device == "dml":
            params["EngineConfig.onnxruntime.use_dml"] = True
        elif self.device == "cuda":
            params["EngineConfig.onnxruntime.use_cuda"] = True
        self.engine = RapidOCR(params=params)

        # the rec model occasionally emits simplified lookalikes (惡→恶)
        # even for Traditional Chinese input; OpenCC normalizes them back
        self._s2t = self._t2s = None
        if s2t:
            try:
                from opencc import OpenCC

                self._s2t = OpenCC("s2t")
                self._t2s = OpenCC("t2s")
            except ImportError:
                pass

    def _fix_simplified_strays(self, text: str) -> str:
        """Convert to Traditional only when a line MIXES both scripts: a
        pure-simplified line is intentional content (e.g. a depicted search
        query), a mixed line is the rec model slipping on single glyphs."""
        if self._s2t is None:
            return text
        as_trad = self._s2t.convert(text)
        if as_trad == text:  # already pure traditional / neutral
            return text
        if self._t2s.convert(text) == text:  # pure simplified: keep
            return text
        return as_trad

    def _rescue_tilted(self, img_rgb: np.ndarray, line: Line):
        """Low-confidence lines are often tilted (ribbon/arc text the
        detector boxes axis-aligned). Re-OCR the region at several rotations
        and keep the best length-weighted result.

        Returns (text, angle_deg, center_px, size_px) or None; angle/center/
        size describe the recovered rotated rect so styling and the output
        shape can follow the tilt (zeros/None when the best angle was 0).
        """
        import math

        from PIL import Image

        h, w = img_rgb.shape[:2]
        x0, y0, x1, y1 = (int(round(v)) for v in line.bbox)
        pad = max(8, round(0.15 * (y1 - y0)))
        cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
        region = img_rgb[cy0:min(h, y1 + pad), cx0:min(w, x1 + pad)]
        if region.size == 0:
            return None
        fill = tuple(int(v) for v in np.median(region.reshape(-1, 3), axis=0))

        plain = line.text.replace(" ", "")
        best, best_key = None, (len(plain), line.score + RESCUE_MARGIN)
        for ang in RESCUE_ANGLES:
            rot = Image.fromarray(region)
            if ang:
                rot = rot.rotate(ang, resample=Image.BICUBIC, expand=True,
                                 fillcolor=fill)
            res = self.engine(np.array(rot)[:, :, ::-1], use_det=True,
                              use_cls=True, use_rec=True)
            if res is None or res.txts is None:
                continue
            # keep only fragments whose own height-band straddles the crop
            # center: the padded crop can clip a neighboring line, and at
            # some angles the detector merges it in
            mid = rot.height / 2
            frags = []
            for q, t, s in zip(res.boxes, res.txts, res.scores):
                q = np.asarray(q, dtype=float)
                cy = float(q[:, 1].mean())
                frag_h = float(q[:, 1].max() - q[:, 1].min())
                if abs(cy - mid) <= 0.8 * frag_h and t.strip():
                    frags.append((float(q[:, 0].min()), t.strip(), float(s), q))
            if not frags:
                continue
            frags.sort(key=lambda f: f[0])
            text = "".join(t for _, t, _, _ in frags)
            n = sum(len(t) for _, t, _, _ in frags)
            wscore = sum(s * len(t) for _, t, s, _ in frags) / max(1, n)
            key = (len(text.replace(" ", "")), wscore)
            # a candidate much longer than the original swallowed a neighbor
            if wscore >= 0.7 and key > best_key and key[0] <= 2 * max(4, len(plain)):
                best_key = key
                best = (text, ang, rot.size, frags)

        if best is None:
            return None
        text, ang, (rw, rh), frags = best
        h_med0 = (float(np.median([f[3][:, 1].max() - f[3][:, 1].min()
                                   for f in frags])) if frags else 0.0)
        arc = _arc_from_fragments(frags, h_med0)
        if not ang or abs(ang) < MIN_TILT_DEG:
            return text, 0.0, None, None, arc
        # fragment geometry in rotated space -> rotated rect in image space
        # (verified mapping: p_in = c_in + R(+ang) @ (p_out - c_out)).
        # Arc text leaves each fragment slightly tilted even after the best
        # rotation, so a plain quad union overshoots the height badly; use
        # the median fragment height/center instead.
        all_q = np.vstack([f[3] for f in frags])
        ux0, ux1 = all_q[:, 0].min(), all_q[:, 0].max()
        h_med = float(np.median([f[3][:, 1].max() - f[3][:, 1].min()
                                 for f in frags]))
        cy_med = float(np.median([f[3][:, 1].mean() for f in frags]))
        a = math.radians(ang)
        cos_a, sin_a = math.cos(a), math.sin(a)
        ox = (ux0 + ux1) / 2 - rw / 2
        oy = cy_med - rh / 2
        cx = cx0 + region.shape[1] / 2 + cos_a * ox - sin_a * oy
        cy = cy0 + region.shape[0] / 2 + sin_a * ox + cos_a * oy
        return text, float(ang), (float(cx), float(cy)), \
            (float(ux1 - ux0), h_med), arc

    def _extend_trailing(self, img_rgb: np.ndarray, line: Line) -> str | None:
        """The detector often crops a trailing 。/) off a line. If there is
        ink just right of the box, re-recognize the line strip extended
        rightward (rec-only — the detector shatters small crops) and accept
        the result only when it adds 1-2 trailing punctuation marks."""
        ih, iw = img_rgb.shape[:2]
        x0, y0, x1, y1 = (int(round(v)) for v in line.bbox)
        h = y1 - y0
        strip = img_rgb[y0 + h // 5: y1 - h // 5, x1 + 2: min(iw, x1 + h)]
        if strip.size == 0 or strip.std() < 12:
            return None

        plain_old = line.text.replace(" ", "")

        # a line-final OPENING bracket is usually hallucinated from the
        # left arc of a 。 that sits past the box edge (p6 "…TOC 直跳」「"
        # — the real 。 is 12px outside the box). Re-reading the WHOLE
        # line cannot fix it: rec on a squeezed 3400px line drops chars
        # (翻 N 本 -> 翻本) and the startswith check dies. Re-read only
        # the tail strip and match on a short suffix instead. A genuine
        # wrap-opening quote re-reads as 「 again, fails TRAIL_PUNCT, and
        # the original text is kept.
        if plain_old and plain_old[-1] in "「『（【《〈" and len(plain_old) >= 5:
            tx0 = max(x0, x1 - 5 * h)
            crop = img_rgb[y0:y1, tx0:min(iw, x1 + round(1.2 * h))]
            res = self.engine(crop[:, :, ::-1], use_det=False, use_cls=False,
                              use_rec=True)
            if res is None or res.txts is None or not res.txts:
                return None
            tail_new = res.txts[0].replace(" ", "")
            suffix = plain_old[:-1][-4:]
            pos = tail_new.rfind(suffix)
            if float(res.scores[0]) < 0.8 or pos < 0:
                return None
            appended = tail_new[pos + len(suffix):]
            if not (1 <= len(appended) <= 2
                    and all(c in TRAIL_PUNCT for c in appended)):
                return None
            cand = line.text.rstrip()[:-1] + appended
        else:
            crop = img_rgb[y0:y1, x0:min(iw, x1 + round(1.2 * h))]
            res = self.engine(crop[:, :, ::-1], use_det=False, use_cls=False,
                              use_rec=True)
            if res is None or res.txts is None or not res.txts:
                return None
            cand = res.txts[0].strip()
            score = float(res.scores[0])
            plain_new = cand.replace(" ", "")
            if not (score >= 0.8 and plain_new.startswith(plain_old)
                    and 1 <= len(plain_new) - len(plain_old) <= 2
                    and all(c in TRAIL_PUNCT
                            for c in plain_new[len(plain_old):])):
                return None
        # widen the box to the recovered punctuation's actual ink, so the
        # cover hides the raster glyph too; stop at the first big gap so a
        # neighboring column's ink can't drag the box across
        scan = img_rgb[y0:y1, x1:min(iw, x1 + round(1.2 * h))]
        med = np.median(scan.reshape(-1, 3), axis=0)
        ink_cols = np.where(
            (np.abs(scan.astype(int) - med).max(axis=2) > 60).sum(axis=0) >= 2)[0]
        end = None
        for c in ink_cols:
            if end is not None and c - end > 0.4 * h:
                break
            end = c
        new_x1 = float(x1 + end + 4) if end is not None else line.bbox[2]
        return cand, new_x1

    def recognize(self, img_rgb: np.ndarray, min_score: float = 0.5) -> list[Line]:
        # use_det/use_cls/use_rec persist across calls inside RapidOCR, so
        # always pass them explicitly (rec-only calls would poison the next)
        result = self.engine(img_rgb[:, :, ::-1], use_det=True, use_cls=True,
                             use_rec=True, return_word_box=True)
        if result is None or result.txts is None:
            return []
        word_results = getattr(result, "word_results", None)
        if word_results is None or len(word_results) != len(result.txts):
            word_results = [None] * len(result.txts)

        lines: list[Line] = []
        for quad, text, score, words in zip(result.boxes, result.txts,
                                            result.scores, word_results):
            text = text.strip()
            if not text or score < min_score:
                continue
            text, char_boxes = _restore_latin_gaps(text, words, img_rgb)
            text = _fix_warning_icon(text, char_boxes, img_rgb)
            quad = np.asarray(quad, dtype=float)
            x0, y0 = quad.min(axis=0)
            x1, y1 = quad.max(axis=0)

            # filled icons read as single letters (p15: the green refresh
            # arrows next to the caption box recognized as 'S' at score
            # 0.86) — a glyph is one ink color, an icon is fill + outline
            if (len(text) == 1 and text.isascii() and text.isalpha()
                    and _looks_like_filled_icon(img_rgb, (x0, y0, x1, y1))):
                continue

            # tilt from the quad's top+bottom edges (averaged for stability);
            # the detector returns rotated quads for slanted band text
            edge = (quad[1] - quad[0]) + (quad[2] - quad[3])
            ang = math.degrees(math.atan2(edge[1], edge[0]))
            if abs(ang) < QUAD_TILT_DEG or abs(ang) > 45:
                ang = 0.0
            w = (np.linalg.norm(quad[1] - quad[0])
                 + np.linalg.norm(quad[2] - quad[3])) / 2
            h = (np.linalg.norm(quad[3] - quad[0])
                 + np.linalg.norm(quad[2] - quad[1])) / 2
            cx, cy = quad.mean(axis=0)

            lines.append(Line(text=text,
                              bbox=(float(x0), float(y0), float(x1), float(y1)),
                              score=float(score),
                              angle=ang,
                              center=(float(cx), float(cy)),
                              size=(float(w), float(h)),
                              char_boxes=char_boxes))

        for ln in lines:
            # tilted lines were already rectified by the detector; the
            # rotation rescue only helps when the tilt was NOT detected
            if ln.score < RESCUE_SCORE and ln.angle == 0.0:
                rescued = self._rescue_tilted(img_rgb, ln)
                if rescued:
                    ln.text, ang, center, size, arc = rescued
                    ln.char_boxes = None  # boxes no longer match the text
                    if arc:
                        # an arc explains the fragments better than the
                        # rescue's single compromise angle
                        ln.arc_sagitta = arc
                    elif ang:
                        ln.angle, ln.center, ln.size = ang, center, size
            if ln.angle == 0.0:
                extended = self._extend_trailing(img_rgb, ln)
                if extended:
                    ln.text, new_x1 = extended
                    ln.bbox = (ln.bbox[0], ln.bbox[1], new_x1, ln.bbox[3])
            ln.text = _pangu_spacing(ln.text).strip()
            ln.text = _fix_trailing_degree(ln.text)
            ln.text = self._fix_simplified_strays(ln.text)

        # banner ribbons hold parallel arc lines, but only the low-score one
        # goes through the rescue that measures the arc; propagate the
        # curvature to overlapping tall siblings (same radius => sagitta
        # scales with the square of the width)
        arcs = [ln for ln in lines if ln.arc_sagitta]
        for ln in lines:
            if ln.arc_sagitta or ln.angle:
                continue
            if ln.bbox[3] - ln.bbox[1] < ARC_MIN_BOX_H:
                continue
            for a in arcs:
                ox = (min(ln.bbox[2], a.bbox[2])
                      - max(ln.bbox[0], a.bbox[0]))
                oy = (min(ln.bbox[3], a.bbox[3])
                      - max(ln.bbox[1], a.bbox[1]))
                w_min = min(ln.bbox[2] - ln.bbox[0], a.bbox[2] - a.bbox[0])
                if ox > 0.6 * w_min and oy > 0:
                    scale = ((ln.bbox[2] - ln.bbox[0])
                             / (a.bbox[2] - a.bbox[0])) ** 2
                    ln.arc_sagitta = a.arc_sagitta * scale
                    break

        lines.sort(key=lambda ln: (ln.bbox[1], ln.bbox[0]))
        return lines
