import sqlite3
from typing import Any

from flask import Flask, render_template, request

from analyzer import analyze_stock
from database import create_tables, get_connection


app = Flask(__name__)

# 啟動網站時確認資料表存在
create_tables()


def get_available_stocks() -> list[dict[str, str]]:
    """取得資料庫中目前可以分析的股票。"""

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


@app.template_filter("number")
def format_number(value: Any) -> str:
    """
    將數字加上千分位。

    例如：
    1234567 -> 1,234,567
    """

    if value is None:
        return "--"

    try:
        number = float(value)

        if number.is_integer():
            return f"{int(number):,}"

        return f"{number:,.2f}"

    except (TypeError, ValueError):
        return str(value)


@app.route("/", methods=["GET", "POST"])
def index():
    """首頁與股票查詢。"""

    result = None
    error = None
    stock_code = ""

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
                analysis = analyze_stock(stock_code)

                if analysis.get("success"):
                    result = analysis
                else:
                    error = analysis.get(
                        "message",
                        "找不到股票資料。",
                    )

            except sqlite3.Error as exception:
                print(f"資料庫錯誤：{exception}")
                error = "讀取資料庫時發生錯誤。"

            except Exception as exception:
                print(f"分析錯誤：{exception}")
                error = "股票分析時發生錯誤。"

    try:
        available_stocks = get_available_stocks()
    except sqlite3.Error:
        available_stocks = []

    return render_template(
        "index.html",
        result=result,
        error=error,
        stock_code=stock_code,
        available_stocks=available_stocks,
    )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )