#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生本專案的應用程式圖示（assets/ 底下那一組）。

    uv run python tools/make_icon.py

這支是圖示的**唯一真值**：幾何與色票都寫在這裡，SVG 與 .ico 都是它的產物。
改了顏色或比例就重跑一次，然後把 assets/ 的六個檔一起提交。

設計
----
藍色圓角磚，上面一張 16:9 的白色投影片（橘色標題列 + 兩行內文），投影片**後面**
升起三道同心弧。弧是 NotebookLM 的語彙、投影片是本工具的產物，合起來就是這支
程式做的事：NotebookLM 的簡報進來、可編輯的 PPT 出去。

⚠️ **不可直接沿用 NotebookLM 的商標圖形**（原稿是三道共用左緣、半徑遞減的
拱，色票 #3186FF / #4FA0FF / #76BBFF→#A9A8FF）。這裡刻意改成**對稱同心**、
換掉色票、並把它放進「投影片」這個本專案自己的主體裡。

⚠️ **卡片必須比弧寬，弧腳要整個藏在卡片後面**：弧腳只要露在卡片兩側，整個
圖示就會讀成一把**掛鎖**（2026-08-25 排過 10 個變體目視，露腳的 5 個全中）。
同理，卡片外圍要留一圈 `HALO` 寬的磚色縫——白弧碰到白卡片會糊成同一塊。

⚠️ **16–32 px 另有一版簡化圖形**（`icon-small.svg`：單弧、筆畫加粗、卡片只留
標題列）。滿版那個的弧縫是 14/512，換算下來 32 px 只剩 0.9 px，三道弧會糊成
一片雜訊——2026-08-25 兩版並排放大目視比過，分界就在 32 px。.ico 裡的小尺寸
一律取簡化版，這是它存在的唯一理由。

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
ASSETS = ROOT / "assets"

# 色票。藍色刻意與 NotebookLM 原稿的 #3186FF 錯開
TILE = "#2B7CF6"        # 磚底
ARC_MID = "#9FCBFF"     # 磚上的第二道弧
ARC_IN = "#D8E9FF"      # 磚上的第三道弧
ORANGE = "#F2610C"      # 投影片的標題列
LINE = "#C9D6E8"        # 投影片的內文列，兼無底版的卡片外框
MARK_ARCS = ("#2B7CF6", "#5AA6FF", "#8FC5FF")   # 無底版的三道弧

TILE_RADIUS = 112       # 512 見方的圓角，約 22%
HALO = 18               # 卡片外圍那圈縫的寬度
# .ico 收哪些尺寸；≤ SMALL_MAX 的用簡化圖形
ICO_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)
SMALL_MAX = 32


def _arch(cx: int, cy: int, r: int, w: int, foot_y: int, color: str) -> str:
    """半圓弧 + 直腳，端點圓角。腳會被卡片蓋掉，所以只要夠長就好。"""
    x0, x1 = cx - r, cx + r
    return (f'<path d="M{x0} {foot_y} L{x0} {cy} A{r} {r} 0 0 1 {x1} {cy} L{x1} {foot_y}" '
            f'fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>')


def _fan(cx: int, cy: int, r_out: int, w: int, gap: int, foot_y: int,
         colors: tuple[str, ...]) -> str:
    return "\n".join(_arch(cx, cy, r_out - i * (w + gap), w, foot_y, c)
                     for i, c in enumerate(colors))


def _card(cx: int, bottom: int, w: int, halo_color: str, halo: int,
          lines: bool, rx: int) -> str:
    """16:9 白色投影片。halo 是外圍那圈把卡片與後面的弧分開的縫。"""
    h = round(w * 9 / 16)
    x, y = cx - w // 2, bottom - h
    s = (f'<rect x="{x - halo}" y="{y - halo}" width="{w + 2 * halo}" '
         f'height="{h + 2 * halo}" rx="{rx + halo}" fill="{halo_color}"/>\n')
    s += f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="#FFFFFF"/>'
    pad = round(w * 0.09)
    bar_h = round(h * 0.15)
    s += (f'\n<rect x="{x + pad}" y="{y + round(h * 0.19)}" width="{round(w * 0.42)}" '
          f'height="{bar_h}" rx="{bar_h // 2}" fill="{ORANGE}"/>')
    if lines:
        lh = round(h * 0.09)
        for i, frac in enumerate((0.68, 0.48)):
            s += (f'\n<rect x="{x + pad}" y="{y + round(h * (0.50 + 0.19 * i))}" '
                  f'width="{round(w * frac)}" height="{lh}" rx="{lh // 2}" fill="{LINE}"/>')
    return s


def _svg(body: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
            f'viewBox="0 0 512 512" fill="none">\n{body}\n</svg>\n')


def build_svgs() -> dict[str, Path]:
    """寫出三份 SVG，回傳 {名稱: 路徑}。"""
    ASSETS.mkdir(exist_ok=True)
    tile = f'<rect width="512" height="512" rx="{TILE_RADIUS}" fill="{TILE}"/>'
    out = {
        # 主圖示：三道弧 + 投影片
        "icon": _svg(
            tile + "\n"
            + _fan(256, 254, 150, 32, 14, 300, ("#FFFFFF", ARC_MID, ARC_IN)) + "\n"
            + _card(256, 430, 344, TILE, HALO, lines=True, rx=20)),
        # 小尺寸：單弧加粗、卡片只留標題列
        "icon-small": _svg(
            tile + "\n"
            + _arch(256, 246, 112, 58, 300, "#FFFFFF") + "\n"
            + _card(256, 428, 328, TILE, 26, lines=False, rx=24)),
        # 無底扁平版：給 README、文件與淺色介面用。沒有磚色可以拿來當縫，
        # 改用卡片外框色，弧則要換成藍階（白弧在白底上看不見）
        "icon-mark": _svg(
            _fan(256, 254, 150, 32, 14, 300, MARK_ARCS) + "\n"
            + _card(256, 430, 344, LINE, 10, lines=True, rx=20)),
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
