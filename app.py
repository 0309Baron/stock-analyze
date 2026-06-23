import os
import sqlite3
from threading import Lock
from typing import Any

from flask import Flask, abort, redirect, render_template, request, url_for

from analyzer import analyze_stock, get_chart_data, run_backtest
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


def get_available_stocks() -> list[dict[str, Any]]:
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

    available_stocks = []

    for row in rows:
        stock_code = row["stock_code"]

        report_path = os.path.join(
            app.root_path,
            "templates",
            "reports",
            f"report_{stock_code}.html",
        )

        has_report = os.path.exists(report_path)

        available_stocks.append(
            {
                "stock_code": stock_code,
                "stock_name": row["stock_name"],
                "has_report": has_report,
            }
        )

    return available_stocks


def get_watchlist() -> list[dict[str, str]]:
    """取得觀察清單。"""

    query = """
        SELECT
            stock_code,
            stock_name,
            created_at
        FROM watchlist
        ORDER BY created_at DESC
    """

    with get_connection() as connection:
        rows = connection.execute(query).fetchall()

    return [
        {
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def add_to_watchlist(
    stock_code: str,
    stock_name: str,
) -> None:
    """加入觀察清單。"""

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO watchlist (
                stock_code,
                stock_name
            )
            VALUES (?, ?)

            ON CONFLICT(stock_code)
            DO UPDATE SET
                stock_name = excluded.stock_name
            """,
            (
                stock_code,
                stock_name,
            ),
        )

        connection.commit()


def remove_from_watchlist(stock_code: str) -> None:
    """從觀察清單移除股票。"""

    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM watchlist
            WHERE stock_code = ?
            """,
            (stock_code,),
        )

        connection.commit()


def find_stock_information(
    stocks: list[dict],
    stock_code: str,
) -> dict | None:
    """從證交所最新股票清單中尋找股票。"""

    return next(
        (
            stock
            for stock in stocks
            if str(stock.get("Code", "")).strip() == stock_code
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

    with import_lock:
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


def analyze_or_import_stock(
    stock_code: str,
) -> tuple[dict | None, str | None, str | None]:
    """
    分析股票。
    若資料庫沒有資料，則自動下載後再分析。

    回傳：
    分析結果、成功訊息、錯誤訊息
    """

    result = analyze_stock(stock_code)

    if result.get("success"):
        return result, None, None

    result, notice, import_error = auto_import_stock(stock_code)

    if import_error:
        return None, None, import_error

    if result is None or not result.get("success"):
        return None, None, f"股票 {stock_code} 分析失敗。"

    return result, notice, None


def compare_stocks(
    stock_codes: list[str],
) -> tuple[list[dict], list[str], list[str]]:
    """
    比較多檔股票。

    回傳：
    比較結果、錯誤訊息、提示訊息
    """

    compare_results = []
    compare_errors = []
    compare_notices = []

    for stock_code in stock_codes:
        result, notice, error = analyze_or_import_stock(stock_code)

        if error:
            compare_errors.append(
                f"{stock_code}：{error}"
            )

        elif result is not None:
            compare_results.append(result)

            if notice:
                compare_notices.append(notice)

    compare_results = sorted(
        compare_results,
        key=lambda item: item.get("score", 0),
        reverse=True,
    )

    return compare_results, compare_errors, compare_notices


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


@app.route("/report/<stock_code>")
def view_report(stock_code):
    """讀取並顯示個別股票的深度分析報告。"""

    report_filename = f"reports/report_{stock_code}.html"

    report_path = os.path.join(
        app.root_path,
        "templates",
        report_filename,
    )

    if os.path.exists(report_path):
        return render_template(report_filename)

    abort(
        404,
        description="目前尚未建立該檔股票的深度分析報告。",
    )


@app.route("/watchlist/add", methods=["POST"])
def add_watchlist():
    """加入股票到觀察清單。"""

    stock_code = (
        request.form
        .get("watch_stock_code", "")
        .strip()
        .upper()
    )

    if not stock_code:
        return redirect(url_for("index"))

    try:
        result, _, error = analyze_or_import_stock(stock_code)

        if error:
            print(error)

        elif result is not None and result.get("success"):
            add_to_watchlist(
                stock_code=result["stock_code"],
                stock_name=result["stock_name"],
            )

    except Exception as exception:
        print(f"加入觀察清單失敗：{exception}")

    return redirect(url_for("index"))


@app.route("/watchlist/remove/<stock_code>", methods=["POST"])
def remove_watchlist(stock_code):
    """從觀察清單移除股票。"""

    try:
        remove_from_watchlist(stock_code)

    except sqlite3.Error as exception:
        print(f"移除觀察清單失敗：{exception}")

    return redirect(url_for("index"))


@app.route("/", methods=["GET", "POST"])
def index():
    """首頁、股票查詢與股票比較。"""

    result = None
    chart_data = None
    error = None
    notice = None
    stock_code = ""
    has_report = False
    backtest_result = None

    compare_results = []
    compare_errors = []
    compare_notices = []

    if request.method == "POST":
        action = request.form.get("action", "analyze")

        if action == "compare":
            raw_codes = (
                request.form
                .get("compare_codes", "")
                .strip()
                .upper()
            )

            stock_codes = (
                raw_codes
                .replace(",", " ")
                .replace("，", " ")
                .split()
            )

            # 去除重複，但保留原本順序
            stock_codes = list(dict.fromkeys(stock_codes))

            if len(stock_codes) < 2:
                compare_errors.append(
                    "請至少輸入兩檔股票代碼進行比較。"
                )

            elif len(stock_codes) > 5:
                compare_errors.append(
                    "一次最多比較 5 檔股票。"
                )

            else:
                valid_codes = []

                for code in stock_codes:
                    if not code.isalnum():
                        compare_errors.append(
                            f"{code}：股票代碼只能包含英文或數字。"
                        )

                    elif len(code) < 4 or len(code) > 6:
                        compare_errors.append(
                            f"{code}：股票代碼長度應為 4 至 6 個字元。"
                        )

                    else:
                        valid_codes.append(code)

                if valid_codes:
                    try:
                        (
                            compare_results,
                            new_errors,
                            compare_notices,
                        ) = compare_stocks(valid_codes)

                        compare_errors.extend(new_errors)

                    except sqlite3.Error as exception:
                        print(f"資料庫錯誤：{exception}")
                        compare_errors.append(
                            "比較股票時讀取資料庫發生錯誤。"
                        )

                    except Exception as exception:
                        print(f"比較錯誤：{exception}")
                        compare_errors.append(
                            "股票比較時發生錯誤。"
                        )

        else:
            stock_code = (
                request.form
                .get("stock_code", "")
                .strip()
                .upper()
            )

            user_buy_threshold = request.form.get(
                "buy_threshold",
                type=int,
                default=75,
            )

            user_stop_loss = request.form.get(
                "stop_loss",
                type=float,
                default=-5.0,
            )

            user_trailing_stop = request.form.get(
                "trailing_stop",
                type=float,
                default=-10.0,
            )

            if not stock_code:
                error = "請輸入股票代碼。"

            elif not stock_code.isalnum():
                error = "股票代碼只能包含英文或數字。"

            elif len(stock_code) < 4 or len(stock_code) > 6:
                error = "股票代碼長度應為 4 至 6 個字元。"

            else:
                try:
                    result, notice, import_error = analyze_or_import_stock(
                        stock_code
                    )

                    if import_error:
                        error = import_error

                    if result is not None and result.get("success"):
                        backtest_result = run_backtest(
                            stock_code,
                            buy_threshold=user_buy_threshold,
                            stop_loss_pct=user_stop_loss,
                            trailing_stop_pct=user_trailing_stop,
                        )

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

    if stock_code:
        expected_report_path = os.path.join(
            app.root_path,
            "templates",
            "reports",
            f"report_{stock_code}.html",
        )

        has_report = os.path.exists(expected_report_path)

    try:
        available_stocks = get_available_stocks()

    except sqlite3.Error as exception:
        print(f"取得股票清單失敗：{exception}")
        available_stocks = []

    try:
        watchlist = get_watchlist()

    except sqlite3.Error as exception:
        print(f"取得觀察清單失敗：{exception}")
        watchlist = []

    return render_template(
        "index.html",
        result=result,
        chart_data=chart_data,
        backtest_result=backtest_result,
        compare_results=compare_results,
        compare_errors=compare_errors,
        compare_notices=compare_notices,
        error=error,
        notice=notice,
        stock_code=stock_code,
        available_stocks=available_stocks,
        watchlist=watchlist,
        has_report=has_report,
    )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )