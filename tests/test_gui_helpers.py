"""圖形介面裡幾支**純函式**的行為。

為什麼只測這幾支：整個 repo 的自動化測試守的是「文件與程式碼一致」，轉換品質
的真值仍然是五份 deck 全跑加目視（見 `docs/dev/verification.md`）。但 2026-08-25
把進度條與結果列改成**解析 `cli.py` 的 stdout** 之後，多了一類壞法是
目視抓不到的：格式對不上時介面不會報錯，只會安靜地退回不定長度進度條、或把英文
原文貼在結果列上。字面值由 `test_docs.py::test_the_gui_reads_the_words_cli_actually_prints`
釘著，這裡補上「認出來之後講成什麼樣子」。

⚠️ import 這支 GUI 只會定義常數與函式（Tk 是 `App()` 才建的），不會開視窗。
"""
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
    import sys
    sys.path.insert(0, str(G.PROJECT_DIR / "tools"))
    try:
        import make_skin
    finally:
        sys.path.pop(0)
    from PIL import Image

    meta = _skin_meta()
    stale = []
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
            if {n: {k: v for k, v in e.items() if k != "states"}
                    for n, e in elems.items()} != \
               {n: {k: v for k, v in e.items() if k != "states"}
                    for n, e in var["elements"].items()}:
                stale.append(f"{theme}@{scale:g}：元件定義變了")
    assert not stale, ("assets/skin/ 不是現在這份 make_skin.py 的產物，"
                       "請重跑 `uv run python tools/make_skin.py`：\n  "
                       + "\n  ".join(stale))
