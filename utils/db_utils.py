import sqlite3
from datetime import datetime

class DataBase:
    def __init__(self, db_path='bitcoin_trades.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn_cursor = self.conn.cursor()

        # 유동성 스캔 테이블
        self.conn_cursor.execute("""
            CREATE TABLE IF NOT EXISTS liquidity_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ticker TEXT,
                score REAL,
                listing_days INTEGER,
                pump_ratio REAL,
                min_turnover REAL,
                max_daily_ret REAL
            )
        """)

        # 거래 로그 테이블 (범용 자산 구조)
        self.conn_cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ticker TEXT,
                decision TEXT,
                percentage INTEGER,
                reason TEXT,
                asset_balance REAL,
                krw_balance REAL,
                asset_avg_buy_price REAL,
                asset_krw_price REAL,
                equity_now REAL,
                profit REAL
            )
        """)

        self.conn.commit()
        self._ensure_columns()

    def get_db_connection(self, db_path=None):
        return sqlite3.connect(db_path or self.db_path)

    def _ensure_columns(self):
        self.conn_cursor.execute("PRAGMA table_info(trades)")
        cols = {row[1] for row in self.conn_cursor.fetchall()}

        for col, sql in {
            "ticker": "ALTER TABLE trades ADD COLUMN ticker TEXT",
            "asset_balance": "ALTER TABLE trades ADD COLUMN asset_balance REAL",
            "asset_avg_buy_price": "ALTER TABLE trades ADD COLUMN asset_avg_buy_price REAL",
            "asset_krw_price": "ALTER TABLE trades ADD COLUMN asset_krw_price REAL",
            "equity_now": "ALTER TABLE trades ADD COLUMN equity_now REAL",
            "profit": "ALTER TABLE trades ADD COLUMN profit REAL",
        }.items():
            if col not in cols:
                self.conn_cursor.execute(sql)

        self.conn.commit()

    def log_liquidity_scan(self, results, row_fn):
        ts = datetime.now().isoformat()
        rows = [row_fn(ts, t, s) for t, s in results]

        self.conn_cursor.executemany("""
            INSERT INTO liquidity_scans
            (timestamp, ticker, score, listing_days, pump_ratio, min_turnover, max_daily_ret)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)

        self.conn.commit()

    def log_trade(self, ticker, decision, percentage, reason,
                  asset_balance, krw_balance, asset_avg_buy_price, asset_krw_price,
                  equity_now=None, profit=None
                  ):
        timestamp = datetime.now().isoformat()

        self.conn_cursor.execute("""
            INSERT INTO trades
            (timestamp, ticker, decision, percentage, reason,
             asset_balance, krw_balance,
             asset_avg_buy_price, asset_krw_price,
             equity_now, profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, ticker, decision, percentage, reason,
            asset_balance, krw_balance,
            asset_avg_buy_price, asset_krw_price,
            equity_now, profit
        ))

        self.conn.commit()
