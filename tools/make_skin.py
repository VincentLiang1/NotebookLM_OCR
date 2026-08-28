#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生圖形介面的皮膚資產（`pdf2ppt/assets/skin/` 底下那一組）。

    uv run python tools/make_skin.py

這支是**這支程式要哪些底板**的唯一真值：圓角半徑、高度、內距、要產哪幾檔縮放全寫
在這裡，`pdf2ppt/assets/skin/` 的 PNG 與 `sprites.json` 都是它的產物。改了半徑就重
跑一次，然後把 `pdf2ppt/assets/skin/` 整個目錄跟著程式碼一起提交。⚠️ **不要手改產物**——下一次重跑就被蓋掉（與
`tools/make_icon.py` 同一條原則）。

⚠️ **顏色不在這裡**，在共用包 `winkit.palette`（產生器與介面共用一份，理由見那支的
docstring）。這裡只負責把那些顏色畫成形狀。

形狀與那五個地雷:在共用包裡
--------------------------
⚠️ **「怎麼畫」2026-08-28 整批搬進 `winkit.skingen`**:為什麼非得預先渲染成圖片、
超橢圓為什麼是 n=2.0 的正圓弧、九宮格與膠囊那五個一踩就壞的地方(中段要夠寬、
`border` 不可超過邊長的一半而且要逐軸比、先畫 RGB 最後才放 alpha、會長高的用
`block()`、膠囊的圖高必須精確等於元件高度)——**動任何一個 `SQ_*` 之前先讀那一支**。

⚠️ **不要把那幾條抄回這裡**:兩份就是兩份會漂的說明,而三個 repo 漂開的成因正是
「要產哪幾張皮」與「超橢圓怎麼取樣」寫在同一支檔案裡(量到 763 行的差距)。這裡留下
來的是**這一支的長相**:要產哪幾張底板、每一張多高多圓、出貨哪幾檔縮放、哪一張坐在
什麼顏色上。

為什麼要產生五種縮放
--------------------
資產是固定像素，而顯示縮放不是：Windows 常見的是 100%／125%／150%／175%／200%。
每一檔各出一組，載入時挑最接近的——⚠️ 這幾檔正好**精確**對上那五個設定值，所以
實務上永遠是精確匹配，內距與圓角不會互相錯開。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

# 幾何走共用包（見檔頭「形狀」那一段）。⚠️ **這一行就是 A/B 界線**：右邊那些是
# 「兩支程式都該一樣」的畫法，左邊留下來的是「這一支要產哪幾張、每一張多大」。
from winkit.skingen import (SQ_N, SQ_SS, SQ_STEPS,   # noqa: F401（SQ_N 只被文件引用）
                            block, block_elem, pad_right, pill,
                            pill_elem, plate, px, shade)
from winkit.skingen import pack as _pack

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pdf2ppt" / "assets" / "skin"

# 色票走共用包（見 `winkit.palette` 的 docstring）。⚠️ **2026-08-28 從專案裡的
# `palette` 換過來**：顏色是「兩支程式要對得起來」的設計系統，不是這一支的身分，
# 所以它的唯一真值在共用包裡，改一次兩邊拿到。⚠️ 連帶拿掉了那行 `sys.path.insert`
# ——它當初的用意是「專案還沒 uv sync 過也跑得動」，而這支本來就要 Pillow，那個
# 承諾早就不成立了。
from winkit.palette import PALETTES as SKINS

# 顯示縮放。⚠️ 這五個值要對上 Windows 顯示設定裡的那五檔。
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)

# `sprites.json` 的 schema 版本。⚠️ **element 的欄位形狀一改就要跳號**，GUI 那邊的
# `SKIN_SCHEMA` 要同號（`tests/test_gui_helpers.py` 兩邊對釘）。
#
# ⚠️ **理由是「舊資產配新程式」是可達的**：使用者換電腦的方式是複製專案資料夾，只
# 覆蓋 `.py` 而留著舊的 `assets/skin/` 完全做得到。舊檔的每一個 key 都還在，
# `_from_assets` 於是會**成功**回傳、`source` 還報 `assets`，把不相容的元件定義裝上
# 去——沒有例外、沒有 log，而那支資產一致性測試只比「資產＝現在的產生器」，看不到
# 別人機器上的舊資產。
#
# 2 = 2026-08-27 膠囊化：`border` 從 int 變成 `[左, 上, 右, 下]` 四元組。
SCHEMA_VERSION = 2

# ⚠️ `SQ_N`（曲線指數，2.0 ＝正圓弧）、`SQ_SS`（超取樣倍率）、`SQ_STEPS`（每個角
# 取樣幾點）**是 import 進來的**，不在這裡定義：它們是「怎麼畫」而不是「畫什麼」，
# 唯一真值在 `winkit.skingen`（連同那三個值為什麼是這樣的完整理由）。這裡只留
# 「這支程式要哪些形狀、多大」。

# ---------------------------------------------------------------------------
# 按鈕與輸入框：**高度**（邏輯 px），半徑不再是自己一把尺
# ---------------------------------------------------------------------------
# ⚠️ 使用者 2026-08-27 指定「做成 https://www.apple.com/ 那樣的」——那一頁的按鈕是
# `border-radius: 980px` 的完整膠囊：**兩端各一個完整半圓**，不是「圓角比較大的
# 矩形」。所以半徑不再由這裡指定，它恆等於圖高的一半（見 `pill()`）；這裡指定的
# 是**高度**，而高度會透過元件的 `height` 把控制項**釘死**。
#
# ⚠️ **釘死不是副作用，是這條路的入場費。** 垂直方向不切九宮格才拿得到完整半圓，
# 而不切的代價是圖高必須精確等於元件高度（不等的兩種壞法與實測見 `pill()`，那裡
# 是正本；兩種都是靜默的）。好處是按鈕高度從此**跨 DPI 與字型一致**，
# 不再被字型度量牽著走（同一顆鈕的邏輯高度本來在 40.0~41.0 之間漂）。
#
# ⚠️ **配套：那一類樣式的垂直 padding 必須讓內容矮於這裡的高度。** 元件高度取
# 「內容需求」與 `height` 的較大者，內容一旦撐過頭就變成「圖比元件矮」那個壞法。
# GUI 那幾行 `st.configure(..., padding=(水平, 垂直))` 因此跟著這裡一起調過，
# 逐檔驗算的餘裕是 **10~27 實體像素**，最小的是 100% 下的輸入框（量法與表格見
# `docs/dev/windows-環境與入口.md` §5.11）。⚠️ 這個數字一度寫成「5~11」而且**兩端
# 都不對**：漏量了輸入框與基底 `TButton`（當時兩格都是 0，見 `SQ_PAD_FIELD`）。
# ⚠️ 餘裕從 2~12 變成 10~27，是 2026-08-27 晚把**元件自己的 `padding` 也改成只給
# 左右**換來的（見 `hpad()`）——`border` 的上下早就是 0，`padding` 卻還是純量，
# 而那一份垂直內距在高度被釘死的膠囊上換不到任何東西。改完畫面**逐像素相同**。
# ⚠️ **現在不必再靠人工重跑**：`tests/test_gui_helpers.py` 的三支膠囊測試把「元件
# 高度＝圖高」「餘裕不得為 0」「底板幾何」釘住了，`uv run pytest` 就會說話。
#
# 取值貼著改版前的自然高度，版面才不會跑掉（實體像素差 0~+3）：
#   主要動作鈕 40（原 40.0~41.0）　收合鈕 45（原 44.7~45.5）
#   開啟紀錄 31（原 30.0~32.0）　一般按鈕・線框鈕・輸入框 30
# ⚠️ 最後那三個**刻意統一**：改版前是 30/31/30（實體 42/45/44 @150%），
# 「瀏覽…」「變更…」與它們中間那個輸入框並排卻各差幾 px，那是沒有人選過的。
#
# ⚠️ 卡片與日誌槽**不走膠囊**：它們沒有「一種高度」（會被內容撐到幾百 px），而且
# 膠囊在一整塊內容區上讀起來不是容器、是藥丸。那兩個維持逐像素量自 MP4-2-SRT
# 參考畫面的 20／10（`SQ_R_CARD`／`SQ_R_BOX`），仍然走四角九宮格。
SQ_H = 30             # 一般按鈕、線框鈕、輸入框（三者從此同高）
SQ_H_RUN = 40         # 主要動作鈕（開始／停止）
SQ_H_ADV = 45         # 收合鈕（兩張可收合卡片的標題列）
SQ_H_SUB = 31         # 開啟紀錄（同一張低調皮的小號版，見 build_variant）
SQ_R_BOX = 10         # 日誌槽（不是膠囊，見上）
SQ_R_CHK = 5          # 核取方塊（不是膠囊：正圓會讀成 radio button）
# 卡片。**比它裡面的框大一號**：圓角一層套一層時內外同半徑會看起來內圈比較胖
# （外圈的曲率被更長的直邊稀釋掉），轉角對不齊。
SQ_R_CARD = 20
SQ_CHK_BOX = 20       # 核取方塊的邊長（沿用 sv_ttk 的尺寸，見下面的 SQ_PAD）
SQ_CHK_GAP = 8        # 方塊與標籤之間的縫（畫進圖片右側的透明區，layout 沒地方塞）
SQ_PB_TH = 7          # 進度條厚度
# 收合鈕的三角形。⚠️ **畫成圖片而不是用文字字元**（2026-08-27，使用者說「三角形
# 太小」）：`▸`／`▾` 在 10pt 下的字墨只有 7×8px，而換成 advance width 更寬的
# `⏵`／`⏷` 也沒有用——那多出來的寬度是字元的間距、glyph 本身一樣小。字級是整顆鈕
# 共用的，沒辦法只放大一個字元，所以唯一能控制大小的路就是圖片。
SQ_CHEV = 11          # 三角形的邊長
SQ_CHEV_GAP = 9       # 三角形與標題之間的縫（畫進圖片右側的透明區）
SQ_MID = 96           # 底板中段的寬度（見檔頭第 1、4 點，不可以縮回 1px）

# ⚠️ **底板自己要撐出來的內距**：sv_ttk 的按鈕／輸入框圖片是**自帶內距的**，換掉
# 圖片就得把那一份補回來，否則全畫面的控制項一起矮 8px、視窗 reqheight 從 426 掉
# 到 387（2026-08-26 用皮膚開／關逐個量 requested size 量出來的：按鈕與收合鈕一律
# 差 8×8，輸入框差 10 寬 7 高）。控制項自己的內距仍然歸 GUI 那幾行樣式設定管。
SQ_PAD = 4            # 按鈕
# ⚠️ **輸入框從 5 降回 4（2026-08-27 晚）：那個「多 1px」的理由已經死了。** 舊註解
# 寫的是「比按鈕多 1px，才跟按鈕一樣高」——那是高度還由內容決定的年代；膠囊化之後
# 輸入框與按鈕共用同一張 `pill(SQ_H)` 底板、`height` 一樣，多出來的 1px 不再換到
# 任何東西，只是把上下各吃掉 1px。⚠️ 代價很實在：它讓 `Sq.field` 成為全畫面**唯一
# 餘裕為 0** 的膠囊（五檔量到 0/1/1/2/2，按鈕是 3~12），而 `ui_font_family()` 在沒裝
# Microsoft JhengHei (UI) 的機器上會退到 Segoe UI，那條路在 150% 下輸入框要 47 而
# 底板只有 45——**下半個圓當場被削平，今天就在發生**。
SQ_PAD_FIELD = 4      # 輸入框（與按鈕同一張底板，就跟按鈕同一個內距）
SQ_PAD_SUNKEN = 5     # 日誌槽（不是膠囊，內距與輸入框無關，2026-08-27 拆開）


def chevron(size: int, color: str, down: bool) -> Image.Image:
    """收合鈕的三角形（▶／▼）。

    ⚠️ **兩個方向畫在一模一樣大小的畫布上**：換狀態時整行文字才不會左右跳一格
    （用文字字元時這一條要靠「挑到同寬的那一對」來滿足，實測 ▶／▼ 是 10／13、
    ‣／▾ 是 5／7，都會跳）。

    ⚠️ **這一張留透明、不給 `on`**（`plate` 那條「一定要給」的唯一例外）：它由 Tk
    合成到按鈕自己的底色上，而那個底色會變——低調皮靜止時是卡片色、滑過去是灰的。
    """
    m = Image.new("L", (size * SQ_SS, size * SQ_SS), 0)
    s = size * SQ_SS
    # 底邊佔滿、頂點在對邊中點；留 0.22 的邊，抗鋸齒才不會把尖角削掉
    pts = ([(0, s * 0.22), (s, s * 0.22), (s / 2, s * 0.78)] if down
           else [(s * 0.22, 0), (s * 0.22, s), (s * 0.78, s / 2)])
    ImageDraw.Draw(m).polygon(pts, fill=255)
    img = Image.new("RGB", (size, size), color).convert("RGBA")
    img.putalpha(m.resize((size, size), Image.LANCZOS))
    return img


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

    def hpad(n: int) -> list[int]:
        """膠囊的內距：**只給左右，上下給 0**。

        ⚠️ **這是 `pill()` 那條「垂直方向什麼都不要切」的最後一塊。** `border` 的
        上下早就是 0 了，`padding` 卻一直是個純量（四邊都套）——而膠囊的高度被
        `height` 釘住、標籤在裡面置中，所以**垂直那一份內距換不到任何東西**：它不
        會移動文字（上下對稱，扣掉之後還是置中），只會把「內容需求」灌高 2n、把
        餘裕吃掉，而餘裕是這條規則唯一的安全邊界。

        ⚠️ 水平那一份**必須留著**：寬度是內容決定的，那正是 `SQ_PAD` 存在的理由
        （補回 sv_ttk 圖片自帶的內距，見那一段）。

        ⚠️ 卡片／日誌槽／核取方塊**不套這支**——它們的高度是內容撐出來的，垂直
        內距在那裡是真的有作用。
        """
        return [px(n, scale), 0, px(n, scale), 0]

    # ---- 一般按鈕：瀏覽…／變更…／開啟簡報／開啟資料夾（都坐在卡片上）----
    # ⚠️ **不描邊**：灰底本身就跟白卡分得開，再加一圈線就變成「框中框」（卡片
    # 一圈、按鈕一圈），meeting-scribe 的按鈕也是無框的
    w, h, r, br_ = pill(SQ_H, scale, mid)
    for key, fill in (("button-rest", p["btn"]), ("button-dis", p["btn_off"]),
                      ("button-pressed", p["btn_lo"]), ("button-hover", p["btn_hi"])):
        imgs[key] = plate(w, h, r, fill, on=p["card"])
    elems["Sq.button"] = pill_elem(
        [["", "button-rest"], ["disabled", "button-dis"],
         ["pressed", "button-pressed"], ["active", "button-hover"]],
        h, br_, p["card"], padding=hpad(SQ_PAD))

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
    elems["Sq.cta"] = pill_elem(
        [["", "cta-rest"], ["disabled", "cta-dis"],
         ["pressed", "cta-pressed"], ["active", "cta-hover"]],
        h, br_, p["card"], padding=hpad(SQ_PAD))

    # ---- 低調按鈕：兩張可收合卡片的標題列，與「開啟紀錄」----
    # ⚠️ 靜止態就是**卡片底色本身**：那三顆讀起來要像區段標題而不是三條灰色橫槓
    # （收合鈕整條寬，做成實底就是畫面上最重的三個元素）。滑過才浮出灰底——
    # 這正是 Fluent 的 Subtle button。
    # ⚠️ `on` 是 `card` 不是 `page`：2026-08-26 使用者指定「展開的內容不要用另外
    # 一張卡片，應該是同一張」，收合鈕於是從卡片之外搬進卡片裡當標題列，靜止色與
    # 外側色都得跟著換——留在 `page` 的話，白卡上會浮出一條視窗底色的灰橫槓。
    # ⚠️ **兩個尺寸各一張**（2026-08-27 膠囊化時拆的）：收合鈕整條寬、高 45 邏輯
    # px，「開啟紀錄」只有 31。膠囊的半徑恆等於**自己**圖高的一半，而圖高又必須
    # 等於元件高度，所以兩種高度就是兩張圖——共用一張的話兩顆必有一顆壞掉（哪兩種
    # 壞法見 `pill()`）。
    for elem, prefix, hh in (("Sq.subtle", "subtle", SQ_H_ADV),
                             ("Sq.subtlesm", "subtlesm", SQ_H_SUB)):
        sw, sh, sr, sbr = pill(hh, scale, mid)
        for key, fill in ((f"{prefix}-rest", p["card"]),
                          (f"{prefix}-dis", p["card"]),
                          (f"{prefix}-pressed", p["btn_lo"]),
                          (f"{prefix}-hover", p["btn"])):
            imgs[key] = plate(sw, sh, sr, fill, on=p["card"])
        elems[elem] = pill_elem(
            [["", f"{prefix}-rest"], ["disabled", f"{prefix}-dis"],
             ["pressed", f"{prefix}-pressed"], ["active", f"{prefix}-hover"]],
            sh, sbr, p["card"], padding=hpad(SQ_PAD))

    # ---- 版面的卡片 ----
    # ⚠️ **內距給 0**：卡片的內距是版面的一把尺（GUI 的 CARD_PAD，要過 App.px()
    # 跟著顯示縮放走），不是底板自帶的。按鈕／輸入框那幾張要自帶內距，是因為它們
    # 換掉的 sv_ttk 圖片本來就帶著一份（見 SQ_PAD）；卡片沒有前身，不必補。
    cr = px(SQ_R_CARD, scale)
    cw, ch = block(cr, mid)      # ⚠️ 卡片很高，見 block() 的說明
    imgs["card-rest"] = plate(cw, ch, cr, p["card"], p["card_line"], on=p["page"])
    elems["Sq.card"] = block_elem([["", "card-rest"]], cr, 0, p["page"])

    # ---- 日誌槽：卡片裡凹下去的那一層 ----
    # ⚠️ 圓角**由這一層畫**：`tk.Text` 是 classic 控制項，沒有 ttk 樣式、做不到
    # 圓角。Text 縮在這個框裡（GUI 那邊給 SP_SM 的內距），方角才不會伸進弧裡。
    br = px(SQ_R_BOX, scale)
    bw, bh = block(br, mid)      # 同上：日誌槽是版面上唯一會長高的東西
    imgs["sunken-rest"] = plate(bw, bh, br, p["field"], p["line"], on=p["card"])
    elems["Sq.sunken"] = block_elem([["", "sunken-rest"]], br,
                                    px(SQ_PAD_SUNKEN, scale), p["card"])

    # ---- 輸入框：取得焦點時描邊換成 accent 並加粗到 2px ----
    imgs["field-rest"] = plate(w, h, r, p["field"], p["line"], on=p["card"])
    imgs["field-dis"] = plate(w, h, r, p["field_off"], p["line_off"], on=p["card"])
    imgs["field-focus"] = plate(w, h, r, p["field"], p["accent"],
                                lw=max(2, px(2, scale)), on=p["card"])
    elems["Sq.field"] = pill_elem(
        [["", "field-rest"], ["disabled", "field-dis"],
         ["focus", "field-focus"]],
        h, br_, p["card"], padding=hpad(SQ_PAD_FIELD))

    # ---- 核取方塊：沒勾是凹下去的空框，勾了才上色（Apple 自己的用法）----
    box, ckr, gap = px(SQ_CHK_BOX, scale), px(SQ_R_CHK, scale), px(SQ_CHK_GAP, scale)

    def ticked(color: str) -> Image.Image:
        img = plate(box, box, ckr, color, on=p["card"])
        ImageDraw.Draw(img).line(
            [(box * .28, box * .52), (box * .43, box * .70), (box * .73, box * .30)],
            fill=p["on_accent"], width=max(2, px(2, scale)), joint="curve")
        return img

    imgs["check-off"] = pad_right(
        plate(box, box, ckr, p["field"], p["line"], on=p["card"]), gap)
    imgs["check-on"] = pad_right(ticked(p["accent"]), gap)
    imgs["check-off-dis"] = pad_right(
        plate(box, box, ckr, p["field_off"], p["line_off"], on=p["card"]), gap)
    imgs["check-on-dis"] = pad_right(ticked(shade(p["accent"], -0.45)), gap)
    # ⚠️ 這一顆**不切九宮格**（border=0）：方塊是固定尺寸的，拉伸只會把它拉歪
    elems["Sq.check"] = dict(
        states=[["", "check-off"], ["disabled selected", "check-on-dis"],
                ["disabled", "check-off-dis"], ["selected", "check-on"]],
        border=0, width=box + gap, height=box, padding=0, sticky="",
        on=p["card"])

    # ---- 進度條：圓頭的軌道與填充條 ----
    # ⚠️ 高度是**釘死**的（thickness ＝ 圖高），所以九宮格的左右兩塊不會被垂直
    # 拉伸、圓頭不會變形；會被拉開的只有中段那一欄純色。
    # ⚠️ **2026-08-27 晚改走 `pill()`。** 它本來就是膠囊（圓頭、高度釘死、只切
    # 左右），卻自己算了一份 `edge = int(pr) + 1`——與 `pill()` 的 `ceil(H/2)` 在
    # **偶數圖高時差 1**（@1.5／@1.75／@2 的圖高 10／12／14，舊式給 6／7／8，正確的
    # 是 5／6／7），等於同一條規則在這支檔案裡有兩種寫法，而檔頭第 4 點又寫著
    # 「按鈕、輸入框、進度條走 `pill()`」——現在才是真的。
    # ⚠️ 多切的那一欄不會壞掉（中段仍落在純色區、只是白白多切一欄），所以這是
    # 一致性修正不是修 bug；改完 `tests/..::test_pill_plates_are_sliced_horizontally_only`
    # 一起管它。
    pw, th, pr, pbr = pill(SQ_PB_TH, scale, mid)
    imgs["trough"] = plate(pw, th, pr, p["trough"], on=p["card"])
    imgs["pbar"] = plate(pw, th, pr, p["accent"], on=p["trough"])
    for name, key, on in (("Sq.trough", "trough", p["card"]),
                          ("Sq.pbar", "pbar", p["trough"])):
        elems[name] = pill_elem([["", key]], th, pbr, on, padding=0)

    # ---- 收合鈕的三角形（見 chevron）----
    # ⚠️ **不進 `elems`**：它們不是 ttk 元件，是 GUI 直接拿去當按鈕的 `image`
    # （`compound="left"`）。沒有皮膚時退回文字字元，見 GUI 的 `_set_chevron`。
    cv, cg = px(SQ_CHEV, scale), px(SQ_CHEV_GAP, scale)
    imgs["chev-right"] = pad_right(chevron(cv, p["ink"], False), cg)
    imgs["chev-down"] = pad_right(chevron(cv, p["ink"], True), cg)

    # ---- 主要動作鈕的兩張皮：開始是 Apple 藍、停止是深紅 ----
    rw, rh, rr, rbr = pill(SQ_H_RUN, scale, mid)
    for kind, hover in (("accent", p["accent_hi"]), ("stop", None)):
        imgs[f"{kind}-rest"] = plate(rw, rh, rr, p[kind], on=p["card"])
        imgs[f"{kind}-dis"] = plate(rw, rh, rr, p["run_off"], on=p["card"])
        imgs[f"{kind}-pressed"] = plate(rw, rh, rr, shade(p[kind], -0.12),
                                        on=p["card"])
        imgs[f"{kind}-hover"] = plate(rw, rh, rr, hover or shade(p[kind], 0.10),
                                      on=p["card"])
        elems[f"Sq.{kind}"] = pill_elem(
            [["", f"{kind}-rest"], ["disabled", f"{kind}-dis"],
             ["pressed", f"{kind}-pressed"], ["active", f"{kind}-hover"]],
            rh, rbr, p["card"], padding=hpad(SQ_PAD))

    return imgs, elems


def pack(imgs: dict[str, Image.Image]) -> tuple[Image.Image, dict]:
    """本專案的 sprite 佈局：走共用包那一支，並且**打開去重**。

    ⚠️ **去重在共用包裡預設是關的**，那是刻意的：開關一改，產出的 sheet 就變了，而
    姊妹專案有「出貨的資產 == 現在的產生器」那種逐位元組比對的測試——共用包改預設，
    那邊當場變紅而在這裡看不到（2026-08-28 `check_downstreams` 真的抓到過一次）。
    所以「要不要去重」由各下游自己決定，理由與量到的數字在 `skingen.pack`。

    ⚠️ **這一層薄薄的轉呼叫不是多餘的**：皮膚載入器存磁碟快取時走的是
    `make_skin.pack`（見 `winkit.skin` 的 `_save_cache`），所以出貨資產與快取的
    佈局在定義上就是同一種——直接讓那邊呼叫共用包的話，兩者會一個去重、一個不去重。
    """
    return _pack(imgs, dedup=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # ⚠️ **前景色不進資產**（2026-08-28 拿掉）：主要動作鈕停用／啟用時的字色改成由
    # 載入器直接查色票。烘進 `sprites.json` 的那一版有個無聲的漂法——色票改了卻忘了
    # 重跑這支，停用態的字色會停在舊值而畫面其他地方都更新了。順帶修掉一個已經漂開
    # 的名字：資產裡那個鍵叫 `run_off`，而色票的 `run_off` 是**另一個顏色**（停用態
    # 的底色），讀起來像同一個其實不是。
    meta = {"version": SCHEMA_VERSION, "scales": list(SCALES), "variants": {}}
    for theme in ("light", "dark"):
        for scale in SCALES:
            imgs, elems = build_variant(theme, scale)
            sheet, rects = pack(imgs)
            name = f"skin-{theme}@{scale:g}x.png"
            sheet.save(OUT / name, optimize=True)
            meta["variants"][f"{theme}@{scale:g}"] = {
                "file": name,
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
