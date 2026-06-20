import argparse
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

from database import create_tables, get_connection


API_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"


def clean_number(
    value: Any,
    number_type: type = float,
) -> int | float | None:
    """清除千分位逗號、正號與無資料符號。"""

    if value is None:
        return None

    text = str(value).strip()
    text = text.replace(",", "")
    text = text.replace("+", "")

    if text in {"", "--", "---", "X"}:
        return None

    try:
        return number_type(text)
    except ValueError:
        return None


def convert_roc_date(roc_date: str) -> str:
    """
    將民國日期轉成西元日期。

    例如：
    115/06/19 -> 2026-06-19
    """

    parts = roc_date.strip().split("/")

    if len(parts) != 3:
        raise ValueError(f"無法解析日期：{roc_date}")

    roc_year, month, day = map(int, parts)
    western_year = roc_year + 1911

    return f"{western_year:04d}-{month:02d}-{day:02d}"


def get_previous_months(month_count: int) -> list[str]:
    """
    產生最近幾個月份，格式為 YYYYMM01。

    例如：
    20260601
    20260501
    20260401
    """

    today = date.today()
    result = []

    year = today.year
    month = today.month

    for _ in range(month_count):
        result.append(f"{year:04d}{month:02d}01")

        month -= 1

        if month == 0:
            month = 12
            year -= 1

    return result


def fetch_month_data(
    stock_code: str,
    query_month: str,
) -> list[list[str]]:
    """取得指定股票某個月份的每日成交資料。"""

    response = requests.get(
        API_URL,
        params={
            "response": "json",
            "date": query_month,
            "stockNo": stock_code,
        },
        headers={
            "User-Agent": "StockAnalysisProject/1.0",
            "Accept": "application/json",
        },
        timeout=30,
    )

    response.raise_for_status()

    result = response.json()

    if result.get("stat") != "OK":
        print(
            f"{query_month[:6]} 沒有資料："
            f"{result.get('stat', '未知錯誤')}"
        )
        return []

    rows = result.get("data", [])

    if not isinstance(rows, list):
        raise ValueError("API data 欄位格式不正確")

    return rows


def save_rows(
    stock_code: str,
    stock_name: str,
    rows: list[list[str]],
) -> int:
    """將每日成交資料存入 SQLite。"""

    saved_count = 0

    with get_connection() as connection:
        for row in rows:
            if len(row) < 9:
                print(f"略過格式不完整資料：{row}")
                continue

            trade_date = convert_roc_date(row[0])

            connection.execute(
                """
                INSERT INTO stock_daily (
                    stock_code,
                    stock_name,
                    trade_date,
                    trade_volume,
                    trade_value,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    change_price,
                    transactions
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(stock_code, trade_date)
                DO UPDATE SET
                    stock_name = excluded.stock_name,
                    trade_volume = excluded.trade_volume,
                    trade_value = excluded.trade_value,
                    open_price = excluded.open_price,
                    high_price = excluded.high_price,
                    low_price = excluded.low_price,
                    close_price = excluded.close_price,
                    change_price = excluded.change_price,
                    transactions = excluded.transactions
                """,
                (
                    stock_code,
                    stock_name,
                    trade_date,
                    clean_number(row[1], int),
                    clean_number(row[2], int),
                    clean_number(row[3]),
                    clean_number(row[4]),
                    clean_number(row[5]),
                    clean_number(row[6]),
                    clean_number(row[7]),
                    clean_number(row[8], int),
                ),
            )

            saved_count += 1

        connection.commit()

    return saved_count


def import_history(
    stock_code: str,
    stock_name: str,
    month_count: int,
) -> None:
    """下載並儲存最近數個月的歷史資料。"""

    create_tables()

    total_count = 0
    months = get_previous_months(month_count)

    for query_month in months:
        print(f"正在下載 {query_month[:6]} 的資料……")

        try:
            rows = fetch_month_data(
                stock_code,
                query_month,
            )

            saved_count = save_rows(
                stock_code,
                stock_name,
                rows,
            )

            total_count += saved_count

            print(f"已處理 {saved_count} 筆")

        except requests.RequestException as error:
            print(f"API 請求失敗：{error}")

        except (ValueError, sqlite3.Error) as error:
            print(f"資料處理失敗：{error}")

        # 避免短時間內發出太多請求
        time.sleep(1)

    print()
    print("歷史資料匯入完成")
    print(f"股票：{stock_name}（{stock_code}）")
    print(f"總處理筆數：{total_count}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下載台股歷史成交資料"
    )

    parser.add_argument(
        "stock_code",
        help="股票代碼，例如 2330",
    )

    parser.add_argument(
        "stock_name",
        help="股票名稱，例如 台積電",
    )

    parser.add_argument(
        "--months",
        type=int,
        default=6,
        help="下載最近幾個月，預設為 6",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    if args.months <= 0:
        raise ValueError("--months 必須大於 0")

    import_history(
        stock_code=args.stock_code,
        stock_name=args.stock_name,
        month_count=args.months,
    )


if __name__ == "__main__":
    main()
