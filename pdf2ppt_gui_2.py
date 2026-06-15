#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NotebookLM PDF → PPT  桌面轉檔工具（圖形介面）
================================================

把 VincentLiang1/NotebookLM_OCR 的命令列工具 pdf2ppt.py 包成一個
有介面、可點選操作的桌面應用程式。

使用方式
--------
1. 先依專案 README 安裝相依套件（在專案資料夾內執行）：
       pip install -r requirements.txt
   （需要 GPU 加速可另外 pip install onnxruntime-directml / onnxruntime-gpu）

2. 把這個檔案放到 NotebookLM_OCR 專案的「根目錄」
   （也就是 pdf2ppt.py 旁邊、能看到 pdf2ppt/ 資料夾的地方），然後執行：
       python pdf2ppt_gui.py

   首次轉檔會自動下載 OCR 模型，需要短暫連網。

這支 GUI 只負責「收集選項 + 呼叫專案的轉檔邏輯 + 即時顯示進度」，
真正的 OCR / 排版工作完全沿用原專案的程式碼，零修改、零重複。
"""
from __future__ import annotations

import os
import json
import queue
import sys
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "NotebookLM PDF → PPT 轉檔工具"

# 記住專案位置的設定檔（存在使用者家目錄，跟著使用者走）
CONFIG_PATH = Path.home() / ".notebooklm_pdf2ppt_gui.json"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass


def is_project_dir(path: Path) -> bool:
    """一個合格的專案根目錄：底下有 pdf2ppt 套件（pdf2ppt/cli.py）。"""
    try:
        return (path / "pdf2ppt" / "cli.py").is_file()
    except Exception:
        return False


def find_project_dir() -> Path | None:
    """依序嘗試：1) 設定檔記住的路徑 2) GUI 自身所在目錄 3) 目前工作目錄。"""
    cfg = load_config()
    remembered = cfg.get("project_dir")
    if remembered and is_project_dir(Path(remembered)):
        return Path(remembered)

    here = Path(__file__).resolve().parent
    for cand in (here, Path.cwd()):
        if is_project_dir(cand):
            return cand
    return None
FONT_CHOICES = [
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "PingFang TC",
    "Noto Sans CJK TC",
    "標楷體",
]


# --------------------------------------------------------------------------- #
#  把背景執行緒裡的 print() 導到 GUI 的工具
# --------------------------------------------------------------------------- #
class QueueWriter:
    """一個假的 stdout：寫入的文字丟進 queue，由主執行緒撈出來顯示。

    cli.py 會檢查 sys.stdout.encoding 並可能呼叫 reconfigure()，
    因此這裡補齊真正文字串流會有的屬性與方法，避免 AttributeError。
    """

    encoding = "utf-8"

    def __init__(self, q: "queue.Queue[str]"):
        self.q = q

    def write(self, text: str) -> int:
        if text:
            self.q.put(text)
        return len(text)

    def flush(self) -> None:  # print 需要這個方法存在
        pass

    def reconfigure(self, *args, **kwargs) -> None:
        """cli.py 會呼叫 sys.stdout.reconfigure(encoding="utf-8")；
        我們本來就是 utf-8，當作無操作即可。"""
        enc = kwargs.get("encoding")
        if enc:
            self.encoding = enc

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def fileno(self) -> int:  # 某些函式庫會問；給個合理錯誤而非崩潰
        raise OSError("QueueWriter has no fileno")


# --------------------------------------------------------------------------- #
#  主應用
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x720")
        self.minsize(680, 640)

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.worker: threading.Thread | None = None
        self.running = False
        self.project_dir: Path | None = find_project_dir()

        self._build_vars()
        self._build_ui()
        self._refresh_project_label()
        self.after(80, self._drain_log)

    # ---- 變數 ----
    def _build_vars(self) -> None:
        self.in_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.pages = tk.StringVar()
        self.font = tk.StringVar(value=FONT_CHOICES[0])
        self.device = tk.StringVar(value="auto")
        self.dpi = tk.IntVar(value=200)
        self.min_score = tk.DoubleVar(value=0.5)
        self.bold_mode = tk.StringVar(value="auto")       # auto / never / always

        self.fast = tk.BooleanVar(value=False)
        self.no_s2t = tk.BooleanVar(value=False)
        self.no_cover = tk.BooleanVar(value=False)
        self.keep_watermark = tk.BooleanVar(value=False)
        self.keep_tiny_text = tk.BooleanVar(value=False)
        self.merge_lines = tk.BooleanVar(value=False)
        self.debug = tk.BooleanVar(value=False)

    # ---- 介面 ----
    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        title = ttk.Label(root, text=APP_TITLE, font=("", 15, "bold"))
        title.pack(anchor="w")
        sub = ttk.Label(
            root,
            text="把 NotebookLM 產出的繁中 PDF 簡報 OCR 後轉成可編輯的 PowerPoint（本地離線執行）。",
            foreground="#666",
        )
        sub.pack(anchor="w", pady=(0, 8))

        # ---- 專案位置區 ----
        proj = ttk.LabelFrame(root, text="專案位置（pdf2ppt 程式所在資料夾）", padding=10)
        proj.pack(fill="x", **pad)
        self.project_label = ttk.Label(proj, text="", foreground="#666",
                                       wraplength=560, justify="left")
        self.project_label.grid(row=0, column=0, sticky="w")
        ttk.Button(proj, text="選擇專案資料夾…",
                   command=self._pick_project).grid(row=0, column=1, padx=6)
        proj.columnconfigure(0, weight=1)

        # ---- 檔案區 ----
        files = ttk.LabelFrame(root, text="檔案", padding=10)
        files.pack(fill="x", **pad)

        ttk.Label(files, text="輸入 PDF：").grid(row=0, column=0, sticky="w")
        ttk.Entry(files, textvariable=self.in_path).grid(
            row=0, column=1, sticky="ew", padx=6)
        ttk.Button(files, text="瀏覽…", command=self._pick_input).grid(
            row=0, column=2)

        ttk.Label(files, text="輸出 PPTX：").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(files, textvariable=self.out_path).grid(
            row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(files, text="另存…", command=self._pick_output).grid(
            row=1, column=2, pady=(6, 0))
        files.columnconfigure(1, weight=1)

        # ---- 常用選項 ----
        opt = ttk.LabelFrame(root, text="常用選項", padding=10)
        opt.pack(fill="x", **pad)

        ttk.Label(opt, text="頁碼（例 1-5,8，留空=全部）：").grid(
            row=0, column=0, sticky="w")
        ttk.Entry(opt, textvariable=self.pages, width=18).grid(
            row=0, column=1, sticky="w", padx=6)

        ttk.Label(opt, text="中文字型：").grid(row=0, column=2, sticky="e")
        ttk.Combobox(opt, textvariable=self.font, values=FONT_CHOICES,
                     width=20).grid(row=0, column=3, sticky="w", padx=6)

        ttk.Label(opt, text="推論裝置：").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(opt, textvariable=self.device,
                     values=["auto", "cpu", "dml", "cuda"], width=8,
                     state="readonly").grid(row=1, column=1, sticky="w",
                                            padx=6, pady=(8, 0))

        ttk.Label(opt, text="粗體模式：").grid(row=1, column=2, sticky="e", pady=(8, 0))
        ttk.Combobox(opt, textvariable=self.bold_mode,
                     values=["auto", "never", "always"], width=10,
                     state="readonly").grid(row=1, column=3, sticky="w",
                                            padx=6, pady=(8, 0))

        ttk.Label(opt, text="渲染 DPI：").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(opt, from_=72, to=600, increment=20, textvariable=self.dpi,
                    width=8).grid(row=2, column=1, sticky="w", padx=6, pady=(8, 0))

        ttk.Label(opt, text="最低信心分數：").grid(row=2, column=2, sticky="e", pady=(8, 0))
        ttk.Spinbox(opt, from_=0.0, to=1.0, increment=0.05, format="%.2f",
                    textvariable=self.min_score, width=8).grid(
            row=2, column=3, sticky="w", padx=6, pady=(8, 0))

        # ---- 進階開關 ----
        adv = ttk.LabelFrame(root, text="進階開關", padding=10)
        adv.pack(fill="x", **pad)
        checks = [
            ("使用快速模型（mobile，較快但繁中較不準）", self.fast),
            ("保留 NotebookLM 浮水印", self.keep_watermark),
            ("保留圖表內小字（預設保留原圖不轉文字）", self.keep_tiny_text),
            ("相鄰同樣式行合併成一個文字方塊", self.merge_lines),
            ("不加色塊，文字直接疊在背景圖上", self.no_cover),
            ("關閉簡體混入修正", self.no_s2t),
            ("輸出除錯資料（OCR 疊圖 PNG + JSON）", self.debug),
        ]
        for i, (label, var) in enumerate(checks):
            ttk.Checkbutton(adv, text=label, variable=var).grid(
                row=i // 2, column=i % 2, sticky="w", padx=6, pady=2)

        # ---- 動作列 ----
        actions = ttk.Frame(root)
        actions.pack(fill="x", **pad)
        self.run_btn = ttk.Button(actions, text="開始轉檔", command=self._start)
        self.run_btn.pack(side="left")
        ttk.Button(actions, text="清除日誌",
                   command=lambda: self.log.delete("1.0", "end")).pack(
            side="left", padx=6)
        self.status = ttk.Label(actions, text="就緒", foreground="#0a0")
        self.status.pack(side="right")

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", **pad)

        # ---- 日誌 ----
        logframe = ttk.LabelFrame(root, text="進度", padding=6)
        logframe.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logframe, height=12, wrap="word",
                           font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logframe, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set)
        self._append("提示：把本程式放在 pdf2ppt.py 旁邊執行。"
                     "首次轉檔會自動下載 OCR 模型，請耐心等候。\n")

    # ---- 專案位置 ----
    def _refresh_project_label(self) -> None:
        if self.project_dir and is_project_dir(self.project_dir):
            self.project_label.config(
                text=f"✓ 已找到：{self.project_dir}", foreground="#0a0")
        else:
            self.project_label.config(
                text="✗ 尚未找到 pdf2ppt 套件，請按右側按鈕選擇專案資料夾"
                     "（裡面要有 pdf2ppt.py 和 pdf2ppt 資料夾）。",
                foreground="#c00")

    def _pick_project(self) -> None:
        d = filedialog.askdirectory(title="選擇 NotebookLM_OCR 專案資料夾")
        if not d:
            return
        path = Path(d)
        if not is_project_dir(path):
            messagebox.showerror(
                "資料夾不正確",
                f"這個資料夾裡找不到 pdf2ppt\\cli.py：\n{path}\n\n"
                "請選擇 NotebookLM_OCR 專案的根目錄"
                "（能看到 pdf2ppt.py 和 pdf2ppt 資料夾的那一層）。")
            return
        self.project_dir = path
        cfg = load_config()
        cfg["project_dir"] = str(path)
        save_config(cfg)
        self._refresh_project_label()
        self._append(f"已記住專案位置：{path}\n")

    # ---- 檔案挑選 ----
    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(
            title="選擇輸入 PDF",
            filetypes=[("PDF 檔", "*.pdf"), ("所有檔案", "*.*")])
        if p:
            self.in_path.set(p)
            if not self.out_path.get():
                self.out_path.set(str(Path(p).with_suffix(".pptx")))

    def _pick_output(self) -> None:
        init = self.out_path.get() or (
            str(Path(self.in_path.get()).with_suffix(".pptx"))
            if self.in_path.get() else "")
        p = filedialog.asksaveasfilename(
            title="輸出 PPTX 另存為",
            defaultextension=".pptx",
            initialfile=Path(init).name if init else "output.pptx",
            initialdir=str(Path(init).parent) if init else ".",
            filetypes=[("PowerPoint 簡報", "*.pptx")])
        if p:
            self.out_path.set(p)

    # ---- 組 argv ----
    def _build_argv(self) -> list[str]:
        if not self.in_path.get():
            raise ValueError("請先選擇輸入 PDF 檔。")
        if not Path(self.in_path.get()).is_file():
            raise ValueError(f"找不到輸入檔：{self.in_path.get()}")

        argv = [self.in_path.get()]
        if self.out_path.get():
            argv += ["-o", self.out_path.get()]
        if self.pages.get().strip():
            argv += ["--pages", self.pages.get().strip()]
        argv += ["--dpi", str(self.dpi.get())]
        argv += ["--min-score", f"{self.min_score.get():.2f}"]
        argv += ["--device", self.device.get()]
        argv += ["--font", self.font.get()]

        if self.bold_mode.get() == "never":
            argv.append("--no-bold")
        elif self.bold_mode.get() == "always":
            argv.append("--force-bold")

        if self.fast.get():
            argv.append("--fast")
        if self.no_s2t.get():
            argv.append("--no-s2t")
        if self.no_cover.get():
            argv.append("--no-cover")
        if self.keep_watermark.get():
            argv.append("--keep-watermark")
        if self.keep_tiny_text.get():
            argv.append("--keep-tiny-text")
        if self.merge_lines.get():
            argv.append("--merge-lines")
        if self.debug.get():
            argv.append("--debug")
        return argv

    # ---- 啟動轉檔 ----
    def _start(self) -> None:
        if self.running:
            return
        if not (self.project_dir and is_project_dir(self.project_dir)):
            messagebox.showwarning(
                "找不到專案",
                "尚未指定 pdf2ppt 專案位置。\n\n"
                "請按上方「選擇專案資料夾…」，指向 NotebookLM_OCR 專案根目錄。")
            return
        try:
            argv = self._build_argv()
        except ValueError as e:
            messagebox.showwarning("缺少資訊", str(e))
            return

        self.running = True
        self.run_btn.config(state="disabled")
        self.status.config(text="轉檔中…", foreground="#c60")
        self.progress.start(12)
        self._append("\n" + "=" * 60 + "\n")
        self._append("執行： pdf2ppt " + " ".join(
            f'"{a}"' if " " in a else a for a in argv) + "\n")

        self.worker = threading.Thread(
            target=self._run_conversion, args=(argv,), daemon=True)
        self.worker.start()

    # ---- 背景執行緒：實際呼叫專案的 main() ----
    def _run_conversion(self, argv: list[str]) -> None:
        old_out, old_err = sys.stdout, sys.stderr
        old_cwd = os.getcwd()
        writer = QueueWriter(self.log_queue)
        sys.stdout = sys.stderr = writer
        rc = 1
        try:
            # 用使用者指定（或自動找到）的專案目錄來載入套件
            proj = str(self.project_dir)
            if proj not in sys.path:
                sys.path.insert(0, proj)
            # 切到專案目錄，確保模型快取等相對路徑落在專案底下
            os.chdir(proj)
            try:
                from pdf2ppt.cli import main
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError(
                    f"在指定的專案目錄找不到 pdf2ppt 套件：{proj}\n"
                    "請確認該資料夾裡有 pdf2ppt 子資料夾，且已執行 "
                    "pip install -r requirements.txt。\n"
                    f"原始錯誤：{e}")
            rc = main(argv)
        except SystemExit as e:        # argparse 在參數錯誤時會 raise 這個
            rc = int(e.code) if isinstance(e.code, int) else 1
        except Exception:
            self.log_queue.put("\n[發生錯誤]\n")
            self.log_queue.put(traceback.format_exc())
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            try:
                os.chdir(old_cwd)
            except Exception:
                pass
            self.log_queue.put(("__DONE__", rc))

    # ---- 主執行緒：把 queue 內容寫進日誌 ----
    def _drain_log(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    self._finish(item[1])
                else:
                    self._append(item)
        except queue.Empty:
            pass
        self.after(80, self._drain_log)

    def _finish(self, rc: int) -> None:
        self.running = False
        self.progress.stop()
        self.run_btn.config(state="normal")
        if rc == 0:
            self.status.config(text="完成 ✓", foreground="#0a0")
            out = self.out_path.get() or "(輸入檔同名 .pptx)"
            self._append(f"\n✓ 轉檔完成：{out}\n")
            if messagebox.askyesno("完成", f"轉檔完成！\n\n{out}\n\n要開啟所在資料夾嗎？"):
                self._open_folder(out)
        else:
            self.status.config(text=f"失敗（代碼 {rc}）", foreground="#c00")
            self._append(f"\n✗ 轉檔失敗（return code = {rc}）\n")

    def _open_folder(self, path: str) -> None:
        try:
            folder = str(Path(path).resolve().parent)
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception:
            pass

    def _append(self, text: str) -> None:
        self.log.insert("end", text)
        self.log.see("end")


def main() -> int:
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
