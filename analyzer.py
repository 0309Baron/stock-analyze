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

    close_price = latest.get("close_price")
    open_price = latest.get("open_price")
    low_price = latest.get("low_price")
    ma5 = latest.get("ma5")
    ma20 = latest.get("ma20")
    volume_ratio = latest.get("volume_ratio")
    volatility = latest.get("volatility_20d_pct")
    momentum_5d = latest.get("momentum_5d_pct")
    daily_return = latest.get("daily_return_pct")

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
        if momentum_5d >= 15:
            score += 10
            reasons.append("近 5 個交易日漲幅超過 15%")
        elif momentum_5d > 0:
            score += 5
            reasons.append("近 5 個交易日股價上漲")
        elif momentum_5d <= -15:
            score -= 10
            reasons.append("近 5 個交易日跌幅超過 15%")
        else:
            score -= 5
            reasons.append("近 5 個交易日股價下跌")

    # 當日漲跌
    if pd.notna(daily_return):
        if daily_return >= 5:
            score += 5
            reasons.append("當日漲幅超過 5%")
        elif daily_return <= -5:
            score -= 5
            reasons.append("當日跌幅超過 5%")

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

def run_backtest(
    stock_code: str, 
    buy_threshold: int = 75, 
    stop_loss_pct: float = -5.0,     
    trailing_stop_pct: float = -10.0  
) -> dict[str, Any]:
    """執行歷史回測，採用獨立的技術與風控出場邏輯。"""
    
    dataframe = get_stock_history(stock_code)
    if dataframe.empty:
        return {"success": False}
        
    dataframe = calculate_indicators(dataframe)
    if len(dataframe) < 30:
        return {"success": False}

    trades = []
    friction_cost = 0.004 # 交易手續費與稅金

    # 狀態記錄變數
    in_position = False
    buy_date = None
    buy_price = 0.0
    highest_price = 0.0  # 紀錄持有期間的最高價

    for i in range(20, len(dataframe) - 1):
        current_day = dataframe.iloc[i]
        score, _, _ = calculate_score(current_day)

        if not in_position:
            # 【進場邏輯】分數大於等於買進標準
            if score >= buy_threshold:
                buy_day = dataframe.iloc[i + 1]
                buy_price = buy_day["open_price"]
                buy_date = buy_day["trade_date"].strftime("%Y-%m-%d")
                highest_price = buy_price # 初始化最高價
                in_position = True
        
        else:
            # 更新持有期間的最高價
            if current_day["high_price"] > highest_price:
                highest_price = current_day["high_price"]

            # 計算當前帳面損益 與 從高點回落的幅度
            current_profit_pct = (current_day["close_price"] - buy_price) / buy_price * 100
            drawdown_from_high = (current_day["close_price"] - highest_price) / highest_price * 100
            
            ma20 = current_day["ma20"]
            
            # 【出場邏輯】滿足以下任一條件即出場
            # 1. 跌破月線 (技術防線)
            # 2. 從最高點回落超過設定幅度 (動能衰退)
            # 3. 帳面直接虧損超過停損標準 (保護本金)
            
            exit_signal = False
            exit_reason = ""

            if pd.notna(ma20) and current_day["close_price"] < ma20:
                exit_signal = True
                exit_reason = "跌破月線"
            elif drawdown_from_high <= trailing_stop_pct:
                exit_signal = True
                exit_reason = f"高點回落 {trailing_stop_pct}%"
            elif current_profit_pct <= stop_loss_pct:
                exit_signal = True
                exit_reason = f"觸及 {stop_loss_pct}% 停損"

            if exit_signal:
                sell_day = dataframe.iloc[i + 1]
                sell_price = sell_day["open_price"]
                sell_date = sell_day["trade_date"].strftime("%Y-%m-%d")

                raw_profit_pct = (sell_price - buy_price) / buy_price
                net_profit_pct = (raw_profit_pct - friction_cost) * 100

                trades.append({
                    "buy_date": buy_date,
                    "sell_date": sell_date,
                    "buy_price": safe_round(buy_price),
                    "sell_price": safe_round(sell_price),
                    "profit_pct": safe_round(net_profit_pct),
                    "reason": exit_reason
                })
                
                in_position = False

    total_trades = len(trades)
    if total_trades == 0:
        return {"success": True, "total_trades": 0}

    winning_trades = [t for t in trades if t["profit_pct"] > 0]
    win_rate = (len(winning_trades) / total_trades) * 100
    avg_profit = sum(t["profit_pct"] for t in trades) / total_trades

    return {
        "success": True,
        "total_trades": total_trades,
        "win_rate": safe_round(win_rate),
        "avg_profit": safe_round(avg_profit),
        "buy_threshold": buy_threshold,
        "stop_loss_pct": stop_loss_pct,         
        "trailing_stop_pct": trailing_stop_pct,
        "recent_trades": trades[-3:]
    }

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
