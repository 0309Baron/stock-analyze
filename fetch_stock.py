import json
import sys

import requests


API_URL = (
    "https://openapi.twse.com.tw/v1/"
    "exchangeReport/STOCK_DAY_ALL"
)


def fetch_all_stocks() -> list[dict]:
    """取得最新上市股票日成交資料。"""

    try:
        response = requests.get(
            API_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": "StockAnalysisProject/1.0",
            },
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            raise ValueError("API 回傳格式不是股票清單")

        return data

    except requests.Timeout as error:
        raise RuntimeError("API 連線逾時") from error

    except requests.RequestException as error:
        raise RuntimeError(f"API 連線失敗：{error}") from error

    except ValueError as error:
        raise RuntimeError(f"資料格式錯誤：{error}") from error


def find_stock(
    stocks: list[dict],
    stock_code: str,
) -> dict | None:
    """根據股票代號尋找股票。"""

    return next(
        (
            stock
            for stock in stocks
            if stock.get("Code") == stock_code
        ),
        None,
    )


def main() -> None:
    stock_code = "2330"

    try:
        stocks = fetch_all_stocks()

        print(f"成功取得 {len(stocks)} 筆上市股票資料")

        stock = find_stock(stocks, stock_code)

        if stock is None:
            print(f"找不到股票代號：{stock_code}")
            sys.exit(1)

        print(f"\n股票 {stock_code} 的原始資料：")

        print(
            json.dumps(
                stock,
                ensure_ascii=False,
                indent=4,
            )
        )

    except RuntimeError as error:
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()
