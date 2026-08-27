"""圖形介面裡幾支**純函式**的行為。

為什麼只測這幾支：整個 repo 的自動化測試守的是「文件與程式碼一致」，轉換品質
的真值仍然是五份 deck 全跑加目視（見 `docs/dev/verification.md`）。但 2026-08-25
把進度條與結果列改成**解析 `cli.py` 的 stdout** 之後，多了一類壞法是
目視抓不到的：格式對不上時介面不會報錯，只會安靜地退回不定長度進度條、或把英文
原文貼在結果列上。字面值由 `test_docs.py::test_the_gui_reads_the_words_cli_actually_prints`
釘著，這裡補上「認出來之後講成什麼樣子」。

⚠️ import 這支 GUI 只會定義常數與函式（Tk 是 `App()` 才建的），不會開視窗。
⚠️ **檔尾那三支膠囊測試是例外**：要量 requested size 就得真的建一個 Tk root，不過
一律 `withdraw()`，畫面上不會有視窗閃出來；開不了 Tk 的機器會 skip 而不是紅。
"""
import pytest

import pdf2ppt_gui_2 as G
from pathlib import Path


def test_page_line_is_parsed_from_the_real_cli_format():
    """cli 每頁印的那一行，照抄 README 裡的範例。"""
    m = G._PAGE_RE.match(
        "page 1 (1/15): 11 lines, 11 shapes, 4 tiny/blurry left as image, "
        "1 watermark wiped, 5.5s")
    assert m and m.groups() == ("1", "15")
    # 頁碼與序號不同的情況（--pages 3-5 時 idx 與 n 對不上），要取的是序號那一組
    m = G._PAGE_RE.match("page 7 (3/4): 19 lines, 19 shapes, 1.6s")
    assert m and m.groups() == ("3", "4")
    # 不是每頁那一行的東西不可以誤判成進度
    for line in ("OCR: PP-OCRv5 rec=server, device=dml, dpi=200",
                 "Saved out.pptx (15 slides, 41.7s)",
                 "WARNING: page 3 dropped"):
        assert not G._PAGE_RE.match(line), line


def test_degraded_pages_are_grouped_and_translated():
    """同一種下場的頁碼併在一起講：30 頁降級 12 頁時逐頁列會長到放不下。"""
    out = G._fmt_degraded("page 3 dropped, page 7 image only, page 9 image only")
    assert out == "第 3 頁整頁沒能產生；第 7、9 頁只保留原圖、沒有可編輯文字"


def test_an_unrecognised_warning_is_passed_through_untouched():
    """⚠️ 認不得就原話照登。把訊息吃掉換成一句「有頁面降級」，等於讓使用者
    連「是哪幾頁」都問不到——那正是這一列存在的理由。"""
    assert G._fmt_degraded("something new we have never seen") == \
        "something new we have never seen"


def test_shortening_a_path_never_eats_the_file_name():
    """⚠️ 使用者要在那一行確認的就是「會存成哪個檔」。"""
    long = Path(r"C:\Users\someone\OneDrive - Contoso\Documents\2026\簡報"
                r"\第三季產品策略檢討會議\deck.pptx")
    short = G._shorten_path(long)
    assert short.endswith("deck.pptx") and len(short) <= 52
    # 放得下就原樣，不要為了縮而縮
    plain = Path(r"C:\decks\a.pptx")
    assert G._shorten_path(plain) == str(plain)


# --------------------------------------------------------------------------- #
#  皮膚資產（assets/skin/）
# --------------------------------------------------------------------------- #
# ⚠️ 這兩支守的是**截圖才看得出來的兩種壞法**，而截圖不在自動化測試裡：
#   · 新增一張底板時忘了指定「它坐在什麼顏色上」→ 圓角外側露出一塊實心方角。
#   · 改了 `tools/make_skin.py` 卻沒重跑 → 資產與程式碼各說各話，而 GUI 有資產
#     時走資產、沒有時當場畫，於是同一支程式在兩台機器上長得不一樣。
def _skin_meta():
    import json
    return json.loads(
        (G.SKIN_DIR / "sprites.json").read_text(encoding="utf-8"))


def test_every_skin_plate_declares_what_it_sits_on():
    """每個元件都要記下自己坐在什麼底色上（`make_skin.plate` 的 `on`）。

    ttk 是先用樣式的 `background` 填滿整塊、再把九宮格圖畫上去的，所以圓角外側
    那圈透明區露出來的是那個 background，不是父容器的顏色——底板一律畫成不透明、
    把外側色畫進圖裡。漏掉的症狀是「白卡上浮出一塊灰色方角」。"""
    missing = [f"{key} / {name}"
               for key, var in _skin_meta()["variants"].items()
               for name, elem in var["elements"].items()
               if not elem.get("on")]
    assert not missing, "這些元件沒說自己坐在什麼顏色上：\n  " + "\n  ".join(missing)


def test_the_shipped_skin_matches_what_the_generator_draws_today():
    """`assets/skin/` 必須是**現在這份** `tools/make_skin.py` 的產物。

    GUI 有資產就讀資產、沒有才 import 產生器當場畫（`SquircleSkin._drawn`），
    所以兩者一旦漂開，同一支程式在「完整複製」與「只有原始碼」的兩台機器上就會
    長得不一樣——而且都不會報錯。改了那支腳本要重跑再提交。"""
    from PIL import Image

    make_skin = G.import_make_skin()

    meta = _skin_meta()
    stale = []
    # ⚠️ **`scales` 與 `version` 也要比。** 前者是 `_from_assets` 拿來挑縮放檔的
    # 那份清單（與 `SCALES` 漂開的話，GUI 找的檔跟產生器出的檔就不是同一組）；後者是
    # 「舊資產配新程式」的唯一擋板，兩邊同號才擋得住。
    if meta["scales"] != list(make_skin.SCALES):
        stale.append(f"scales 清單變了：{meta['scales']} vs {list(make_skin.SCALES)}")
    if meta["version"] != make_skin.SCHEMA_VERSION:
        stale.append(f"version {meta['version']} != make_skin.SCHEMA_VERSION "
                     f"{make_skin.SCHEMA_VERSION}，請重跑產生器")
    if G.SKIN_SCHEMA != make_skin.SCHEMA_VERSION:
        stale.append(f"GUI 的 SKIN_SCHEMA {G.SKIN_SCHEMA} != "
                     f"make_skin.SCHEMA_VERSION {make_skin.SCHEMA_VERSION}")
    for theme in ("light", "dark"):
        for scale in make_skin.SCALES:
            var = meta["variants"][f"{theme}@{scale:g}"]
            imgs, elems = make_skin.build_variant(theme, scale)
            sheet, rects = make_skin.pack(imgs)
            if rects != {k: list(v) for k, v in var["sprites"].items()}:
                stale.append(f"{theme}@{scale:g}：sprite 的位置或名單變了")
                continue
            shipped = Image.open(G.SKIN_DIR / var["file"]).convert("RGBA")
            if shipped.tobytes() != sheet.tobytes():
                stale.append(f"{theme}@{scale:g}：{var['file']} 的像素變了")
            # ⚠️ **`states` 一起比**（2026-08-27 補）：這裡原本把 `states` 從兩邊
            # 都剔掉，於是 state→sprite 的對應——包含 `pressed` 與 `active` 同時成立
            # 時誰排前面——完全沒有人驗。手改 `sprites.json` 那一段，像素、rects、
            # border、width、height、padding、on 全都還相符，測試照樣綠，而有資產與
            # 只有原始碼的兩台機器會顯示不同的 hover/pressed/disabled，正是這支測試
            # 存在要擋的分歧。⚠️ 產生器出來的就已經全是 list（`states`／`border` 都寫
            # 成 list 字面值），與 JSON 讀回來的直接可比，不必先正規化。
                stale.append(f"{theme}@{scale:g}：元件定義變了")
    assert not stale, ("assets/skin/ 不是現在這份 make_skin.py 的產物，"
                       "請重跑 `uv run python tools/make_skin.py`：\n  "
                       + "\n  ".join(stale))


# ---------------------------------------------------------------------------
# 膠囊：底板圖高就是元件高度
# ---------------------------------------------------------------------------
# 底下兩支釘的是 2026-08-27 膠囊化引進的那條規則：垂直方向不切九宮格，所以**圖高
# 必須等於元件高度**（不等的兩種壞法見 `tools/make_skin.py` 的 `pill()`，那裡是
# 正本）。⚠️ 兩種都**不當掉、不報錯、不丟例外**，`reqheight` 也看不出來（它已經是
# max(內容需求, height)），在這之前唯一的守門員是人工重跑 `docs/dev/windows-環境與
# 入口.md` §5.11 那兩項。
#
# ⚠️ **測試開得了 Tk。** §5.11 一度寫「`tests/` 那一套是純文字的，開不了 Tk」而把這
# 兩項留給人工——那句話是錯的：`tk.Tk()` 在 pytest 裡建得起來，`withdraw()` 之後畫面
# 上不會有東西閃出來，五個縮放檔全跑約 2 秒。
#
# ⚠️ **量法照 §5.11**：`tk scaling` 是 dpi/72、`App.ui_scale` 是 dpi/96，兩個分母不
# 一樣，混用會量到另一個縮放檔的數字（第一次量就踩到過）。

def _pill_styles() -> dict:
    """{樣式: 底板元件名}——**從 `SKIN_SWAPS` 推導，不另外手抄一份**。

    那張表本來就記著「誰的背景換成哪張底板」，抄第二份的下場是加了新控制項只改一
    邊：測試看不到的那顆就是會被裁掉的那顆。⚠️ 只留**膠囊**（垂直 `border` 為 0
    的），卡片／日誌槽／核取方塊走四角九宮格、不受這條規則管。

    ⚠️ 兩個例外，都要手寫：`Small.TButton` 沿用 `TButton` 的 layout、不在表裡（畫面
    上「變更…／開啟簡報／開啟資料夾」三顆走的就是它）；進度條雖然也是膠囊，但它的
    高度是 GUI 直接拿 `Sq.trough` 的 `height` 去設 `thickness` 的，量法不同、也漂不掉。
    """
    var = _skin_meta()["variants"][f"{G.preferred_theme_mode()}@1"]
    out = {}
    for style, _src, table in G.SKIN_SWAPS:
        if style == "Horizontal.TProgressbar":      # 見 docstring
            continue
        for elem in table.values():
            e = var["elements"].get(elem)
            b = e and e["border"]
            if isinstance(b, list) and not b[1] and not b[3]:
                out[style] = elem
    out["Small.TButton"] = out["TButton"]           # 見 docstring
    return out


def _measure_pills(scale: float, pin_height: bool = True) -> dict:
    """回傳 {樣式: (量到的高度, 底板圖高)}。開不了 Tk 或裝不上皮膚就 skip。

    ⚠️ 底板圖高是從**載入的元件定義**讀的（`elem["height"]`），不是拿
    `make_skin.SQ_H_*` 重算一次——重算等於把產生器的算式在測試裡抄第二份。
    「元件定義的 `height` 真的等於圖片高度」由
    `test_pill_plates_are_sliced_horizontally_only` 另外釘著。

    ⚠️ `pin_height=False` 會把每個元件的 `height` 覆寫成 1，量到的於是是**純內容
    需求**（§5.11 驗收 6 的量法）。少了這一步就看不到安全邊界：`reqheight` 平常是
    max(內容, height)，內容就算只差 1px 就要爆，驗收 5 照樣是綠的。
    """
    import tkinter as tk
    from tkinter import ttk

    styles = _pill_styles()
    var = _skin_meta()["variants"][f"{G.preferred_theme_mode()}@{scale:g}"]
    try:
        root = tk.Tk()
    except tk.TclError as exc:                    # 沒有顯示裝置
        pytest.skip(f"這台機器開不了 Tk：{exc}")
    orig = G.SquircleSkin._from_assets
    try:
        root.withdraw()
        root.tk.call("tk", "scaling", scale * 96.0 / 72.0)
        if not pin_height:
            # ⚠️ 簽章要跟著 `_from_assets(self, root)` 走（2026-08-27 加了磁碟快取
            # 之後那一支收一個目錄參數）——少一個參數的話這裡會 TypeError，而
            # `install()` 把它接住當成「沒有資產」，測試就變成在量沒有皮膚的畫面
            def unpinned(self, root):
                spec = orig(self, root)
                if spec is None:
                    return None
                elems, fg = spec
                return {n: dict(e, height=1) for n, e in elems.items()}, fg
            G.SquircleSkin._from_assets = unpinned
        try:
            _fam, _pal, skin = G.apply_ui_style(root, scale)
        finally:
            G.SquircleSkin._from_assets = orig
        if skin is None:
            pytest.skip("這台機器裝不上 squircle 皮膚（多半是沒有 sv_ttk）")
        frame = ttk.Frame(root)
        out = {}
        for style, elem in styles.items():
            make = ttk.Entry if style == "TEntry" else ttk.Button
            kw = {} if make is ttk.Entry else {"text": "開始轉檔 Ag"}
            w = make(frame, style=style, **kw)
            root.update_idletasks()
            out[style] = (w.winfo_reqheight(), var["elements"][elem]["height"])
            w.destroy()
        return out
    finally:
        G.SquircleSkin._from_assets = orig
        root.destroy()


def test_every_pill_widget_fits_its_plate_exactly():
    """§5.11 驗收 5 ＋ 6，一支到底：高度要**剛好等於**底板圖高，而且純內容需求要
    **矮於**它（貼齊、餘裕 0 就算不過）。

    ⚠️ 兩件事要一起驗，少一件都看不到問題：只驗高度的話，`reqheight` 是
    max(內容, height)，內容就算只差 1px 就要爆也照樣相等；只驗餘裕的話，看不到
    版面把元件**拉高**過底板的那半邊（`sticky` 帶著 `n`／`s`）。

    ⚠️ 餘裕 0 不是「剛好」而是「已經沒有退路」：`ui_font_family()` 在沒裝
    Microsoft JhengHei (UI) 的機器上會退到 Segoe UI，字型度量一換就直接超出。
    2026-08-27 `Sq.field` 就是這樣——`SQ_PAD_FIELD` 留著一個理由已經失效的 +1px，
    五檔餘裕 0/1/1/2/2，而 Segoe UI 在 150% 下要 47、底板只有 45。
    """
    bad, tight = [], []
    for scale in G.import_make_skin().SCALES:
        for style, (got, plate) in _measure_pills(scale).items():
            if got != plate:
                how = "下緣被裁掉" if got > plate else "底板垂直重複貼"
                bad.append(f"{style} @{scale:g}x：元件 {got} vs 底板 {plate}（{how}）")
        for style, (need, plate) in _measure_pills(
                scale, pin_height=False).items():
            if need >= plate:
                tight.append(f"{style} @{scale:g}x：內容 {need} vs 底板 {plate}"
                             f"（餘裕 {plate - need}）")
    assert not bad, (
        "膠囊的圖高必須等於元件高度（tools/make_skin.py 的 `pill()`）：\n  "
        + "\n  ".join(bad))
    assert not tight, (
        "這些控制項的內容撐到底板高度了，換個字型或字級就會把下半個圓削平——"
        "調 `PILL_PADDING` 的垂直欄或 `SQ_H_*`：\n  " + "\n  ".join(tight))


def test_pill_plates_are_sliced_horizontally_only():
    """膠囊底板的幾何不變量，這一支不必開 Tk，所以永遠跑得到。

    三條：垂直 `border` 要是 0（切了就留下直邊、半徑再也大不過 H/2−1）、元件的
    `height` 要等於圖高（不等就是重複貼或裁切）、水平 `border` 不得小於
    `ceil(圖高/2)`（少一欄的話中段第一欄不是純色，水平重複貼會透出一條細紋），
    而且切得開（左＋右要小於圖寬，否則 ttk 在幾何計算裡原地打轉、事件迴圈當場
    卡死）。⚠️ 進度條的軌道與填充條也是這個形狀，一起驗。
    """
    bad = []
    for key, var in _skin_meta()["variants"].items():
        for name, elem in var["elements"].items():
            border = elem["border"]
            if not isinstance(border, list):
                continue        # 卡片／日誌槽／核取方塊走四邊九宮格，不是膠囊
            _x, _y, sw, sh = var["sprites"][elem["states"][0][1]]
            need = -(-sh // 2)          # ceil(sh / 2)
            if border[1] or border[3]:
                bad.append(f"{key} / {name}：垂直 border 不是 0（{border}）")
            if elem["height"] != sh:
                bad.append(f"{key} / {name}：height {elem['height']} != 圖高 {sh}")
            if border[0] != border[2]:
                bad.append(f"{key} / {name}：左右 border 不對稱（{border}）")
            if border[0] < need:
                bad.append(f"{key} / {name}：水平 border {border[0]} < "
                           f"ceil(圖高/2)＝{need}，中段第一欄不是純色")
            if border[0] + border[2] >= sw:
                bad.append(f"{key} / {name}：左＋右 {border[0] + border[2]} "
                           f">= 圖寬 {sw}，ttk 會卡死")
    assert not bad, "膠囊底板的幾何壞了：\n  " + "\n  ".join(bad)
