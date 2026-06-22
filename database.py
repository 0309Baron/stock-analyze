import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "stock.db"


def get_connection() -> sqlite3.Connection:
    """建立 SQLite 連線。"""
    DATA_DIR.mkdir(exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def create_tables() -> None:
    """建立資料表。"""
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_daily (
                stock_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,

                trade_volume INTEGER,
                trade_value INTEGER,

                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,

                change_price REAL,
                transactions INTEGER,

                PRIMARY KEY (stock_code, trade_date)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                stock_code TEXT PRIMARY KEY,
                stock_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        connection.commit()


if __name__ == "__main__":
    create_tables()

    print("資料庫建立完成")
    print(f"位置：{DATABASE_PATH}")