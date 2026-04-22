import pandas as pd
import streamlit as st

from config.settings import settings
from utils.config_audit import (
    flatten_futures_threshold_values,
    flatten_premium_threshold_values,
    flatten_threshold_values,
    record_config_changes,
)
from utils.db_manager import DBManager
from utils.futures_config import (
    get_futures_config_rows,
    reset_futures_thresholds,
    save_futures_thresholds,
)
from utils.metals_config import (
    get_legacy_metals_thresholds_preview,
    get_metals_config_rows,
    migrate_legacy_metals_thresholds,
    reset_metals_thresholds,
    save_metals_thresholds,
)
from utils.premium_config import (
    CRYPTO_PREMIUM_ASSETS,
    DEFAULT_PREMIUM_THRESHOLDS,
    get_premium_config_rows,
    save_premium_thresholds,
)
from utils.runtime_config import apply_runtime_updates, get_gui_config_values, write_env_updates


st.set_page_config(page_title="参数设置", page_icon="⚙️", layout="wide")

st.title("⚙️ 参数设置")
st.caption(
    "参数页已按模块重组。每个模块的开关、时钟和阈值都放在同一个面板里，并支持模块级单独保存。"
)
st.caption(
    "仓库里的 `config/*.json` 是共享基线；GUI 保存会写入本机的 `config/*.local.json`，因此不会被 `git pull` 覆盖。"
)

db_manager = DBManager()
settings.reload_from_env()
current = get_gui_config_values()


FUTURES_RUNTIME_FIELDS = [
    "ENABLE_FUTURES_MONITOR",
    "ENABLE_FUTURES_CRUISE",
    "ENABLE_FUTURES_WATCH",
    "FUTURES_CRUISE_INTERVAL_MINUTES",
    "FUTURES_WATCH_INTERVAL_SECONDS",
    "FUTURES_MORNING_START",
    "FUTURES_MORNING_END",
    "FUTURES_AFTERNOON_START",
    "FUTURES_AFTERNOON_END",
    "FUTURES_NIGHT_START",
    "FUTURES_NIGHT_END",
]
CONVERTIBLE_FIELDS = [
    "ENABLE_CONVERTIBLE_MONITOR",
    "ENABLE_CONVERTIBLE_CRUISE",
    "ENABLE_CONVERTIBLE_WATCH",
    "CONVERTIBLE_CRUISE_INTERVAL_MINUTES",
    "CONVERTIBLE_WATCH_INTERVAL_SECONDS",
    "CONVERTIBLE_MORNING_START",
    "CONVERTIBLE_MORNING_END",
    "CONVERTIBLE_AFTERNOON_START",
    "CONVERTIBLE_AFTERNOON_END",
    "CONVERTIBLE_NIGHT_START",
    "CONVERTIBLE_NIGHT_END",
    "ENABLE_CB_NEGATIVE_PREMIUM_THRESHOLD",
    "CB_NEGATIVE_PREMIUM_THRESHOLD",
    "ENABLE_CB_SAFE_PRICE_THRESHOLD",
    "CB_SAFE_PRICE_THRESHOLD",
    "ENABLE_CB_DOUBLE_LOW_THRESHOLD",
    "CB_DOUBLE_LOW_THRESHOLD",
    "ENABLE_CB_YTM_THRESHOLD",
    "CB_YTM_THRESHOLD",
]
SENTIMENT_FIELDS = [
    "ENABLE_SENTIMENT_MONITOR",
    "ENABLE_SENTIMENT_CRUISE",
    "SENTIMENT_CRUISE_INTERVAL_MINUTES",
    "SENTIMENT_MORNING_START",
    "SENTIMENT_MORNING_END",
    "SENTIMENT_AFTERNOON_START",
    "SENTIMENT_AFTERNOON_END",
    "SENTIMENT_NIGHT_START",
    "SENTIMENT_NIGHT_END",
    "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD",
    "SENTIMENT_HOT_SCORE_THRESHOLD",
    "ENABLE_SENTIMENT_PULSE_THRESHOLD",
    "SENTIMENT_PULSE_THRESHOLD",
]
METALS_RUNTIME_FIELDS = [
    "ENABLE_METALS_MONITOR",
    "ENABLE_METALS_CRUISE",
    "ENABLE_METALS_WATCH",
    "METALS_CRUISE_INTERVAL_MINUTES",
    "METALS_WATCH_INTERVAL_SECONDS",
    "METALS_MORNING_START",
    "METALS_MORNING_END",
    "METALS_AFTERNOON_START",
    "METALS_AFTERNOON_END",
    "METALS_NIGHT_START",
    "METALS_NIGHT_END",
]
PREMIUM_RUNTIME_FIELDS = [
    "ENABLE_PREMIUM_MONITOR",
    "ENABLE_PREMIUM_CRUISE",
    "ENABLE_PREMIUM_WATCH",
    "PREMIUM_CRUISE_INTERVAL_MINUTES",
    "PREMIUM_WATCH_INTERVAL_SECONDS",
    "PREMIUM_MORNING_START",
    "PREMIUM_MORNING_END",
    "PREMIUM_AFTERNOON_START",
    "PREMIUM_AFTERNOON_END",
    "PREMIUM_NIGHT_START",
    "PREMIUM_NIGHT_END",
]
SYSTEM_FIELDS = ["COOLDOWN_MINUTES", "DATA_RETENTION_DAYS"]


def build_history_df(limit: int = 200) -> pd.DataFrame:
    rows = db_manager.get_recent_config_changes(limit=limit)
    if not rows:
        return pd.DataFrame(
            columns=[
                "changed_at",
                "config_key",
                "old_value",
                "new_value",
                "source",
                "destination",
                "immediate_effect",
            ]
        )
    return pd.DataFrame(
        rows,
        columns=[
            "changed_at",
            "config_key",
            "old_value",
            "new_value",
            "source",
            "destination",
            "immediate_effect",
        ],
    )


history_df = build_history_df()


def render_history_table(
    *,
    prefixes: tuple[str, ...] = (),
    exact_keys: tuple[str, ...] = (),
    empty_text: str = "暂无该模块配置变更记录",
) -> None:
    if history_df.empty:
        st.info(empty_text)
        return

    filtered = history_df[
        history_df["config_key"].apply(
            lambda key: key in exact_keys or any(str(key).startswith(prefix) for prefix in prefixes)
        )
    ].copy()

    if filtered.empty:
        st.info(empty_text)
        return

    filtered = filtered.rename(
        columns={
            "changed_at": "变更时间",
            "config_key": "配置项",
            "old_value": "旧值",
            "new_value": "新值",
            "source": "来源",
            "destination": "写入位置",
            "immediate_effect": "立即生效",
        }
    )
    filtered["立即生效"] = filtered["立即生效"].map({1: "是", 0: "否", True: "是", False: "否"})
    st.dataframe(filtered, use_container_width=True, hide_index=True)


def render_time_window(
    prefix: str,
    values: dict[str, object],
    *,
    key_prefix: str | None = None,
) -> dict[str, str]:
    key_base = key_prefix or prefix
    st.markdown("**时间窗口**")
    col1, col2 = st.columns(2)
    with col1:
        morning_start = st.text_input(
            "上午开始", value=str(values[f"{prefix}_MORNING_START"]), key=f"{key_base}_morning_start"
        )
        afternoon_start = st.text_input(
            "下午开始", value=str(values[f"{prefix}_AFTERNOON_START"]), key=f"{key_base}_afternoon_start"
        )
        night_start = st.text_input(
            "夜盘开始", value=str(values[f"{prefix}_NIGHT_START"]), key=f"{key_base}_night_start"
        )
    with col2:
        morning_end = st.text_input(
            "上午结束", value=str(values[f"{prefix}_MORNING_END"]), key=f"{key_base}_morning_end"
        )
        afternoon_end = st.text_input(
            "下午结束", value=str(values[f"{prefix}_AFTERNOON_END"]), key=f"{key_base}_afternoon_end"
        )
        night_end = st.text_input(
            "夜盘结束", value=str(values[f"{prefix}_NIGHT_END"]), key=f"{key_base}_night_end"
        )

    return {
        f"{prefix}_MORNING_START": morning_start.strip(),
        f"{prefix}_MORNING_END": morning_end.strip(),
        f"{prefix}_AFTERNOON_START": afternoon_start.strip(),
        f"{prefix}_AFTERNOON_END": afternoon_end.strip(),
        f"{prefix}_NIGHT_START": night_start.strip(),
        f"{prefix}_NIGHT_END": night_end.strip(),
    }


def render_threshold_header(widths: list[float], labels: list[str]) -> None:
    header_cols = st.columns(widths)
    for col, label in zip(header_cols, labels):
        col.markdown(f"**{label}**")


def build_premium_threshold_payload(rows: list[dict[str, object]]) -> dict[str, dict[str, float | bool]]:
    payload: dict[str, dict[str, float | bool]] = {}
    for row in rows:
        threshold_key = str(row["threshold_key"])
        payload[threshold_key] = {
            "upper_enabled": bool(row["upper_enabled"]),
            "upper": float(row["upper"]),
            "annualized_upper_enabled": bool(row["annualized_upper_enabled"]),
            "annualized_upper": float(row["annualized_upper"]),
            "lower_enabled": bool(row["lower_enabled"]),
            "lower": float(row["lower"]),
            "annualized_lower_enabled": bool(row["annualized_lower_enabled"]),
            "annualized_lower": float(row["annualized_lower"]),
        }
    return payload


def reset_premium_threshold_group(threshold_keys: list[str]) -> None:
    threshold_payload = build_premium_threshold_payload(get_premium_config_rows())
    for threshold_key in threshold_keys:
        threshold_payload[threshold_key] = dict(DEFAULT_PREMIUM_THRESHOLDS[threshold_key])
    save_premium_thresholds(threshold_payload)


def save_runtime_module(updates: dict[str, object], tracked_fields: list[str], *, success_text: str) -> None:
    previous = {field: current[field] for field in tracked_fields}
    config_path = write_env_updates(updates)
    apply_runtime_updates(updates)
    latest = get_gui_config_values()
    destination = "local_override" if config_path.name.endswith(".local.json") else "shared_baseline"
    record_config_changes(
        previous,
        {field: latest[field] for field in tracked_fields},
        source="dashboard_gui",
        destination=destination,
    )
    st.success(f"{success_text} 已保存到 {config_path.name}，当前进程已热更新。")


with st.expander("股指期货", expanded=True):
    st.caption("股指期货的监控开关、巡航/盯盘、时间窗口和 `IH/IF/IC/IM` 分品种阈值都在这里。")
    futures_rows = get_futures_config_rows()
    futures_before = flatten_futures_threshold_values(futures_rows)
    with st.form("futures_module_form"):
        st.markdown("**模块开关**")
        col1, col2, col3 = st.columns(3)
        enable_futures = col1.toggle("启用股指期货监控", value=current["ENABLE_FUTURES_MONITOR"])
        enable_futures_cruise = col2.checkbox("启用巡航", value=current["ENABLE_FUTURES_CRUISE"])
        enable_futures_watch = col3.checkbox("启用盯盘", value=current["ENABLE_FUTURES_WATCH"])

        st.markdown("**运行频率**")
        col1, col2 = st.columns(2)
        futures_cruise = col1.number_input(
            "巡航间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["FUTURES_CRUISE_INTERVAL_MINUTES"]),
            step=1,
        )
        futures_watch = col2.number_input(
            "盯盘间隔 (秒)",
            min_value=5,
            max_value=3600,
            value=int(current["FUTURES_WATCH_INTERVAL_SECONDS"]),
            step=5,
        )

        futures_windows = render_time_window("FUTURES", current)

        st.markdown("**分品种阈值**")
        futures_threshold_widths = [0.8, 1.2, 0.8, 1, 0.8, 1.1, 0.8, 1, 0.8, 1.1]
        render_threshold_header(
            futures_threshold_widths,
            [
                "品种",
                "名称",
                "升水启用",
                "升水阈值(%)",
                "年化升水启用",
                "年化升水阈值(%)",
                "贴水启用",
                "贴水阈值(%)",
                "年化贴水启用",
                "年化贴水阈值(%)",
            ],
        )
        futures_threshold_updates: dict[str, dict[str, float | bool]] = {}
        for row in futures_rows:
            cols = st.columns(futures_threshold_widths)
            cols[0].markdown(f"`{row['product_code']}`")
            cols[1].markdown(row["name"])
            upper_enabled = cols[2].checkbox(
                f"{row['product_code']}_upper_enabled",
                value=bool(row["upper_enabled"]),
                label_visibility="collapsed",
                key=f"futures_threshold_upper_enabled_{row['product_code']}",
            )
            upper_threshold = cols[3].number_input(
                f"{row['product_code']}_upper_threshold",
                min_value=0.0,
                max_value=1000.0,
                value=float(row["upper"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"futures_threshold_upper_{row['product_code']}",
            )
            annualized_upper_enabled = cols[4].checkbox(
                f"{row['product_code']}_annualized_upper_enabled",
                value=bool(row.get("annualized_upper_enabled", True)),
                label_visibility="collapsed",
                key=f"futures_threshold_annualized_upper_enabled_{row['product_code']}",
            )
            annualized_upper_threshold = cols[5].number_input(
                f"{row['product_code']}_annualized_upper",
                min_value=0.0,
                max_value=1000.0,
                value=float(row["annualized_upper"]),
                step=0.5,
                label_visibility="collapsed",
                key=f"futures_threshold_annualized_upper_{row['product_code']}",
            )
            lower_enabled = cols[6].checkbox(
                f"{row['product_code']}_lower_enabled",
                value=bool(row["lower_enabled"]),
                label_visibility="collapsed",
                key=f"futures_threshold_lower_enabled_{row['product_code']}",
            )
            lower_threshold = cols[7].number_input(
                f"{row['product_code']}_lower_threshold",
                min_value=-1000.0,
                max_value=0.0,
                value=float(row["lower"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"futures_threshold_lower_{row['product_code']}",
            )
            annualized_lower_enabled = cols[8].checkbox(
                f"{row['product_code']}_annualized_lower_enabled",
                value=bool(row.get("annualized_lower_enabled", True)),
                label_visibility="collapsed",
                key=f"futures_threshold_annualized_lower_enabled_{row['product_code']}",
            )
            annualized_lower_threshold = cols[9].number_input(
                f"{row['product_code']}_annualized_lower",
                min_value=-1000.0,
                max_value=0.0,
                value=float(row["annualized_lower"]),
                step=0.5,
                label_visibility="collapsed",
                key=f"futures_threshold_annualized_lower_{row['product_code']}",
            )
            futures_threshold_updates[row["product_code"]] = {
                "upper_enabled": bool(upper_enabled),
                "upper": float(upper_threshold),
                "annualized_upper_enabled": bool(annualized_upper_enabled),
                "annualized_upper": float(annualized_upper_threshold),
                "lower_enabled": bool(lower_enabled),
                "lower": float(lower_threshold),
                "annualized_lower_enabled": bool(annualized_lower_enabled),
                "annualized_lower": float(annualized_lower_threshold),
            }

        save_futures = st.form_submit_button("保存股指期货设置", use_container_width=True)
        reset_futures = st.form_submit_button("恢复期指阈值默认值")

    if save_futures:
        runtime_updates = {
            "ENABLE_FUTURES_MONITOR": enable_futures,
            "ENABLE_FUTURES_CRUISE": enable_futures_cruise,
            "ENABLE_FUTURES_WATCH": enable_futures_watch,
            "FUTURES_CRUISE_INTERVAL_MINUTES": int(futures_cruise),
            "FUTURES_WATCH_INTERVAL_SECONDS": int(futures_watch),
        }
        runtime_updates.update(futures_windows)
        try:
            save_runtime_module(runtime_updates, FUTURES_RUNTIME_FIELDS, success_text="股指期货运行配置")
            path = save_futures_thresholds(futures_threshold_updates)
            after_rows = get_futures_config_rows()
            record_config_changes(
                futures_before,
                flatten_futures_threshold_values(after_rows),
                source="dashboard_gui",
                destination="local_override" if path.name.endswith(".local.json") else "shared_baseline",
            )
            st.success(f"股指期货分品种阈值已保存到 {path.name}。")
        except Exception as exc:
            st.error(f"保存股指期货设置失败：{exc}")

    if reset_futures:
        try:
            path = reset_futures_thresholds()
            after_rows = get_futures_config_rows()
            record_config_changes(
                futures_before,
                flatten_futures_threshold_values(after_rows),
                source="dashboard_gui",
                destination="shared_baseline",
            )
            st.success(f"期指阈值已恢复为共享基线，当前使用 {path.name}。")
        except Exception as exc:
            st.error(f"恢复期指阈值失败：{exc}")

    st.markdown("**最近变更**")
    render_history_table(prefixes=("ENABLE_FUTURES_", "FUTURES_", "FUTURES_THRESHOLD."))


premium_rows = get_premium_config_rows()
premium_before = flatten_premium_threshold_values(premium_rows)
a50_rows = [row for row in premium_rows if row["market"] == "A50"]
crypto_rows = [row for row in premium_rows if row["market"] == "CRYPTO"]
a50_threshold_keys = [str(row["threshold_key"]) for row in a50_rows]
crypto_threshold_keys = [str(row["threshold_key"]) for row in crypto_rows]
crypto_threshold_prefixes = tuple(
    f"PREMIUM_THRESHOLD.{asset_group}_" for asset_group in CRYPTO_PREMIUM_ASSETS
)


with st.expander("A50", expanded=False):
    st.caption("A50 区块内直接维护运行时和阈值。运行时仍对应同一套 premium 模块字段，不会拆成第二套任务。")
    with st.form("premium_a50_form"):
        st.markdown("**模块开关**")
        col1, col2, col3 = st.columns(3)
        enable_premium = col1.toggle("启用 A50 监控", value=current["ENABLE_PREMIUM_MONITOR"])
        enable_premium_cruise = col2.checkbox("启用巡航", value=current["ENABLE_PREMIUM_CRUISE"])
        enable_premium_watch = col3.checkbox("启用盯盘", value=current["ENABLE_PREMIUM_WATCH"])

        st.markdown("**运行频率**")
        col1, col2 = st.columns(2)
        premium_cruise = col1.number_input(
            "巡航间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["PREMIUM_CRUISE_INTERVAL_MINUTES"]),
            step=1,
            key="premium_a50_cruise",
        )
        premium_watch = col2.number_input(
            "盯盘间隔 (秒)",
            min_value=5,
            max_value=3600,
            value=int(current["PREMIUM_WATCH_INTERVAL_SECONDS"]),
            step=5,
            key="premium_a50_watch",
        )

        premium_windows = render_time_window("PREMIUM", current, key_prefix="PREMIUM_A50")

        st.markdown("**A50 阈值**")
        premium_threshold_widths = [0.9, 1.2, 0.8, 1, 0.8, 1.1, 0.8, 1, 0.8, 1.1]
        render_threshold_header(
            premium_threshold_widths,
            [
                "键",
                "名称",
                "升水启用",
                "升水阈值(%)",
                "年化升水启用",
                "年化升水阈值(%)",
                "贴水启用",
                "贴水阈值(%)",
                "年化贴水启用",
                "年化贴水阈值(%)",
            ],
        )
        premium_threshold_updates = build_premium_threshold_payload(premium_rows)
        for row in a50_rows:
            cols = st.columns(premium_threshold_widths)
            threshold_key = row["threshold_key"]
            cols[0].markdown(f"`{threshold_key}`")
            cols[1].markdown(row["name"])
            upper_enabled = cols[2].checkbox(
                f"{threshold_key}_upper_enabled",
                value=bool(row.get("upper_enabled", True)),
                label_visibility="collapsed",
                key=f"premium_a50_upper_enabled_{threshold_key}",
            )
            upper_threshold = cols[3].number_input(
                f"{threshold_key}_upper",
                min_value=0.0,
                value=float(row["upper"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"premium_a50_upper_{threshold_key}",
            )
            annualized_upper_enabled = cols[4].checkbox(
                f"{threshold_key}_annualized_upper_enabled",
                value=bool(row.get("annualized_upper_enabled", True)),
                label_visibility="collapsed",
                key=f"premium_a50_annualized_upper_enabled_{threshold_key}",
            )
            annualized_upper_threshold = cols[5].number_input(
                f"{threshold_key}_annualized_upper",
                min_value=0.0,
                value=float(row["annualized_upper"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"premium_a50_annualized_upper_{threshold_key}",
            )
            lower_enabled = cols[6].checkbox(
                f"{threshold_key}_lower_enabled",
                value=bool(row.get("lower_enabled", True)),
                label_visibility="collapsed",
                key=f"premium_a50_lower_enabled_{threshold_key}",
            )
            lower_threshold = cols[7].number_input(
                f"{threshold_key}_lower",
                max_value=0.0,
                value=float(row["lower"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"premium_a50_lower_{threshold_key}",
            )
            annualized_lower_enabled = cols[8].checkbox(
                f"{threshold_key}_annualized_lower_enabled",
                value=bool(row.get("annualized_lower_enabled", True)),
                label_visibility="collapsed",
                key=f"premium_a50_annualized_lower_enabled_{threshold_key}",
            )
            annualized_lower_threshold = cols[9].number_input(
                f"{threshold_key}_annualized_lower",
                max_value=0.0,
                value=float(row["annualized_lower"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"premium_a50_annualized_lower_{threshold_key}",
            )
            premium_threshold_updates[threshold_key] = {
                "upper_enabled": bool(upper_enabled),
                "upper": float(upper_threshold),
                "annualized_upper_enabled": bool(annualized_upper_enabled),
                "annualized_upper": float(annualized_upper_threshold),
                "lower_enabled": bool(lower_enabled),
                "lower": float(lower_threshold),
                "annualized_lower_enabled": bool(annualized_lower_enabled),
                "annualized_lower": float(annualized_lower_threshold),
            }

        save_premium_a50 = st.form_submit_button("保存 A50 设置", use_container_width=True)

    if save_premium_a50:
        premium_runtime_updates = {
            "ENABLE_PREMIUM_MONITOR": enable_premium,
            "ENABLE_PREMIUM_CRUISE": enable_premium_cruise,
            "ENABLE_PREMIUM_WATCH": enable_premium_watch,
            "PREMIUM_CRUISE_INTERVAL_MINUTES": int(premium_cruise),
            "PREMIUM_WATCH_INTERVAL_SECONDS": int(premium_watch),
        }
        premium_runtime_updates.update(premium_windows)
        try:
            save_runtime_module(
                premium_runtime_updates,
                PREMIUM_RUNTIME_FIELDS,
                success_text="A50 运行配置",
            )
            path = save_premium_thresholds(premium_threshold_updates)
            after_rows = get_premium_config_rows()
            record_config_changes(
                premium_before,
                flatten_premium_threshold_values(after_rows),
                source="dashboard_gui",
                destination="local_override" if path.name.endswith(".local.json") else "shared_baseline",
            )
            st.success(f"A50 阈值已保存到 {path.name}。")
        except Exception as exc:
            st.error(f"保存 A50 设置失败：{exc}")

    if st.button("恢复 A50 阈值默认值", key="reset_premium_a50", use_container_width=True):
        try:
            reset_premium_threshold_group(a50_threshold_keys)
            after_rows = get_premium_config_rows()
            record_config_changes(
                premium_before,
                flatten_premium_threshold_values(after_rows),
                source="dashboard_gui",
                destination="local_override",
            )
            st.success("A50 阈值已恢复为默认值。")
        except Exception as exc:
            st.error(f"恢复 A50 阈值失败：{exc}")

    st.markdown("**最近变更**")
    render_history_table(prefixes=("ENABLE_PREMIUM_", "PREMIUM_", "PREMIUM_THRESHOLD.A50"))


with st.expander("加密货币", expanded=False):
    st.caption("加密货币区块内直接维护运行时和阈值。每个币种只保留两组阈值：永续单独一组，其他交割合约共用一组。")
    with st.form("premium_crypto_form"):
        st.markdown("**模块开关**")
        col1, col2, col3 = st.columns(3)
        enable_premium = col1.toggle("启用加密货币监控", value=current["ENABLE_PREMIUM_MONITOR"])
        enable_premium_cruise = col2.checkbox("启用巡航", value=current["ENABLE_PREMIUM_CRUISE"])
        enable_premium_watch = col3.checkbox("启用盯盘", value=current["ENABLE_PREMIUM_WATCH"])

        st.markdown("**运行频率**")
        col1, col2 = st.columns(2)
        premium_cruise = col1.number_input(
            "巡航间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["PREMIUM_CRUISE_INTERVAL_MINUTES"]),
            step=1,
            key="premium_crypto_cruise",
        )
        premium_watch = col2.number_input(
            "盯盘间隔 (秒)",
            min_value=5,
            max_value=3600,
            value=int(current["PREMIUM_WATCH_INTERVAL_SECONDS"]),
            step=5,
            key="premium_crypto_watch",
        )

        premium_windows = render_time_window("PREMIUM", current, key_prefix="PREMIUM_CRYPTO")

        st.markdown("**加密货币阈值**")
        crypto_threshold_widths = [0.9, 0.9, 1.1, 0.8, 1, 0.8, 1.1, 0.8, 1, 0.8, 1.1]
        render_threshold_header(
            crypto_threshold_widths,
            [
                "资产",
                "阈值组",
                "名称",
                "升水启用",
                "升水阈值(%)",
                "年化升水启用",
                "年化升水阈值(%)",
                "贴水启用",
                "贴水阈值(%)",
                "年化贴水启用",
                "年化贴水阈值(%)",
            ],
        )
        premium_threshold_updates = build_premium_threshold_payload(premium_rows)
        for row in crypto_rows:
            cols = st.columns(crypto_threshold_widths)
            threshold_key = row["threshold_key"]
            cols[0].markdown(f"`{row['asset_group']}`")
            cols[1].markdown(row["bucket_label"])
            cols[2].markdown(row["name"])
            upper_enabled = cols[3].checkbox(
                f"{threshold_key}_upper_enabled",
                value=bool(row.get("upper_enabled", True)),
                label_visibility="collapsed",
                key=f"premium_crypto_upper_enabled_{threshold_key}",
            )
            upper_threshold = cols[4].number_input(
                f"{threshold_key}_upper",
                min_value=0.0,
                value=float(row["upper"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"premium_crypto_upper_{threshold_key}",
            )
            annualized_upper_enabled = cols[5].checkbox(
                f"{threshold_key}_annualized_upper_enabled",
                value=bool(row.get("annualized_upper_enabled", True)),
                label_visibility="collapsed",
                key=f"premium_crypto_annualized_upper_enabled_{threshold_key}",
            )
            annualized_upper_threshold = cols[6].number_input(
                f"{threshold_key}_annualized_upper",
                min_value=0.0,
                value=float(row["annualized_upper"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"premium_crypto_annualized_upper_{threshold_key}",
            )
            lower_enabled = cols[7].checkbox(
                f"{threshold_key}_lower_enabled",
                value=bool(row.get("lower_enabled", True)),
                label_visibility="collapsed",
                key=f"premium_crypto_lower_enabled_{threshold_key}",
            )
            lower_threshold = cols[8].number_input(
                f"{threshold_key}_lower",
                max_value=0.0,
                value=float(row["lower"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"premium_crypto_lower_{threshold_key}",
            )
            annualized_lower_enabled = cols[9].checkbox(
                f"{threshold_key}_annualized_lower_enabled",
                value=bool(row.get("annualized_lower_enabled", True)),
                label_visibility="collapsed",
                key=f"premium_crypto_annualized_lower_enabled_{threshold_key}",
            )
            annualized_lower_threshold = cols[10].number_input(
                f"{threshold_key}_annualized_lower",
                max_value=0.0,
                value=float(row["annualized_lower"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"premium_crypto_annualized_lower_{threshold_key}",
            )
            premium_threshold_updates[threshold_key] = {
                "upper_enabled": bool(upper_enabled),
                "upper": float(upper_threshold),
                "annualized_upper_enabled": bool(annualized_upper_enabled),
                "annualized_upper": float(annualized_upper_threshold),
                "lower_enabled": bool(lower_enabled),
                "lower": float(lower_threshold),
                "annualized_lower_enabled": bool(annualized_lower_enabled),
                "annualized_lower": float(annualized_lower_threshold),
            }

        save_premium_crypto = st.form_submit_button("保存加密货币设置", use_container_width=True)

    if save_premium_crypto:
        premium_runtime_updates = {
            "ENABLE_PREMIUM_MONITOR": enable_premium,
            "ENABLE_PREMIUM_CRUISE": enable_premium_cruise,
            "ENABLE_PREMIUM_WATCH": enable_premium_watch,
            "PREMIUM_CRUISE_INTERVAL_MINUTES": int(premium_cruise),
            "PREMIUM_WATCH_INTERVAL_SECONDS": int(premium_watch),
        }
        premium_runtime_updates.update(premium_windows)
        try:
            save_runtime_module(
                premium_runtime_updates,
                PREMIUM_RUNTIME_FIELDS,
                success_text="加密货币运行配置",
            )
            path = save_premium_thresholds(premium_threshold_updates)
            after_rows = get_premium_config_rows()
            record_config_changes(
                premium_before,
                flatten_premium_threshold_values(after_rows),
                source="dashboard_gui",
                destination="local_override" if path.name.endswith(".local.json") else "shared_baseline",
            )
            st.success(f"加密货币阈值已保存到 {path.name}。")
        except Exception as exc:
            st.error(f"保存加密货币设置失败：{exc}")

    if st.button("恢复加密货币阈值默认值", key="reset_premium_crypto", use_container_width=True):
        try:
            reset_premium_threshold_group(crypto_threshold_keys)
            after_rows = get_premium_config_rows()
            record_config_changes(
                premium_before,
                flatten_premium_threshold_values(after_rows),
                source="dashboard_gui",
                destination="local_override",
            )
            st.success("加密货币阈值已恢复为默认值。")
        except Exception as exc:
            st.error(f"恢复加密货币阈值失败：{exc}")

    st.markdown("**最近变更**")
    render_history_table(prefixes=("ENABLE_PREMIUM_", "PREMIUM_", *crypto_threshold_prefixes))


with st.expander("可转债", expanded=False):
    st.caption("可转债模块的监控开关、时钟和负溢价/安全价格/双低/YTM 阈值都在这里。")
    with st.form("convertible_module_form"):
        st.markdown("**模块开关**")
        col1, col2, col3 = st.columns(3)
        enable_convertible = col1.toggle("启用可转债监控", value=current["ENABLE_CONVERTIBLE_MONITOR"])
        enable_convertible_cruise = col2.checkbox("启用巡航", value=current["ENABLE_CONVERTIBLE_CRUISE"])
        enable_convertible_watch = col3.checkbox("启用盯盘", value=current["ENABLE_CONVERTIBLE_WATCH"])

        st.markdown("**运行频率**")
        col1, col2 = st.columns(2)
        convertible_cruise = col1.number_input(
            "巡航间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["CONVERTIBLE_CRUISE_INTERVAL_MINUTES"]),
            step=1,
        )
        convertible_watch = col2.number_input(
            "盯盘间隔 (秒)",
            min_value=5,
            max_value=3600,
            value=int(current["CONVERTIBLE_WATCH_INTERVAL_SECONDS"]),
            step=5,
        )

        convertible_windows = render_time_window("CONVERTIBLE", current)

        st.markdown("**策略阈值**")
        col1, col2 = st.columns(2)
        with col1:
            enable_cb_negative_premium = st.checkbox(
                "启用负溢价阈值",
                value=current["ENABLE_CB_NEGATIVE_PREMIUM_THRESHOLD"],
            )
            cb_negative_premium = st.number_input(
                "负溢价阈值 (%)",
                min_value=-100.0,
                max_value=100.0,
                value=float(current["CB_NEGATIVE_PREMIUM_THRESHOLD"]),
                step=0.1,
                disabled=not enable_cb_negative_premium,
            )
            enable_cb_safe_price = st.checkbox(
                "启用安全价格上限",
                value=current["ENABLE_CB_SAFE_PRICE_THRESHOLD"],
            )
            cb_safe_price = st.number_input(
                "安全价格上限",
                min_value=0.0,
                max_value=1000.0,
                value=float(current["CB_SAFE_PRICE_THRESHOLD"]),
                step=1.0,
                disabled=not enable_cb_safe_price,
            )
        with col2:
            enable_cb_double_low = st.checkbox(
                "启用双低阈值",
                value=current["ENABLE_CB_DOUBLE_LOW_THRESHOLD"],
            )
            cb_double_low = st.number_input(
                "双低阈值",
                min_value=0.0,
                max_value=1000.0,
                value=float(current["CB_DOUBLE_LOW_THRESHOLD"]),
                step=1.0,
                disabled=not enable_cb_double_low,
            )
            enable_cb_ytm = st.checkbox(
                "启用税前 YTM 下限",
                value=current["ENABLE_CB_YTM_THRESHOLD"],
            )
            cb_ytm = st.number_input(
                "税前 YTM 下限 (%)",
                min_value=-100.0,
                max_value=1000.0,
                value=float(current["CB_YTM_THRESHOLD"]),
                step=0.1,
                disabled=not enable_cb_ytm,
            )

        save_convertible = st.form_submit_button("保存可转债设置", use_container_width=True)

    if save_convertible:
        convertible_updates = {
            "ENABLE_CONVERTIBLE_MONITOR": enable_convertible,
            "ENABLE_CONVERTIBLE_CRUISE": enable_convertible_cruise,
            "ENABLE_CONVERTIBLE_WATCH": enable_convertible_watch,
            "CONVERTIBLE_CRUISE_INTERVAL_MINUTES": int(convertible_cruise),
            "CONVERTIBLE_WATCH_INTERVAL_SECONDS": int(convertible_watch),
            "ENABLE_CB_NEGATIVE_PREMIUM_THRESHOLD": enable_cb_negative_premium,
            "CB_NEGATIVE_PREMIUM_THRESHOLD": cb_negative_premium,
            "ENABLE_CB_SAFE_PRICE_THRESHOLD": enable_cb_safe_price,
            "CB_SAFE_PRICE_THRESHOLD": cb_safe_price,
            "ENABLE_CB_DOUBLE_LOW_THRESHOLD": enable_cb_double_low,
            "CB_DOUBLE_LOW_THRESHOLD": cb_double_low,
            "ENABLE_CB_YTM_THRESHOLD": enable_cb_ytm,
            "CB_YTM_THRESHOLD": cb_ytm,
        }
        convertible_updates.update(convertible_windows)
        try:
            save_runtime_module(convertible_updates, CONVERTIBLE_FIELDS, success_text="可转债配置")
        except Exception as exc:
            st.error(f"保存可转债设置失败：{exc}")

    st.markdown("**最近变更**")
    render_history_table(prefixes=("ENABLE_CONVERTIBLE_", "CONVERTIBLE_", "ENABLE_CB_", "CB_"))


with st.expander("舆情", expanded=False):
    st.caption("舆情模块的监控开关、运行窗口和阈值都在这里。")
    with st.form("sentiment_module_form"):
        st.markdown("**模块开关**")
        col1, col2 = st.columns(2)
        enable_sentiment = col1.toggle("启用舆情监控", value=current["ENABLE_SENTIMENT_MONITOR"])
        enable_sentiment_cruise = col2.checkbox("启用巡航", value=current["ENABLE_SENTIMENT_CRUISE"])

        st.markdown("**运行频率**")
        sentiment_cruise = st.number_input(
            "低频间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["SENTIMENT_CRUISE_INTERVAL_MINUTES"]),
            step=1,
        )

        sentiment_windows = render_time_window("SENTIMENT", current)

        st.markdown("**策略阈值**")
        col1, col2 = st.columns(2)
        with col1:
            enable_sentiment_hot_score = st.checkbox(
                "启用热度异常阈值",
                value=current["ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD"],
            )
            sentiment_hot_score = st.number_input(
                "热度异常阈值",
                min_value=0,
                max_value=100_000_000,
                value=int(current["SENTIMENT_HOT_SCORE_THRESHOLD"]),
                step=100_000,
                disabled=not enable_sentiment_hot_score,
            )
        with col2:
            enable_sentiment_pulse = st.checkbox(
                "启用情绪脉冲阈值",
                value=current["ENABLE_SENTIMENT_PULSE_THRESHOLD"],
            )
            sentiment_pulse = st.number_input(
                "情绪脉冲阈值",
                min_value=-100.0,
                max_value=100.0,
                value=float(current["SENTIMENT_PULSE_THRESHOLD"]),
                step=0.1,
                disabled=not enable_sentiment_pulse,
            )

        save_sentiment = st.form_submit_button("保存舆情设置", use_container_width=True)

    if save_sentiment:
        sentiment_updates = {
            "ENABLE_SENTIMENT_MONITOR": enable_sentiment,
            "ENABLE_SENTIMENT_CRUISE": enable_sentiment_cruise,
            "SENTIMENT_CRUISE_INTERVAL_MINUTES": int(sentiment_cruise),
            "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD": enable_sentiment_hot_score,
            "SENTIMENT_HOT_SCORE_THRESHOLD": int(sentiment_hot_score),
            "ENABLE_SENTIMENT_PULSE_THRESHOLD": enable_sentiment_pulse,
            "SENTIMENT_PULSE_THRESHOLD": sentiment_pulse,
        }
        sentiment_updates.update(sentiment_windows)
        try:
            save_runtime_module(sentiment_updates, SENTIMENT_FIELDS, success_text="舆情配置")
        except Exception as exc:
            st.error(f"保存舆情设置失败：{exc}")

    st.markdown("**最近变更**")
    render_history_table(prefixes=("ENABLE_SENTIMENT_", "SENTIMENT_"))


with st.expander("金属套利", expanded=False):
    st.caption("金属模块的监控开关、时钟和逐品种升水/贴水阈值都在这里。")
    legacy_preview = get_legacy_metals_thresholds_preview()
    if legacy_preview:
        st.warning(
            "检测到旧版 `data/metals_thresholds.json` 与当前配置不同。升级后的正式配置只使用 `config/metals_thresholds.json`。"
        )
        st.dataframe(legacy_preview["differences"], use_container_width=True, hide_index=True)
        if st.button("迁移旧版金属阈值", use_container_width=True, key="migrate_legacy_metals"):
            try:
                before_rows = get_metals_config_rows()
                result = migrate_legacy_metals_thresholds()
                after_rows = get_metals_config_rows()
                record_config_changes(
                    flatten_threshold_values(before_rows),
                    flatten_threshold_values(after_rows),
                    source="migration",
                    destination="local_override" if result["path"].name.endswith(".local.json") else "shared_baseline",
                )
                removed_text = "，旧文件已清理" if result["removed_legacy"] else ""
                st.success(f"已迁移 {result['count']} 个金属阈值到 {result['path'].name}{removed_text}。")
            except Exception as exc:
                st.error(f"迁移旧版金属阈值失败：{exc}")

    threshold_rows = get_metals_config_rows()
    current_threshold_values = flatten_threshold_values(threshold_rows)

    with st.form("metals_module_form"):
        st.markdown("**模块开关**")
        col1, col2, col3 = st.columns(3)
        enable_metals = col1.toggle("启用金属套利监控", value=current["ENABLE_METALS_MONITOR"])
        enable_metals_cruise = col2.checkbox("启用巡航", value=current["ENABLE_METALS_CRUISE"])
        enable_metals_watch = col3.checkbox("启用盯盘", value=current["ENABLE_METALS_WATCH"])

        st.markdown("**运行频率**")
        col1, col2 = st.columns(2)
        metals_cruise = col1.number_input(
            "巡航间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["METALS_CRUISE_INTERVAL_MINUTES"]),
            step=1,
        )
        metals_watch = col2.number_input(
            "盯盘间隔 (秒)",
            min_value=5,
            max_value=3600,
            value=int(current["METALS_WATCH_INTERVAL_SECONDS"]),
            step=5,
        )

        metals_windows = render_time_window("METALS", current)

        st.markdown("**金属阈值**")
        metals_threshold_widths = [1, 1.2, 0.8, 1, 0.8, 1]
        render_threshold_header(
            metals_threshold_widths,
            ["代码", "名称", "升水启用", "升水阈值(%)", "贴水启用", "贴水阈值(%)"],
        )
        threshold_updates: dict[str, dict[str, float | bool]] = {}
        for row in threshold_rows:
            cols = st.columns(metals_threshold_widths)
            cols[0].markdown(f"`{row['symbol']}`")
            cols[1].markdown(row["name"])
            upper_enabled = cols[2].checkbox(
                f"{row['symbol']}_upper_enabled",
                value=bool(row.get("upper_enabled", True)),
                label_visibility="collapsed",
                key=f"threshold_upper_enabled_{row['symbol']}",
            )
            upper = cols[3].number_input(
                f"{row['symbol']}_upper",
                min_value=0.0,
                value=float(row["upper"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"threshold_upper_{row['symbol']}",
            )
            lower_enabled = cols[4].checkbox(
                f"{row['symbol']}_lower_enabled",
                value=bool(row.get("lower_enabled", True)),
                label_visibility="collapsed",
                key=f"threshold_lower_enabled_{row['symbol']}",
            )
            lower = cols[5].number_input(
                f"{row['symbol']}_lower",
                min_value=-1000.0,
                max_value=0.0,
                value=float(row["lower"]),
                step=0.1,
                label_visibility="collapsed",
                key=f"threshold_lower_{row['symbol']}",
            )
            threshold_updates[row["symbol"]] = {
                "upper": float(upper),
                "lower": float(lower),
                "upper_enabled": bool(upper_enabled),
                "lower_enabled": bool(lower_enabled),
            }

        save_metals = st.form_submit_button("保存金属设置", use_container_width=True)
        reset_metals = st.form_submit_button("恢复金属阈值默认值")

    if save_metals:
        metals_runtime_updates = {
            "ENABLE_METALS_MONITOR": enable_metals,
            "ENABLE_METALS_CRUISE": enable_metals_cruise,
            "ENABLE_METALS_WATCH": enable_metals_watch,
            "METALS_CRUISE_INTERVAL_MINUTES": int(metals_cruise),
            "METALS_WATCH_INTERVAL_SECONDS": int(metals_watch),
        }
        metals_runtime_updates.update(metals_windows)
        try:
            save_runtime_module(metals_runtime_updates, METALS_RUNTIME_FIELDS, success_text="金属运行配置")
            path = save_metals_thresholds(threshold_updates)
            updated_rows = get_metals_config_rows()
            record_config_changes(
                current_threshold_values,
                flatten_threshold_values(updated_rows),
                source="dashboard_gui",
                destination="local_override" if path.name.endswith(".local.json") else "shared_baseline",
            )
            st.success(f"金属阈值已保存到 {path.name}。")
        except Exception as exc:
            st.error(f"保存金属设置失败：{exc}")

    if reset_metals:
        try:
            path = reset_metals_thresholds()
            updated_rows = get_metals_config_rows()
            record_config_changes(
                current_threshold_values,
                flatten_threshold_values(updated_rows),
                source="dashboard_gui",
                destination="shared_baseline",
            )
            st.success(f"金属阈值已恢复为共享基线，当前使用 {path.name}。")
        except Exception as exc:
            st.error(f"恢复金属阈值失败：{exc}")

    st.markdown("**最近变更**")
    render_history_table(prefixes=("ENABLE_METALS_", "METALS_", "METALS_THRESHOLD."))


with st.expander("系统运行", expanded=False):
    st.caption("冷却期和数据保留期属于全局运行参数，因此单独放在系统面板里。")
    with st.form("system_module_form"):
        cooldown_minutes = st.number_input(
            "冷却期 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["COOLDOWN_MINUTES"]),
            step=1,
        )
        data_retention_days = st.number_input(
            "数据保留天数",
            min_value=1,
            max_value=3650,
            value=int(current["DATA_RETENTION_DAYS"]),
            step=1,
            help="每天凌晨清理超过该保留期的报警、保证金与快照历史。",
        )
        save_system = st.form_submit_button("保存系统设置", use_container_width=True)

    if save_system:
        try:
            save_runtime_module(
                {
                    "COOLDOWN_MINUTES": int(cooldown_minutes),
                    "DATA_RETENTION_DAYS": int(data_retention_days),
                },
                SYSTEM_FIELDS,
                success_text="系统运行配置",
            )
        except Exception as exc:
            st.error(f"保存系统设置失败：{exc}")

    st.markdown("**最近变更**")
    render_history_table(exact_keys=("COOLDOWN_MINUTES", "DATA_RETENTION_DAYS"))
