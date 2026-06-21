import sqlite3
import os
from threading import Lock
from typing import Any

from flask import Flask, render_template, request

from analyzer import analyze_stock, get_chart_data
from database import create_tables, get_connection
from fetch_stock import fetch_all_stocks
from import_history import import_history


app = Flask(__name__)

# 找不到股票時，自動下載最近幾個月
AUTO_IMPORT_MONTHS = 6

# 避免兩個請求同時下載相同資料
import_lock = Lock()

# 啟動 Flask 時確認資料表存在
create_tables()


def get_available_stocks() -> list[dict[str, str]]:
    """取得資料庫內已有的股票。"""

    query = """
        SELECT
            stock_code,
            MAX(stock_name) AS stock_name
        FROM stock_daily
        GROUP BY stock_code
        ORDER BY stock_code
    """

    with get_connection() as connection:
        rows = connection.execute(query).fetchall()

    return [
        {
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
        }
        for row in rows
    ]


def find_stock_information(
    stocks: list[dict],
    stock_code: str,
) -> dict | None:
    """從證交所最新股票清單中尋找股票。"""

    return next(
        (
            stock
            for stock in stocks
            if str(stock.get("Code", "")).strip()
            == stock_code
        ),
        None,
    )


def auto_import_stock(
    stock_code: str,
) -> tuple[dict | None, str | None, str | None]:
    """
    自動下載尚未匯入的股票。

    回傳：
    分析結果、成功訊息、錯誤訊息
    """

    # 鎖定匯入程序，避免同時重複下載
    with import_lock:
        # 取得鎖之後再確認一次，避免其他請求已經匯入
        existing_result = analyze_stock(stock_code)

        if existing_result.get("success"):
            return existing_result, None, None

        try:
            stocks = fetch_all_stocks()
        except RuntimeError as error:
            print(f"取得股票清單失敗：{error}")

            return (
                None,
                None,
                "無法連接證交所 API，請稍後再試。",
            )

        stock = find_stock_information(
            stocks,
            stock_code,
        )

        if stock is None:
            return (
                None,
                None,
                (
                    f"找不到股票代碼 {stock_code}。"
                    "目前系統只支援證交所上市股票。"
                ),
            )

        stock_name = str(
            stock.get("Name", "")
        ).strip()

        if not stock_name:
            return (
                None,
                None,
                "成功找到股票代碼，但無法取得股票名稱。",
            )

        print()
        print("=" * 50)
        print(
            f"資料庫尚無 {stock_name}（{stock_code}），"
            "開始自動下載歷史資料。"
        )
        print("=" * 50)

        try:
            imported_count = import_history(
                stock_code=stock_code,
                stock_name=stock_name,
                month_count=AUTO_IMPORT_MONTHS,
            )

        except Exception as error:
            print(f"自動匯入失敗：{error}")

            return (
                None,
                None,
                "下載歷史資料時發生錯誤。",
            )

        if imported_count <= 0:
            return (
                None,
                None,
                (
                    f"沒有取得 {stock_name}（{stock_code}）"
                    "的歷史資料。"
                ),
            )

        result = analyze_stock(stock_code)

        if not result.get("success"):
            return (
                None,
                None,
                result.get(
                    "message",
                    "資料下載完成，但分析失敗。",
                ),
            )

        success_message = (
            f"首次查詢 {stock_name}（{stock_code}），"
            f"已自動匯入最近 {AUTO_IMPORT_MONTHS} 個月，"
            f"共處理 {imported_count} 筆交易資料。"
        )

        return result, success_message, None


@app.template_filter("number")
def format_number(value: Any) -> str:
    """將數字加上千分位。"""

    if value is None:
        return "--"

    try:
        number = float(value)

        if number.is_integer():
            return f"{int(number):,}"

        return f"{number:,.2f}"

    except (TypeError, ValueError):
        return str(value)

# --- 1. 新增：專門用來顯示深度報告的路由 ---
@app.route("/report/<stock_code>")
def view_report(stock_code):
    """讀取並顯示個別股票的深度分析報告"""
    # 組合出預期的檔案路徑，例如 templates/reports/report_3413.html
    report_filename = f"reports/report_{stock_code}.html"
    report_path = os.path.join(app.root_path, 'templates', report_filename)
    
    # 如果檔案存在，就渲染該報告；如果不存在，回傳 404 錯誤
    if os.path.exists(report_path):
        return render_template(report_filename)
    else:
        abort(404, description="目前尚未建立該檔股票的深度分析報告。")

@app.route("/", methods=["GET", "POST"])
def index():
    """首頁與股票查詢。"""

    result = None
    chart_data = None
    error = None
    notice = None
    stock_code = ""
    has_report = False # 預設為沒有報告

    if request.method == "POST":
        stock_code = (
            request.form
            .get("stock_code", "")
            .strip()
            .upper()
        )

        if not stock_code:
            error = "請輸入股票代碼。"

        elif not stock_code.isalnum():
            error = "股票代碼只能包含英文或數字。"

        elif len(stock_code) < 4 or len(stock_code) > 6:
            error = "股票代碼長度應為 4 至 6 個字元。"

        else:
            try:
                # 先查詢資料庫
                analysis = analyze_stock(stock_code)

                if analysis.get("success"):
                    result = analysis

                else:
                    # 找不到時，自動下載歷史資料
                    (
                        result,
                        notice,
                        import_error,
                    ) = auto_import_stock(stock_code)

                    if import_error:
                        error = import_error
                        
                if result is not None:
                    chart_data = get_chart_data(
                        stock_code,
                        days=60,
                    )

            except sqlite3.Error as exception:
                print(f"資料庫錯誤：{exception}")
                error = "讀取資料庫時發生錯誤。"

            except Exception as exception:
                print(f"分析錯誤：{exception}")
                error = "股票分析時發生錯誤。"
    # 新增：檢查該股票是否有實體的 HTML 報告檔案
    if stock_code:
        expected_report_path = os.path.join(
            app.root_path, 
            'templates', 
            'reports', 
            f'report_{stock_code}.html'
        )
        has_report = os.path.exists(expected_report_path)
    try:
        # 放在分析之後，剛匯入的股票才會立即出現在清單
        available_stocks = get_available_stocks()

    except sqlite3.Error as exception:
        print(f"取得股票清單失敗：{exception}")
        available_stocks = []

    return render_template(
        "index.html",
        result=result,
        chart_data=chart_data,
        error=error,
        notice=notice,
        stock_code=stock_code,
        available_stocks=available_stocks,
        has_report=has_report
    )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )