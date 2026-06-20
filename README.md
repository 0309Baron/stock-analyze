# 台股每日數據分析平台

本專案透過台灣證券交易所 API 取得台股歷史交易資料，將資料儲存至 SQLite，並使用 Pandas 計算技術指標與產生規則式分析結果。

目前支援的功能：

* 取得台股每日交易資料
* 下載指定股票的歷史資料
* 將資料儲存至 SQLite
* 計算每日報酬率
* 計算 MA5、MA20
* 計算近 5 日漲跌幅
* 計算成交量倍率
* 計算 20 日波動度
* 產生趨勢分數與分析原因

> 本專案目前以 Ubuntu 環境進行開發。

---

## 專案架構

```text
stock_project/
├── data/
│   └── stock.db
├── static/
├── templates/
├── .gitignore
├── analyzer.py
├── database.py
├── fetch_stock.py
├── import_history.py
├── requirements.txt
└── README.md
```

各檔案用途：

| 檔案                  | 功能                |
| ------------------- | ----------------- |
| `fetch_stock.py`    | 測試證交所每日股票 API     |
| `database.py`       | 建立 SQLite 資料庫與資料表 |
| `import_history.py` | 下載指定股票的歷史交易資料     |
| `analyzer.py`       | 計算技術指標並產生分析結果     |
| `requirements.txt`  | 專案需要的 Python 套件   |
| `data/stock.db`     | SQLite 資料庫檔案      |

---

# 第一次下載專案

## 使用vscode 安裝 WSL 使用 ubuntu 環境

## 1. Clone 專案

```bash
git clone https://github.com/0309Baron/stock-analyze.git
```

進入專案資料夾：

```bash
cd stock_project
```

---

## 2. 安裝 Ubuntu 必要套件

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv sqlite3
```

確認 Python 是否安裝成功：

```bash
python3 --version
```

---

## 3. 建立 Python 虛擬環境

```bash
python3 -m venv .venv
```

啟用虛擬環境：

```bash
source .venv/bin/activate
```

成功啟用後，終端機前面通常會出現：

```text
(.venv)
```

之後所有 Python 指令都應該在虛擬環境內執行。

---

## 4. 安裝 Python 套件

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

安裝完成後可以確認：

```bash
pip list
```

---

## 5. 建立 SQLite 資料庫

```bash
python database.py
```

成功後應該會看到：

```text
資料庫建立完成
位置：.../stock_project/data/stock.db
```

確認資料庫檔案：

```bash
ls -l data
```

---

## 6. 測試台股 API

```bash
python fetch_stock.py
```

程式會呼叫證交所 API，並顯示台積電 `2330` 的最新交易資料。

正常情況會看到：

```text
成功取得股票資料

股票代碼：2330
股票名稱：台積電
開盤價：...
最高價：...
最低價：...
收盤價：...
成交量：...
```

實際數字會依照最新交易日改變。

---

## 7. 下載歷史資料

下載台積電最近 6 個月的交易資料：

```bash
python import_history.py 2330 台積電 --months 6
```

指令格式：

```bash
python import_history.py <股票代碼> <股票名稱> --months <月份數量>
```

例如下載鴻海最近 12 個月資料：

```bash
python import_history.py 2317 鴻海 --months 12
```

下載聯發科最近 6 個月資料：

```bash
python import_history.py 2454 聯發科 --months 6
```

歷史資料會儲存在：

```text
data/stock.db
```

---

## 8. 執行股票分析

分析台積電：

```bash
python analyzer.py 2330
```

分析鴻海：

```bash
python analyzer.py 2317
```

分析聯發科：

```bash
python analyzer.py 2454
```

輸出結果大致如下：

```text
==================================================
台積電 (2330)
==================================================

分析日期：2026-06-19
歷史資料筆數：100

【當日行情】
開盤價：...
最高價：...
最低價：...
收盤價：...
成交量：...

【技術指標】
每日報酬率：...
MA5：...
MA20：...
近 5 日漲跌幅：...
成交量倍率：...
20 日波動度：...

【分析結果】
分數：75 / 100
趨勢：偏多

【判斷原因】
- 收盤價高於 MA5，短期價格相對強勢
- MA5 高於 MA20，均線結構偏多
- 近 5 個交易日股價上漲
```

> 分析結果為規則式數據分析，不構成任何投資建議。

---

# 查看資料庫

使用 SQLite 開啟資料庫：

```bash
sqlite3 data/stock.db
```

設定顯示格式：

```sql
.headers on
.mode column
```

查看所有已經下載的股票：

```sql
SELECT DISTINCT stock_code, stock_name
FROM stock_daily;
```

查看台積電最新 10 筆資料：

```sql
SELECT
    trade_date,
    stock_code,
    stock_name,
    open_price,
    high_price,
    low_price,
    close_price,
    trade_volume
FROM stock_daily
WHERE stock_code = '2330'
ORDER BY trade_date DESC
LIMIT 10;
```

查看台積電總資料筆數：

```sql
SELECT COUNT(*)
FROM stock_daily
WHERE stock_code = '2330';
```

離開 SQLite：

```sql
.quit
```

---

# 已經下載過專案的人如何更新

進入專案：

```bash
cd stock_project
```

取得 GitHub 最新版本：

```bash
git pull
```

啟用虛擬環境：

```bash
source .venv/bin/activate
```

如果 `requirements.txt` 有更新，重新安裝套件：

```bash
pip install -r requirements.txt
```

如果資料庫結構有更新，可以再次執行：

```bash
python database.py
```

`CREATE TABLE IF NOT EXISTS` 不會刪除原本已存在的資料。

---

# 每次重新打開終端機

每次關閉終端機後，虛擬環境會自動退出。

重新開啟終端機時需要執行：

```bash
cd ~/stock_project
source .venv/bin/activate
```

接著才能執行：

```bash
python analyzer.py 2330
```

使用完畢後可以退出虛擬環境：

```bash
deactivate
```

---

# 更新 requirements.txt

當專案新增 Python 套件時，請更新：

```bash
pip freeze > requirements.txt
```

其他人執行：

```bash
pip install -r requirements.txt
```

就能安裝相同的套件版本。

---

# 建議的 .gitignore

專案根目錄建議建立 `.gitignore`：

```gitignore
# Python virtual environment
.venv/
venv/

# Python cache
__pycache__/
*.py[cod]

# Environment variables
.env

# IDE settings
.vscode/
.idea/

# SQLite database
data/*.db

# Log files
*.log
```

`.venv` 不應上傳到 GitHub，因為每個使用者應在自己的電腦重新建立虛擬環境。

如果希望所有人共用同一份測試資料庫，可以暫時移除：

```gitignore
data/*.db
```

但正式專案通常不建議將資料庫檔案直接提交到 GitHub。

---

# 常見問題

## 出現 `ModuleNotFoundError`

例如：

```text
ModuleNotFoundError: No module named 'pandas'
```

先確認虛擬環境是否啟用：

```bash
source .venv/bin/activate
```

再安裝套件：

```bash
pip install -r requirements.txt
```

---

## 找不到資料庫中的股票

例如：

```text
資料庫中找不到股票 2330
```

代表尚未下載該股票的歷史資料：

```bash
python import_history.py 2330 台積電 --months 6
```

下載完成後再分析：

```bash
python analyzer.py 2330
```

---

## 找不到 `python` 指令

可以改用：

```bash
python3 analyzer.py 2330
```

如果已正確啟用虛擬環境，通常可以直接使用：

```bash
python analyzer.py 2330
```

---

## API 連線失敗

請先確認網路連線：

```bash
ping -c 4 www.twse.com.tw
```

也可以稍後重新執行：

```bash
python fetch_stock.py
```

證交所可能會在短時間大量請求時限制連線，因此不要在迴圈中過度頻繁地呼叫 API。

---

# 完整執行流程

第一次下載專案後，可以依序執行：

```bash
git clone <你的 GitHub repository URL>
cd stock_project

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

python database.py
python fetch_stock.py
python import_history.py 2330 台積電 --months 6
python analyzer.py 2330
```

之後每次使用：

```bash
cd stock_project
source .venv/bin/activate
python analyzer.py 2330
```

---

# 開發進度

* [x] 台股 API 串接
* [x] SQLite 資料庫
* [x] 歷史資料下載
* [x] 每日報酬率
* [x] MA5 與 MA20
* [x] 成交量倍率
* [x] 20 日波動度
* [x] 規則式評分
* [ ] Flask 網頁
* [ ] 股價走勢圖
* [ ] 每日自動更新
* [ ] 三大法人資料
* [ ] 新聞資料整合
* [ ] 股票觀察清單

---

# 使用技術

* Python 3
* Requests
* Pandas
* SQLite
* Flask
* HTML
* CSS
* Chart.js

---

# 免責聲明

本專案僅供課程學習、程式設計與資料分析使用。

系統產生的分數、趨勢與文字分析皆為規則式計算結果，不代表未來股價表現，也不構成任何形式的投資建議。
