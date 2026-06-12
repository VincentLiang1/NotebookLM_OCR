# NotebookLM_PDF_2_PPT

把 **NotebookLM 產出的 PDF 簡報** OCR 後轉換成**可編輯的 PowerPoint**。完全在本地執行、資料零上傳。

每頁投影片的輸出結構：

- 以全解析度的頁面渲染圖作為背景，版面 100% 保留
- 每行文字疊上一個「取樣自原圖底色」的實心色塊，蓋住圖中的點陣文字
- 色塊上承載**真正可編輯的文字方塊**，字級、粗體、文字顏色、對齊都從影像自動估計

## 特色

- **本地離線**：OCR 使用 [RapidOCR](https://github.com/RapidAI/RapidOCR)（PP-OCRv5 server 模型），只有首次執行需要網路下載模型
- **繁體中文最佳化**：PP-OCRv5 server 模型對繁中準確度遠勝預設模型；自動修正辨識混入的簡體字形（恶→惡），同時保留刻意呈現的純簡體內容
- **樣式擬真**：字級以字墨高度實證校準、文字色取筆畫核心避免反鋸齒偏色、底色支援緞帶/膠囊/多層背景的判別
- **傾斜與弧形文字**：偵測器給出旋轉框時直接輸出旋轉文字方塊；弧形緞帶（圓弧排列的橫幅文字）自動偵測曲率，以分段切線文字方塊沿弧線排列、色塊條帶沿弧線覆蓋
- **文字品質**：自動還原英文單字間的空格（含物理墨水驗證防誤插）、中英交界補空格（盤古之白）、復原被裁掉的行尾標點、同一行多種顏色會拆成多個 run、行首 ⚠ 警告圖示不會誤認成字母 A
- **浮水印清除**：右下角的 NotebookLM Logo 與字樣自動以同底色色塊遮蓋（`--keep-watermark` 可保留）

## 安裝

需求：Python 3.10+（開發環境為 3.14）、Windows/macOS/Linux

```bash
pip install -r requirements.txt
```

預設輸出字型為 Microsoft YaHei（Windows 內建），可用 `--font` 改成其他字型。

## 使用方式

```bash
python pdf2ppt.py input.pdf                    # 輸出 input.pptx
python pdf2ppt.py input.pdf -o output.pptx     # 指定輸出檔名
python pdf2ppt.py input.pdf --pages 1-5,8      # 只轉指定頁
python pdf2ppt.py input.pdf --keep-watermark   # 保留右下角 NotebookLM 浮水印
```

### 選項

| 選項 | 說明 |
|---|---|
| `-o, --output` | 輸出檔路徑（預設：輸入檔名改副檔名 `.pptx`）|
| `--dpi N` | 渲染解析度（預設 200）|
| `--pages 1-5,8` | 頁碼選擇 |
| `--min-score 0.5` | 過濾低於此信心分數的 OCR 行 |
| `--no-cover` | 不加實心色塊，文字直接疊在背景圖上 |
| `--keep-watermark` | 保留右下角的 NotebookLM 浮水印 |
| `--merge-lines` | 相鄰同樣式行合併為一個文字方塊（多段落）|
| `--no-bold` / `--force-bold` | 全域強制細體 / 粗體 |
| `--no-s2t` | 關閉簡體混入修正 |
| `--font "Microsoft YaHei"` | 輸出字型 |
| `--fast` | 改用 mobile 辨識模型（較快，繁中準確度較低）|
| `--lang` | 指定 RapidOCR 辨識語言（預設中英混合）|
| `--debug` | 輸出每頁 OCR 框疊圖 PNG 與樣式 JSON，供調參 |

## 運作原理

```
PDF 頁面 ──PyMuPDF 渲染(200dpi)──▶ 頁面影像 ─┬─▶ 投影片背景圖
                                             │
                                             ▼
                                   RapidOCR (PP-OCRv5 server)
                                   逐行文字 + 座標框 + 逐字框
                                             │
                                             ▼
                              樣式估計（全部來自影像分析）
                              字級 ← 緊貼字墨高度 / 0.91
                              　　　（中英混合行取逐字 CJK 共識，
                              　　　  拉丁降部不會灌高字級；
                              　　　  同段折行字級自動調和、
                              　　　  同款標題粗體隊列投票）
                              底色 ← 框外環帶 + 光暈/膠囊/緞帶判別
                              文字色 ← 筆畫核心（離底色最遠的 30% 像素）
                              多色行 ← 逐字取色分段
                                             │
                                             ▼
                              python-pptx 輸出
                              背景圖 + 實心色塊 + 可編輯文字方塊
```

## 驗證

倉庫附有比對工具，可把轉換結果與參考 PPTX 做文字召回率比對：

```bash
python tools/compare_pptx.py generated.pptx reference.pptx
```

在 15 頁的範例簡報上，文字召回率 100%。

## 已知限制

- 來源 PDF 解析度過低（72dpi 點陣）時，小字的粗體/細體無法從像素判別，改以字級規則推定（≥24pt 視為粗體）
- 同一行中英混排只使用單一字級
- 弧形文字以 3–6 段切線文字方塊近似（各段可分別編輯，段間可能有微小空隙）
- 漸層或照片背景上的文字不加色塊（文字直接疊圖，可用 `--no-cover` 全域達成相同效果）
