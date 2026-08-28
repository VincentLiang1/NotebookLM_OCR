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
from winkit import skin as wskin, winui
from winkit.palette import PALETTES
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


# --------------------------------------------------------------------------- #
#  同一個登入 session 只開一個
# --------------------------------------------------------------------------- #
# ⚠️ **這四支一律樁 `claim_single_instance` 與 `raise_existing_window` 兩支原始零件,
# 不樁 `single_instance_or_raise`**：要驗的正是那三格真值表有沒有真的接到 `main()`
# 上。樁掉政策本身的話，「鎖被拿走、視窗卻找不到」那一格在這裡就永遠走不到——而它
# 是唯一沒有目視徵狀的一格（開發機上第一個實例永遠好好地開著）。
# ⚠️ 替身一律 `lambda *a, **k:`：共用包用關鍵字傳 `class_name`，只吃位置參數的替身
# 會當場 TypeError——而那個紅是紅在測試管線上、不是紅在規則上。


def _stub_single_instance(monkeypatch, did, *, claimed, found, project_ok=True):
    """把單一實例那兩支原始零件換掉，其餘讓 `main()` 照真的跑。

    ⚠️ `project_ok` 開成參數、而不是讓呼叫端事後再 `setattr` 蓋一次：蓋回去的寫法
    要對照兩個地方才知道最後生效的是哪個值。"""
    monkeypatch.setattr(winui, "claim_single_instance",
                        lambda *a, **k: did.append("claim") or claimed)
    monkeypatch.setattr(winui, "raise_existing_window",
                        lambda *a, **k: did.append("raise") or found)
    for name in ("enable_dpi_awareness", "set_app_user_model_id"):
        monkeypatch.setattr(winui, name, lambda *a, n=name, **k: did.append(n))
    monkeypatch.setattr(G, "is_project_dir", lambda *a: project_ok)
    monkeypatch.setattr(G, "App", lambda *a: did.append("App") or _FakeApp())


def test_a_second_instance_shows_the_existing_window_instead_of_opening_one(
        monkeypatch):
    """程式已經開著時再點圖示：**不開第二個**，把既有那個叫到前景。

    使用者 2026-08-28：「啟動多個程式沒有用」。兩份轉檔會搶同一顆 GPU、也各自載一份
    OCR 模型，而兩邊都以為自己在正常轉檔——那是一種查不出來的慢。
    ⚠️ **不可以只是安靜退出**：使用者剛按下桌面圖示，什麼都沒發生的話他會以為程式
    壞了、再點兩三次。
    ⚠️ **不可以走到 `App()`**：那一步會開紀錄檔，`logs\\` 底下就多長一個只有檔頭的
    檔，而那個資料夾正是出事時要去讀的地方。
    ⚠️ **離開碼必須是 0**：非 0 的話「啟動.vbs」會跳一個訊息框，而且會觸發它那道
    「非正常結束又不到 5 秒就用 uv 再跑一次」的退路——那會真的開出第二個視窗，
    正好是這條規則要擋的事。"""
    did = []
    _stub_single_instance(monkeypatch, did, claimed=False, found=True)

    assert G.main() == 0, "第二個實例回了非 0：啟動器會跳框、還會用 uv 再跑一次"
    assert "raise" in did, "第二個實例安靜退出了，既有的視窗沒有被叫出來"
    assert "App" not in did, f"第二個實例走到了 App()，logs 會多一個空檔：{did}"


def test_a_second_instance_that_cannot_find_the_window_opens_anyway(monkeypatch):
    """⚠️ **鎖被拿走、卻找不到那個視窗 → 照常開**（`docs/spec/09-執行環境與效能.md`
    §9.8「失效方向要往放行倒」）。

    那個狀態是真的到得了的：第一個實例還在 `App.__init__`（視窗全程 `withdraw()`、
    標題比對不到）、正在 `destroy()` 與行程結束之間，或者是個已經沒有視窗的殘留行程
    （轉檔跑在 daemon thread 的 onnxruntime 上，直譯器關不掉時就是這一種）。
    ⚠️ 這一格**沒有任何目視徵狀**：開發機上第一個實例永遠好好地開著，所以永遠走不到
    ——安靜地 `return 0` 的話，使用者看到的是「點了圖示什麼都沒發生」，而且 rc=0 讓
    「啟動.vbs」也依約定閉嘴。"""
    did = []
    _stub_single_instance(monkeypatch, did, claimed=False, found=False)

    assert G.main() == 0
    assert "App" in did, \
        f"鎖被拿走、視窗又找不到，卻什麼都沒開也什麼都沒說：{did}"


def test_the_first_instance_opens_its_window_without_stealing_the_foreground(
        monkeypatch):
    """**第一個**實例不可以把視窗叫到前景，而且那兩支 Windows 設定要先做完。

    ⚠️ 前景那一半是「工作列的提醒不可以搶前景」那條硬規則的邊界（正本在
    `docs/dev/windows-環境與入口.md` §5.8）：叫到前景只在「使用者剛點了圖示、而程式
    已經開著」那一種情況成立。判斷寫反的話，每一次正常啟動都會多做一次前景切換——而
    開發機上看起來完全正常，因為那時本來就要開視窗。
    ⚠️ 另一半釘的是 `enable_dpi_awareness()`／`set_app_user_model_id()` **仍然在
    `App()` 之前被呼叫**：兩支都是文件明載的靜默失效（前者缺了整個視窗被點陣放大、
    每個字都是鋸齒，後者缺了工作列顯示的是 wscript 的圖示），而單一實例那道守門就
    插在它們旁邊——最容易在下一次編輯時被順手吃掉的位置。"""
    did = []
    _stub_single_instance(monkeypatch, did, claimed=True, found=True)

    assert G.main() == 0
    assert "raise" not in did, "第一個實例也去叫了一次前景"
    for name in ("enable_dpi_awareness", "set_app_user_model_id"):
        assert name in did, f"{name}() 沒被呼叫：{did}"
        assert did.index(name) < did.index("App"), \
            f"{name}() 排到 App()（＝建 Tk）後面去了：{did}"


def test_a_copy_that_cannot_run_never_takes_the_lock(monkeypatch):
    """⚠️ **跑不起來的副本不可以佔住那把鎖**（2026-08-28）。

    守門排在 `is_project_dir()` **之後**的理由：一份缺了 `pdf2ppt/` 的副本（那種副本
    過得了「啟動.vbs」的守門，那支只檢查 `pyproject.toml`、`pdf2ppt_gui_2.py` 與共用
    資料夾）若擋在最前面就會先搶到鎖，接著跳 `fail_no_project()` 的框——而它的視窗是
    class `#32770` 的訊息框與標題 `tk` 的隱藏 root，**兩個都比對不到** `APP_TITLE`。
    框被壓在別的視窗後面沒關掉的話，另一份好的副本從此搶不到鎖、也找不到視窗。
    ⚠️ 而且那份好的副本回的是 0 不是 `SELF_REPORTED_RC`，所以「啟動.vbs」不是「已說
    明過所以閉嘴」，是真的認為一切正常。"""
    did = []
    # ⚠️ 兩個都給 False：守門若被搬回 `is_project_dir()` 之前，`did` 就會多出
    # `claim`（而且是搶得到的那一格），全等斷言當場紅。
    _stub_single_instance(monkeypatch, did, claimed=False, found=False,
                          project_ok=False)
    monkeypatch.setattr(G, "fail_no_project", lambda: did.append("box") or True)

    assert G.main() == G.SELF_REPORTED_RC
    assert did == ["enable_dpi_awareness", "set_app_user_model_id", "box"], \
        f"跑不起來的副本做了它不該做的事（尤其是搶鎖）：{did}"


class _FakeApp:
    """`main()` 只對 App 做一件事：`mainloop()`。不要真的建 Tk。"""

    def mainloop(self) -> None:
        pass


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


class _FakeRoot:
    """假的 Tk root：`fail_no_project()` 只用到這三支，而且都不開視窗。"""

    def __init__(self, *, destroy_raises=False):
        self.destroy_raises = destroy_raises

    def withdraw(self):
        pass

    def iconbitmap(self, **kwargs):
        pass

    def destroy(self):
        if self.destroy_raises:
            raise RuntimeError("can't invoke \"destroy\" command")


@pytest.mark.parametrize("destroy_raises", [False, True])
def test_a_box_that_appeared_is_reported_as_appeared_even_if_teardown_blows_up(
        monkeypatch, destroy_raises):
    """框跳出來了就要回 True——**即使收尾那幾行炸掉**。

    這個回傳值是與「啟動.vbs」講好的握手：True → 呼叫端回 `SELF_REPORTED_RC`，
    啟動器安靜收工，使用者只看到我們這一個框；False → 回 1，啟動器把 stderr 那
    一份也跳出來。

    ⚠️ **回報「框」，不是回報「這段跑完了」**（2026-08-28）：`root.destroy()` 排在
    `return True` 之前、又同在一個 `try` 裡的話，`destroy()` 一拋例外（直譯器已經
    在拆、顯示工作階段被收掉、`iconbitmap` 留下的舊 handle）就會回報成「沒跳」——
    而框其實已經給使用者看過了，於是啟動器再跳一次:同一件事兩個框，正是那套握手
    要消滅的東西。
    """
    seen = []
    monkeypatch.setattr(G.tk, "Tk",
                        lambda: _FakeRoot(destroy_raises=destroy_raises))
    monkeypatch.setattr(G.messagebox, "showerror",
                        lambda title, msg: seen.append(title))
    assert G.fail_no_project() is True
    assert seen, "訊息框根本沒跳,卻回報跳了"


@pytest.mark.parametrize("boom", ["tk", "showerror"])
def test_a_box_that_never_appeared_is_reported_as_missing(monkeypatch, boom):
    """框跳不出來就要回 False,讓啟動端接手顯示 stderr 那一份。

    ⚠️ **不可以無條件回報「已說明過」**:Tk 起不來的機器上那等於什麼都沒說,而啟
    動器收到那個結束碼會把攔到的訊息連同暫存檔一起刪掉——使用者手上什麼都不剩。
    """
    def explode(*args, **kwargs):
        raise RuntimeError("no display")

    monkeypatch.setattr(G.tk, "Tk",
                        explode if boom == "tk" else lambda: _FakeRoot())
    monkeypatch.setattr(G.messagebox, "showerror", explode)
    assert G.fail_no_project() is False


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
        (wskin.skin_dir() / "sprites.json").read_text(encoding="utf-8"))


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

    make_skin = wskin.import_make_skin()

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
            shipped = Image.open(wskin.skin_dir() / var["file"]).convert("RGBA")
            if shipped.tobytes() != sheet.tobytes():
                stale.append(f"{theme}@{scale:g}：{var['file']} 的像素變了")
            # ⚠️ **`states` 一起比**（2026-08-27 補）：這裡原本把 `states` 從兩邊
            # 都剔掉，於是 state→sprite 的對應——包含 `pressed` 與 `active` 同時成立
            # 時誰排前面——完全沒有人驗。手改 `sprites.json` 那一段，像素、rects、
            # border、width、height、padding、on 全都還相符，測試照樣綠，而有資產與
            # 只有原始碼的兩台機器會顯示不同的 hover/pressed/disabled，正是這支測試
            # 存在要擋的分歧。⚠️ 產生器出來的就已經全是 list（`states`／`border` 都寫
            # 成 list 字面值），與 JSON 讀回來的直接可比，不必先正規化。
            # ⚠️ **這個 `if` 2026-08-28 補回來**：它在 a231a2f「拿掉沒作用的正規化」
            # 時被連同那層 `_as_lists()` 一起刪掉了，只剩下面那句 `stale.append`
            # 縮排在像素那條分支裡——於是 `elems` 綁了沒人用、`sprites.json` 的
            # border／width／height／padding／on／states 漂掉時測試照樣綠，而像素
            # 真的不同時還會多印一句從來沒驗過的「元件定義變了」。
            if elems != var["elements"]:
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
    var = _skin_meta()["variants"][f"{winui.preferred_theme_mode(PALETTES)}@1"]
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
    var = _skin_meta()["variants"][f"{winui.preferred_theme_mode(PALETTES)}@{scale:g}"]
    try:
        root = tk.Tk()
    except tk.TclError as exc:                    # 沒有顯示裝置
        pytest.skip(f"這台機器開不了 Tk：{exc}")
    orig = wskin.SquircleSkin._from_assets
    try:
        root.withdraw()
        root.tk.call("tk", "scaling", scale * 96.0 / 72.0)
        if not pin_height:
            # ⚠️ 簽章要跟著共用包那一支 `_from_assets(self, root, tag, *, exact)`
            # 走——少一個參數的話這裡會 TypeError，而 `install()` 把它接住當成「沒有
            # 資產」，測試就變成在量沒有皮膚的畫面。⚠️ 2026-08-28 起它回的是 `elems`
            # 本身（前景色改成直接查色票，不再從資產繞一圈）。
            def unpinned(self, root, tag, *, exact=False):
                elems = orig(self, root, tag, exact=exact)
                if elems is None:
                    return None
                return {n: dict(e, height=1) for n, e in elems.items()}
            wskin.SquircleSkin._from_assets = unpinned
        try:
            _fam, _pal, skin = G.apply_ui_style(root, scale)
        finally:
            wskin.SquircleSkin._from_assets = orig
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
        wskin.SquircleSkin._from_assets = orig
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
    for scale in wskin.import_make_skin().SCALES:
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
