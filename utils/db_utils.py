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
                coin_name TEXT,
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
                coin_name TEXT,
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
            "coin_name": "ALTER TABLE trades ADD COLUMN coin_name TEXT",
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
            (timestamp, coin_name, score, listing_days, pump_ratio, min_turnover, max_daily_ret)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)

        self.conn.commit()

    def get_liq_cand(self, limit=20):
        sql = """
        SELECT coin_name
        FROM liquidity_scans
        WHERE timestamp = (SELECT MAX(timestamp) FROM liquidity_scans)
        ORDER BY score DESC
        LIMIT ?
        """
        rows = self.conn_cursor.execute(sql, (limit,)).fetchall()
        return [r[0] for r in rows] if rows else []


    def log_trade(self, decision, percentage, reason,
                coin_name, asset_balance, krw_balance,
                asset_avg_buy_price, asset_krw_price,
                equity_now=None, profit=None):
        timestamp = datetime.now().isoformat()

        self.conn_cursor.execute("""
            INSERT INTO trades
            (timestamp, coin_name, decision, percentage, reason,
            asset_balance, krw_balance,
            asset_avg_buy_price, asset_krw_price,
            equity_now, profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            coin_name,
            decision,
            int(percentage),
            reason,
            float(asset_balance),
            float(krw_balance),
            float(asset_avg_buy_price),
            float(asset_krw_price),
            float(equity_now) if equity_now is not None else None,
            float(profit) if profit is not None else None
        ))

        self.conn.commit()


