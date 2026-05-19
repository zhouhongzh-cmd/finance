import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional

from models.market_data import (
    CBData,
    FuturesData,
    FuturesMarginData,
    MetalArbitrageData,
    PremiumArbitrageData,
    SentimentData,
)
from models.signals import Signal
from config.premium_assets import INDEX_PREMIUM_ASSETS


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "monitor_history.db"
DB_PATH_ENV = "ARBITRAGE_MONITOR_DB_PATH"


def resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> str:
    configured = db_path or os.environ.get(DB_PATH_ENV) or DEFAULT_DB_PATH
    return str(Path(configured).expanduser().resolve())


class DBManager:
    """提供线程安全的 SQLite WAL 连接与持久化"""
    _instance = None
    _lock = threading.Lock()
    SNAPSHOT_HEARTBEAT_MINUTES = 15
    PREMIUM_LATEST_BATCH_WINDOW_MINUTES = 5
    
    def __new__(cls, db_path: str | os.PathLike[str] | None = None):
        resolved_db_path = resolve_db_path(db_path)
        with cls._lock:
            if cls._instance is None or getattr(cls._instance, "db_path", None) != resolved_db_path:
                cls._instance = super(DBManager, cls).__new__(cls)
                cls._instance._write_lock = threading.Lock()
                cls._instance._init_db(resolved_db_path)
        return cls._instance

    def _init_db(self, db_path):
        db_path = resolve_db_path(db_path)
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
                    contract_bucket TEXT DEFAULT '',
                    contract_type TEXT DEFAULT '',
                    expiry_ts TEXT DEFAULT '',
                    bucket_rank INTEGER NOT NULL DEFAULT 0,
                    source_exchange TEXT DEFAULT '',
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
                CREATE TABLE IF NOT EXISTS convertible_live_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    bond_code TEXT NOT NULL,
                    bond_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    premium_rate REAL NOT NULL,
                    double_low REAL NOT NULL,
                    ytm REAL NOT NULL,
                    listing_status TEXT DEFAULT '',
                    is_listed INTEGER NOT NULL DEFAULT 0,
                    is_delisted INTEGER NOT NULL DEFAULT 0,
                    listing_date TEXT DEFAULT '',
                    delist_date TEXT DEFAULT '',
                    fetched_at TEXT NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS sentiment_live_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    hot_score INTEGER NOT NULL,
                    sentiment_pulse REAL NOT NULL,
                    rank INTEGER NOT NULL,
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
            self._ensure_column(conn, "premium_arbitrage_snapshot", "contract_bucket", "TEXT DEFAULT ''")
            self._ensure_column(conn, "premium_arbitrage_snapshot", "contract_type", "TEXT DEFAULT ''")
            self._ensure_column(conn, "premium_arbitrage_snapshot", "expiry_ts", "TEXT DEFAULT ''")
            self._ensure_column(conn, "premium_arbitrage_snapshot", "bucket_rank", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "premium_arbitrage_snapshot", "source_exchange", "TEXT DEFAULT ''")

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

    def _classify_snapshot_write(
        self,
        current_ts: datetime,
        latest: Optional[dict],
        changed: bool,
    ) -> str:
        if latest is None:
            return "insert"
        latest_ts = latest["fetched_at"]
        if self._same_minute(current_ts, latest_ts):
            return "update" if changed else "skip"
        if changed or self._heartbeat_due(current_ts, latest_ts):
            return "insert"
        return "skip"

    def _save_snapshots_with_template(
        self,
        snapshots: Iterable,
        *,
        get_latest_rows,
        classify_write,
        build_row,
        build_state,
        update_sql: str,
        insert_sql: str,
    ) -> None:
        snapshots = list(snapshots)
        if not snapshots:
            return

        with self._write_lock:
            with self.get_connection() as conn:
                latest_rows = get_latest_rows(conn, [snapshot.symbol for snapshot in snapshots])
                for snapshot in snapshots:
                    latest = latest_rows.get(snapshot.symbol)
                    action = classify_write(snapshot, latest)
                    if action == "skip":
                        continue
                    row = build_row(snapshot)
                    if action == "update" and latest is not None:
                        conn.execute(update_sql, row[1:] + (latest["id"],))
                    else:
                        cursor = conn.execute(insert_sql, row)
                        latest = {"id": int(cursor.lastrowid), **build_state(snapshot)}
                    latest_rows[snapshot.symbol] = {
                        "id": latest["id"],
                        **build_state(snapshot),
                    }
                conn.commit()

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
            "contract_bucket": snapshot.contract_bucket,
            "contract_type": snapshot.contract_type,
            "expiry_ts": snapshot.expiry_ts,
            "bucket_rank": int(snapshot.bucket_rank),
            "source_exchange": snapshot.source_exchange,
            "spot_price": float(snapshot.spot_price),
            "future_price": float(snapshot.future_price),
            "premium": float(snapshot.premium),
            "premium_rate": float(snapshot.premium_rate),
            "state": snapshot.state,
            "days_to_maturity": snapshot.days_to_maturity,
        }

    def _build_convertible_snapshot_state(self, snapshot: CBData) -> dict:
        return {
            "fetched_at": snapshot.timestamp,
            "price": float(snapshot.price),
            "premium_rate": float(snapshot.premium_rate),
            "double_low": float(snapshot.double_low),
            "ytm": float(snapshot.ytm),
            "listing_status": snapshot.listing_status,
            "is_listed": bool(snapshot.is_listed),
            "is_delisted": bool(snapshot.is_delisted),
            "listing_date": snapshot.listing_date,
            "delist_date": snapshot.delist_date,
        }

    def _build_sentiment_snapshot_state(self, snapshot: SentimentData) -> dict:
        return {
            "fetched_at": snapshot.timestamp,
            "name": snapshot.name,
            "hot_score": int(snapshot.hot_score),
            "sentiment_pulse": float(snapshot.sentiment_pulse),
            "rank": int(snapshot.rank),
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
            SELECT p.id, p.symbol, p.contract_bucket, p.contract_type, p.expiry_ts, p.bucket_rank,
                   p.source_exchange, p.spot_price, p.future_price, p.premium, p.premium_rate,
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
                "contract_bucket": str(row[2] or ""),
                "contract_type": str(row[3] or ""),
                "expiry_ts": str(row[4] or ""),
                "bucket_rank": int(row[5] or 0),
                "source_exchange": str(row[6] or ""),
                "spot_price": float(row[7]),
                "future_price": float(row[8]),
                "premium": float(row[9]),
                "premium_rate": float(row[10]),
                "state": str(row[11]),
                "days_to_maturity": int(row[12]) if row[12] is not None else None,
                "fetched_at": datetime.fromisoformat(row[13]),
            }
        return result

    def _get_latest_convertible_snapshot_rows(self, conn, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        placeholders = ",".join(["?"] * len(symbols))
        rows = conn.execute(
            f"""
            SELECT c.id, c.symbol, c.price, c.premium_rate, c.double_low, c.ytm,
                   c.listing_status, c.is_listed, c.is_delisted, c.listing_date, c.delist_date, c.fetched_at
            FROM convertible_live_snapshot c
            INNER JOIN (
                SELECT symbol, MAX(id) AS max_id
                FROM convertible_live_snapshot
                WHERE symbol IN ({placeholders})
                GROUP BY symbol
            ) latest
            ON c.id = latest.max_id
            """,
            tuple(symbols),
        ).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            result[row[1]] = {
                "id": int(row[0]),
                "price": float(row[2]),
                "premium_rate": float(row[3]),
                "double_low": float(row[4]),
                "ytm": float(row[5]),
                "listing_status": str(row[6] or ""),
                "is_listed": bool(row[7]),
                "is_delisted": bool(row[8]),
                "listing_date": str(row[9] or ""),
                "delist_date": str(row[10] or ""),
                "fetched_at": datetime.fromisoformat(row[11]),
            }
        return result

    def _get_latest_sentiment_snapshot_rows(self, conn, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        placeholders = ",".join(["?"] * len(symbols))
        rows = conn.execute(
            f"""
            SELECT s.id, s.symbol, s.name, s.hot_score, s.sentiment_pulse, s.rank, s.fetched_at
            FROM sentiment_live_snapshot s
            INNER JOIN (
                SELECT symbol, MAX(id) AS max_id
                FROM sentiment_live_snapshot
                WHERE symbol IN ({placeholders})
                GROUP BY symbol
            ) latest
            ON s.id = latest.max_id
            """,
            tuple(symbols),
        ).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            result[row[1]] = {
                "id": int(row[0]),
                "name": str(row[2] or ""),
                "hot_score": int(row[3]),
                "sentiment_pulse": float(row[4]),
                "rank": int(row[5]),
                "fetched_at": datetime.fromisoformat(row[6]),
            }
        return result

    def _classify_futures_snapshot_write(self, snapshot: FuturesData, latest: Optional[dict]) -> str:
        changed = any(
            (
                float(snapshot.price) != latest["price"],
                float(snapshot.spot_price) != latest["spot_price"],
                float(snapshot.discount_rate) != latest["discount_rate"],
                float(snapshot.margin_ratio) != latest["margin_ratio"],
                int(snapshot.days_to_maturity) != latest["days_to_maturity"],
            )
        ) if latest is not None else False
        return self._classify_snapshot_write(snapshot.timestamp, latest, changed)

    def _classify_metal_snapshot_write(self, snapshot: MetalArbitrageData, latest: Optional[dict]) -> str:
        changed = any(
            (
                float(snapshot.dom_price) != latest["dom_price"],
                float(snapshot.for_price_cny) != latest["for_price_cny"],
                float(snapshot.spread) != latest["spread"],
                float(snapshot.spread_pct) != latest["spread_pct"],
                float(snapshot.exchange_rate) != latest["exchange_rate"],
            )
        ) if latest is not None else False
        return self._classify_snapshot_write(snapshot.timestamp, latest, changed)

    def _classify_premium_snapshot_write(self, snapshot: PremiumArbitrageData, latest: Optional[dict]) -> str:
        changed = any(
            (
                snapshot.contract_bucket != latest["contract_bucket"],
                snapshot.contract_type != latest["contract_type"],
                snapshot.expiry_ts != latest["expiry_ts"],
                int(snapshot.bucket_rank) != latest["bucket_rank"],
                snapshot.source_exchange != latest["source_exchange"],
                float(snapshot.spot_price) != latest["spot_price"],
                float(snapshot.future_price) != latest["future_price"],
                float(snapshot.premium) != latest["premium"],
                float(snapshot.premium_rate) != latest["premium_rate"],
                snapshot.state != latest["state"],
                snapshot.days_to_maturity != latest["days_to_maturity"],
            )
        ) if latest is not None else False
        return self._classify_snapshot_write(snapshot.timestamp, latest, changed)

    def _classify_convertible_snapshot_write(self, snapshot: CBData, latest: Optional[dict]) -> str:
        changed = any(
            (
                float(snapshot.price) != latest["price"],
                float(snapshot.premium_rate) != latest["premium_rate"],
                float(snapshot.double_low) != latest["double_low"],
                float(snapshot.ytm) != latest["ytm"],
                snapshot.listing_status != latest["listing_status"],
                bool(snapshot.is_listed) != latest["is_listed"],
                bool(snapshot.is_delisted) != latest["is_delisted"],
                snapshot.listing_date != latest["listing_date"],
                snapshot.delist_date != latest["delist_date"],
            )
        ) if latest is not None else False
        return self._classify_snapshot_write(snapshot.timestamp, latest, changed)

    def _classify_sentiment_snapshot_write(self, snapshot: SentimentData, latest: Optional[dict]) -> str:
        changed = any(
            (
                snapshot.name != latest["name"],
                int(snapshot.hot_score) != latest["hot_score"],
                float(snapshot.sentiment_pulse) != latest["sentiment_pulse"],
                int(snapshot.rank) != latest["rank"],
            )
        ) if latest is not None else False
        return self._classify_snapshot_write(snapshot.timestamp, latest, changed)

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
        self._save_snapshots_with_template(
            snapshots,
            get_latest_rows=self._get_latest_futures_snapshot_rows,
            classify_write=self._classify_futures_snapshot_write,
            build_row=lambda snapshot: (
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
            ),
            build_state=self._build_futures_snapshot_state,
            update_sql="""
                UPDATE futures_live_snapshot
                SET product_code = ?, price = ?, spot_price = ?, discount_rate = ?,
                    contract_multiplier = ?, margin_ratio = ?, notional_per_lot = ?,
                    margin_required_per_lot = ?, days_to_maturity = ?, fetched_at = ?
                WHERE id = ?
            """,
            insert_sql="""
                INSERT INTO futures_live_snapshot
                (symbol, product_code, price, spot_price, discount_rate, contract_multiplier,
                 margin_ratio, notional_per_lot, margin_required_per_lot, days_to_maturity, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
        )

    def save_metal_snapshots(self, snapshots: Iterable[MetalArbitrageData]) -> None:
        self._save_snapshots_with_template(
            snapshots,
            get_latest_rows=self._get_latest_metal_snapshot_rows,
            classify_write=self._classify_metal_snapshot_write,
            build_row=lambda snapshot: (
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
            ),
            build_state=self._build_metal_snapshot_state,
            update_sql="""
                UPDATE metal_arbitrage_snapshot
                SET metal_symbol = ?, metal_name = ?, benchmark_symbol = ?, benchmark_name = ?,
                    benchmark_display_name = ?, domestic_symbol = ?, domestic_name = ?,
                    domestic_unit = ?, category = ?, dom_price = ?, for_price_usd = ?,
                    for_price_cny = ?, exchange_rate = ?, implied_rate = ?, spread = ?,
                    spread_pct = ?, dom_time = ?, for_time = ?, for_date = ?,
                    used_api_cny_quote = ?, fetched_at = ?
                WHERE id = ?
            """,
            insert_sql="""
                INSERT INTO metal_arbitrage_snapshot
                (symbol, metal_symbol, metal_name, benchmark_symbol, benchmark_name, benchmark_display_name,
                 domestic_symbol, domestic_name, domestic_unit, category, dom_price, for_price_usd,
                 for_price_cny, exchange_rate, implied_rate, spread, spread_pct, dom_time, for_time,
                 for_date, used_api_cny_quote, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
        )

    def save_premium_snapshots(self, snapshots: Iterable[PremiumArbitrageData]) -> None:
        self._save_snapshots_with_template(
            snapshots,
            get_latest_rows=self._get_latest_premium_snapshot_rows,
            classify_write=self._classify_premium_snapshot_write,
            build_row=lambda snapshot: (
                snapshot.symbol,
                snapshot.asset_group,
                snapshot.contract_bucket,
                snapshot.contract_type,
                snapshot.expiry_ts,
                snapshot.bucket_rank,
                snapshot.source_exchange,
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
            ),
            build_state=self._build_premium_snapshot_state,
            update_sql="""
                UPDATE premium_arbitrage_snapshot
                SET asset_group = ?, contract_bucket = ?, contract_type = ?, expiry_ts = ?,
                    bucket_rank = ?, source_exchange = ?, spot_symbol = ?, spot_name = ?, spot_price = ?,
                    future_symbol = ?, future_name = ?, future_price = ?, premium = ?,
                    premium_rate = ?, state = ?, days_to_maturity = ?, source_spot = ?, source_future = ?, fetched_at = ?
                WHERE id = ?
            """,
            insert_sql="""
                INSERT INTO premium_arbitrage_snapshot
                (symbol, asset_group, contract_bucket, contract_type, expiry_ts, bucket_rank,
                 source_exchange, spot_symbol, spot_name, spot_price, future_symbol,
                 future_name, future_price, premium, premium_rate, state, days_to_maturity, source_spot,
                 source_future, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
        )

    def save_convertible_snapshots(self, snapshots: Iterable[CBData]) -> None:
        self._save_snapshots_with_template(
            snapshots,
            get_latest_rows=self._get_latest_convertible_snapshot_rows,
            classify_write=self._classify_convertible_snapshot_write,
            build_row=lambda snapshot: (
                snapshot.symbol,
                snapshot.bond_code,
                snapshot.bond_name,
                snapshot.price,
                snapshot.premium_rate,
                snapshot.double_low,
                snapshot.ytm,
                snapshot.listing_status,
                1 if snapshot.is_listed else 0,
                1 if snapshot.is_delisted else 0,
                snapshot.listing_date,
                snapshot.delist_date,
                snapshot.timestamp.isoformat(),
            ),
            build_state=self._build_convertible_snapshot_state,
            update_sql="""
                UPDATE convertible_live_snapshot
                SET bond_code = ?, bond_name = ?, price = ?, premium_rate = ?, double_low = ?, ytm = ?,
                    listing_status = ?, is_listed = ?, is_delisted = ?, listing_date = ?, delist_date = ?, fetched_at = ?
                WHERE id = ?
            """,
            insert_sql="""
                INSERT INTO convertible_live_snapshot
                (symbol, bond_code, bond_name, price, premium_rate, double_low, ytm,
                 listing_status, is_listed, is_delisted, listing_date, delist_date, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
        )

    def save_sentiment_snapshots(self, snapshots: Iterable[SentimentData]) -> None:
        self._save_snapshots_with_template(
            snapshots,
            get_latest_rows=self._get_latest_sentiment_snapshot_rows,
            classify_write=self._classify_sentiment_snapshot_write,
            build_row=lambda snapshot: (
                snapshot.symbol,
                snapshot.name,
                snapshot.hot_score,
                snapshot.sentiment_pulse,
                snapshot.rank,
                snapshot.timestamp.isoformat(),
            ),
            build_state=self._build_sentiment_snapshot_state,
            update_sql="""
                UPDATE sentiment_live_snapshot
                SET name = ?, hot_score = ?, sentiment_pulse = ?, rank = ?, fetched_at = ?
                WHERE id = ?
            """,
            insert_sql="""
                INSERT INTO sentiment_live_snapshot
                (symbol, name, hot_score, sentiment_pulse, rank, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
        )

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

    def purge_convertible_snapshots_older_than(self, retention_days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM convertible_live_snapshot WHERE fetched_at < ?",
                    (cutoff,),
                )
                conn.commit()
                return int(cursor.rowcount or 0)

    def purge_sentiment_snapshots_older_than(self, retention_days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM sentiment_live_snapshot WHERE fetched_at < ?",
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
                SELECT asset_group, contract_bucket, contract_type, expiry_ts, bucket_rank, source_exchange,
                       spot_symbol, spot_name, spot_price, future_symbol, future_name,
                       future_price, premium, premium_rate, state, source_spot, source_future, fetched_at
                FROM premium_arbitrage_snapshot
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cursor.fetchall()

    def get_latest_futures_live_snapshots(self) -> list[FuturesData]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT f.symbol, f.product_code, f.price, f.spot_price, f.discount_rate,
                       f.contract_multiplier, f.margin_ratio, f.notional_per_lot,
                       f.margin_required_per_lot, f.days_to_maturity, f.fetched_at
                FROM futures_live_snapshot f
                INNER JOIN (
                    SELECT symbol, MAX(id) AS max_id
                    FROM futures_live_snapshot
                    GROUP BY symbol
                ) latest
                ON f.id = latest.max_id
                ORDER BY f.product_code, f.symbol
                """
            ).fetchall()
        return [
            FuturesData(
                symbol=row[0],
                product_code=row[1],
                price=float(row[2]),
                spot_price=float(row[3]),
                discount_rate=float(row[4]),
                contract_multiplier=int(row[5]),
                margin_ratio=float(row[6]),
                notional_per_lot=float(row[7]),
                margin_required_per_lot=float(row[8]),
                days_to_maturity=int(row[9]),
                timestamp=datetime.fromisoformat(row[10]),
            )
            for row in rows
        ]

    def get_latest_metal_snapshots(self) -> list[MetalArbitrageData]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT m.symbol, m.metal_symbol, m.metal_name, m.benchmark_symbol, m.benchmark_name,
                       m.benchmark_display_name, m.domestic_symbol, m.domestic_name, m.domestic_unit,
                       m.category, m.dom_price, m.for_price_usd, m.for_price_cny, m.exchange_rate,
                       m.implied_rate, m.spread, m.spread_pct, m.dom_time, m.for_time, m.for_date,
                       m.used_api_cny_quote, m.fetched_at
                FROM metal_arbitrage_snapshot m
                INNER JOIN (
                    SELECT symbol, MAX(id) AS max_id
                    FROM metal_arbitrage_snapshot
                    GROUP BY symbol
                ) latest
                ON m.id = latest.max_id
                ORDER BY m.metal_symbol, m.benchmark_display_name
                """
            ).fetchall()
        return [
            MetalArbitrageData(
                symbol=row[0],
                metal_symbol=row[1],
                metal_name=row[2],
                benchmark_symbol=row[3],
                benchmark_name=row[4],
                benchmark_display_name=row[5],
                domestic_symbol=row[6],
                domestic_name=row[7],
                domestic_unit=row[8],
                category=row[9],
                dom_price=float(row[10]),
                for_price_usd=float(row[11]),
                for_price_cny=float(row[12]),
                exchange_rate=float(row[13]),
                implied_rate=float(row[14]),
                spread=float(row[15]),
                spread_pct=float(row[16]),
                dom_time=str(row[17] or ""),
                for_time=str(row[18] or ""),
                for_date=str(row[19] or ""),
                used_api_cny_quote=bool(row[20]),
                timestamp=datetime.fromisoformat(row[21]),
            )
            for row in rows
        ]

    def get_latest_premium_snapshots(self) -> list[PremiumArbitrageData]:
        index_assets = tuple(INDEX_PREMIUM_ASSETS)
        index_placeholders = ",".join("?" for _ in index_assets)
        with self.get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT p.symbol, p.asset_group, p.contract_bucket, p.contract_type, p.expiry_ts,
                       p.bucket_rank, p.source_exchange, p.spot_symbol, p.spot_name, p.spot_price,
                       p.future_symbol, p.future_name, p.future_price, p.premium, p.premium_rate,
                       p.state, p.days_to_maturity, p.source_spot, p.source_future, p.fetched_at
                FROM premium_arbitrage_snapshot p
                INNER JOIN (
                    SELECT symbol, MAX(id) AS max_id
                    FROM premium_arbitrage_snapshot
                    GROUP BY symbol
                ) latest
                ON p.id = latest.max_id
                WHERE NOT (
                    p.asset_group NOT IN ({index_placeholders})
                    AND COALESCE(p.contract_bucket, '') = ''
                )
                AND julianday(p.fetched_at) >= julianday((
                    SELECT MAX(fetched_at) FROM premium_arbitrage_snapshot
                )) - (? / 1440.0)
                ORDER BY p.asset_group, p.bucket_rank, p.future_symbol
                """,
                (*index_assets, self.PREMIUM_LATEST_BATCH_WINDOW_MINUTES),
            ).fetchall()
        return [
            PremiumArbitrageData(
                symbol=row[0],
                asset_group=row[1],
                contract_bucket=str(row[2] or ""),
                contract_type=str(row[3] or ""),
                expiry_ts=str(row[4] or ""),
                bucket_rank=int(row[5] or 0),
                source_exchange=str(row[6] or ""),
                spot_symbol=row[7],
                spot_name=row[8],
                spot_price=float(row[9]),
                future_symbol=row[10],
                future_name=row[11],
                future_price=float(row[12]),
                premium=float(row[13]),
                premium_rate=float(row[14]),
                state=str(row[15]),
                days_to_maturity=int(row[16]) if row[16] is not None else None,
                source_spot=str(row[17] or ""),
                source_future=str(row[18] or ""),
                timestamp=datetime.fromisoformat(row[19]),
            )
            for row in rows
        ]

    def get_latest_convertible_snapshots(self) -> list[CBData]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT c.symbol, c.bond_code, c.bond_name, c.price, c.premium_rate,
                       c.double_low, c.ytm, c.listing_status, c.is_listed, c.is_delisted,
                       c.listing_date, c.delist_date, c.fetched_at
                FROM convertible_live_snapshot c
                INNER JOIN (
                    SELECT symbol, MAX(id) AS max_id
                    FROM convertible_live_snapshot
                    GROUP BY symbol
                ) latest
                ON c.id = latest.max_id
                ORDER BY c.double_low ASC, c.premium_rate ASC, c.ytm DESC
                """
            ).fetchall()
        return [
            CBData(
                symbol=row[0],
                bond_code=row[1],
                bond_name=row[2],
                price=float(row[3]),
                premium_rate=float(row[4]),
                double_low=float(row[5]),
                ytm=float(row[6]),
                listing_status=str(row[7] or ""),
                is_listed=bool(row[8]),
                is_delisted=bool(row[9]),
                listing_date=str(row[10] or ""),
                delist_date=str(row[11] or ""),
                timestamp=datetime.fromisoformat(row[12]),
            )
            for row in rows
        ]

    def get_latest_sentiment_snapshots(self) -> list[SentimentData]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT s.symbol, s.name, s.hot_score, s.sentiment_pulse, s.rank, s.fetched_at
                FROM sentiment_live_snapshot s
                INNER JOIN (
                    SELECT symbol, MAX(id) AS max_id
                    FROM sentiment_live_snapshot
                    GROUP BY symbol
                ) latest
                ON s.id = latest.max_id
                ORDER BY s.rank ASC, s.symbol ASC
                """
            ).fetchall()
        return [
            SentimentData(
                symbol=row[0],
                name=str(row[1] or ""),
                hot_score=int(row[2]),
                sentiment_pulse=float(row[3]),
                rank=int(row[4]),
                timestamp=datetime.fromisoformat(row[5]),
            )
            for row in rows
        ]

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
