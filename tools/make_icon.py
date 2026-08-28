#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生本專案的應用程式圖示（assets/ 底下那一組）。

    uv run python tools/make_icon.py

這支是圖示的**唯一真值**：幾何與色票都寫在這裡，SVG 與 .ico 都是它的產物。
改了顏色或比例就重跑一次，然後把 assets/ 的六個檔一起提交。

設計
----
立意是 **OCR 的定義本身：把光學影像認成字元**（使用者 2026-08-25 指示改用這個
立意）。藍色圓角磚，中間四個白色**取景角**框住一個白色的「文」——取景角是辨識
的通用符號、在 16px 也認得出來，而框住的東西是**一個繁體字**：這個專案整套是
為繁中調的（PP-OCRv5 server 辨識模型、s2tw、頁面詞彙校正），不是拉丁字母。

「文」怎麼畫
-----------
⚠️ **不是憑感覺畫的，是從 msyhbd.ttc 的「文」量出來的**：把真字形縮進字身框
(160,138)-(352,362)、逐列取墨水游程中心當骨架，撇捺做三次貝茲最小平方擬合
（殘差 3px）。量出來的數字：橫在 y 173..203（厚 31、近滿寬），撇捺從橫的正
下方 y=204 出發，**交叉點在 y≈291**。

⚠️ **這三個數字錯了就會變成「女」**（使用者 2026-08-25 當場指出第一版就是）：
文與女的差別**不在撇捺的形狀**，而在——**①** 文有點、女沒有；**②** 文的橫在
撇捺**之上、不穿過它們**，女的橫**穿過**撇捺；**③** 文的交叉點在下段約 59%
（y≈291／字身 138..362），女的交叉點在橫**之上**。第一版把橫畫在 210、交叉點
落在 313（77%），三條全踩，於是整個字讀成「女」。

⚠️ **點與橫之間要留得開**：點的圓端加上橫的半筆寬很容易吃掉那道縫，黏起來
就少了判別特徵 ①。

⚠️ **16–32 px 另有一版簡化圖形**（`icon-small.svg`：取景角臂變短、筆畫全部加
粗）。滿版那版的筆畫是 30/512，換算下來 16 px 只剩 0.9 px，整個字會斷掉。

⚠️ **全部用平塗、不用漸層**：小尺寸看不出漸層，而 mupdf 的 SVG 轉檔對
`url(#…)` 填色的支援不完整（實測 radialGradient 會整塊變黑）。
"""
from __future__ import annotations

import io
import struct
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "pdf2ppt" / "assets"

# 色票。藍色刻意與 NotebookLM 原稿的 #3186FF 錯開
TILE = "#2B7CF6"        # 磚底
INK = "#FFFFFF"         # 磚上的取景角與字
MARK_INK = "#2B7CF6"    # 無底版的取景角與字（白的在白底上看不見）

TILE_RADIUS = 112       # 512 見方的圓角，約 22%
# .ico 收哪些尺寸；≤ SMALL_MAX 的用簡化圖形
ICO_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)
SMALL_MAX = 32

# 「文」的骨架，量自 msyhbd.ttc（見模組 docstring）。(d, 筆寬鍵)
WEN_SKELETON = (
    ("M249 150 L257 172", "dot"),                        # 點
    ("M178 188 L332 188", "bar"),                        # 橫
    ("M303 204 C295 274 213 302 181 359", "dia"),        # 撇
    ("M208 204 C216 275 298 302 329 359", "dia"),        # 捺
)
WEN_INK_CENTER = 255    # 骨架加上圓端之後的墨水中心，縮放要繞著它


def _corners(x0: int, y0: int, x1: int, y1: int, arm: int, w: int, color: str) -> str:
    """四個取景角（L 形）。線端與轉角都是圓的，跟字的圓端一致。"""
    paths = [f"M{x0} {y0 + arm} L{x0} {y0} L{x0 + arm} {y0}",
             f"M{x1 - arm} {y0} L{x1} {y0} L{x1} {y0 + arm}",
             f"M{x1} {y1 - arm} L{x1} {y1} L{x1 - arm} {y1}",
             f"M{x0 + arm} {y1} L{x0} {y1} L{x0} {y1 - arm}"]
    return "\n".join(
        f'<path d="{d}" stroke="{color}" stroke-width="{w}" stroke-linecap="round" '
        f'stroke-linejoin="round" fill="none"/>' for d in paths)


def _wen(color: str, widths: dict[str, int], scale: float = 1.0) -> str:
    """「文」的四筆。widths 是 {dot, bar, dia} 三種筆寬。"""
    body = "\n".join(
        f'<path d="{d}" stroke="{color}" stroke-width="{widths[key]}" '
        f'stroke-linecap="round" fill="none"/>' for d, key in WEN_SKELETON)
    if scale == 1.0:
        return body
    off = WEN_INK_CENTER * (1 - scale)
    return f'<g transform="translate({off:.1f} {off:.1f}) scale({scale})">\n{body}\n</g>'


def _svg(body: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
            f'viewBox="0 0 512 512" fill="none">\n{body}\n</svg>\n')


def build_svgs() -> dict[str, Path]:
    """寫出三份 SVG，回傳 {名稱: 路徑}。"""
    ASSETS.mkdir(exist_ok=True)
    tile = f'<rect width="512" height="512" rx="{TILE_RADIUS}" fill="{TILE}"/>'
    out = {
        # 主圖示
        "icon": _svg(tile + "\n" + _corners(96, 96, 416, 416, 96, 32, INK)
                     + "\n" + _wen(INK, {"dot": 28, "bar": 30, "dia": 30}, 0.90)),
        # 小尺寸：取景角臂短一點、筆畫全部加粗
        "icon-small": _svg(tile + "\n" + _corners(92, 92, 420, 420, 80, 44, INK)
                           + "\n" + _wen(INK, {"dot": 44, "bar": 46, "dia": 46}, 0.88)),
        # 無底扁平版：給 README、文件與淺色介面用
        "icon-mark": _svg(_corners(72, 72, 440, 440, 108, 36, MARK_INK)
                          + "\n" + _wen(MARK_INK, {"dot": 30, "bar": 32, "dia": 32})),
    }
    paths = {}
    for name, text in out.items():
        p = ASSETS / f"{name}.svg"
        p.write_text(text, encoding="utf-8")
        paths[name] = p
    return paths


def render(svg: Path, px: int, supersample: int = 4) -> Image.Image:
    """SVG -> RGBA。先以 4 倍渲染再 LANCZOS 縮，小尺寸的邊緣比直接渲染乾淨。"""
    doc = pymupdf.open(svg)
    pdf = pymupdf.open("pdf", doc.convert_to_pdf())
    page = pdf[0]
    scale = px * supersample / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=True)
    im = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    return im.resize((px, px), Image.LANCZOS)


def _dib(im: Image.Image) -> bytes:
    """把一張 RGBA 圖打包成 .ico 用的 BITMAPINFOHEADER + BGRA + AND 遮罩。

    ⚠️ 兩段點陣都是**由下往上**存的（DIB 的慣例），AND 遮罩每列要補齊到
    4 位元組。Windows 的 LoadImage 對 32 位元 DIB 仍會讀 AND 遮罩來決定形狀，
    全零（＝全部不透明）在圓角磚上會露出方角。"""
    im = im.convert("RGBA")
    w, h = im.size
    raw = im.tobytes("raw", "BGRA")
    xor = b"".join(raw[y * w * 4:(y + 1) * w * 4] for y in reversed(range(h)))

    stride = ((w + 31) // 32) * 4
    alpha = im.getchannel("A").load()
    rows = []
    for y in range(h):
        bits = bytearray(stride)
        for x in range(w):
            if alpha[x, y] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        rows.append(bytes(bits))
    and_mask = b"".join(reversed(rows))

    header = struct.pack(
        "<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + xor + and_mask


def build_ico(dst: Path, images: dict[int, Image.Image]) -> None:
    """自己組 .ico：小尺寸與大尺寸的來源圖形不同，Pillow 的 sizes= 只會把
    同一張圖縮放，做不到這件事。256 用 PNG 承載（.ico 的標準作法），其餘用
    DIB —— 舊版 Windows 的圖示載入器對小尺寸的 PNG 承載支援不一致。"""
    payloads = []
    for size in sorted(images):
        im = images[size]
        if size >= 256:
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            payloads.append((size, buf.getvalue()))
        else:
            payloads.append((size, _dib(im)))

    offset = 6 + 16 * len(payloads)
    head = struct.pack("<HHH", 0, 1, len(payloads))
    entries, blobs = b"", b""
    for size, data in payloads:
        entries += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    dst.write_bytes(head + entries + blobs)


def main() -> int:
    svgs = build_svgs()
    images = {
        s: render(svgs["icon-small" if s <= SMALL_MAX else "icon"], s)
        for s in ICO_SIZES
    }
    build_ico(ASSETS / "icon.ico", images)
    images[256].save(ASSETS / "icon-256.png")
    render(svgs["icon-mark"], 256).save(ASSETS / "icon-mark-256.png")
    for name in ("icon.svg", "icon-small.svg", "icon-mark.svg",
                 "icon.ico", "icon-256.png", "icon-mark-256.png"):
        p = ASSETS / name
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
