#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生圖形介面的皮膚資產（assets/skin/ 底下那一組）。

    uv run python tools/make_skin.py

這支是**形狀**的唯一真值：圓角半徑、內距、九宮格的切法全寫在這裡，`assets/skin/`
的 PNG 與 `sprites.json` 都是它的產物。改了半徑就重跑一次，然後把 `assets/skin/`
整個目錄跟著程式碼一起提交。⚠️ **不要手改產物**——下一次重跑就被蓋掉（與
`tools/make_icon.py` 同一條原則）。

⚠️ **顏色不在這裡**，在 `pdf2ppt/palette.py`（產生器與介面共用一份，理由見那支的
docstring）。這裡只負責把那些顏色畫成形狀。

為什麼是圖
----------
ttk 內建的繪圖能力只有矩形、3D 浮雕邊框、直線——**沒有圓角、沒有抗鋸齒、沒有
任意路徑**。Windows 原生的 vista 佈景不必用圖，是因為它把繪圖整個交給作業系統
的 UxTheme API，拿到的是系統長什麼樣就什麼樣、形狀不能自訂。所以在 Tk 上要一個
自訂形狀的圓角，只有兩條路：**預先渲染成圖片**，或換掉整個 GUI 框架。

現在這個 Sun Valley 佈景（sv_ttk）自己就是這樣做的：一張 `spritesheet_light.png`
切成一堆小圖，再用 `ttk::style element create ... image` 掛上去。本檔產出的東西
與它同構，換掉的也正是它的 `Button.button`／`AccentButton.button`／`Entry.field`
／`Checkbutton.indicator`／進度條那幾個元件，另外多畫三張沒有前身的底板（卡片、
日誌槽、低調按鈕）。

形狀：正圓角，直邊保持直的
--------------------------
輪廓是 `|x|^n + |y|^n = r^n` 的四分之一：`n=2` 就是**正圓弧**，n 愈大愈方。

⚠️ **這裡曾經是 5.0（squircle），2026-08-26 使用者指定改成正圓**：他要「按鈕都
依照 MP4-2-SRT 樣式」，而那支同一天已經因為同一句話（「所有按鈕圓角弧度也跟
meeting-scribe 那張截圖相同」）換成了正圓。**畫面上不要有兩種曲線**。

為什麼 5.0 撐不住：超橢圓幾乎填滿整個角落方框、只在最角落切掉一點，半徑 21 時
**視覺上的圓角只有 7px**（量 sprite 的 alpha 量出來的）。小按鈕看不出來，卡片那麼
大一塊就是「幾乎直角」——所以光加大半徑沒有用，指數才是那個旋鈕。

⚠️ 四個一踩就壞的地方（1~3 是 2026-08-26 換皮時撞到的，第 4 點是同月卡片化時
撞到的；完整記述在 `docs/dev/windows-環境與入口.md` §5.9）：

1. **底板中段要夠寬**（`SQ_MID`）。九宮格的中段是 Tk **一格一格重複貼**滿的，
   不是拉伸；中段留 1px 的話，填一顆 840px 寬的收合鈕就是幾百次繪製呼叫，重畫
   整個視窗要 2.5 秒（看起來就像當掉）。對照組：sv_ttk 的按鈕 sprite 是 20×20
   配 `-border 4`，中段 12px。
2. **`border` 不可超過圖片邊長的一半。** 切不出九宮格時 ttk 會在幾何計算裡原地
   打轉，事件迴圈當場卡死——沒有例外、沒有訊息。
3. **先畫成不透明的 RGB，最後才把遮罩放進 alpha 通道。** 拿遮罩去 `paste` 一張
   RGB 到透明畫布上的話，角落抗鋸齒帶的 RGB 會先跟畫布的黑色混一次，而 Tk 合成
   時又依 alpha 混第二次，四個角就各浮出一圈比底色深的邊。
4. **第 1 點有垂直版**（`block()`）。卡片與日誌槽會被撐到好幾百 px 高，而只留
   1px 高的中段就是垂直幾百次 × 水平十幾次的繪製呼叫。會被撐得又寬又高的東西
   一律用 `block()`（兩個方向都留中段），只被水平拉開的（按鈕、輸入框、進度條）
   用 `wide()` 就好。

為什麼要產生五種縮放
--------------------
資產是固定像素，而顯示縮放不是：Windows 常見的是 100%／125%／150%／175%／200%。
每一檔各出一組，載入時挑最接近的——⚠️ 這幾檔正好**精確**對上那五個設定值，所以
實務上永遠是精確匹配，內距與圓角不會互相錯開。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "skin"

# 色票是共用的（見 `pdf2ppt/palette.py` 的 docstring）。⚠️ 走 sys.path 而不是
# 直接 `from pdf2ppt.palette import ...`，是為了讓這支在專案還沒 `uv sync` 過的
# 環境下也跑得動——它是開發工具，不該要求先把整套相依裝起來。
sys.path.insert(0, str(ROOT))
from pdf2ppt.palette import PALETTES as SKINS   # noqa: E402

# 顯示縮放。⚠️ 這五個值要對上 Windows 顯示設定裡的那五檔。
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)

SQ_N = 2.0            # 角落的曲線指數：**2.0 就是正圓弧**（見檔頭）
SQ_SS = 4             # 遮罩超取樣倍率（畫 4× 再縮回來，這就是抗鋸齒）
SQ_STEPS = 24         # 每個角取樣幾個點（再多肉眼看不出來，只是變慢）

# 圓角半徑（邏輯 px）。⚠️ 半徑是**新的一把尺**，不要拿版面的 SP_* 那把來湊——
# 間距與圓角在版面上管的是兩件事。數值逐像素量自 MP4-2-SRT 的參考畫面：
# 卡片 30 實體 ÷ 150% = 20，按鈕 12 ÷ 1.5 = 8（我們維持 10，差 3 實體像素，
# 肉眼分不出來）。
SQ_R = 10             # 一般按鈕、低調按鈕、輸入框
SQ_R_RUN = 12         # 主要動作鈕（大一號才撐得住那個字級）
SQ_R_BOX = 10         # 日誌槽
SQ_R_CHK = 5          # 核取方塊
# 卡片。**比它裡面的框大一號**：圓角一層套一層時內外同半徑會看起來內圈比較胖
# （外圈的曲率被更長的直邊稀釋掉），轉角對不齊。
SQ_R_CARD = 20
SQ_CHK_BOX = 20       # 核取方塊的邊長（沿用 sv_ttk 的尺寸，見下面的 SQ_PAD）
SQ_CHK_GAP = 8        # 方塊與標籤之間的縫（畫進圖片右側的透明區，layout 沒地方塞）
SQ_PB_TH = 7          # 進度條厚度
SQ_MID = 96           # 底板中段的寬度（見檔頭第 1、4 點，不可以縮回 1px）

# ⚠️ **底板自己要撐出來的內距**：sv_ttk 的按鈕／輸入框圖片是**自帶內距的**，換掉
# 圖片就得把那一份補回來，否則全畫面的控制項一起矮 8px、視窗 reqheight 從 426 掉
# 到 387（2026-08-26 用皮膚開／關逐個量 requested size 量出來的：按鈕與收合鈕一律
# 差 8×8，輸入框差 10 寬 7 高）。控制項自己的內距仍然歸 GUI 那幾行樣式設定管。
SQ_PAD = 4            # 按鈕
SQ_PAD_FIELD = 5      # 輸入框（比按鈕多 1px，才跟按鈕一樣高）


def px(n: float, scale: float) -> int:
    return max(1, int(round(n * scale)))


def _sq_points(w: float, h: float, r: float) -> list[tuple[float, float]]:
    """圓角的輪廓點：四個角各是四分之一超橢圓，直邊保持直的。"""
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
          line: str | None = None, lw: int = 1,
          on: str | None = None) -> Image.Image:
    """一張圓角底板：實色填滿，可選描邊。

    ⚠️ 先畫成不透明的 RGB、**最後**才把遮罩放進 alpha 通道（理由見檔頭第 3 點）。

    `on` ＝ **這張底板坐在什麼顏色上**。給了就把圓角外側直接畫成那個色、整張圖
    不透明；不給就留透明。

    ⚠️ **一定要給。** 理由是 ttk 的繪製順序：它先用樣式的 `background` 把整塊填滿，
    **再**把九宮格的圖畫上去——圓角外側那圈透明區露出來的是那個 background，不是
    父容器的顏色。沒有卡片的年代這件事看不出來（樣式的預設背景正好就是視窗底），
    2026-08-26 卡片化之後就是「按鈕的圓角外露出一圈視窗底的灰、方方正正貼在白卡
    上」。⚠️ 也**不要**改走「把樣式的 `background` 設成外側色」那條捷徑：那對
    `TFrame` 有效，但對有自己 `background` 語意的控制項（`Treeview` 的列底色、
    `TEntry` 的欄位底）就是把別的東西一起改掉。代價只是「同一張底板不能重複用在
    兩種背景上」——本專案的每個控制項都只坐在一種底色上（按鈕／輸入框／核取方塊
    在卡片上、卡片與收合鈕在視窗底上）。
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
    if on is not None:
        # 圓角外側直接畫成它坐的那個顏色，整張不透明（見 docstring）。
        # ⚠️ 用 `outer` 當遮罩貼上去：抗鋸齒那一圈於是與外側色**混得對**，而不是
        # 先跟黑色混一次再由 Tk 混第二次（檔頭第 3 點的同一個坑）
        base = Image.new("RGB", (w, h), on)
        base.paste(img, (0, 0), outer)
        return base.convert("RGBA")
    img = img.convert("RGBA")
    img.putalpha(outer)
    return img


def shade(color: str, amt: float) -> str:
    """把**色碼**往白（amt>0）或黑（amt<0）拉，回傳新的色碼。

    ⚠️ **對顏色做，不是對圖片做。** 這支原本是整張圖去 blend，那在底板還透明的
    年代沒問題；底板改成不透明（見 `plate` 的 `on`）之後，整張 blend 會把圓角外側
    那圈「它坐的顏色」一起壓暗——按下按鈕時，卡片上會浮出一圈比周圍暗的方框。

    hover 有明確色碼、pressed 沒有，所以 pressed 那一階一律由這支從同一個底色推
    出來，免得再手配一組沒有人記得該差多少的色碼。
    """
    rgb = ImageColor.getrgb(color)
    tone = 255 if amt >= 0 else 0
    return "#%02x%02x%02x" % tuple(
        round(c + (tone - c) * abs(amt)) for c in rgb)


def _pad_right(img: Image.Image, gap: int) -> Image.Image:
    """右邊補一段透明——核取方塊與標籤之間的縫，layout 裡沒有地方塞。"""
    out = Image.new("RGBA", (img.width + gap, img.height), (0, 0, 0, 0))
    out.paste(img, (0, 0))
    return out


def build_variant(theme: str, scale: float) -> tuple[dict, dict]:
    """畫出一組（某個佈景 × 某個縮放）的所有底板，回傳 (圖片, 元件定義)。

    ⚠️ **每一個元件都要在 `elems` 裡記下自己的 `on`**（它坐在什麼顏色上，見
    `plate`）。那個欄位 ttk 用不到——它進資產是為了讓**測試**驗得到「新增一張底板
    時忘了指定外側色」，而那個漏法的症狀（圓角外側一塊實心方角）只有截圖看得
    出來。`tests/test_gui_helpers.py` 釘著。
    """
    p = SKINS[theme]
    mid = px(SQ_MID, scale)
    imgs: dict[str, Image.Image] = {}
    elems: dict[str, dict] = {}

    def wide(r: int) -> tuple[int, int]:
        """底板的寬高：高剛好包得住兩個圓角，寬再多留 SQ_MID 的中段。

        給**高度固定**的東西用（按鈕、輸入框、進度條）：它們只會被水平拉開，
        垂直方向重複貼一兩次而已。"""
        return 2 * (r + 1) + mid, 2 * (r + 1) + 1

    def block(r: int) -> tuple[int, int]:
        """兩個方向都留中段。給**會被撐得又寬又高**的東西用（卡片、日誌槽）。

        ⚠️ 這是檔頭第 1 點的垂直版（第 4 點），而且它比水平版痛得多：`wide()` 的
        中段高只有 1px，填一張 400px 高的卡片就是垂直三百多次 × 水平十幾次的繪製
        呼叫，而畫面上有四張卡片加一個日誌槽。代價是圖片面積變大，但那是實色圓角、
        PNG 壓得掉。

        ⚠️ 元件的 `width`／`height` **不可以跟著改成圖片邊長**——那兩個是「最小
        尺寸」，給了整張圖的邊長之後每一張卡片都會被硬撐成一百多 px 高。"""
        return 2 * (r + 1) + mid, 2 * (r + 1) + mid

    # ---- 一般按鈕：瀏覽…／變更…／開啟簡報／開啟資料夾（都坐在卡片上）----
    # ⚠️ **不描邊**：灰底本身就跟白卡分得開，再加一圈線就變成「框中框」（卡片
    # 一圈、按鈕一圈），meeting-scribe 的按鈕也是無框的
    r = px(SQ_R, scale)
    w, h = wide(r)
    for key, fill in (("button-rest", p["btn"]), ("button-dis", p["btn_off"]),
                      ("button-pressed", p["btn_lo"]), ("button-hover", p["btn_hi"])):
        imgs[key] = plate(w, h, r, fill, on=p["card"])
    elems["Sq.button"] = dict(
        states=[["", "button-rest"], ["disabled", "button-dis"],
                ["pressed", "button-pressed"], ["active", "button-hover"]],
        border=r + 1, width=2 * (r + 1) + 1, height=h,
        padding=px(SQ_PAD, scale), sticky="nswe", on=p["card"])

    # ---- 線框鈕：「瀏覽…」----
    # ⚠️ **整個畫面只有這一顆**（使用者 2026-08-27）：它是「選檔」這條主線的起點，
    # 值得在滑鼠經過時明確地說「按這裡」。「變更…」一度也套上去、當場被要求還原
    # ——**主要焦點只有一個**；「開啟簡報／開啟資料夾」是跑完之後的分岔。
    # ⚠️ **靜止是「白底藍框」不是灰底實心**（使用者 2026-08-27 更正，指的是那一頁上
    # 「查看價格」那顆而不是「進一步了解」）：底色就是卡片本身，只有一圈線與字是藍的。
    # ⚠️ 三個藍不可互換：線框走 `cta_fg`（深色要亮一階才讀得到）、翻過去的底走
    # `cta_hi`（兩模式同值），理由都在色票。
    # ⚠️ 線寬跟著顯示縮放走（輸入框那圈是固定 1px）：這一圈是**強調**，200% 下留 1
    # 實體像素會細到看不出它是個按鈕。
    lw = max(1, px(1, scale))
    imgs["cta-rest"] = plate(w, h, r, p["card"], p["cta_fg"], lw=lw, on=p["card"])
    # 停用：淡框淡字，看得出「這裡本來有顆鈕，但現在按不動」
    imgs["cta-dis"] = plate(w, h, r, p["card"], p["line_off"], lw=lw, on=p["card"])
    imgs["cta-pressed"] = plate(w, h, r, shade(p["cta_hi"], -0.12), on=p["card"])
    imgs["cta-hover"] = plate(w, h, r, p["cta_hi"], on=p["card"])
    elems["Sq.cta"] = dict(
        states=[["", "cta-rest"], ["disabled", "cta-dis"],
                ["pressed", "cta-pressed"], ["active", "cta-hover"]],
        border=r + 1, width=2 * (r + 1) + 1, height=h,
        padding=px(SQ_PAD, scale), sticky="nswe", on=p["card"])

    # ---- 低調按鈕：兩張可收合卡片的標題列，與「開啟紀錄」----
    # ⚠️ 靜止態就是**卡片底色本身**：那三顆讀起來要像區段標題而不是三條灰色橫槓
    # （收合鈕整條寬，做成實底就是畫面上最重的三個元素）。滑過才浮出灰底——
    # 這正是 Fluent 的 Subtle button。
    # ⚠️ `on` 是 `card` 不是 `page`：2026-08-26 使用者指定「展開的內容不要用另外
    # 一張卡片，應該是同一張」，收合鈕於是從卡片之外搬進卡片裡當標題列，靜止色與
    # 外側色都得跟著換——留在 `page` 的話，白卡上會浮出一條視窗底色的灰橫槓。
    for key, fill in (("subtle-rest", p["card"]), ("subtle-dis", p["card"]),
                      ("subtle-pressed", p["btn_lo"]), ("subtle-hover", p["btn"])):
        imgs[key] = plate(w, h, r, fill, on=p["card"])
    elems["Sq.subtle"] = dict(
        states=[["", "subtle-rest"], ["disabled", "subtle-dis"],
                ["pressed", "subtle-pressed"], ["active", "subtle-hover"]],
        border=r + 1, width=2 * (r + 1) + 1, height=h,
        padding=px(SQ_PAD, scale), sticky="nswe", on=p["card"])

    # ---- 版面的卡片 ----
    # ⚠️ **內距給 0**：卡片的內距是版面的一把尺（GUI 的 CARD_PAD，要過 App.px()
    # 跟著顯示縮放走），不是底板自帶的。按鈕／輸入框那幾張要自帶內距，是因為它們
    # 換掉的 sv_ttk 圖片本來就帶著一份（見 SQ_PAD）；卡片沒有前身，不必補。
    cr = px(SQ_R_CARD, scale)
    cw, ch = block(cr)      # ⚠️ 卡片很高，見 block() 的說明
    imgs["card-rest"] = plate(cw, ch, cr, p["card"], p["card_line"], on=p["page"])
    elems["Sq.card"] = dict(
        states=[["", "card-rest"]],
        border=cr + 1, width=2 * (cr + 1) + 1, height=2 * (cr + 1) + 1,
        padding=0, sticky="nswe", on=p["page"])

    # ---- 日誌槽：卡片裡凹下去的那一層 ----
    # ⚠️ 圓角**由這一層畫**：`tk.Text` 是 classic 控制項，沒有 ttk 樣式、做不到
    # 圓角。Text 縮在這個框裡（GUI 那邊給 SP_SM 的內距），方角才不會伸進弧裡。
    br = px(SQ_R_BOX, scale)
    bw, bh = block(br)      # 同上：日誌槽是版面上唯一會長高的東西
    imgs["sunken-rest"] = plate(bw, bh, br, p["field"], p["line"], on=p["card"])
    elems["Sq.sunken"] = dict(
        states=[["", "sunken-rest"]],
        border=br + 1, width=2 * (br + 1) + 1, height=2 * (br + 1) + 1,
        padding=px(SQ_PAD_FIELD, scale), sticky="nswe", on=p["card"])

    # ---- 輸入框：取得焦點時描邊換成 accent 並加粗到 2px ----
    imgs["field-rest"] = plate(w, h, r, p["field"], p["line"], on=p["card"])
    imgs["field-dis"] = plate(w, h, r, p["field_off"], p["line_off"], on=p["card"])
    imgs["field-focus"] = plate(w, h, r, p["field"], p["accent"],
                                lw=max(2, px(2, scale)), on=p["card"])
    elems["Sq.field"] = dict(
        states=[["", "field-rest"], ["disabled", "field-dis"],
                ["focus", "field-focus"]],
        border=r + 1, width=2 * (r + 1) + 1, height=h,
        padding=px(SQ_PAD_FIELD, scale), sticky="nswe", on=p["card"])

    # ---- 核取方塊：沒勾是凹下去的空框，勾了才上色（Apple 自己的用法）----
    box, ckr, gap = px(SQ_CHK_BOX, scale), px(SQ_R_CHK, scale), px(SQ_CHK_GAP, scale)

    def ticked(color: str) -> Image.Image:
        img = plate(box, box, ckr, color, on=p["card"])
        ImageDraw.Draw(img).line(
            [(box * .28, box * .52), (box * .43, box * .70), (box * .73, box * .30)],
            fill=p["on_accent"], width=max(2, px(2, scale)), joint="curve")
        return img

    imgs["check-off"] = _pad_right(
        plate(box, box, ckr, p["field"], p["line"], on=p["card"]), gap)
    imgs["check-on"] = _pad_right(ticked(p["accent"]), gap)
    imgs["check-off-dis"] = _pad_right(
        plate(box, box, ckr, p["field_off"], p["line_off"], on=p["card"]), gap)
    imgs["check-on-dis"] = _pad_right(ticked(shade(p["accent"], -0.45)), gap)
    # ⚠️ 這一顆**不切九宮格**（border=0）：方塊是固定尺寸的，拉伸只會把它拉歪
    elems["Sq.check"] = dict(
        states=[["", "check-off"], ["disabled selected", "check-on-dis"],
                ["disabled", "check-off-dis"], ["selected", "check-on"]],
        border=0, width=box + gap, height=box, padding=0, sticky="",
        on=p["card"])

    # ---- 進度條：圓頭的軌道與填充條 ----
    # ⚠️ 高度是**釘死**的（thickness ＝ 圖高），所以九宮格的左右兩塊不會被垂直
    # 拉伸、圓頭不會變形；會被拉開的只有中段那一欄純色。
    th = px(SQ_PB_TH, scale)
    pr = th / 2.0
    pw = int(2 * (pr + 1) + mid)
    imgs["trough"] = plate(pw, th, pr, p["trough"], on=p["card"])
    imgs["pbar"] = plate(pw, th, pr, p["accent"], on=p["trough"])
    edge = int(pr) + 1
    for name, key, on in (("Sq.trough", "trough", p["card"]),
                          ("Sq.pbar", "pbar", p["trough"])):
        elems[name] = dict(states=[["", key]], border=[edge, 0, edge, 0],
                           width=int(2 * (pr + 1) + 1), height=th,
                           padding=0, sticky="nswe", on=on)

    # ---- 主要動作鈕的兩張皮：開始是 Apple 藍、停止是深紅 ----
    rr = px(SQ_R_RUN, scale)
    rw, rh = wide(rr)
    for kind, hover in (("accent", p["accent_hi"]), ("stop", None)):
        imgs[f"{kind}-rest"] = plate(rw, rh, rr, p[kind], on=p["card"])
        imgs[f"{kind}-dis"] = plate(rw, rh, rr, p["run_off"], on=p["card"])
        imgs[f"{kind}-pressed"] = plate(rw, rh, rr, shade(p[kind], -0.12),
                                        on=p["card"])
        imgs[f"{kind}-hover"] = plate(rw, rh, rr, hover or shade(p[kind], 0.10),
                                      on=p["card"])
        elems[f"Sq.{kind}"] = dict(
            states=[["", f"{kind}-rest"], ["disabled", f"{kind}-dis"],
                    ["pressed", f"{kind}-pressed"], ["active", f"{kind}-hover"]],
            border=rr + 1, width=2 * (rr + 1) + 1, height=rh,
            padding=px(SQ_PAD, scale), sticky="nswe", on=p["card"])

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
