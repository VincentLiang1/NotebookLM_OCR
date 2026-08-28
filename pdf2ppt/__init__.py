r"""pdf2ppt — convert image-only PDF slide decks into editable PPTX via OCR.

⚠️ **這裡是共用包 `winkit` 的唯一注入點。** 放在 `__init__.py` 的理由:**任何子模組
被 import 都會先經過這裡**,所以「忘了 bind」不會發生在正常的執行路徑上——連那支
跑在安裝當下、刻意不載整個套件的 `tools/make_shortcut.py` 也一樣(它走
`from pdf2ppt.brand import ...`,而匯入子模組必先匯入父套件)。

⚠️ **`repo_root` 是 `parents[1]`,不可以讓 `winkit` 自己推**:這個 repo 是 flat
layout(`pdf2ppt/` 直接坐在根目錄上),姊妹專案 MP4-2-SRT 是 src layout
(`src/mp4_2_srt/`)要往上兩層——差一層,而**推的那個版本會在其中一邊安靜地算錯**:
紀錄檔寫進別的資料夾、版本號讀成別人的 `.git`、資產在那邊找不到,三個症狀都沒有
錯誤訊息、看起來全都像「東西不見了」。

⚠️ **皮膚產生器的位置也要給**:共用包的預設是下游 `scripts` 目錄底下那一支,而這個
repo 的開發腳本全在 `tools/`。⚠️ **指錯是安靜降級**——「當場畫」那條路 import 不到,
於是顯示縮放對不上出貨資產的機器整個掉皮膚,畫面只是「這台的長相跟別台不一樣」。

⚠️ **匯入代價要維持在「只有 pathlib」這一級**:GUI 的啟動路徑會經過這裡
(GUI 為了三個字串 import `pdf2ppt.brand`,那就在雙擊到視窗出現之間),而 `winkit` 的
`__init__` 與本專案的 `brand` 都刻意零相依。⚠️ 不要在這裡 import 任何領域模組
(`cli`、`ocr`、`style`…)「順便省一行」——那等於把 numpy／pymupdf／python-pptx
那一整串塞進啟動路徑。
"""
from pathlib import Path

import winkit

from pdf2ppt import brand

winkit.bind(brand,
            package_dir=Path(__file__).resolve().parent,
            repo_root=Path(__file__).resolve().parents[1],
            skin_generator=Path(__file__).resolve().parents[1]
            / "tools" / "make_skin.py")
