import sqlite3
import threading
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

from models.market_data import FuturesData, FuturesMarginData, MetalArbitrageData
from models.signals import Signal

class DBManager:
    """提供线程安全的 SQLite WAL 连接与持久化"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path="data/monitor_history.db"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DBManager, cls).__new__(cls)
                cls._instance._write_lock = threading.Lock()
                cls._instance._init_db(db_path)
        return cls._instance

    def _init_db(self, db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        with self.get_connection() as conn:
            # 开启并发安全最重要的预写重做日志 (WAL)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS alert_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    notified INTEGER DEFAULT 0
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cooldown_state (
                    strategy_key TEXT PRIMARY KEY,
                    last_alert TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS futures_margin_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_code TEXT NOT NULL,
                    margin_ratio REAL NOT NULL,
                    source TEXT NOT NULL,
                    source_url TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    fetched_at TEXT NOT NULL
                )
            ''')
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS futures_live_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    product_code TEXT NOT NULL,
                    price REAL NOT NULL,
                    spot_price REAL NOT NULL,
                    discount_rate REAL NOT NULL,
                    contract_multiplier INTEGER NOT NULL,
                    margin_ratio REAL NOT NULL,
                    notional_per_lot REAL NOT NULL,
                    margin_required_per_lot REAL NOT NULL,
                    days_to_maturity INTEGER NOT NULL,
                    fetched_at TEXT NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS metal_arbitrage_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    metal_symbol TEXT NOT NULL,
                    metal_name TEXT NOT NULL,
                    benchmark_symbol TEXT NOT NULL,
                    benchmark_name TEXT NOT NULL,
                    benchmark_display_name TEXT NOT NULL,
                    domestic_symbol TEXT NOT NULL,
                    domestic_name TEXT NOT NULL,
                    domestic_unit TEXT NOT NULL,
                    category TEXT NOT NULL,
                    dom_price REAL NOT NULL,
                    for_price_usd REAL NOT NULL,
                    for_price_cny REAL NOT NULL,
                    exchange_rate REAL NOT NULL,
                    implied_rate REAL NOT NULL,
                    spread REAL NOT NULL,
                    spread_pct REAL NOT NULL,
                    dom_time TEXT DEFAULT '',
                    for_time TEXT DEFAULT '',
                    for_date TEXT DEFAULT '',
                    used_api_cny_quote INTEGER DEFAULT 0,
                    fetched_at TEXT NOT NULL
                )
                '''
            )
            conn.commit()

    @contextmanager
    def get_connection(self):
        # 允许线程池中跨线程共享连接请求操作
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        try:
            yield conn
        finally:
            conn.close()

    def save_signal(self, signal: Signal) -> int:
        """保存信号并返回记录 ID。"""
        with self._write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO alert_history (timestamp, asset, strategy, level, message, notified)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.timestamp.isoformat(),
                        signal.asset,
                        signal.strategy_name,
                        signal.level,
                        signal.message,
                        0,
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)

    def mark_alert_notified(self, alert_id: int) -> None:
        """将指定报警记录标记为通知已送达至少一个渠道。"""
        with self._write_lock:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE alert_history SET notified = 1 WHERE id = ?",
                    (alert_id,),
                )
                conn.commit()

    def save_futures_margin_snapshots(self, snapshots: Iterable[FuturesMarginData]):
        rows = [
            (
                snapshot.symbol,
                snapshot.margin_ratio,
                snapshot.source,
                snapshot.source_url,
                snapshot.notes,
                snapshot.timestamp.isoformat(),
            )
            for snapshot in snapshots
        ]
        if not rows:
            return

        with self._write_lock:
            with self.get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO futures_margin_snapshot
                    (product_code, margin_ratio, source, source_url, notes, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()

    def save_futures_live_snapshots(self, snapshots: Iterable[FuturesData]) -> None:
        rows = [
            (
                snapshot.symbol,
                snapshot.product_code,
                snapshot.price,
                snapshot.spot_price,
                snapshot.discount_rate,
                snapshot.contract_multiplier,
                snapshot.margin_ratio,
                snapshot.notional_per_lot,
                snapshot.margin_required_per_lot,
                snapshot.days_to_maturity,
                snapshot.timestamp.isoformat(),
            )
            for snapshot in snapshots
        ]
        if not rows:
            return

        with self._write_lock:
            with self.get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO futures_live_snapshot
                    (symbol, product_code, price, spot_price, discount_rate, contract_multiplier,
                     margin_ratio, notional_per_lot, margin_required_per_lot, days_to_maturity, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()

    def save_metal_snapshots(self, snapshots: Iterable[MetalArbitrageData]) -> None:
        rows = [
            (
                snapshot.symbol,
                snapshot.metal_symbol,
                snapshot.metal_name,
                snapshot.benchmark_symbol,
                snapshot.benchmark_name,
                snapshot.benchmark_display_name,
                snapshot.domestic_symbol,
                snapshot.domestic_name,
                snapshot.domestic_unit,
                snapshot.category,
                snapshot.dom_price,
                snapshot.for_price_usd,
                snapshot.for_price_cny,
                snapshot.exchange_rate,
                snapshot.implied_rate,
                snapshot.spread,
                snapshot.spread_pct,
                snapshot.dom_time,
                snapshot.for_time,
                snapshot.for_date,
                1 if snapshot.used_api_cny_quote else 0,
                snapshot.timestamp.isoformat(),
            )
            for snapshot in snapshots
        ]
        if not rows:
            return

        with self._write_lock:
            with self.get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO metal_arbitrage_snapshot
                    (symbol, metal_symbol, metal_name, benchmark_symbol, benchmark_name, benchmark_display_name,
                     domestic_symbol, domestic_name, domestic_unit, category, dom_price, for_price_usd,
                     for_price_cny, exchange_rate, implied_rate, spread, spread_pct, dom_time, for_time,
                     for_date, used_api_cny_quote, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()

    def save_cooldown_state(self, strategy_key: str, last_alert_iso: str) -> None:
        """持久化冷却期状态。"""
        with self._write_lock:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cooldown_state (strategy_key, last_alert) VALUES (?, ?)",
                    (strategy_key, last_alert_iso),
                )
                conn.commit()

    def purge_alert_history_older_than(self, retention_days: int) -> int:
        """清理超过保留期的报警历史。"""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM alert_history WHERE timestamp < ?",
                    (cutoff,),
                )
                conn.commit()
                return int(cursor.rowcount or 0)

    def purge_futures_margin_snapshots_older_than(self, retention_days: int) -> int:
        """清理超过保留期的保证金快照。"""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM futures_margin_snapshot WHERE fetched_at < ?",
                    (cutoff,),
                )
                conn.commit()
                return int(cursor.rowcount or 0)

    def purge_futures_live_snapshots_older_than(self, retention_days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM futures_live_snapshot WHERE fetched_at < ?",
                    (cutoff,),
                )
                conn.commit()
                return int(cursor.rowcount or 0)

    def purge_metal_snapshots_older_than(self, retention_days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM metal_arbitrage_snapshot WHERE fetched_at < ?",
                    (cutoff,),
                )
                conn.commit()
                return int(cursor.rowcount or 0)

    def get_latest_futures_margin(self, product_code: str) -> Optional[FuturesMarginData]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT product_code, margin_ratio, source, source_url, notes, fetched_at
                FROM futures_margin_snapshot
                WHERE product_code = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (product_code,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return FuturesMarginData(
            symbol=row[0],
            margin_ratio=float(row[1]),
            source=row[2],
            source_url=row[3] or "",
            notes=row[4] or "",
            timestamp=datetime.fromisoformat(row[5]),
        )

    def get_latest_futures_margins(self) -> Dict[str, FuturesMarginData]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT s.product_code, s.margin_ratio, s.source, s.source_url, s.notes, s.fetched_at
                FROM futures_margin_snapshot s
                INNER JOIN (
                    SELECT product_code, MAX(fetched_at) AS max_fetched_at
                    FROM futures_margin_snapshot
                    GROUP BY product_code
                ) latest
                ON s.product_code = latest.product_code
                AND s.fetched_at = latest.max_fetched_at
                ORDER BY s.id DESC
                """
            )
            rows = cursor.fetchall()

        results: Dict[str, FuturesMarginData] = {}
        for row in rows:
            product_code = row[0]
            if product_code in results:
                continue
            results[product_code] = FuturesMarginData(
                symbol=product_code,
                margin_ratio=float(row[1]),
                source=row[2],
                source_url=row[3] or "",
                notes=row[4] or "",
                timestamp=datetime.fromisoformat(row[5]),
            )

        return results

    def get_recent_futures_live_snapshots(self, limit: int = 200):
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT symbol, product_code, price, spot_price, discount_rate, contract_multiplier,
                       margin_ratio, notional_per_lot, margin_required_per_lot, days_to_maturity, fetched_at
                FROM futures_live_snapshot
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cursor.fetchall()

    def get_recent_metal_snapshots(self, limit: int = 200):
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT metal_symbol, metal_name, benchmark_display_name, dom_price, for_price_cny,
                       for_price_usd, exchange_rate, implied_rate, spread, spread_pct, category, fetched_at
                FROM metal_arbitrage_snapshot
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cursor.fetchall()
