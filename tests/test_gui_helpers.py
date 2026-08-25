"""圖形介面裡幾支**純函式**的行為。

為什麼只測這幾支：整個 repo 的自動化測試守的是「文件與程式碼一致」，轉換品質
的真值仍然是五份 deck 全跑加目視（見 `docs/dev/verification.md`）。但 2026-08-25
把進度條、剩餘時間與結果列改成**解析 `cli.py` 的 stdout** 之後，多了一類壞法是
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


def test_eta_never_pretends_to_be_precise():
    """每頁耗時本來就差很多（一行進旋轉救援要跑七次 OCR），報到秒是假裝有精度。"""
    assert G._fmt_eta(3) == "快好了"
    assert G._fmt_eta(42) == "約剩 40 秒"
    assert G._fmt_eta(170) == "約剩 3 分"
    # 半分鐘的平手點走 Python 的 round（銀行家捨入）：150 秒是 2.5 分 → 2。
    # 釘在這裡不是因為 2 比 3 好，是因為「哪一邊」不重要、**別再改來改去**重要
    assert G._fmt_eta(150) == "約剩 2 分"


def test_shortening_a_path_never_eats_the_file_name():
    """⚠️ 使用者要在那一行確認的就是「會存成哪個檔」。"""
    long = Path(r"C:\Users\someone\OneDrive - Contoso\Documents\2026\簡報"
                r"\第三季產品策略檢討會議\deck.pptx")
    short = G._shorten_path(long)
    assert short.endswith("deck.pptx") and len(short) <= 52
    # 放得下就原樣，不要為了縮而縮
    plain = Path(r"C:\decks\a.pptx")
    assert G._shorten_path(plain) == str(plain)
