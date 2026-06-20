import argparse
import sqlite3
from typing import Any

import pandas as pd

from database import create_tables, get_connection


def get_stock_history(stock_code: str) -> pd.DataFrame:
    """從 SQLite 取得指定股票的所有歷史資料。"""

    query = """
        SELECT
            stock_code,
            stock_name,
            trade_date,
            open_price,
            high_price,
            low_price,
            close_price,
            trade_volume,
            change_price,
            transactions
        FROM stock_daily
        WHERE stock_code = ?
        ORDER BY trade_date ASC
    """

    with get_connection() as connection:
        dataframe = pd.read_sql_query(
            query,
            connection,
            params=(stock_code,),
        )

    return dataframe


def calculate_indicators(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """計算股票技術指標。"""

    if dataframe.empty:
        return dataframe

    dataframe = dataframe.copy()

    # 將日期轉成 pandas 日期格式
    dataframe["trade_date"] = pd.to_datetime(
        dataframe["trade_date"],
        errors="coerce",
    )

    numeric_columns = [
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "trade_volume",
        "change_price",
        "transactions",
    ]

    # 確保價格與成交量是數字
    for column in numeric_columns:
        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

    # 移除沒有日期或收盤價的資料
    dataframe = dataframe.dropna(
        subset=["trade_date", "close_price"]
    )

    dataframe = dataframe.sort_values("trade_date")
    dataframe = dataframe.reset_index(drop=True)

    # 每日報酬率，例如 0.02 轉為 2%
    dataframe["daily_return_pct"] = (
        dataframe["close_price"]
        .pct_change(fill_method=None)
        * 100
    )

    # 5 日移動平均線
    dataframe["ma5"] = (
        dataframe["close_price"]
        .rolling(window=5)
        .mean()
    )

    # 20 日移動平均線
    dataframe["ma20"] = (
        dataframe["close_price"]
        .rolling(window=20)
        .mean()
    )

    # 5 個交易日漲跌幅
    dataframe["momentum_5d_pct"] = (
        dataframe["close_price"]
        .pct_change(periods=5, fill_method=None)
        * 100
    )

    # 前 5 日平均成交量
    # shift(1) 代表不把今天的成交量算進平均
    dataframe["previous_volume_ma5"] = (
        dataframe["trade_volume"]
        .shift(1)
        .rolling(window=5)
        .mean()
    )

    # 當日量 ÷ 前 5 日平均量
    dataframe["volume_ratio"] = (
        dataframe["trade_volume"]
        / dataframe["previous_volume_ma5"]
    )

    # 近 20 日每日報酬率標準差
    dataframe["volatility_20d_pct"] = (
        dataframe["daily_return_pct"]
        .rolling(window=20)
        .std()
    )

    return dataframe


def safe_round(
    value: Any,
    digits: int = 2,
) -> float | None:
    """避免 NaN 被直接輸出。"""

    if value is None or pd.isna(value):
        return None

    return round(float(value), digits)


def calculate_score(latest: pd.Series) -> tuple[int, str, list[str]]:
    """依照技術面與量價關係產生簡單分數。"""

    score = 50
    reasons: list[str] = []

    close_price = latest["close_price"]
    ma5 = latest["ma5"]
    ma20 = latest["ma20"]
    daily_return = latest["daily_return_pct"]
    momentum_5d = latest["momentum_5d_pct"]
    volume_ratio = latest["volume_ratio"]

    # 收盤價與短期均線
    if pd.notna(ma5):
        if close_price > ma5:
            score += 10
            reasons.append("收盤價高於 MA5，短期價格相對強勢")
        else:
            score -= 10
            reasons.append("收盤價低於 MA5，短期價格相對弱勢")
    else:
        reasons.append("資料不足，尚無法計算 MA5")

    # 短期均線與中期均線
    if pd.notna(ma5) and pd.notna(ma20):
        if ma5 > ma20:
            score += 15
            reasons.append("MA5 高於 MA20，均線結構偏多")
        else:
            score -= 15
            reasons.append("MA5 低於 MA20，均線結構偏空")
    else:
        reasons.append("資料不足，尚無法比較 MA5 與 MA20")

    # 5 日動能
    if pd.notna(momentum_5d):
        if momentum_5d >= 3:
            score += 10
            reasons.append("近 5 個交易日漲幅超過 3%")
        elif momentum_5d > 0:
            score += 5
            reasons.append("近 5 個交易日股價上漲")
        elif momentum_5d <= -3:
            score -= 10
            reasons.append("近 5 個交易日跌幅超過 3%")
        else:
            score -= 5
            reasons.append("近 5 個交易日股價下跌")

    # 當日漲跌
    if pd.notna(daily_return):
        if daily_return >= 2:
            score += 5
            reasons.append("當日漲幅超過 2%")
        elif daily_return <= -2:
            score -= 5
            reasons.append("當日跌幅超過 2%")

    # 量價關係
    if pd.notna(volume_ratio):
        if volume_ratio >= 1.5:
            if pd.notna(daily_return) and daily_return > 0:
                score += 10
                reasons.append("上漲且成交量放大，呈現量價齊揚")
            elif pd.notna(daily_return) and daily_return < 0:
                score -= 10
                reasons.append("下跌且成交量放大，賣壓可能較強")
            else:
                reasons.append("成交量明顯放大，但價格變化不大")
        elif volume_ratio <= 0.7:
            reasons.append("成交量明顯萎縮")

    score = max(0, min(100, score))

    if score >= 75:
        trend = "偏多"
    elif score >= 60:
        trend = "中性偏多"
    elif score >= 40:
        trend = "中性"
    elif score >= 25:
        trend = "中性偏空"
    else:
        trend = "偏空"

    return score, trend, reasons

def chart_value(value: Any) -> float | int | None:
    """將 Pandas 數值轉成可傳給 JavaScript 的格式。"""

    if value is None or pd.isna(value):
        return None

    number = float(value)

    if number.is_integer():
        return int(number)

    return round(number, 2)


def get_chart_data(
    stock_code: str,
    days: int = 60,
) -> dict[str, list]:
    """
    取得圖表使用的歷史資料。

    包含：
    - 日期
    - 收盤價
    - MA5
    - MA20
    - 成交量
    """

    dataframe = get_stock_history(stock_code)

    if dataframe.empty:
        return {}

    dataframe = calculate_indicators(dataframe)

    if dataframe.empty:
        return {}

    # 只取最近指定交易日
    dataframe = dataframe.tail(days)

    labels = [
        trade_date.strftime("%m/%d")
        for trade_date in dataframe["trade_date"]
    ]

    close_prices = [
        chart_value(value)
        for value in dataframe["close_price"]
    ]

    ma5_values = [
        chart_value(value)
        for value in dataframe["ma5"]
    ]

    ma20_values = [
        chart_value(value)
        for value in dataframe["ma20"]
    ]

    volumes = [
        chart_value(value)
        for value in dataframe["trade_volume"]
    ]

    return {
        "labels": labels,
        "close_prices": close_prices,
        "ma5": ma5_values,
        "ma20": ma20_values,
        "volumes": volumes,
    }

def analyze_stock(stock_code: str) -> dict[str, Any]:
    """取得指定股票的最新分析結果。"""

    create_tables()

    dataframe = get_stock_history(stock_code)

    if dataframe.empty:
        return {
            "success": False,
            "message": f"資料庫中找不到股票 {stock_code}",
        }

    dataframe = calculate_indicators(dataframe)

    if dataframe.empty:
        return {
            "success": False,
            "message": "資料格式錯誤，沒有可分析的收盤價",
        }

    latest = dataframe.iloc[-1]

    score, trend, reasons = calculate_score(latest)

    return {
        "success": True,
        "stock_code": latest["stock_code"],
        "stock_name": latest["stock_name"],
        "trade_date": latest["trade_date"].strftime("%Y-%m-%d"),
        "data_count": len(dataframe),
        "open_price": safe_round(latest["open_price"]),
        "high_price": safe_round(latest["high_price"]),
        "low_price": safe_round(latest["low_price"]),
        "close_price": safe_round(latest["close_price"]),
        "trade_volume": (
            int(latest["trade_volume"])
            if pd.notna(latest["trade_volume"])
            else None
        ),
        "daily_return_pct": safe_round(
            latest["daily_return_pct"]
        ),
        "ma5": safe_round(latest["ma5"]),
        "ma20": safe_round(latest["ma20"]),
        "momentum_5d_pct": safe_round(
            latest["momentum_5d_pct"]
        ),
        "volume_ratio": safe_round(
            latest["volume_ratio"]
        ),
        "volatility_20d_pct": safe_round(
            latest["volatility_20d_pct"]
        ),
        "score": score,
        "trend": trend,
        "reasons": reasons,
    }


def print_result(result: dict[str, Any]) -> None:
    """將分析結果顯示在終端機。"""

    if not result["success"]:
        print(result["message"])
        return

    print()
    print("=" * 50)
    print(
        f"{result['stock_name']} "
        f"({result['stock_code']})"
    )
    print("=" * 50)

    print(f"分析日期：{result['trade_date']}")
    print(f"歷史資料筆數：{result['data_count']}")
    print()

    print("【當日行情】")
    print(f"開盤價：{result['open_price']}")
    print(f"最高價：{result['high_price']}")
    print(f"最低價：{result['low_price']}")
    print(f"收盤價：{result['close_price']}")
    print(f"成交量：{result['trade_volume']:,}")

    if result["daily_return_pct"] is not None:
        print(
            f"每日報酬率："
            f"{result['daily_return_pct']:.2f}%"
        )

    print()
    print("【技術指標】")
    print(f"MA5：{result['ma5']}")
    print(f"MA20：{result['ma20']}")
    print(
        f"近 5 日漲跌幅："
        f"{result['momentum_5d_pct']}%"
    )
    print(
        f"成交量倍率："
        f"{result['volume_ratio']} 倍"
    )
    print(
        f"20 日波動度："
        f"{result['volatility_20d_pct']}%"
    )

    print()
    print("【分析結果】")
    print(f"分數：{result['score']} / 100")
    print(f"趨勢：{result['trend']}")

    print()
    print("【判斷原因】")

    for reason in result["reasons"]:
        print(f"- {reason}")

    print()
    print("此結果為規則式數據分析，不構成投資建議。")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="分析台股歷史資料"
    )

    parser.add_argument(
        "stock_code",
        help="股票代碼，例如 2330",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    try:
        result = analyze_stock(args.stock_code)
        print_result(result)

    except sqlite3.Error as error:
        print(f"資料庫錯誤：{error}")

    except Exception as error:
        print(f"分析失敗：{error}")


if __name__ == "__main__":
    main()
