#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生圖形介面的 squircle 皮膚資產（assets/skin/ 底下那一組）。

    uv run python tools/make_skin.py

這支是皮膚的**唯一真值**：形狀、圓角半徑、色票、內距全寫在這裡，`assets/skin/`
的 PNG 與 `sprites.json` 都是它的產物。改了顏色或半徑就重跑一次，然後把
`assets/skin/` 整個目錄跟著程式碼一起提交。⚠️ **不要手改產物**——下一次重跑
就被蓋掉（與 `tools/make_icon.py` 同一條原則）。

為什麼是圖
----------
ttk 內建的繪圖能力只有矩形、3D 浮雕邊框、直線——**沒有圓角、沒有抗鋸齒、沒有
任意路徑**。Windows 原生的 vista 佈景不必用圖，是因為它把繪圖整個交給作業系統
的 UxTheme API，拿到的是系統長什麼樣就什麼樣、形狀不能自訂。所以在 Tk 上要一個
自訂形狀的圓角，只有兩條路：**預先渲染成圖片**，或換掉整個 GUI 框架。

現在這個 Sun Valley 佈景（sv_ttk）自己就是這樣做的：一張 `spritesheet_light.png`
切成一堆小圖，再用 `ttk::style element create ... image` 掛上去。本檔產出的東西
與它同構，換掉的也正是它的 `Button.button`／`AccentButton.button`／`Entry.field`
／`Checkbutton.indicator`／進度條那幾個元件。

形狀：四分之一超橢圓，直邊保持直的
----------------------------------
圓角矩形的角是一段**圓弧**，弧與直邊接得上位置、接不上曲率，交界處看得出一個
轉折；squircle 的角是超橢圓 `|x|^n + |y|^n = r^n` 的四分之一，曲率從邊上的 0
連續長到角落的最大值——同樣的半徑看起來更飽滿、轉角更長一段。

⚠️ 三個一踩就壞的地方（都是 2026-08-26 實際撞到的，全在 `docs/dev/windows-環境
與入口.md` §5.9）：

1. **底板中段要夠寬**（`SQ_MID`）。九宮格的中段是 Tk **一格一格重複貼**滿的，
   不是拉伸；中段留 1px 的話，填一顆 840px 寬的收合鈕就是幾百次繪製呼叫，重畫
   整個視窗要 2.5 秒（看起來就像當掉）。對照組：sv_ttk 的按鈕 sprite 是 20×20
   配 `-border 4`，中段 12px。
2. **`border` 不可超過圖片邊長的一半。** 切不出九宮格時 ttk 會在幾何計算裡原地
   打轉，事件迴圈當場卡死——沒有例外、沒有訊息。
3. **先畫成不透明的 RGB，最後才把遮罩放進 alpha 通道。** 拿遮罩去 `paste` 一張
   RGB 到透明畫布上的話，角落抗鋸齒帶的 RGB 會先跟畫布的黑色混一次，而 Tk 合成
   時又依 alpha 混第二次，四個角就各浮出一圈比底色深的邊。

為什麼要產生五種縮放
--------------------
資產是固定像素，而顯示縮放不是：Windows 常見的是 100%／125%／150%／175%／200%。
每一檔各出一組，載入時挑最接近的——⚠️ 這幾檔正好**精確**對上那五個設定值，所以
實務上永遠是精確匹配，內距與圓角不會互相錯開。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "skin"

# 顯示縮放。⚠️ 這五個值要對上 Windows 顯示設定裡的那五檔。
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)

SQ_N = 5.0            # 超橢圓指數：4 還看得出方、6 之後跟正圓角就分不出來了
SQ_SS = 4             # 遮罩超取樣倍率（畫 4× 再縮回來，這就是抗鋸齒）
SQ_STEPS = 24         # 每個角取樣幾個點（再多肉眼看不出來，只是變慢）

# 圓角半徑（邏輯 px）。⚠️ 半徑是**新的一把尺**，不要拿版面的 SP_* 那把來湊——
# 間距與圓角在版面上管的是兩件事。
SQ_R = 10             # 一般按鈕、輸入框（對齊 meeting-scribe 的 input_radius）
SQ_R_RUN = 12         # 主要動作鈕（大一號才撐得住那個字級）
SQ_R_CHK = 5          # 核取方塊
SQ_CHK_BOX = 20       # 核取方塊的邊長（沿用 sv_ttk 的尺寸，見下面的 SQ_PAD）
SQ_CHK_GAP = 8        # 方塊與標籤之間的縫（畫進圖片右側的透明區，layout 沒地方塞）
SQ_PB_TH = 7          # 進度條厚度
SQ_MID = 96           # 底板中段的寬度（見檔頭第 1 點，不可以縮回 1px）

# ⚠️ **底板自己要撐出來的內距**：sv_ttk 的按鈕／輸入框圖片是**自帶內距的**，換掉
# 圖片就得把那一份補回來，否則全畫面的控制項一起矮 8px、視窗 reqheight 從 426 掉
# 到 387（2026-08-26 用皮膚開／關逐個量 requested size 量出來的：按鈕與收合鈕一律
# 差 8×8，輸入框差 10 寬 7 高）。控制項自己的內距仍然歸 GUI 那幾行樣式設定管。
SQ_PAD = 4            # 按鈕
SQ_PAD_FIELD = 5      # 輸入框（比按鈕多 1px，才跟按鈕一樣高）

# hover 有明確色碼（meeting-scribe 給了），pressed 沒有——那一階一律由 _shade()
# 從同一個底色壓暗，免得再手配一組沒有人記得該差多少的色碼。
#
# ⚠️ **色票抄自 meeting-scribe 那支工具的 UI 樣式模組**（使用者 2026-08-26 指示
# 「顏色可以參考 meeting-scribe」，那份的來源是 apple.com）：兩支都是同一個人在用
# 的工具，主色、次要底、破壞性紅要對得起來。⚠️ **形狀不跟著抄**——那邊的按鈕是
# 膠囊（`button_*_radius: 999px`），這裡是 squircle，那是這支自己的決定。
SKINS = {
    "light": {
        "accent": "#0071e3", "accent_hi": "#0077ed",
        "on_accent": "#ffffff",
        # ⚠️ 停止鈕**兩個模式都用這個深紅**：深色模式的 systemRed（#ff453a）拿來
        # 當大面積底色時，白字只有 3.4:1；#d70015 是 5.4:1。這顆鈕坐在主要動作的
        # 位置上、字又是粗體 12pt，讀不清楚不是選項。
        "stop": "#d70015",
        "run_off": "#d2d2d7", "run_off_fg": "#8e8e93",
        "btn": "#e8e8ed", "btn_hi": "#dcdce1", "btn_lo": "#cfcfd6",
        "btn_off": "#f0f0f3",
        "field": "#f5f5f7", "field_off": "#f0f0f3",
        "line": "#d2d2d7", "line_off": "#e4e4e8",
        "trough": "#e8e8ed",
        "chk": "#ffffff", "chk_line": "#c7c7cc",
        "chk_off": "#f0f0f3", "chk_off_line": "#dcdce1",
    },
    "dark": {
        "accent": "#0a84ff", "accent_hi": "#3395ff",
        "on_accent": "#ffffff",
        "stop": "#d70015",
        "run_off": "#3a3a3c", "run_off_fg": "#7c7c80",
        # ⚠️ 次要按鈕比 meeting-scribe 亮一階（那邊是 #2c2c2e）：它的深色卡片是
        # #1d1d1f，而這裡的卡片是 sv_ttk 畫的、明顯亮一截——照抄的話按鈕會整顆
        # 融進卡片，畫面上只剩浮著的文字（2026-08-26 截圖確認）
        "btn": "#3a3a3c", "btn_hi": "#48484a", "btn_lo": "#2c2c2e",
        "btn_off": "#2c2c2e",
        "field": "#2c2c2e", "field_off": "#242426",
        "line": "#48484a", "line_off": "#3a3a3c",
        "trough": "#2c2c2e",
        "chk": "#2c2c2e", "chk_line": "#5a5a5e",
        "chk_off": "#242426", "chk_off_line": "#3a3a3c",
    },
}


def px(n: float, scale: float) -> int:
    return max(1, int(round(n * scale)))


def _sq_points(w: float, h: float, r: float) -> list[tuple[float, float]]:
    """連續圓角的輪廓點：四個角各是四分之一超橢圓，直邊保持直的。"""
    r = min(r, w / 2.0, h / 2.0)
    k = 2.0 / SQ_N
    q = [(r - r * math.cos(t) ** k, r - r * math.sin(t) ** k)
         for t in (i / SQ_STEPS * (math.pi / 2) for i in range(SQ_STEPS + 1))]
    rev = list(reversed(q))
    return (q                                     # 左上：(0,r) → (r,0)
            + [(w - x, y) for x, y in rev]        # 右上：(w-r,0) → (w,r)
            + [(w - x, h - y) for x, y in q]      # 右下：(w,h-r) → (w-r,h)
            + [(x, h - y) for x, y in rev])       # 左下：(r,h) → (0,h-r)


def _sq_mask(w: int, h: int, r: float) -> Image.Image:
    m = Image.new("L", (w * SQ_SS, h * SQ_SS), 0)
    ImageDraw.Draw(m).polygon(
        [(x * SQ_SS, y * SQ_SS) for x, y in _sq_points(w, h, r)], fill=255)
    return m.resize((w, h), Image.LANCZOS)


def plate(w: int, h: int, r: float, fill: str,
          line: str | None = None, lw: int = 1) -> Image.Image:
    """一張 squircle 底板：實色填滿，可選描邊。

    ⚠️ 先畫成不透明的 RGB、**最後**才把遮罩放進 alpha 通道（理由見檔頭第 3 點）。
    """
    w, h = max(1, w), max(1, h)
    outer = _sq_mask(w, h, r)
    img = Image.new("RGB", (w, h), fill)
    if line and lw > 0:
        inner = Image.new("L", (w, h), 0)
        inner.paste(_sq_mask(max(1, w - 2 * lw), max(1, h - 2 * lw),
                             max(1.0, r - lw)), (lw, lw))
        ring = Image.composite(outer, Image.new("L", (w, h), 0),
                               Image.eval(inner, lambda v: 255 - v))
        # 這一次 paste 是**在不透明的圖層裡**混色，描邊與填色混得對
        img.paste(Image.new("RGB", (w, h), line), (0, 0), ring)
    img = img.convert("RGBA")
    img.putalpha(outer)
    return img


def shade(img: Image.Image, amt: float) -> Image.Image:
    """整體提亮（amt>0）或壓暗（amt<0），**不動 alpha**。

    ⚠️ 不可以直接對 RGBA 做 blend／ImageEnhance：alpha 會跟著被混，抗鋸齒的邊緣
    當場糊掉一圈。
    """
    r, g, b, a = img.split()
    rgb = Image.merge("RGB", (r, g, b))
    tone = (255, 255, 255) if amt >= 0 else (0, 0, 0)
    rgb = Image.blend(rgb, Image.new("RGB", img.size, tone), abs(amt))
    return Image.merge("RGBA", (*rgb.split(), a))


def _pad_right(img: Image.Image, gap: int) -> Image.Image:
    """右邊補一段透明——核取方塊與標籤之間的縫，layout 裡沒有地方塞。"""
    out = Image.new("RGBA", (img.width + gap, img.height), (0, 0, 0, 0))
    out.paste(img, (0, 0))
    return out


def build_variant(theme: str, scale: float) -> tuple[dict, dict]:
    """畫出一組（某個佈景 × 某個縮放）的所有底板，回傳 (圖片, 元件定義)。"""
    p = SKINS[theme]
    imgs: dict[str, Image.Image] = {}
    elems: dict[str, dict] = {}

    def wide(r: int) -> tuple[int, int]:
        """底板的寬高：高剛好包得住兩個圓角，寬再多留 SQ_MID 的中段。"""
        return 2 * (r + 1) + px(SQ_MID, scale), 2 * (r + 1) + 1

    # ---- 一般按鈕：瀏覽…／變更…／開啟簡報／開啟紀錄／兩顆收合鈕 ----
    # ⚠️ **不描邊**：灰底本身就跟卡片分得開，再加一圈線就變成「框中框」（卡片
    # 一圈、按鈕一圈），meeting-scribe 的按鈕也是無框的
    r = px(SQ_R, scale)
    w, h = wide(r)
    for key, fill in (("button-rest", p["btn"]), ("button-dis", p["btn_off"]),
                      ("button-pressed", p["btn_lo"]), ("button-hover", p["btn_hi"])):
        imgs[key] = plate(w, h, r, fill)
    elems["Sq.button"] = dict(
        states=[["", "button-rest"], ["disabled", "button-dis"],
                ["pressed", "button-pressed"], ["active", "button-hover"]],
        border=r + 1, width=2 * (r + 1) + 1, height=h,
        padding=px(SQ_PAD, scale), sticky="nswe")

    # ---- 輸入框：取得焦點時描邊換成 accent 並加粗到 2px ----
    imgs["field-rest"] = plate(w, h, r, p["field"], p["line"])
    imgs["field-dis"] = plate(w, h, r, p["field_off"], p["line_off"])
    imgs["field-focus"] = plate(w, h, r, p["field"], p["accent"],
                                lw=max(2, px(2, scale)))
    elems["Sq.field"] = dict(
        states=[["", "field-rest"], ["disabled", "field-dis"],
                ["focus", "field-focus"]],
        border=r + 1, width=2 * (r + 1) + 1, height=h,
        padding=px(SQ_PAD_FIELD, scale), sticky="nswe")

    # ---- 核取方塊：沒勾是描邊空框，勾了才上色（Apple 自己的用法）----
    box, cr, gap = px(SQ_CHK_BOX, scale), px(SQ_R_CHK, scale), px(SQ_CHK_GAP, scale)

    def ticked(color: str) -> Image.Image:
        img = plate(box, box, cr, color)
        ImageDraw.Draw(img).line(
            [(box * .28, box * .52), (box * .43, box * .70), (box * .73, box * .30)],
            fill=p["on_accent"], width=max(2, px(2, scale)), joint="curve")
        return img

    imgs["check-off"] = _pad_right(plate(box, box, cr, p["chk"], p["chk_line"]), gap)
    imgs["check-on"] = _pad_right(ticked(p["accent"]), gap)
    imgs["check-off-dis"] = _pad_right(
        plate(box, box, cr, p["chk_off"], p["chk_off_line"]), gap)
    imgs["check-on-dis"] = _pad_right(shade(ticked(p["accent"]), -0.45), gap)
    # ⚠️ 這一顆**不切九宮格**（border=0）：方塊是固定尺寸的，拉伸只會把它拉歪
    elems["Sq.check"] = dict(
        states=[["", "check-off"], ["disabled selected", "check-on-dis"],
                ["disabled", "check-off-dis"], ["selected", "check-on"]],
        border=0, width=box + gap, height=box, padding=0, sticky="")

    # ---- 進度條：圓頭的軌道與填充條 ----
    # ⚠️ 高度是**釘死**的（thickness ＝ 圖高），所以九宮格的左右兩塊不會被垂直
    # 拉伸、圓頭不會變形；會被拉開的只有中段那一欄純色。
    th = px(SQ_PB_TH, scale)
    pr = th / 2.0
    pw = int(2 * (pr + 1) + px(SQ_MID, scale))
    imgs["trough"] = plate(pw, th, pr, p["trough"])
    imgs["pbar"] = plate(pw, th, pr, p["accent"])
    edge = int(pr) + 1
    for name, key in (("Sq.trough", "trough"), ("Sq.pbar", "pbar")):
        elems[name] = dict(states=[["", key]], border=[edge, 0, edge, 0],
                           width=int(2 * (pr + 1) + 1), height=th,
                           padding=0, sticky="nswe")

    # ---- 主要動作鈕的兩張皮：開始是 Apple 藍、停止是深紅 ----
    rr = px(SQ_R_RUN, scale)
    rw, rh = wide(rr)
    for kind, hover in (("accent", p["accent_hi"]), ("stop", None)):
        face = plate(rw, rh, rr, p[kind])
        imgs[f"{kind}-rest"] = face
        imgs[f"{kind}-dis"] = plate(rw, rh, rr, p["run_off"])
        imgs[f"{kind}-pressed"] = shade(face, -0.12)
        imgs[f"{kind}-hover"] = (plate(rw, rh, rr, hover) if hover
                                 else shade(face, 0.10))
        elems[f"Sq.{kind}"] = dict(
            states=[["", f"{kind}-rest"], ["disabled", f"{kind}-dis"],
                    ["pressed", f"{kind}-pressed"], ["active", f"{kind}-hover"]],
            border=rr + 1, width=2 * (rr + 1) + 1, height=rh,
            padding=px(SQ_PAD, scale), sticky="nswe")

    return imgs, elems


def pack(imgs: dict[str, Image.Image]) -> tuple[Image.Image, dict]:
    """把底板疊成一張 sprite sheet（單欄，最省事也最好對）。"""
    order = sorted(imgs)
    sheet_w = max(im.width for im in imgs.values())
    sheet_h = sum(imgs[k].height for k in order)
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    rects, y = {}, 0
    for k in order:
        im = imgs[k]
        sheet.paste(im, (0, y))
        rects[k] = [0, y, im.width, im.height]
        y += im.height
    return sheet, rects


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"version": 1, "scales": list(SCALES), "variants": {}}
    for theme in ("light", "dark"):
        for scale in SCALES:
            imgs, elems = build_variant(theme, scale)
            sheet, rects = pack(imgs)
            name = f"skin-{theme}@{scale:g}x.png"
            sheet.save(OUT / name, optimize=True)
            meta["variants"][f"{theme}@{scale:g}"] = {
                "file": name,
                "fg": {"on_accent": SKINS[theme]["on_accent"],
                       "run_off": SKINS[theme]["run_off_fg"]},
                "sprites": rects,
                "elements": elems,
            }
    (OUT / "sprites.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")

    total = 0
    for p in sorted(OUT.iterdir()):
        total += p.stat().st_size
        print(f"{p.relative_to(ROOT).as_posix()}  {p.stat().st_size:,} bytes")
    print(f"合計 {total:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
