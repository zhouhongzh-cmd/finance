import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

from models.market_data import (
    FuturesData,
    FuturesMarginData,
    MetalArbitrageData,
    PremiumArbitrageData,
)
from models.signals import Signal

class DBManager:
    """提供线程安全的 SQLite WAL 连接与持久化"""
    _instance = None
    _lock = threading.Lock()
    SNAPSHOT_HEARTBEAT_MINUTES = 15
    
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
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS premium_arbitrage_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    asset_group TEXT NOT NULL,
                    spot_symbol TEXT NOT NULL,
                    spot_name TEXT NOT NULL,
                    spot_price REAL NOT NULL,
                    future_symbol TEXT NOT NULL,
                    future_name TEXT NOT NULL,
                    future_price REAL NOT NULL,
                    premium REAL NOT NULL,
                    premium_rate REAL NOT NULL,
                    state TEXT NOT NULL,
                    days_to_maturity INTEGER,
                    source_spot TEXT DEFAULT '',
                    source_future TEXT DEFAULT '',
                    fetched_at TEXT NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS source_health_status (
                    source_name TEXT PRIMARY KEY,
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT DEFAULT '',
                    recent_successes INTEGER NOT NULL DEFAULT 0,
                    recent_total INTEGER NOT NULL DEFAULT 0,
                    success_rate REAL NOT NULL DEFAULT 0,
                    avg_duration_ms REAL NOT NULL DEFAULT 0,
                    p95_duration_ms REAL NOT NULL DEFAULT 0,
                    active_source TEXT DEFAULT '',
                    is_fallback INTEGER NOT NULL DEFAULT 0,
                    recent_outcomes_json TEXT NOT NULL DEFAULT '[]',
                    recent_durations_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS config_change_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    changed_at TEXT NOT NULL,
                    config_key TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    source TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    immediate_effect INTEGER NOT NULL DEFAULT 1
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS job_run_status (
                    job_name TEXT PRIMARY KEY,
                    current_running INTEGER NOT NULL DEFAULT 0,
                    last_started_at TEXT,
                    last_finished_at TEXT,
                    last_duration_ms REAL NOT NULL DEFAULT 0,
                    last_status TEXT DEFAULT '',
                    last_error TEXT DEFAULT '',
                    total_skipped INTEGER NOT NULL DEFAULT 0,
                    consecutive_skipped INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                '''
            )
            conn.commit()
            self._ensure_column(conn, "premium_arbitrage_snapshot", "days_to_maturity", "INTEGER")

    def _ensure_column(self, conn, table: str, column: str, definition: str) -> None:
        columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            conn.commit()

    @contextmanager
    def get_connection(self):
        # 允许线程池中跨线程共享连接请求操作
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        try:
            yield conn
        finally:
            conn.close()

    def _same_minute(self, left: datetime, right: datetime) -> bool:
        return left.replace(second=0, microsecond=0) == right.replace(second=0, microsecond=0)

    def _heartbeat_due(self, current: datetime, previous: datetime) -> bool:
        return (current - previous) >= timedelta(minutes=self.SNAPSHOT_HEARTBEAT_MINUTES)

    def _build_futures_snapshot_state(self, snapshot: FuturesData) -> dict:
        return {
            "fetched_at": snapshot.timestamp,
            "price": float(snapshot.price),
            "spot_price": float(snapshot.spot_price),
            "discount_rate": float(snapshot.discount_rate),
            "margin_ratio": float(snapshot.margin_ratio),
            "days_to_maturity": int(snapshot.days_to_maturity),
        }

    def _build_metal_snapshot_state(self, snapshot: MetalArbitrageData) -> dict:
        return {
            "fetched_at": snapshot.timestamp,
            "dom_price": float(snapshot.dom_price),
            "for_price_cny": float(snapshot.for_price_cny),
            "spread": float(snapshot.spread),
            "spread_pct": float(snapshot.spread_pct),
            "exchange_rate": float(snapshot.exchange_rate),
        }

    def _build_premium_snapshot_state(self, snapshot: PremiumArbitrageData) -> dict:
        return {
            "fetched_at": snapshot.timestamp,
            "spot_price": float(snapshot.spot_price),
            "future_price": float(snapshot.future_price),
            "premium": float(snapshot.premium),
            "premium_rate": float(snapshot.premium_rate),
            "state": snapshot.state,
            "days_to_maturity": snapshot.days_to_maturity,
        }

    def _get_latest_futures_snapshot_rows(self, conn, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        placeholders = ",".join(["?"] * len(symbols))
        rows = conn.execute(
            f"""
            SELECT f.id, f.symbol, f.price, f.spot_price, f.discount_rate, f.margin_ratio,
                   f.days_to_maturity, f.fetched_at
            FROM futures_live_snapshot f
            INNER JOIN (
                SELECT symbol, MAX(id) AS max_id
                FROM futures_live_snapshot
                WHERE symbol IN ({placeholders})
                GROUP BY symbol
            ) latest
            ON f.id = latest.max_id
            """,
            tuple(symbols),
        ).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            result[row[1]] = {
                "id": int(row[0]),
                "price": float(row[2]),
                "spot_price": float(row[3]),
                "discount_rate": float(row[4]),
                "margin_ratio": float(row[5]),
                "days_to_maturity": int(row[6]),
                "fetched_at": datetime.fromisoformat(row[7]),
            }
        return result

    def _get_latest_metal_snapshot_rows(self, conn, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        placeholders = ",".join(["?"] * len(symbols))
        rows = conn.execute(
            f"""
            SELECT m.id, m.symbol, m.dom_price, m.for_price_cny, m.spread, m.spread_pct,
                   m.exchange_rate, m.fetched_at
            FROM metal_arbitrage_snapshot m
            INNER JOIN (
                SELECT symbol, MAX(id) AS max_id
                FROM metal_arbitrage_snapshot
                WHERE symbol IN ({placeholders})
                GROUP BY symbol
            ) latest
            ON m.id = latest.max_id
            """,
            tuple(symbols),
        ).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            result[row[1]] = {
                "id": int(row[0]),
                "dom_price": float(row[2]),
                "for_price_cny": float(row[3]),
                "spread": float(row[4]),
                "spread_pct": float(row[5]),
                "exchange_rate": float(row[6]),
                "fetched_at": datetime.fromisoformat(row[7]),
            }
        return result

    def _get_latest_premium_snapshot_rows(self, conn, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        placeholders = ",".join(["?"] * len(symbols))
        rows = conn.execute(
            f"""
            SELECT p.id, p.symbol, p.spot_price, p.future_price, p.premium, p.premium_rate,
                   p.state, p.days_to_maturity, p.fetched_at
            FROM premium_arbitrage_snapshot p
            INNER JOIN (
                SELECT symbol, MAX(id) AS max_id
                FROM premium_arbitrage_snapshot
                WHERE symbol IN ({placeholders})
                GROUP BY symbol
            ) latest
            ON p.id = latest.max_id
            """,
            tuple(symbols),
        ).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            result[row[1]] = {
                "id": int(row[0]),
                "spot_price": float(row[2]),
                "future_price": float(row[3]),
                "premium": float(row[4]),
                "premium_rate": float(row[5]),
                "state": str(row[6]),
                "days_to_maturity": int(row[7]) if row[7] is not None else None,
                "fetched_at": datetime.fromisoformat(row[8]),
            }
        return result

    def _classify_futures_snapshot_write(self, snapshot: FuturesData, latest: Optional[dict]) -> str:
        if latest is None:
            return "insert"
        current_ts = snapshot.timestamp
        latest_ts = latest["fetched_at"]
        changed = any(
            (
                float(snapshot.price) != latest["price"],
                float(snapshot.spot_price) != latest["spot_price"],
                float(snapshot.discount_rate) != latest["discount_rate"],
                float(snapshot.margin_ratio) != latest["margin_ratio"],
                int(snapshot.days_to_maturity) != latest["days_to_maturity"],
            )
        )
        if self._same_minute(current_ts, latest_ts):
            return "update" if changed else "skip"
        if changed or self._heartbeat_due(current_ts, latest_ts):
            return "insert"
        return "skip"

    def _classify_metal_snapshot_write(self, snapshot: MetalArbitrageData, latest: Optional[dict]) -> str:
        if latest is None:
            return "insert"
        current_ts = snapshot.timestamp
        latest_ts = latest["fetched_at"]
        changed = any(
            (
                float(snapshot.dom_price) != latest["dom_price"],
                float(snapshot.for_price_cny) != latest["for_price_cny"],
                float(snapshot.spread) != latest["spread"],
                float(snapshot.spread_pct) != latest["spread_pct"],
                float(snapshot.exchange_rate) != latest["exchange_rate"],
            )
        )
        if self._same_minute(current_ts, latest_ts):
            return "update" if changed else "skip"
        if changed or self._heartbeat_due(current_ts, latest_ts):
            return "insert"
        return "skip"

    def _classify_premium_snapshot_write(self, snapshot: PremiumArbitrageData, latest: Optional[dict]) -> str:
        if latest is None:
            return "insert"
        current_ts = snapshot.timestamp
        latest_ts = latest["fetched_at"]
        changed = any(
            (
                float(snapshot.spot_price) != latest["spot_price"],
                float(snapshot.future_price) != latest["future_price"],
                float(snapshot.premium) != latest["premium"],
                float(snapshot.premium_rate) != latest["premium_rate"],
                snapshot.state != latest["state"],
                snapshot.days_to_maturity != latest["days_to_maturity"],
            )
        )
        if self._same_minute(current_ts, latest_ts):
            return "update" if changed else "skip"
        if changed or self._heartbeat_due(current_ts, latest_ts):
            return "insert"
        return "skip"

    def save_signal(self, signal: Signal) -> int:
        """保存信号并返回记录 ID。"""
        with self._write_lock:
            with self.get_connection() as conn:
                conn.execute(
                    "DELETE FROM alert_history WHERE asset = ?",
                    (signal.asset,),
                )
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
        snapshots = list(snapshots)
        if not snapshots:
            return

        with self._write_lock:
            with self.get_connection() as conn:
                latest_rows = self._get_latest_futures_snapshot_rows(
                    conn, [snapshot.symbol for snapshot in snapshots]
                )
                for snapshot in snapshots:
                    latest = latest_rows.get(snapshot.symbol)
                    action = self._classify_futures_snapshot_write(snapshot, latest)
                    if action == "skip":
                        continue
                    row = (
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
                    if action == "update" and latest is not None:
                        conn.execute(
                            """
                            UPDATE futures_live_snapshot
                            SET product_code = ?, price = ?, spot_price = ?, discount_rate = ?,
                                contract_multiplier = ?, margin_ratio = ?, notional_per_lot = ?,
                                margin_required_per_lot = ?, days_to_maturity = ?, fetched_at = ?
                            WHERE id = ?
                            """,
                            row[1:] + (latest["id"],),
                        )
                    else:
                        cursor = conn.execute(
                            """
                            INSERT INTO futures_live_snapshot
                            (symbol, product_code, price, spot_price, discount_rate, contract_multiplier,
                             margin_ratio, notional_per_lot, margin_required_per_lot, days_to_maturity, fetched_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            row,
                        )
                        latest = {"id": int(cursor.lastrowid), **self._build_futures_snapshot_state(snapshot)}
                    latest_rows[snapshot.symbol] = {
                        "id": latest["id"],
                        **self._build_futures_snapshot_state(snapshot),
                    }
                conn.commit()

    def save_metal_snapshots(self, snapshots: Iterable[MetalArbitrageData]) -> None:
        snapshots = list(snapshots)
        if not snapshots:
            return

        with self._write_lock:
            with self.get_connection() as conn:
                latest_rows = self._get_latest_metal_snapshot_rows(
                    conn, [snapshot.symbol for snapshot in snapshots]
                )
                for snapshot in snapshots:
                    latest = latest_rows.get(snapshot.symbol)
                    action = self._classify_metal_snapshot_write(snapshot, latest)
                    if action == "skip":
                        continue
                    row = (
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
                    if action == "update" and latest is not None:
                        conn.execute(
                            """
                            UPDATE metal_arbitrage_snapshot
                            SET metal_symbol = ?, metal_name = ?, benchmark_symbol = ?, benchmark_name = ?,
                                benchmark_display_name = ?, domestic_symbol = ?, domestic_name = ?,
                                domestic_unit = ?, category = ?, dom_price = ?, for_price_usd = ?,
                                for_price_cny = ?, exchange_rate = ?, implied_rate = ?, spread = ?,
                                spread_pct = ?, dom_time = ?, for_time = ?, for_date = ?,
                                used_api_cny_quote = ?, fetched_at = ?
                            WHERE id = ?
                            """,
                            row[1:] + (latest["id"],),
                        )
                    else:
                        cursor = conn.execute(
                            """
                            INSERT INTO metal_arbitrage_snapshot
                            (symbol, metal_symbol, metal_name, benchmark_symbol, benchmark_name, benchmark_display_name,
                             domestic_symbol, domestic_name, domestic_unit, category, dom_price, for_price_usd,
                             for_price_cny, exchange_rate, implied_rate, spread, spread_pct, dom_time, for_time,
                             for_date, used_api_cny_quote, fetched_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            row,
                        )
                        latest = {"id": int(cursor.lastrowid), **self._build_metal_snapshot_state(snapshot)}
                    latest_rows[snapshot.symbol] = {
                        "id": latest["id"],
                        **self._build_metal_snapshot_state(snapshot),
                    }
                conn.commit()

    def save_premium_snapshots(self, snapshots: Iterable[PremiumArbitrageData]) -> None:
        snapshots = list(snapshots)
        if not snapshots:
            return

        with self._write_lock:
            with self.get_connection() as conn:
                latest_rows = self._get_latest_premium_snapshot_rows(
                    conn, [snapshot.symbol for snapshot in snapshots]
                )
                for snapshot in snapshots:
                    latest = latest_rows.get(snapshot.symbol)
                    action = self._classify_premium_snapshot_write(snapshot, latest)
                    if action == "skip":
                        continue
                    row = (
                        snapshot.symbol,
                        snapshot.asset_group,
                        snapshot.spot_symbol,
                        snapshot.spot_name,
                        snapshot.spot_price,
                        snapshot.future_symbol,
                        snapshot.future_name,
                        snapshot.future_price,
                        snapshot.premium,
                        snapshot.premium_rate,
                        snapshot.state,
                        snapshot.days_to_maturity,
                        snapshot.source_spot,
                        snapshot.source_future,
                        snapshot.timestamp.isoformat(),
                    )
                    if action == "update" and latest is not None:
                        conn.execute(
                            """
                            UPDATE premium_arbitrage_snapshot
                            SET asset_group = ?, spot_symbol = ?, spot_name = ?, spot_price = ?,
                                future_symbol = ?, future_name = ?, future_price = ?, premium = ?,
                                premium_rate = ?, state = ?, days_to_maturity = ?, source_spot = ?, source_future = ?, fetched_at = ?
                            WHERE id = ?
                            """,
                            row[1:] + (latest["id"],),
                        )
                    else:
                        cursor = conn.execute(
                            """
                            INSERT INTO premium_arbitrage_snapshot
                            (symbol, asset_group, spot_symbol, spot_name, spot_price, future_symbol,
                             future_name, future_price, premium, premium_rate, state, days_to_maturity, source_spot,
                             source_future, fetched_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            row,
                        )
                        latest = {"id": int(cursor.lastrowid), **self._build_premium_snapshot_state(snapshot)}
                    latest_rows[snapshot.symbol] = {
                        "id": latest["id"],
                        **self._build_premium_snapshot_state(snapshot),
                    }
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

    def purge_premium_snapshots_older_than(self, retention_days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM premium_arbitrage_snapshot WHERE fetched_at < ?",
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

    def get_recent_premium_snapshots(self, limit: int = 200):
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT asset_group, spot_symbol, spot_name, spot_price, future_symbol, future_name,
                       future_price, premium, premium_rate, state, source_spot, source_future, fetched_at
                FROM premium_arbitrage_snapshot
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cursor.fetchall()

    def save_source_health_status(
        self,
        source_name: str,
        *,
        success: bool,
        duration_ms: float,
        active_source: str,
        is_fallback: bool,
        error_summary: str = "",
        window_size: int = 20,
    ) -> None:
        timestamp = datetime.now().isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT last_success_at, last_failure_at, consecutive_failures, recent_outcomes_json,
                           recent_durations_json
                    FROM source_health_status
                    WHERE source_name = ?
                    """,
                    (source_name,),
                ).fetchone()

                last_success_at = row[0] if row else None
                last_failure_at = row[1] if row else None
                consecutive_failures = int(row[2] or 0) if row else 0
                outcomes = json.loads(row[3]) if row and row[3] else []
                durations = json.loads(row[4]) if row and row[4] else []

                outcomes.append(1 if success else 0)
                durations.append(round(float(duration_ms), 2))
                outcomes = outcomes[-window_size:]
                durations = durations[-window_size:]

                if success:
                    last_success_at = timestamp
                    consecutive_failures = 0
                    error_summary = ""
                else:
                    last_failure_at = timestamp
                    consecutive_failures += 1

                recent_total = len(outcomes)
                recent_successes = int(sum(outcomes))
                success_rate = round((recent_successes / recent_total) * 100, 2) if recent_total else 0.0
                avg_duration_ms = round(sum(durations) / len(durations), 2) if durations else 0.0
                sorted_durations = sorted(durations)
                if sorted_durations:
                    idx = max(0, int(len(sorted_durations) * 0.95) - 1)
                    p95_duration_ms = round(sorted_durations[idx], 2)
                else:
                    p95_duration_ms = 0.0

                conn.execute(
                    """
                    INSERT INTO source_health_status (
                        source_name, last_success_at, last_failure_at, consecutive_failures,
                        last_error, recent_successes, recent_total, success_rate, avg_duration_ms,
                        p95_duration_ms, active_source, is_fallback, recent_outcomes_json,
                        recent_durations_json, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_name) DO UPDATE SET
                        last_success_at = excluded.last_success_at,
                        last_failure_at = excluded.last_failure_at,
                        consecutive_failures = excluded.consecutive_failures,
                        last_error = excluded.last_error,
                        recent_successes = excluded.recent_successes,
                        recent_total = excluded.recent_total,
                        success_rate = excluded.success_rate,
                        avg_duration_ms = excluded.avg_duration_ms,
                        p95_duration_ms = excluded.p95_duration_ms,
                        active_source = excluded.active_source,
                        is_fallback = excluded.is_fallback,
                        recent_outcomes_json = excluded.recent_outcomes_json,
                        recent_durations_json = excluded.recent_durations_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        source_name,
                        last_success_at,
                        last_failure_at,
                        consecutive_failures,
                        error_summary[:500],
                        recent_successes,
                        recent_total,
                        success_rate,
                        avg_duration_ms,
                        p95_duration_ms,
                        active_source,
                        1 if is_fallback else 0,
                        json.dumps(outcomes, ensure_ascii=False),
                        json.dumps(durations, ensure_ascii=False),
                        timestamp,
                    ),
                )
                conn.commit()

    def get_source_health_statuses(self):
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT source_name, last_success_at, last_failure_at, consecutive_failures, last_error,
                       recent_successes, recent_total, success_rate, avg_duration_ms, p95_duration_ms,
                       active_source, is_fallback, updated_at
                FROM source_health_status
                ORDER BY source_name
                """
            )
            return cursor.fetchall()

    def save_config_changes(self, changes: Iterable[dict]) -> None:
        rows = [
            (
                change["changed_at"],
                change["config_key"],
                change.get("old_value"),
                change.get("new_value"),
                change["source"],
                change["destination"],
                1 if change.get("immediate_effect", True) else 0,
            )
            for change in changes
        ]
        if not rows:
            return

        with self._write_lock:
            with self.get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO config_change_history
                    (changed_at, config_key, old_value, new_value, source, destination, immediate_effect)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()

    def get_recent_config_changes(self, limit: int = 50):
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT changed_at, config_key, old_value, new_value, source, destination, immediate_effect
                FROM config_change_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cursor.fetchall()

    def mark_job_started(self, job_name: str, started_at: str) -> None:
        with self._write_lock:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO job_run_status
                    (job_name, current_running, last_started_at, updated_at)
                    VALUES (?, 1, ?, ?)
                    ON CONFLICT(job_name) DO UPDATE SET
                        current_running = 1,
                        last_started_at = excluded.last_started_at,
                        updated_at = excluded.updated_at
                    """,
                    (job_name, started_at, started_at),
                )
                conn.commit()

    def mark_job_finished(
        self,
        job_name: str,
        *,
        finished_at: str,
        status: str,
        duration_ms: float,
        error_summary: str = "",
    ) -> None:
        with self._write_lock:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO job_run_status
                    (job_name, current_running, last_finished_at, last_duration_ms, last_status,
                     last_error, total_skipped, consecutive_skipped, updated_at)
                    VALUES (?, 0, ?, ?, ?, ?, 0, 0, ?)
                    ON CONFLICT(job_name) DO UPDATE SET
                        current_running = 0,
                        last_finished_at = excluded.last_finished_at,
                        last_duration_ms = excluded.last_duration_ms,
                        last_status = excluded.last_status,
                        last_error = excluded.last_error,
                        consecutive_skipped = 0,
                        updated_at = excluded.updated_at
                    """,
                    (
                        job_name,
                        finished_at,
                        round(float(duration_ms), 2),
                        status,
                        error_summary[:500],
                        finished_at,
                    ),
                )
                conn.commit()

    def mark_job_skipped(self, job_name: str, reason: str = "OVERLAP") -> None:
        timestamp = datetime.now().isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO job_run_status
                    (job_name, current_running, last_status, total_skipped, consecutive_skipped, updated_at)
                    VALUES (?, 1, ?, 1, 1, ?)
                    ON CONFLICT(job_name) DO UPDATE SET
                        last_status = excluded.last_status,
                        total_skipped = job_run_status.total_skipped + 1,
                        consecutive_skipped = job_run_status.consecutive_skipped + 1,
                        updated_at = excluded.updated_at
                    """,
                    (job_name, f"SKIPPED_{reason}", timestamp),
                )
                conn.commit()

    def get_job_run_statuses(self):
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT job_name, current_running, last_started_at, last_finished_at, last_duration_ms,
                       last_status, last_error, total_skipped, consecutive_skipped, updated_at
                FROM job_run_status
                ORDER BY job_name
                """
            )
            return cursor.fetchall()
