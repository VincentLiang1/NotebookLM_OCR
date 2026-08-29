"""圖形介面裡幾支**純函式**的行為。

為什麼只測這幾支：整個 repo 的自動化測試守的是「文件與程式碼一致」，轉換品質
的真值仍然是五份 deck 全跑加目視（見 `docs/dev/verification.md`）。但 2026-08-25
把進度條與結果列改成**解析 `cli.py` 的 stdout** 之後，多了一類壞法是
目視抓不到的：格式對不上時介面不會報錯，只會安靜地退回不定長度進度條、或把英文
原文貼在結果列上。字面值由 `test_docs.py::test_the_gui_reads_the_words_cli_actually_prints`
釘著，這裡補上「認出來之後講成什麼樣子」。

⚠️ import 這支 GUI 只會定義常數與函式（Tk 是 `App()` 才建的），不會開視窗。
⚠️ **有四支要真的建一個 Tk root**（三支膠囊測試量 requested size，一支量狀態字有多
寬），不過一律 `withdraw()`，畫面上不會有視窗閃出來；開不了 Tk 的機器會 skip 而不是
紅。⚠️ **量狀態字那一支必須排在膠囊那三支之前**，理由寫在它自己頭上——那三支反覆建
毀 root 之後再建一個會間歇性失敗，而失敗的形式是 skip（看起來還是綠的）。
"""
import re

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



# ⚠️ **底下這兩支要排在「會真的建 Tk root」那批之前**（2026-08-29）：`_measure_pills`
# 那批每個縮放檔建一次 root 又 destroy 一次，之後再 `tk.Tk()` 會**間歇性**丟
# `Can't find a usable init.tcl`／`invalid command name "tcl_findLibrary"`（單獨跑這一
# 支 5/5 綠，跟在它們後面跑 8 次跳過 6 次；先 `gc.collect()` 試過，沒有用）。
# ⚠️ 症狀是 **skip 不是 fail**——那一輪看起來還是綠的，其實根本沒有在守。位置就是修
# 法，往下搬會重演。
# ⚠️ **但這不是根治**：搬過來之後連跑 42 輪沒有再現，中間卻在「突變腳本剛跑完」那一輪
# 出現過一次（10 輪 1 次），之後 30 輪又完全乾淨、抓不到訊息。所以 skip 照舊要當成訊號
# 去追（`docs/dev/verification.md` 第 1 節：本機應該是 0），**不要因為這裡搬過位置就假設
# 它不會再來**。


def _status_words(src: str) -> set:
    """程式裡會被寫進狀態字那一格的每一句話。

    ⚠️ **要走 AST，不能用正則抓 `_set_status("…")`**：第一版就是那樣寫的，而
    `_refresh_input_state` 是先把話存進一個變數再傳出去（`bad = "這不是 PDF 檔"`），
    正則看不見——故障注入時把那句改成更長的字串，測試照樣全綠。所以這裡收三種寫法：
    直接給字面值、給同一個函式裡指派過的變數、以及三元式的兩邊。
    """
    import ast

    def strings(node):
        """節點底下的字串字面值。⚠️ **f-string 整個跳過**：`f"{n}/{total} 頁"` 那種
        句子的寬度取決於當下的數字，驗不了——名單裡改放它**最寬的長相**
        （`888/888 頁`、`失敗（代碼 78）`）當樣本。不跳過的話收到的是
        `' 頁'`、`'/'`、`'失敗（代碼 '` 這些碎片，然後整支測試變成雜訊。"""
        if isinstance(node, ast.JoinedStr):
            return set()
        out = set()
        for child in ast.iter_child_nodes(node):
            out |= strings(child)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
            out.add(node.value)
        return out

    words = set()
    for fn in [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)]:
        assigned = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                got = strings(node.value)
                for t in node.targets:
                    if isinstance(t, ast.Name) and got:
                        assigned.setdefault(t.id, set()).update(got)
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("_set_status", "_flash_status")
                    and node.args):
                first = node.args[0]
                words |= (assigned.get(first.id, set())
                          if isinstance(first, ast.Name) else strings(first))
    return words


def _fresh_tk():
    """建一個 withdraw 過的 Tk root；建不起來就 skip（但先重試三次）。

    ⚠️ **要重試**：`tk.Tk()` 在這台機器上會**間歇性**丟 `Can't find a usable
    init.tcl`／`invalid command name "tcl_findLibrary"`（跑完 `check_downstreams`
    那種大量建毀 Tk 的工作之後特別容易中）。⚠️ skip 的形式是**綠的**——靠運氣的
    那一輪根本沒在守，而摘要行不會有任何警告（`docs/dev/verification.md` 第 1 節：
    本機應該是 0 skipped）。真的沒有 Tk 的機器照樣 skip，這裡只是不讓它靠運氣。
    """
    import tkinter as tk

    last = None
    for _ in range(3):
        try:
            root = tk.Tk()
            root.withdraw()
            return root
        except tk.TclError as e:
            last = e
    # ⚠️ 原因要寫進 skip 訊息：沒有原因的 skip 連追都追不了
    pytest.skip(f"這台機器開不了 Tk（試了 3 次）：{last}")


def test_this_apps_own_styles_actually_take_effect():
    """這支程式自己的樣式要**真的生效**——問的是 Tk，不是原始碼。

    ⚠️ 2026-08-29 的災情：`apply_ui_style()` 只有一行 `return wskin.apply(...)`，而它
    底下還留著 2026-08-28 收攏到共用包**之前**的整段舊實作（137 行死碼，沒刪）。當天
    新加的 `FieldHint.TLabel`（輸入框裡那句提示的顏色）就加進了那段裡，於是**從未執行**。

    ⚠️ **症狀完全看不出來**：ttk 照後綴繼承，那句提示安靜地沿用 `TLabel` 的預設——
    字色 #1c1c1c（近正文黑）、底色 #fafafa（與輸入框底 #f0f0f3 差 10 階，目視分不出）。
    不報錯、`reqheight` 不變、截圖也看不出來。⚠️ **掃原始碼的測試一樣擋不住**：那一行
    確確實實寫在檔案裡。只有真的建一次 Tk、問它「最後生效的是什麼」才抓得到。

    ⚠️ 所以這一支要問的是**值**，不是有沒有寫。新增樣式時把它加進下面那張表。
    """
    root = _fresh_tk()
    try:
        from tkinter import ttk

        _fam, pal, _skin = G.apply_ui_style(root, root.winfo_fpixels("1i") / 96.0)
        st = ttk.Style(root)
        want = {
            # 這支程式**多出來的**那幾種（共用包不知道它們的存在）
            ("FieldHint.TLabel", "foreground"): pal["muted"],
            ("FieldHint.TLabel", "background"): pal["field"],
            # 共用包設的那批,一起釘著:哪天 `configure_styles` 被搬到錯的地方,
            # 或共用包的回呼斷掉,這裡會一起紅
            ("CardHint.Card.TLabel", "foreground"): pal["muted"],
            ("Card.TLabel", "background"): pal["card"],
            ("Page.TFrame", "background"): pal["page"],
            ("CardBody.TFrame", "background"): pal["card"],
        }
        bad = [f"{style}.{opt} = {st.lookup(style, opt)}（期望 {expect}）"
               for (style, opt), expect in want.items()
               if str(st.lookup(style, opt)).lower() != str(expect).lower()]
    finally:
        root.destroy()
    assert not bad, (
        "這些樣式沒有真的生效——最可能的原因是設定寫在 `apply_ui_style()` 的 "
        "`return` 後面（死碼），或沒有寫進 `configure_styles()`：\n  "
        + "\n  ".join(bad))

def test_status_words_that_would_stretch_their_column_are_caught():
    """每一句狀態字都要進 `STATUS_SAMPLES`，而且不可以比最寬的那句還寬。

    右欄的 `minsize` 是量這份名單來的。漏了一句的症狀是：那一句一出現就把欄位撐開、
    進度條當場縮一截（而它只在特定狀態下出現，平常看不到）。
    ⚠️ 2026-08-29 把輸入的毛病改講在這一格時，第一版寫的「拖進來的不是 PDF：<檔名>」
    是 189px，比最寬的「載入 OCR 引擎…」還寬 40px——改成「只收 PDF 檔」才收得住。
    """
    said = _status_words(Path(G.__file__).read_text(encoding="utf-8"))
    missing = sorted(w for w in said if w not in G.STATUS_SAMPLES)
    assert not missing, f"這些狀態字沒進 STATUS_SAMPLES：{missing}"
    # ⚠️ Tk 一律在函式裡 import（與檔尾那幾支膠囊測試同一個作法）：這個檔其餘的
    # 測試都不必開 Tk，import 提到頂上會讓「開不了 Tk 的機器」整支檔一起紅
    import tkinter as tk
    from tkinter import font as tkfont
    root = _fresh_tk()
    try:
        root.withdraw()
        # 字型家族要拿真正在用的那一個（狀態字是 10pt 粗體，見 apply_ui_style）
        fam = G.apply_ui_style(root, root.winfo_fpixels("1i") / 96.0)[0]
        f = tkfont.Font(root, font=(fam, 10, "bold"))
        widths = {t: f.measure(t) for t in G.STATUS_SAMPLES}
    finally:
        root.destroy()
    cap = max(widths.values())
    # 名單自己就是上限的來源,所以這裡驗的是「新加的那幾句沒有變成新的上限」
    late = ("找不到檔案", "這不是 PDF 檔", "只收 PDF 檔", "轉檔中不能換檔")
    over = [f"{t}={widths[t]}" for t in late if widths[t] > cap]
    assert not over, f"這幾句會把狀態欄撐開（上限 {cap}）：{over}"


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


# 卡片一最左邊那一條直欄（瀏覽…／變更…／開始轉檔，2026-08-29）。⚠️ **掃的是原始碼
# 不是行為**：欄位換回去之後每個函式都還是對的、測試照樣全綠，版面只有真的開一次
# 視窗才看得到（驗收數字見 docs/dev/windows-環境與入口.md §5.15）。
def _build_ui_src() -> str:
    src = Path(G.__file__).read_text(encoding="utf-8")
    return src[src.index("    def _build_ui"):src.index("    def _set_chevron")]


def test_the_pick_buttons_sit_in_the_left_rail():
    """挑選那兩顆鈕在**最左**（`column=0`），輸入框與說明文字在右邊那一欄。

    使用者 2026-08-29 指定的順序（「那是最常用的功能，以視覺來說使用者通常都是從
    螢幕的左上看到右邊」），推翻 2026-08-27 併卡片那一版的左右。

    ⚠️ **這一條連 `weight` 一起釘**：兩件事分開就會出兩種不同的畫面——欄位對調而
    `weight` 留在 column 0 的話，兩顆鈕會被拉成半個卡片寬、輸入框縮到剛好裝得下
    路徑，按鈕反而成了這張卡片的主體。
    """
    build = _build_ui_src()
    for name, row in (("browse", 1), ("change", 3)):
        assert f"{name}.grid(row={row}, column=0, sticky=\"ew\"" in build, \
            f"{name} 不在最左那一欄——使用者指定挑選鈕在左"
    assert "self.in_entry.grid(row=1, column=1," in build, \
        "輸入框要在挑選鈕的右邊"
    # ⚠️ 2026-08-29 起框底下沒有那一行說明了（提示字收進框裡），改釘輸出框那一格
    assert "self.out_entry.grid(row=3, column=1," in build, \
        "輸出框要在挑選鈕的右邊，與輸入框等長"
    # ⚠️ 要擋掉字首才比得對：`adv_card.columnconfigure(0, weight=1)` 是收合卡片的，
    # 那一張整條寬、本來就該有 weight——用 `in` 比對會把它讀成卡片一的設定。
    assert re.search(r"(?<![\w.])card\.columnconfigure\(1, weight=1\)", build), \
        "吃寬的要是內容那一欄"
    assert not re.search(r"(?<![\w.])card\.columnconfigure\(0, weight=1\)", build), \
        "挑選鈕那一欄不可以有 weight：寬度由 _pin_rail() 釘死"


def test_the_left_rail_is_as_wide_as_the_main_button():
    """左欄的寬度是**量**主鈕來的，而且兩個容器都要釘。

    三顆鈕（瀏覽…／變更…／開始轉檔）分屬兩個 grid——前兩顆在卡片自己的第 0 欄、
    主鈕在動作區那張 `CardBody` 的第 0 欄。只釘一邊的話另一邊照自然寬走，右緣差的
    就是那道 `SP_MD`；寬度寫死一個數字則是下次換字、換字級或換 DPI 就漂。
    ⚠️ 主鈕還要 `sticky="ew"`：「■ 停止轉檔」比「▶ 開始轉檔」窄，照自然寬擺的話
    按下去的那一刻整條欄的右緣會抽動一下。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    pin = src[src.index("    def _pin_rail"):src.index("    def px(")]
    assert "self.run_btn.winfo_reqwidth() + self.px(SP_MD)" in pin, \
        "左欄寬度要用量的（主鈕的 reqwidth ＋ 它與內容欄那道縫）"
    assert "self.main_card.columnconfigure(0, minsize=rail)" in pin, \
        "卡片那兩顆挑選鈕的欄沒釘住"
    assert "self._actions.columnconfigure(0, minsize=rail)" in pin, \
        "動作區那顆主鈕的欄沒釘住"
    build = _build_ui_src()
    assert "self._pin_rail()" in build, "_build_ui 建完卡片之後要釘一次欄寬"
    assert "self.run_btn.grid(row=0, column=0, sticky=\"ew\"" in build, \
        "主鈕要撐滿左欄，否則開始／停止切換時右緣會抽動"


def test_the_status_line_no_longer_aims_at_a_button_that_is_gone():
    """狀態字改成貼卡片右緣：右上那一欄已經沒有鈕可以對齊了（2026-08-29）。

    舊版逐字串算右內距，好與「瀏覽…／變更…」同一條中線（沿革見 docs/dev §5.10
    十二）。鈕搬到左邊之後那條規則的對象不存在，留著的話狀態字會照著一顆不存在的
    鈕往左縮一截。⚠️ 這種壞法**沒有徵狀**：畫面照樣畫得出來，只是誰都沒對齊。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    assert "_status_pad" not in src, \
        "殘骸：對齊右上那顆鈕的內距算式，鈕已經搬到左邊了"
    assert "_rail_btns" not in src, \
        "殘骸：那兩顆鈕只被 _status_pad 用來量欄寬"
    set_status = src[src.index("    def _set_status"):src.index("    def _start")]
    assert "grid_configure" not in set_status, \
        "_set_status 只換文字與顏色；內距那半已經拿掉了"
    # 欄寬仍要釘住，否則進度條右端會跟著狀態字長短抽動（那條規則沒有被推翻）
    assert "minsize=self._status_width()" in _build_ui_src(), \
        "狀態字那一欄的 minsize 不見了：進度條右端會在不同狀態字之間抽動"


# 提示字收進輸入框、輸出也做成一個框（2026-08-29，見 docs/dev §5.16）。
def test_the_hint_line_is_gone_and_its_words_have_somewhere_to_go():
    """框底下那一行說明整個拿掉了，而它原本講的四件事都要有新的落點。

    ⚠️ 這一條守的是**「擋掉時必須說原因」**那條硬規則：拿掉一個顯示區塊很容易，
    連同它承載的訊息一起悄悄拿掉也一樣容易——而症狀是「拖了檔進來卻什麼都沒發生」。
    四句話的去處：還沒選 → 框裡的提示字；找不到／不是 PDF → 狀態字；
    被擋下來的操作（轉檔中換檔、拖進來不是 PDF）→ `_flash_status`。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    assert "_set_hint" not in src and "self.hint" not in src, \
        "殘骸：那一行說明已經收進輸入框了"
    assert "def _flash_status" in src, \
        "被擋下來的操作要有地方說原因（拖放與 Ctrl+V 各自擋掉並說原因）"
    dropped = src[src.index("    def _on_files_dropped"):src.index("    def _on_paste_path")]
    assert dropped.count("_flash_status") == 2, \
        "拖放被擋的兩種情況（轉檔中換檔、不是 PDF）都要說原因"


def test_the_placeholder_is_a_label_on_top_not_a_value_in_the_field():
    """框裡那句提示是**疊上去的標籤**，不是塞進輸入欄的值。

    ⚠️ 塞值的做法（Tk 沒有原生 placeholder，網路上多半這樣教）在這支程式裡是會
    出事的：`_build_argv()` 讀的就是 `in_path`，那句提示會被當成使用者選的路徑送進
    命令列，而且**要按下轉檔才發作**。
    ⚠️ 順帶釘住拖放目標：那塊標籤蓋在輸入框上，沒把它一起註冊的話，「拖到那句話
    上面」沒反應而拖到旁邊可以——而那句話寫的正是「或把 PDF 直接拖進這個視窗」。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    build = src[src.index("    def _build_ui"):src.index("    def _set_chevron")]
    assert "self.placeholder = ttk.Label(self.in_entry" in build, \
        "提示字要是一塊疊在輸入框上的標籤"
    assert "self.placeholder.place(" in build, "疊上去要用 place()"
    assert "self._dnd_targets = (root, card, self.in_entry, self.placeholder)" in src, \
        "提示字那塊標籤也要是拖放目標，否則拖到它上面沒反應"


def test_the_output_box_is_read_only_and_locks_with_the_rest():
    """輸出那一格是**唯讀**的框，而且轉檔中跟著鎖。

    ⚠️ 做成一個跟輸入框一樣長的框是使用者 2026-08-29 要的對稱，但「主畫面只問一
    件事」那條（docs/spec/09 §9.6.1）沒有被推翻——唯讀就是它現在的守法：看起來對稱、
    但點下去不會有游標，要改仍然按「變更…」。
    ⚠️ 兩個 widget 的 `pady` 要用同一個值：只換一個的話那一列的高度由較大的決定，
    看起來就是鈕沒對齊框。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    build = src[src.index("    def _build_ui"):src.index("    def _set_chevron")]
    assert 'self.out_entry = ttk.Entry(card, textvariable=self.out_show,\n' \
           '                                   state="readonly")' in build, \
        "輸出那一格要是唯讀的 Entry"
    assert "self._inputs += [change, self.out_entry]" in build, \
        "輸出框要跟著一起鎖（轉檔中改它對這一趟沒有作用）"
    for who in ("change.grid(row=3, column=0", "self.out_entry.grid(row=3, column=1"):
        seg = build[build.index(who):]
        assert "pady=(p(SP_MD), 0)" in seg[:seg.index("\n\n")], \
            f"{who} 的 pady 不是 SP_MD——兩個要一起換"


def test_a_broken_input_path_never_shows_a_ready_looking_output_name():
    """路徑打錯時，輸出那一格不可以顯示從它推出來的檔名（2026-08-29 修）。

    `_effective_out()` 在輸出欄留空時會拿輸入路徑推一個同名的 .pptx——那是給
    `_build_argv` 與結果列用的（那時輸入一定成立），顯示這一路照抄就會在路徑打錯時
    寫出「輸出：某某.pptx（與來源同資料夾）」，而旁邊的按鈕是灰的、狀態字寫著
    「找不到檔案」。⚠️ 判斷要**共用同一支**（`_valid_input`），各寫一份就會再漂開。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    assert "def _valid_input" in src, "驗證輸入的那一道判斷要抽成一支給兩邊共用"
    show = src[src.index("    def _refresh_out_show"):src.index("    def _set_inputs_enabled")]
    assert "self._valid_input()" in show, \
        "輸出顯示要先問輸入成不成立，不然打錯路徑也會推出一個檔名"
    state = src[src.index("    def _refresh_input_state"):src.index("    def _set_placeholder")]
    assert "self._valid_input()" in state, "能不能按也走同一支判斷"


def test_the_window_still_paints_a_backdrop_and_does_it_after_withdraw():
    """`winui.set_backdrop()` 要留在 `App.__init__` 裡，而且排在 `withdraw()` 之後。

    ⚠️ **它看起來像多餘的一行**：上一行的 `self.configure(background=…)` 已經設過底色
    了，而兩者的差別在「誰畫的」——`configure` 只管 **Tk 自己畫的**那一份，視窗最小化
    再還原時露出來的是 **Windows 那一層**（Tk 的兩個 window class 的 `hbrBackground`
    都是 NULL、又沒有雙緩衝），沒有它就是一片黑被內容一塊一塊填掉。

    ⚠️ **平常的驗收路徑抓不到它被拿掉**：`PrintWindow` 走 DWM 的 redirection surface，
    會把還沒畫完的部分**補齊**——截圖看起來永遠正常（`docs/dev` §5.14 那一輪是靠另一個
    行程連拍螢幕、比對相鄰兩幀才量到的）。所以這一條只能用測試釘。

    ⚠️ **順序也要釘**：`set_backdrop()` 內部會 `update_idletasks()`，排在 `withdraw()`
    之前等於在建介面之前就把一個空視窗貼上螢幕——正是 §5.13「啟動時不要先閃一個小畫面」
    要擋的事。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    init = src[src.index("    def __init__(self) -> None:\n        super().__init__()"):
               src.index("    def _apply_window_icon")]   # ⚠️ 收斂到 __init__ 自己
    assert "winui.set_backdrop(" in init, \
        "App.__init__ 不再給 window class 底色：最小化再還原會露出一片黑"
    assert init.index("self.withdraw()") < init.index("winui.set_backdrop("), \
        "set_backdrop() 會 update_idletasks()，排在 withdraw() 之前會把空視窗貼上螢幕"


def test_the_window_only_shows_up_once_it_is_finished():
    """啟動那四步的**順序**：量高度 → 擺位置 → 現身 → 鉗工作區。

    §5.13 那條「不要先閃一個小畫面」的全部就是這個順序。⚠️ 排錯了**不會當掉**，
    使用者看到的是「先出現一個 460 高的空視窗、再跳成 549」或「先出現在 A、再跳到
    B」那兩幀，而 `PrintWindow` 抓的是最終狀態、**永遠看不出來**（同 §5.14 那條：
    截圖驗收抓不到中間狀態）。

    四件事：`withdraw()` 要排在第一個會 `update_idletasks()` 的東西之前
    （`apply_ui_style()` 要送 `<<ThemeChanged>>`），`place_window()` 夾在第一次
    `_fit_window()` 與 `deiconify()` 之間（更早會拿還沒定案的高度去算、更晚就是
    「先出現在 A 再跳到 B」），`deiconify()` 只有一次，而最後一次 `_fit_window()`
    在它之後（標題列高度與實際落點要 map 之後才量得到）。

    ⚠️ 這一支刻意用**字串位置**、不用 `ast.walk`：後者是廣度優先、不是原始碼順序，
    巢狀呼叫（`winui.place_window(self, self.px(WIN_W), …)` 裡的 `self.px`）會被排到
    後面去，於是「誰在誰前面」得到的是錯的答案。要用 AST 就得自己按
    `(lineno, col_offset)` 排——姊妹專案 meeting-scribe 2026-08-29 踩過這一格。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    init = src[src.index("    def __init__(self) -> None:\n        super().__init__()"):
               src.index("    def _apply_window_icon")]   # ⚠️ 收斂到 __init__ 自己
    # ⚠️ 套佈景那一步要比對「賦值＋呼叫」的形狀：`__init__` 開頭的註解裡就寫著
    # 「`apply_ui_style()` 要送 `<<ThemeChanged>>`」，只比對函式名會抓到那句話，
    # 於是測試在**正確的**程式碼上就紅（第一版正是這樣，說 600 != 234）
    steps = ("self.withdraw()", "= apply_ui_style(", "self._fit_window()",
             "winui.place_window(", "self.deiconify()")
    at = [init.index(s) for s in steps]
    assert at == sorted(at), (
        "啟動那幾步的順序錯了（正確是 withdraw → 套佈景 → 量高度 → 擺位置 → 現身）："
        + "、".join(f"{s}@{i}" for s, i in sorted(zip(steps, at), key=lambda x: x[1])))
    assert init.count("self.deiconify()") == 1, "deiconify() 只該有一次"
    assert init.rindex("self._fit_window()") > init.index("self.deiconify()"), \
        "最後一次 _fit_window() 要在 deiconify() 之後（工作區鉗制要 map 了才量得到）"


def test_no_style_is_configured_for_a_widget_that_no_longer_exists():
    """`configure_styles()` 設過的樣式，都要真的有 widget 指名在用。

    ⚠️ 這是上一支的**反面**：那一支問「設了的有沒有生效」，這一支問「設了的有沒有人
    用」。兩面都要，因為它們擋的是不同的錯：前者擋「寫了卻沒作用」，後者擋**殘骸**。

    2026-08-29 抓到一個：`CardHint.Card.TLabel` 的字級覆寫。那天把框底下那一行說明收進
    輸入框、輸出改成唯讀 `Entry` 之後，用它的 widget 一個都不剩，而那行 `configure` 留
    著沒清。⚠️ **殘骸不會壞掉任何東西**——所以沒有任何徵狀——壞的是它讓下一個人以為
    那個樣式歸這支程式管（而它的顏色其實是共用包設的）。

    ⚠️ 這一支只管 `configure_styles()`：共用包設的那批是**兩支程式共有**的，這裡沒有
    widget 在用不代表那邊也沒有。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    body = src[src.index("def configure_styles"):src.index("def apply_ui_style")]
    consts = dict(re.findall(r'^([A-Z_]+)\s*=\s*"([^"]+)"', src, re.M))
    declared = set()
    for name in re.findall(r'st\.(?:configure|map)\(\s*"([^"]+)"', body):
        declared.add(name)
    for const in re.findall(r'st\.(?:configure|map)\(\s*([A-Z_]+)\s*,', body):
        declared.add(consts.get(const, const))

    used = set(re.findall(r'style="([^"]+)"', src))
    used |= {consts[c] for c in re.findall(r"style=([A-Z_]+)\b", src) if c in consts}
    # 那幾張表裡出現的樣式名也算「有人用」（皮膚換裝、按鈕內距是照表跑的）
    for table in ("SKIN_SWAPS", "SKIN_FRAMES", "BUTTONS", "ACCENT_STYLES"):
        m = re.search(rf"^{table}\s*[:=].*?^\)", src, re.S | re.M)
        if m:
            used |= set(re.findall(r'"([A-Za-z][\w.]*\.T\w+)"', m.group(0)))
            used |= {consts[c] for c in re.findall(r"\b([A-Z_]+)\b", m.group(0))
                     if c in consts}

    orphans = sorted(declared - used)
    assert not orphans, (
        "這些樣式設了卻沒有任何 widget 在用（殘骸，或是 widget 忘了指定 style=）：\n  "
        + "\n  ".join(orphans))


def test_each_run_resets_the_spinner_period_not_just_the_mode():
    """每一趟開始都要把 `maximum` 設回動畫的週期，不能只換 `mode`。

    ⚠️ **`maximum` 在 indeterminate 下不是「總量」，是動畫的週期**（滑塊幾步走完全程），
    而 `_scan_line` 會把同一個欄位設成**總頁數**。只重設 `mode` 與 `value` 的話，第二趟
    的滑塊會用四五步走完全程——使用者 2026-08-29 回報：「轉第二次時狀態列就會左右左
    跳動…那個藍點」。

    ⚠️ **這一類只有連跑兩趟才看得到**：單趟怎麼測都是對的（第一趟吃到 ttk 的預設值
    100，正好就是要的值）。實測前後：壞的那版第二趟是 `12/4 → 20/4 → …`（四步一趟），
    修好之後是 `6/100 → 16/100 → …`（≈5 秒一趟）。

    ⚠️ 週期**不可以**沿用頁數那個刻度：那一份是「進度的解析度」（愈細愈好），這一份是
    「動畫多快」（愈細愈慢）——姊妹專案 MP4-2-SRT 2026-08-28 就是把兩者合成一個常數而
    做壞過一次。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    start = src[src.index("    def _start(self)"):src.index("    def _run_conversion")]
    line = [l for l in start.splitlines() if 'mode="indeterminate"' in l]
    assert line, "_start() 沒有把進度條切回不定長度"
    assert "maximum=SPIN_STEPS" in line[0], (
        "切回不定長度時要一起重設 `maximum`（上一趟的頁數還留在裡面）：\n  "
        + line[0].strip())
    assert G.SPIN_STEPS == 100, (
        f"動畫走一趟的步數改了（現在 {G.SPIN_STEPS}）——100 步 ≈ 5 秒是量過的：\n"
        "  太少 → 在兩端之間狂跳、讀成閃爍；太多 → 慢到看不出在動")
