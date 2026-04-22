"""
套利监控 Web 看板 (Streamlit)
L5: 展现与触达层

显示风格参考旧 Tkinter GUI:
- 按数据类型分页面查看
- 每页优先展示整张数据表
- 提供显式“刷新”按钮
- 避免整页重跑导致的过度联网抓取
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Callable

import pandas as pd
import streamlit as st

from config.settings import settings
from fetchers.ak_convertible import convertible_fetcher
from fetchers.ak_futures import futures_fetcher
from fetchers.ak_metals import metals_fetcher
from fetchers.premium_fetcher import premium_fetcher
from fetchers.sentiment_spider import sentiment_fetcher
from strategies.cb_strategy import ConvertibleStrategy
from strategies.futures_strategy import FuturesDiscountStrategy
from strategies.metals_strategy import MetalsArbitrageStrategy
from strategies.premium_strategy import PremiumArbitrageStrategy
from strategies.sentiment_strategy import SentimentStrategy
from utils.dashboard_tables import (
    build_convertible_live_tables,
    build_futures_live_tables,
    build_metals_live_tables,
    build_premium_live_tables,
    build_sentiment_live_tables,
)
from utils.db_manager import DBManager


st.set_page_config(
    page_title="期货期权套利",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

db_manager = DBManager()
SNAPSHOT_STALE_WINDOWS = {
    "futures": min(
        settings.FUTURES_CRUISE_INTERVAL_MINUTES * 60,
        settings.FUTURES_WATCH_INTERVAL_SECONDS,
    ),
    "convertible": min(
        settings.CONVERTIBLE_CRUISE_INTERVAL_MINUTES * 60,
        settings.CONVERTIBLE_WATCH_INTERVAL_SECONDS,
    ),
    "sentiment": settings.SENTIMENT_CRUISE_INTERVAL_MINUTES * 60,
    "metals": min(
        settings.METALS_CRUISE_INTERVAL_MINUTES * 60,
        settings.METALS_WATCH_INTERVAL_SECONDS,
    ),
    "premium": min(
        settings.PREMIUM_CRUISE_INTERVAL_MINUTES * 60,
        settings.PREMIUM_WATCH_INTERVAL_SECONDS,
    ),
}


def format_sentiment_asset(name: str, symbol: str) -> str:
    if name and name != symbol:
        return f"{symbol} {name}"
    return symbol


def level_badge(level: str) -> str:
    return {
        "INFO": "🔵 INFO",
        "WARNING": "🟡 WARNING",
        "CRITICAL": "🔴 CRITICAL",
    }.get(level, level)


@st.cache_data(ttl=10)
def fetch_alert_history(limit: int = 500) -> pd.DataFrame:
    with db_manager.get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT id, timestamp, asset, strategy, level, message, notified
            FROM alert_history
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data(ttl=30)
def fetch_today_summary() -> pd.DataFrame:
    with db_manager.get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT strategy, level, COUNT(*) AS count
            FROM alert_history
            WHERE date(timestamp) = date('now', 'localtime')
            GROUP BY strategy, level
            ORDER BY count DESC
            """,
            conn,
        )


@st.cache_data(ttl=30)
def fetch_latest_signals(limit: int = 10) -> pd.DataFrame:
    with db_manager.get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT timestamp, asset, strategy, level, message, notified
            FROM alert_history
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data(ttl=60)
def get_db_stats() -> dict[str, float]:
    with db_manager.get_connection() as conn:
        total_alerts = conn.execute("SELECT COUNT(*) FROM alert_history").fetchone()[0]
        today_alerts = conn.execute(
            "SELECT COUNT(*) FROM alert_history WHERE date(timestamp) = date('now','localtime')"
        ).fetchone()[0]
        unique_assets = conn.execute(
            "SELECT COUNT(DISTINCT asset) FROM alert_history"
        ).fetchone()[0]
        notified = conn.execute(
            "SELECT COUNT(*) FROM alert_history WHERE notified = 1"
        ).fetchone()[0]
        cooldowns = conn.execute("SELECT COUNT(*) FROM cooldown_state").fetchone()[0]
        margin_snapshots = conn.execute(
            "SELECT COUNT(*) FROM futures_margin_snapshot"
        ).fetchone()[0]
        futures_snapshots = conn.execute(
            "SELECT COUNT(*) FROM futures_live_snapshot"
        ).fetchone()[0]
        metal_snapshots = conn.execute(
            "SELECT COUNT(*) FROM metal_arbitrage_snapshot"
        ).fetchone()[0]
        premium_snapshots = conn.execute(
            "SELECT COUNT(*) FROM premium_arbitrage_snapshot"
        ).fetchone()[0]

    db_size = (
        os.path.getsize(db_manager.db_path) if os.path.exists(db_manager.db_path) else 0
    )
    return {
        "total_alerts": total_alerts,
        "today_alerts": today_alerts,
        "unique_assets": unique_assets,
        "notified": notified,
        "cooldowns": cooldowns,
        "margin_snapshots": margin_snapshots,
        "futures_snapshots": futures_snapshots,
        "metal_snapshots": metal_snapshots,
        "premium_snapshots": premium_snapshots,
        "db_size_kb": round(db_size / 1024, 1),
    }


@st.cache_data(ttl=300)
def fetch_latest_margin_table() -> pd.DataFrame:
    with db_manager.get_connection() as conn:
        df = pd.read_sql_query(
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
            ORDER BY s.product_code
            """,
            conn,
        )
    return df


@st.cache_data(ttl=30)
def fetch_futures_live_view() -> tuple[pd.DataFrame, pd.DataFrame]:
    data = futures_fetcher.fetch_live()
    db_manager.save_futures_live_snapshots(data)
    signals = FuturesDiscountStrategy().evaluate(data)
    return build_futures_live_tables(data, signals)


@st.cache_data(ttl=60)
def fetch_metals_live_view() -> tuple[pd.DataFrame, pd.DataFrame]:
    data = metals_fetcher.fetch_live()
    db_manager.save_metal_snapshots(data)
    signals = MetalsArbitrageStrategy().evaluate(data)
    return build_metals_live_tables(data, signals)


@st.cache_data(ttl=30)
def fetch_premium_live_view() -> tuple[pd.DataFrame, pd.DataFrame]:
    data = premium_fetcher.fetch_live()
    db_manager.save_premium_snapshots(data)
    signals = PremiumArbitrageStrategy().evaluate(data)
    return build_premium_live_tables(data, signals)


@st.cache_data(ttl=15)
def fetch_futures_snapshot_view() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    data = db_manager.get_latest_futures_live_snapshots()
    signals = FuturesDiscountStrategy().evaluate(data) if data else []
    data_df, signal_df = build_futures_live_tables(data, signals)
    fetched_at = max((item.timestamp for item in data), default=None)
    return data_df, signal_df, fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else ""


@st.cache_data(ttl=15)
def fetch_metals_snapshot_view() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    data = db_manager.get_latest_metal_snapshots()
    signals = MetalsArbitrageStrategy().evaluate(data) if data else []
    data_df, signal_df = build_metals_live_tables(data, signals)
    fetched_at = max((item.timestamp for item in data), default=None)
    return data_df, signal_df, fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else ""


@st.cache_data(ttl=15)
def fetch_premium_snapshot_view() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    data = db_manager.get_latest_premium_snapshots()
    signals = PremiumArbitrageStrategy().evaluate(data) if data else []
    data_df, signal_df = build_premium_live_tables(data, signals)
    fetched_at = max((item.timestamp for item in data), default=None)
    return data_df, signal_df, fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else ""


@st.cache_data(ttl=60)
def fetch_recent_metal_snapshot_history(limit: int = 200) -> pd.DataFrame:
    with db_manager.get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT fetched_at, metal_symbol, metal_name, benchmark_display_name, dom_price,
                   for_price_cny, for_price_usd, exchange_rate, implied_rate, spread, spread_pct, category
            FROM metal_arbitrage_snapshot
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )
    if not df.empty:
        df["fetched_at"] = pd.to_datetime(df["fetched_at"])
    return df


@st.cache_data(ttl=60)
def fetch_recent_premium_snapshot_history(limit: int = 200) -> pd.DataFrame:
    with db_manager.get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT fetched_at, asset_group, contract_bucket, contract_type, expiry_ts, bucket_rank,
                   source_exchange, spot_symbol, spot_name, spot_price,
                   future_symbol, future_name, future_price, premium, premium_rate,
                   state, days_to_maturity, source_spot, source_future
            FROM premium_arbitrage_snapshot
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )
    if not df.empty:
        df["fetched_at"] = pd.to_datetime(df["fetched_at"])
    return df


def filter_premium_table(df: pd.DataFrame, *, a50_only: bool) -> pd.DataFrame:
    if df.empty or "资产组" not in df.columns:
        return df
    if a50_only:
        return df[df["资产组"] == "A50"].copy()
    return df[df["资产组"] != "A50"].copy()


def filter_premium_signal_table(df: pd.DataFrame, *, a50_only: bool) -> pd.DataFrame:
    if df.empty or "标的" not in df.columns:
        return df
    mask = df["标的"].astype(str).str.startswith("A50 ")
    return df[mask].copy() if a50_only else df[~mask].copy()


def prepare_premium_history_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    history_df = df.copy()
    if "days_to_maturity" in history_df.columns:
        annualized_series = history_df.apply(
            lambda row: (
                round(row["premium_rate"] * (365 / max(int(row["days_to_maturity"]), 1)), 4)
                if pd.notna(row["days_to_maturity"])
                else "N/A"
            ),
            axis=1,
        )
        history_df["annualized_premium_rate"] = annualized_series
    if "state" in history_df.columns:
        history_df["direction"] = history_df["state"].map(
            {"contango": "升水", "backwardation": "贴水"}
        ).fillna(history_df["state"])
    history_df["fetched_at"] = history_df["fetched_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return history_df


@st.cache_data(ttl=30)
def fetch_source_health_table() -> pd.DataFrame:
    rows = db_manager.get_source_health_statuses()
    df = pd.DataFrame(
        rows,
        columns=[
            "source_name",
            "last_success_at",
            "last_failure_at",
            "consecutive_failures",
            "last_error",
            "recent_successes",
            "recent_total",
            "success_rate",
            "avg_duration_ms",
            "p95_duration_ms",
            "active_source",
            "is_fallback",
            "updated_at",
        ],
    )
    if df.empty:
        return df
    df["降级中"] = df["is_fallback"].map({1: "是", 0: "否"})
    return df[
        [
            "source_name",
            "active_source",
            "降级中",
            "consecutive_failures",
            "success_rate",
            "avg_duration_ms",
            "p95_duration_ms",
            "last_success_at",
            "last_failure_at",
            "last_error",
            "updated_at",
        ]
    ].rename(
        columns={
            "source_name": "数据源",
            "active_source": "当前来源",
            "consecutive_failures": "连续失败",
            "success_rate": "最近成功率(%)",
            "avg_duration_ms": "平均耗时(ms)",
            "p95_duration_ms": "P95耗时(ms)",
            "last_success_at": "最近成功",
            "last_failure_at": "最近失败",
            "last_error": "最近错误",
            "updated_at": "更新时间",
        }
    )


@st.cache_data(ttl=15)
def fetch_job_run_status_table() -> pd.DataFrame:
    rows = db_manager.get_job_run_statuses()
    df = pd.DataFrame(
        rows,
        columns=[
            "job_name",
            "current_running",
            "last_started_at",
            "last_finished_at",
            "last_duration_ms",
            "last_status",
            "last_error",
            "total_skipped",
            "consecutive_skipped",
            "updated_at",
        ],
    )
    if df.empty:
        return df
    df["运行中"] = df["current_running"].map({1: "是", 0: "否"})
    return df[
        [
            "job_name",
            "运行中",
            "last_status",
            "last_started_at",
            "last_finished_at",
            "last_duration_ms",
            "total_skipped",
            "consecutive_skipped",
            "last_error",
            "updated_at",
        ]
    ].rename(
        columns={
            "job_name": "任务",
            "last_status": "最近状态",
            "last_started_at": "最近开始",
            "last_finished_at": "最近结束",
            "last_duration_ms": "最近耗时(ms)",
            "total_skipped": "累计跳过",
            "consecutive_skipped": "连续跳过",
            "last_error": "最近异常",
            "updated_at": "更新时间",
        }
    )


@st.cache_data(ttl=60)
def fetch_convertible_live_view() -> tuple[pd.DataFrame, pd.DataFrame]:
    data = convertible_fetcher.fetch_live()
    db_manager.save_convertible_snapshots(data)
    signals = ConvertibleStrategy().evaluate(data)
    return build_convertible_live_tables(data, signals)


@st.cache_data(ttl=15)
def fetch_convertible_snapshot_view() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    data = db_manager.get_latest_convertible_snapshots()
    signals = ConvertibleStrategy().evaluate(data) if data else []
    data_df, signal_df = build_convertible_live_tables(data, signals)
    fetched_at = max((item.timestamp for item in data), default=None)
    return data_df, signal_df, fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else ""


@st.cache_data(ttl=30)
def fetch_sentiment_live_view() -> tuple[pd.DataFrame, pd.DataFrame]:
    data = sentiment_fetcher.fetch_live()
    db_manager.save_sentiment_snapshots(data)
    signals = SentimentStrategy().evaluate(data)
    return build_sentiment_live_tables(data, signals)


@st.cache_data(ttl=15)
def fetch_sentiment_snapshot_view() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    data = db_manager.get_latest_sentiment_snapshots()
    signals = SentimentStrategy().evaluate(data) if data else []
    data_df, signal_df = build_sentiment_live_tables(data, signals)
    fetched_at = max((item.timestamp for item in data), default=None)
    return data_df, signal_df, fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else ""


def clear_snapshot_cache(cache_func) -> None:
    cache_func.clear()


def load_snapshot_view(
    state_key: str,
    snapshot_func: Callable[[], tuple[pd.DataFrame, pd.DataFrame, str]],
    refresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    data_key = f"{state_key}_data"
    signal_key = f"{state_key}_signals"
    fetched_key = f"{state_key}_fetched_at"
    source_key = f"{state_key}_source"

    needs_fetch = (
        refresh
        or data_key not in st.session_state
        or signal_key not in st.session_state
        or fetched_key not in st.session_state
        or source_key not in st.session_state
    )

    if needs_fetch:
        data_df, signal_df, fetched_at = snapshot_func()
        st.session_state[data_key] = data_df
        st.session_state[signal_key] = signal_df
        st.session_state[fetched_key] = fetched_at
        st.session_state[source_key] = "快照"

    return (
        st.session_state[data_key],
        st.session_state[signal_key],
        st.session_state[fetched_key],
        st.session_state[source_key],
    )


def force_refresh_live_view(
    state_key: str,
    live_func: Callable[[], tuple[pd.DataFrame, pd.DataFrame]],
    snapshot_func: Callable[[], tuple[pd.DataFrame, pd.DataFrame, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    data_key = f"{state_key}_data"
    signal_key = f"{state_key}_signals"
    fetched_key = f"{state_key}_fetched_at"
    source_key = f"{state_key}_source"
    error_key = f"{state_key}_error"

    try:
        live_func.clear()
        live_func()
        clear_snapshot_cache(snapshot_func)
        data_df, signal_df, fetched_at = snapshot_func()
        st.session_state[data_key] = data_df
        st.session_state[signal_key] = signal_df
        st.session_state[fetched_key] = fetched_at
        st.session_state[source_key] = "强制抓新"
        st.session_state[error_key] = ""
    except Exception as exc:
        st.session_state[error_key] = str(exc)
        return load_snapshot_view(state_key, snapshot_func, refresh=True)

    return (
        st.session_state[data_key],
        st.session_state[signal_key],
        st.session_state[fetched_key],
        st.session_state[source_key],
    )


def get_snapshot_health(module_name: str, fetched_at: str) -> str:
    if not fetched_at:
        return "暂无快照"
    snapshot_time = datetime.fromisoformat(fetched_at)
    stale_window = SNAPSHOT_STALE_WINDOWS[module_name] * 2
    elapsed = (datetime.now() - snapshot_time).total_seconds()
    return "可能过期" if elapsed > stale_window else "新鲜"


def render_snapshot_meta(module_name: str, fetched_at: str, source: str, state_key: str) -> None:
    status = get_snapshot_health(module_name, fetched_at)
    st.caption(
        f"最新快照时间：{fetched_at or '暂无'} | 数据来源：{source} | 数据状态：{status}"
    )
    error_text = st.session_state.get(f"{state_key}_error", "")
    if error_text:
        st.warning(f"强制抓新失败，当前回退到最近快照：{error_text}")


st.title("期货期权套利")
st.caption("显示风格参考老 Tkinter GUI：按标签页分模块、每页优先整表展示、手动刷新。")

sidebar = st.sidebar
sidebar.subheader("系统状态")
stats = get_db_stats()
col1, col2 = sidebar.columns(2)
col1.metric("今日报警", stats["today_alerts"])
col2.metric("累计报警", stats["total_alerts"])
sidebar.metric("已送达", stats["notified"])
sidebar.metric("冷却记录", stats["cooldowns"])
sidebar.metric("保证金快照", stats["margin_snapshots"])
sidebar.metric("期指快照", stats["futures_snapshots"])
sidebar.metric("金属快照", stats["metal_snapshots"])
sidebar.metric("溢价快照", stats["premium_snapshots"])
sidebar.metric("监控标的数", stats["unique_assets"])
sidebar.metric("数据库大小", f"{stats['db_size_kb']} KB")
sidebar.info(f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
if hasattr(st, "page_link"):
    sidebar.page_link("pages/1_参数设置.py", label="打开参数设置", icon="⚙️")
sidebar.caption("各模块阈值与时钟都在“参数设置”页。")

view = st.radio(
    "模块",
    ["中金所股指", "可转债", "舆情热度", "金属套利", "A50", "加密货币", "报警记录", "系统状态", "软件说明"],
    horizontal=True,
    label_visibility="collapsed",
)

if view == "中金所股指":
    left, mid, right = st.columns([1, 1.2, 4.8])
    refresh_snapshot = False
    force_refresh = False
    with left:
        refresh_snapshot = st.button("刷新显示", key="refresh_futures_snapshot")
    with mid:
        force_refresh = st.button("强制抓新", key="refresh_futures_live")
    with right:
        st.markdown("#### 股指期货套利数据")

    with st.spinner("加载期指实时数据..."):
        if force_refresh:
            futures_df, futures_signal_df, futures_fetched_at, futures_source = force_refresh_live_view(
                "futures_live", fetch_futures_live_view, fetch_futures_snapshot_view
            )
        else:
            if refresh_snapshot:
                clear_snapshot_cache(fetch_futures_snapshot_view)
            futures_df, futures_signal_df, futures_fetched_at, futures_source = load_snapshot_view(
                "futures_live", fetch_futures_snapshot_view, refresh=refresh_snapshot
            )

    render_snapshot_meta("futures", futures_fetched_at, futures_source, "futures_live")

    product_filter = st.multiselect(
        "品种筛选",
        options=sorted(futures_df["品种"].unique().tolist()),
        default=sorted(futures_df["品种"].unique().tolist()),
        key="futures_product_filter",
    )
    if product_filter:
        futures_df = futures_df[futures_df["品种"].isin(product_filter)]

    st.dataframe(futures_df, width="stretch", hide_index=True)
    st.caption(f"当前有效合约数：{len(futures_df)}")

    st.markdown("#### 当前触发信号")
    if futures_signal_df.empty:
        st.info("当前无期指触发信号")
    else:
        st.dataframe(futures_signal_df, width="stretch", hide_index=True)

elif view == "可转债":
    left, mid, right = st.columns([1, 1.2, 4.8])
    refresh_snapshot = False
    force_refresh = False
    with left:
        refresh_snapshot = st.button("刷新显示", key="refresh_cb_snapshot")
    with mid:
        force_refresh = st.button("强制抓新", key="refresh_cb_live")
    with right:
        st.markdown("#### 可转债监控数据")

    with st.spinner("加载可转债实时数据..."):
        if force_refresh:
            cb_df, cb_signal_df, cb_fetched_at, cb_source = force_refresh_live_view(
                "cb_live", fetch_convertible_live_view, fetch_convertible_snapshot_view
            )
        else:
            if refresh_snapshot:
                clear_snapshot_cache(fetch_convertible_snapshot_view)
            cb_df, cb_signal_df, cb_fetched_at, cb_source = load_snapshot_view(
                "cb_live", fetch_convertible_snapshot_view, refresh=refresh_snapshot
            )

    render_snapshot_meta("convertible", cb_fetched_at, cb_source, "cb_live")

    top_n = st.slider("显示前 N 条候选", 20, 300, 80, 20, key="cb_top_n")
    cb_mode = st.radio(
        "排序模式",
        options=["双低优先", "低溢价优先", "高YTM优先"],
        horizontal=True,
        key="cb_sort_mode",
    )
    if cb_mode == "低溢价优先":
        cb_df = cb_df.sort_values(
            by=["溢价率", "双低", "税前YTM"], ascending=[True, True, False]
        )
    elif cb_mode == "高YTM优先":
        cb_df = cb_df.sort_values(by=["税前YTM", "双低"], ascending=[False, True])
    st.dataframe(cb_df.head(top_n), width="stretch", hide_index=True)
    st.caption(f"当前载入转债总数：{len(cb_df)}")

    st.markdown("#### 当前触发信号")
    if cb_signal_df.empty:
        st.info("当前无可转债触发信号")
    else:
        st.dataframe(cb_signal_df.head(100), width="stretch", hide_index=True)

elif view == "舆情热度":
    left, mid, right = st.columns([1, 1.2, 4.8])
    refresh_snapshot = False
    force_refresh = False
    with left:
        refresh_snapshot = st.button("刷新显示", key="refresh_sentiment_snapshot")
    with mid:
        force_refresh = st.button("强制抓新", key="refresh_sentiment_live")
    with right:
        st.markdown("#### 舆情热度监控数据")

    with st.spinner("加载舆情实时数据..."):
        if force_refresh:
            sentiment_df, sentiment_signal_df, sentiment_fetched_at, sentiment_source = force_refresh_live_view(
                "sentiment_live", fetch_sentiment_live_view, fetch_sentiment_snapshot_view
            )
        else:
            if refresh_snapshot:
                clear_snapshot_cache(fetch_sentiment_snapshot_view)
            sentiment_df, sentiment_signal_df, sentiment_fetched_at, sentiment_source = load_snapshot_view(
                "sentiment_live", fetch_sentiment_snapshot_view, refresh=refresh_snapshot
            )

    render_snapshot_meta("sentiment", sentiment_fetched_at, sentiment_source, "sentiment_live")
    st.dataframe(sentiment_df, width="stretch", hide_index=True)
    st.caption(f"当前榜单记录数：{len(sentiment_df)}")

    st.markdown("#### 当前触发信号")
    if sentiment_signal_df.empty:
        st.info("当前无舆情触发信号")
    else:
        st.dataframe(sentiment_signal_df, width="stretch", hide_index=True)

elif view == "金属套利":
    left, mid, right = st.columns([1, 1.2, 4.8])
    refresh_snapshot = False
    force_refresh = False
    with left:
        refresh_snapshot = st.button("刷新显示", key="refresh_metals_snapshot")
    with mid:
        force_refresh = st.button("强制抓新", key="refresh_metals_live")
    with right:
        st.markdown("#### 金属跨市场套利数据")

    if hasattr(st, "page_link"):
        st.page_link("pages/1_参数设置.py", label="去调整金属阈值和模块时钟", icon="⚙️")
    else:
        st.info("金属阈值和模块时钟在左侧多页面导航的“参数设置”页。")

    with st.spinner("加载金属实时数据..."):
        if force_refresh:
            metals_df, metals_signal_df, metals_fetched_at, metals_source = force_refresh_live_view(
                "metals_live", fetch_metals_live_view, fetch_metals_snapshot_view
            )
        else:
            if refresh_snapshot:
                clear_snapshot_cache(fetch_metals_snapshot_view)
            metals_df, metals_signal_df, metals_fetched_at, metals_source = load_snapshot_view(
                "metals_live", fetch_metals_snapshot_view, refresh=refresh_snapshot
            )

    render_snapshot_meta("metals", metals_fetched_at, metals_source, "metals_live")

    category_filter = st.multiselect(
        "分类筛选",
        options=sorted(metals_df["分类"].unique().tolist()),
        default=sorted(metals_df["分类"].unique().tolist()),
        key="metals_category_filter",
    )
    if category_filter:
        metals_df = metals_df[metals_df["分类"].isin(category_filter)]

    st.dataframe(metals_df, width="stretch", hide_index=True)
    st.caption(f"当前套利对数：{len(metals_df)}")

    st.markdown("#### 当前触发信号")
    if metals_signal_df.empty:
        st.info("当前无金属套利触发信号")
    else:
        st.dataframe(metals_signal_df, width="stretch", hide_index=True)

    st.markdown("#### 最近快照历史")
    history_limit = st.slider(
        "历史快照条数", 20, 500, 100, 20, key="metals_history_limit"
    )
    history_df = fetch_recent_metal_snapshot_history(limit=history_limit)
    if history_df.empty:
        st.info("暂无金属快照历史")
    else:
        history_df["fetched_at"] = history_df["fetched_at"].dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        st.dataframe(history_df, width="stretch", hide_index=True)

elif view in {"A50", "加密货币"}:
    a50_only = view == "A50"
    left, mid, right = st.columns([1, 1.2, 4.8])
    refresh_snapshot = False
    force_refresh = False
    with left:
        refresh_snapshot = st.button("刷新显示", key=f"refresh_premium_snapshot_{view}")
    with mid:
        force_refresh = st.button("强制抓新", key=f"refresh_premium_live_{view}")
    with right:
        st.markdown(f"#### {view}")

    if hasattr(st, "page_link"):
        target_label = "去调整 A50 阈值和模块时钟" if a50_only else "去调整加密货币阈值和模块时钟"
        st.page_link("pages/1_参数设置.py", label=target_label, icon="⚙️")
    if a50_only:
        st.caption("A50 维持原有多合约展示，继续复用 premium 模块的抓取与快照链路。")
    else:
        st.caption("加密资产池按 Top10 币种展示永续、当月、次月、近季、次季可用行情。")

    if refresh_snapshot or force_refresh:
        st.session_state.pop(f"premium_asset_filter_{view}", None)

    with st.spinner(f"加载{view}实时数据..."):
        if force_refresh:
            premium_df, premium_signal_df, premium_fetched_at, premium_source = force_refresh_live_view(
                "premium_live", fetch_premium_live_view, fetch_premium_snapshot_view
            )
        else:
            if refresh_snapshot:
                clear_snapshot_cache(fetch_premium_snapshot_view)
            premium_df, premium_signal_df, premium_fetched_at, premium_source = load_snapshot_view(
                "premium_live", fetch_premium_snapshot_view, refresh=refresh_snapshot
            )

    render_snapshot_meta("premium", premium_fetched_at, premium_source, "premium_live")
    premium_df = filter_premium_table(premium_df, a50_only=a50_only)
    premium_signal_df = filter_premium_signal_table(premium_signal_df, a50_only=a50_only)

    if not premium_df.empty and not a50_only:
        asset_filter = st.multiselect(
            "资产组筛选",
            options=sorted(premium_df["资产组"].unique().tolist()),
            default=sorted(premium_df["资产组"].unique().tolist()),
            key=f"premium_asset_filter_{view}",
        )
        if asset_filter:
            premium_df = premium_df[premium_df["资产组"].isin(asset_filter)]
            if not premium_signal_df.empty and "标的" in premium_signal_df.columns:
                premium_signal_df = premium_signal_df[
                    premium_signal_df["标的"].astype(str).str.startswith(
                        tuple(f"{asset} " for asset in asset_filter)
                    )
                ]

    st.dataframe(premium_df, width="stretch", hide_index=True)
    st.caption(f"当前溢价对数：{len(premium_df)}")

    st.markdown("#### 当前触发信号")
    if premium_signal_df.empty:
        st.info(f"当前无{view}触发信号")
    else:
        st.dataframe(premium_signal_df, width="stretch", hide_index=True)

    st.markdown("#### 最近快照历史")
    history_limit = st.slider("历史快照条数", 20, 500, 100, 20, key=f"premium_history_limit_{view}")
    history_df = fetch_recent_premium_snapshot_history(limit=history_limit)
    history_df = prepare_premium_history_table(history_df)
    history_df = history_df[
        history_df["asset_group"].eq("A50") if a50_only else history_df["asset_group"].ne("A50")
    ].copy()
    if history_df.empty:
        st.info(f"暂无{view}快照历史")
    else:
        st.dataframe(history_df, width="stretch", hide_index=True)

elif view == "报警记录":
    st.markdown("#### 历史报警记录")
    latest_limit = st.slider("显示最近记录数", 50, 1000, 200, 50, key="alert_limit")
    alerts_df = fetch_alert_history(limit=latest_limit)
    if alerts_df.empty:
        st.info("暂无报警记录")
    else:
        display_df = alerts_df.copy()
        display_df["timestamp"] = display_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        display_df["level"] = display_df["level"].apply(level_badge)
        display_df["notified"] = display_df["notified"].map({1: "是", 0: "否"})
        st.dataframe(
            display_df[["timestamp", "strategy", "level", "asset", "notified", "message"]],
            width="stretch",
            hide_index=True,
        )

    st.markdown("#### 今日报警汇总")
    summary_df = fetch_today_summary()
    if summary_df.empty:
        st.info("今日暂无报警")
    else:
        summary_df["level"] = summary_df["level"].apply(level_badge)
        st.dataframe(summary_df, width="stretch", hide_index=True)

elif view == "系统状态":
    st.markdown("#### 数据库状态")
    cols = st.columns(4)
    cols[0].metric("今日报警", stats["today_alerts"])
    cols[1].metric("累计报警", stats["total_alerts"])
    cols[2].metric("已送达", stats["notified"])
    cols[3].metric("数据库大小", f"{stats['db_size_kb']} KB")
    cols2 = st.columns(4)
    cols2[0].metric("保证金快照", stats["margin_snapshots"])
    cols2[1].metric("期指快照", stats["futures_snapshots"])
    cols2[2].metric("金属快照", stats["metal_snapshots"])
    cols2[3].metric("溢价快照", stats["premium_snapshots"])
    cols3 = st.columns(4)
    cols3[0].metric("冷却记录", stats["cooldowns"])

    st.markdown("#### 保证金最新快照")
    margin_df = fetch_latest_margin_table()
    if margin_df.empty:
        st.info("暂无保证金快照")
    else:
        st.dataframe(margin_df, width="stretch", hide_index=True)

    st.markdown("#### 最新信号快照")
    latest_df = fetch_latest_signals(limit=10)
    if latest_df.empty:
        st.info("暂无最新信号")
    else:
        latest_df["timestamp"] = latest_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        latest_df["level"] = latest_df["level"].apply(level_badge)
        latest_df["notified"] = latest_df["notified"].map({1: "是", 0: "否"})
        st.dataframe(
            latest_df[["timestamp", "strategy", "level", "asset", "notified"]],
            width="stretch",
            hide_index=True,
        )

    st.markdown("#### 数据源健康度")
    source_health_df = fetch_source_health_table()
    if source_health_df.empty:
        st.info("暂无数据源健康度记录")
    else:
        st.dataframe(source_health_df, width="stretch", hide_index=True)

    st.markdown("#### 任务运行状态")
    job_status_df = fetch_job_run_status_table()
    if job_status_df.empty:
        st.info("暂无任务运行状态记录")
    else:
        st.dataframe(job_status_df, width="stretch", hide_index=True)

elif view == "软件说明":
    st.markdown("#### 软件说明")
    st.markdown(
        """
当前看板的显示思路参考老版 Tkinter GUI：

- 每个模块独立页面
- 每页先看整张数据表，再看触发信号
- 用显式“刷新”替代隐式自动轮询
- 保留数据库与历史报警页用于复盘

本版还做了一个关键性能优化：

- dashboard 默认读取数据库中的最新快照，不再把“刷新显示”直接绑定到联网抓取
- 不再因为页面上其他控件变化，把其他模块一起重抓一遍
- 每页都提供“强制抓新”作为兜底，仅在你明确需要时才联网更新当前模块

当前对应关系：

- `中金所股指`：展示期指实时行情、贴水率、年化贴水、保证金占用
- `可转债`：展示实时转债候选与当前触发信号
- `舆情热度`：展示实时榜单与风险信号
- `金属套利`：展示国内外金属套利对、触发信号和快照历史
- `A50 以及加密货币`：展示 A50 多合约与 Top10 加密资产池的期现溢价对、触发信号和快照历史
- `报警记录`：展示历史报警与今日汇总
- `系统状态`：展示数据库、保证金快照、期指/金属/溢价快照、最新信号
        """
    )
