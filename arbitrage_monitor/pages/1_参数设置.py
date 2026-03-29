import pandas as pd
import streamlit as st

from config.settings import settings
from utils.config_audit import flatten_threshold_values, record_config_changes
from utils.db_manager import DBManager
from utils.metals_config import (
    get_metals_config_rows,
    get_legacy_metals_thresholds_preview,
    migrate_legacy_metals_thresholds,
    reset_metals_thresholds,
    save_metals_thresholds,
)
from utils.runtime_config import (
    apply_runtime_updates,
    get_gui_config_values,
    write_env_updates,
)


st.set_page_config(
    page_title="参数设置",
    page_icon="⚙️",
    layout="wide",
)

st.title("⚙️ 参数设置")
st.caption(
    "在 GUI 中调整各模块开关、阈值和独立时钟。仓库里的 `config/*.json` 作为共享基线，"
    "本机在 GUI 中保存的改动会写入 `config/*.local.json`，因此不会被 `git pull` 覆盖。"
)

db_manager = DBManager()
settings.reload_from_env()
current = get_gui_config_values()


def render_time_window(prefix: str, title: str) -> dict[str, str]:
    st.markdown(f"**{title}**")
    col1, col2 = st.columns(2)
    with col1:
        morning_start = st.text_input(
            "上午开始", value=str(current[f"{prefix}_MORNING_START"]), key=f"{prefix}_morning_start"
        )
        afternoon_start = st.text_input(
            "下午开始", value=str(current[f"{prefix}_AFTERNOON_START"]), key=f"{prefix}_afternoon_start"
        )
        night_start = st.text_input(
            "夜盘开始", value=str(current[f"{prefix}_NIGHT_START"]), key=f"{prefix}_night_start"
        )
    with col2:
        morning_end = st.text_input(
            "上午结束", value=str(current[f"{prefix}_MORNING_END"]), key=f"{prefix}_morning_end"
        )
        afternoon_end = st.text_input(
            "下午结束", value=str(current[f"{prefix}_AFTERNOON_END"]), key=f"{prefix}_afternoon_end"
        )
        night_end = st.text_input(
            "夜盘结束", value=str(current[f"{prefix}_NIGHT_END"]), key=f"{prefix}_night_end"
        )

    return {
        f"{prefix}_MORNING_START": morning_start.strip(),
        f"{prefix}_MORNING_END": morning_end.strip(),
        f"{prefix}_AFTERNOON_START": afternoon_start.strip(),
        f"{prefix}_AFTERNOON_END": afternoon_end.strip(),
        f"{prefix}_NIGHT_START": night_start.strip(),
        f"{prefix}_NIGHT_END": night_end.strip(),
    }


with st.form("runtime_settings_form"):
    st.subheader("模块开关与策略阈值")
    col1, col2 = st.columns(2)
    with col1:
        enable_futures = st.toggle("启用股指期货监控", value=current["ENABLE_FUTURES_MONITOR"])
        enable_futures_cruise = st.checkbox("期指启用巡航", value=current["ENABLE_FUTURES_CRUISE"])
        enable_futures_watch = st.checkbox("期指启用盯盘", value=current["ENABLE_FUTURES_WATCH"])
        enable_convertible = st.toggle(
            "启用可转债监控", value=current["ENABLE_CONVERTIBLE_MONITOR"]
        )
        enable_convertible_cruise = st.checkbox(
            "转债启用巡航", value=current["ENABLE_CONVERTIBLE_CRUISE"]
        )
        enable_convertible_watch = st.checkbox(
            "转债启用盯盘", value=current["ENABLE_CONVERTIBLE_WATCH"]
        )
        enable_sentiment = st.toggle("启用舆情监控", value=current["ENABLE_SENTIMENT_MONITOR"])
        enable_sentiment_cruise = st.checkbox(
            "舆情启用巡航", value=current["ENABLE_SENTIMENT_CRUISE"]
        )
        enable_metals = st.toggle("启用金属套利监控", value=current["ENABLE_METALS_MONITOR"])
        enable_metals_cruise = st.checkbox("金属启用巡航", value=current["ENABLE_METALS_CRUISE"])
        enable_metals_watch = st.checkbox("金属启用盯盘", value=current["ENABLE_METALS_WATCH"])
    with col2:
        enable_futures_percent_threshold = st.checkbox(
            "启用期指贴水率阈值",
            value=current["ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD"],
        )
        futures_percent_threshold = st.number_input(
            "期指贴水率阈值 (%)",
            min_value=0.0,
            max_value=1000.0,
            value=float(current["FUTURES_DISCOUNT_PERCENT_THRESHOLD"]),
            step=0.1,
            disabled=not enable_futures_percent_threshold,
        )
        enable_futures_threshold = st.checkbox(
            "启用期指年化贴水率阈值",
            value=current["ENABLE_FUTURES_DISCOUNT_RATE_THRESHOLD"],
        )
        futures_threshold = st.number_input(
            "期指年化贴水率阈值 (%)",
            min_value=0.0,
            max_value=1000.0,
            value=float(current["FUTURES_DISCOUNT_RATE_THRESHOLD"]),
            step=0.5,
            disabled=not enable_futures_threshold,
        )
        enable_cb_negative_premium = st.checkbox(
            "启用转债负溢价阈值",
            value=current["ENABLE_CB_NEGATIVE_PREMIUM_THRESHOLD"],
        )
        cb_negative_premium = st.number_input(
            "转债负溢价阈值 (%)",
            min_value=-100.0,
            max_value=100.0,
            value=float(current["CB_NEGATIVE_PREMIUM_THRESHOLD"]),
            step=0.1,
            disabled=not enable_cb_negative_premium,
        )
        enable_cb_safe_price = st.checkbox(
            "启用转债安全价格上限",
            value=current["ENABLE_CB_SAFE_PRICE_THRESHOLD"],
        )
        cb_safe_price = st.number_input(
            "转债安全价格上限",
            min_value=0.0,
            max_value=1000.0,
            value=float(current["CB_SAFE_PRICE_THRESHOLD"]),
            step=1.0,
            disabled=not enable_cb_safe_price,
        )
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
        enable_sentiment_hot_score = st.checkbox(
            "启用舆情热度异常阈值",
            value=current["ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD"],
        )
        sentiment_hot_score = st.number_input(
            "舆情热度异常阈值",
            min_value=0,
            max_value=100_000_000,
            value=int(current["SENTIMENT_HOT_SCORE_THRESHOLD"]),
            step=100_000,
            disabled=not enable_sentiment_hot_score,
        )
        enable_sentiment_pulse = st.checkbox(
            "启用舆情情绪脉冲阈值",
            value=current["ENABLE_SENTIMENT_PULSE_THRESHOLD"],
        )
        sentiment_pulse = st.number_input(
            "舆情情绪脉冲阈值",
            min_value=-100.0,
            max_value=100.0,
            value=float(current["SENTIMENT_PULSE_THRESHOLD"]),
            step=0.1,
            disabled=not enable_sentiment_pulse,
        )

    st.subheader("模块独立时钟")
    f1, f2 = st.columns(2)
    with f1:
        futures_cruise = st.number_input(
            "期指巡航间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["FUTURES_CRUISE_INTERVAL_MINUTES"]),
            step=1,
        )
        futures_watch = st.number_input(
            "期指盯盘间隔 (秒)",
            min_value=5,
            max_value=3600,
            value=int(current["FUTURES_WATCH_INTERVAL_SECONDS"]),
            step=5,
        )
    with f2:
        convertible_cruise = st.number_input(
            "转债巡航间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["CONVERTIBLE_CRUISE_INTERVAL_MINUTES"]),
            step=1,
        )
        convertible_watch = st.number_input(
            "转债盯盘间隔 (秒)",
            min_value=5,
            max_value=3600,
            value=int(current["CONVERTIBLE_WATCH_INTERVAL_SECONDS"]),
            step=5,
        )

    f3, f4 = st.columns(2)
    with f3:
        sentiment_cruise = st.number_input(
            "舆情低频间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["SENTIMENT_CRUISE_INTERVAL_MINUTES"]),
            step=1,
        )
    with f4:
        metals_cruise = st.number_input(
            "金属巡航间隔 (分钟)",
            min_value=1,
            max_value=1440,
            value=int(current["METALS_CRUISE_INTERVAL_MINUTES"]),
            step=1,
        )
        metals_watch = st.number_input(
            "金属盯盘间隔 (秒)",
            min_value=5,
            max_value=3600,
            value=int(current["METALS_WATCH_INTERVAL_SECONDS"]),
            step=5,
        )

    with st.expander("期指时间窗口", expanded=False):
        futures_windows = render_time_window("FUTURES", "期指交易窗口")
    with st.expander("转债时间窗口", expanded=False):
        convertible_windows = render_time_window("CONVERTIBLE", "转债交易窗口")
    with st.expander("舆情时间窗口", expanded=False):
        sentiment_windows = render_time_window("SENTIMENT", "舆情运行窗口")
    with st.expander("金属时间窗口", expanded=True):
        metals_windows = render_time_window("METALS", "金属运行窗口")

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

    submitted = st.form_submit_button("保存模块配置", use_container_width=True)

if submitted:
    previous_runtime_values = dict(current)
    updates = {
        "ENABLE_FUTURES_MONITOR": enable_futures,
        "ENABLE_FUTURES_CRUISE": enable_futures_cruise,
        "ENABLE_FUTURES_WATCH": enable_futures_watch,
        "ENABLE_CONVERTIBLE_MONITOR": enable_convertible,
        "ENABLE_CONVERTIBLE_CRUISE": enable_convertible_cruise,
        "ENABLE_CONVERTIBLE_WATCH": enable_convertible_watch,
        "ENABLE_SENTIMENT_MONITOR": enable_sentiment,
        "ENABLE_SENTIMENT_CRUISE": enable_sentiment_cruise,
        "ENABLE_METALS_MONITOR": enable_metals,
        "ENABLE_METALS_CRUISE": enable_metals_cruise,
        "ENABLE_METALS_WATCH": enable_metals_watch,
        "ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD": enable_futures_percent_threshold,
        "FUTURES_DISCOUNT_PERCENT_THRESHOLD": futures_percent_threshold,
        "ENABLE_FUTURES_DISCOUNT_RATE_THRESHOLD": enable_futures_threshold,
        "FUTURES_DISCOUNT_RATE_THRESHOLD": futures_threshold,
        "ENABLE_CB_NEGATIVE_PREMIUM_THRESHOLD": enable_cb_negative_premium,
        "CB_NEGATIVE_PREMIUM_THRESHOLD": cb_negative_premium,
        "ENABLE_CB_SAFE_PRICE_THRESHOLD": enable_cb_safe_price,
        "CB_SAFE_PRICE_THRESHOLD": cb_safe_price,
        "ENABLE_CB_DOUBLE_LOW_THRESHOLD": enable_cb_double_low,
        "CB_DOUBLE_LOW_THRESHOLD": cb_double_low,
        "ENABLE_CB_YTM_THRESHOLD": enable_cb_ytm,
        "CB_YTM_THRESHOLD": cb_ytm,
        "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD": enable_sentiment_hot_score,
        "SENTIMENT_HOT_SCORE_THRESHOLD": int(sentiment_hot_score),
        "ENABLE_SENTIMENT_PULSE_THRESHOLD": enable_sentiment_pulse,
        "SENTIMENT_PULSE_THRESHOLD": sentiment_pulse,
        "FUTURES_CRUISE_INTERVAL_MINUTES": int(futures_cruise),
        "FUTURES_WATCH_INTERVAL_SECONDS": int(futures_watch),
        "CONVERTIBLE_CRUISE_INTERVAL_MINUTES": int(convertible_cruise),
        "CONVERTIBLE_WATCH_INTERVAL_SECONDS": int(convertible_watch),
        "SENTIMENT_CRUISE_INTERVAL_MINUTES": int(sentiment_cruise),
        "METALS_CRUISE_INTERVAL_MINUTES": int(metals_cruise),
        "METALS_WATCH_INTERVAL_SECONDS": int(metals_watch),
        "COOLDOWN_MINUTES": int(cooldown_minutes),
        "DATA_RETENTION_DAYS": int(data_retention_days),
    }
    updates.update(futures_windows)
    updates.update(convertible_windows)
    updates.update(sentiment_windows)
    updates.update(metals_windows)

    try:
        config_path = write_env_updates(updates)
        apply_runtime_updates(updates)
        destination = "local_override" if config_path.name.endswith(".local.json") else "shared_baseline"
        record_config_changes(
            previous_runtime_values,
            get_gui_config_values(),
            source="dashboard_gui",
            destination=destination,
        )
        st.success(f"模块配置已保存到 {config_path.name}，当前进程已热更新。")
        st.info("其他电脑默认仍会跟随仓库里的共享基线；本机保存过的 `.local.json` 不会被拉代码覆盖。")
    except Exception as exc:
        st.error(f"保存失败：{exc}")


st.markdown("---")
st.subheader("金属阈值")
st.caption(
    "每个金属独立维护上/下阈值。仓库里的 `config/metals_thresholds.json` 是共享基线，"
    "GUI 保存会写入本机的 `config/metals_thresholds.local.json` 并立即生效。"
)
st.caption("当前 `config/metals_thresholds.json` 若是旧版本结构，系统会自动补齐新增金属并忽略已废弃项。")

legacy_preview = get_legacy_metals_thresholds_preview()
if legacy_preview:
    st.warning(
        "检测到旧版 `data/metals_thresholds.json` 与当前配置不同。"
        "升级后的正式配置只使用 `config/metals_thresholds.json`，请确认是否迁移旧值。"
    )
    st.dataframe(legacy_preview["differences"], use_container_width=True, hide_index=True)
    migrate_col, skip_col = st.columns([1, 1])
    with migrate_col:
        if st.button("迁移旧版金属阈值", use_container_width=True):
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
                st.success(
                    f"已迁移 {result['count']} 个金属阈值到 {result['path'].name}{removed_text}。"
                )
                st.rerun()
            except Exception as exc:
                st.error(f"迁移旧版阈值失败：{exc}")
    with skip_col:
        st.info("如果你暂时不迁移，当前程序会继续使用 `config/metals_thresholds.json`。")

threshold_rows = get_metals_config_rows()
current_threshold_values = flatten_threshold_values(threshold_rows)
with st.form("metals_threshold_form"):
    st.markdown("**当前阈值**")
    st.write("代码 | 名称 | 上阈值启用 | 上阈值(%) | 下阈值启用 | 下阈值(%)")
    threshold_updates: dict[str, dict[str, float | bool]] = {}
    for row in threshold_rows:
        cols = st.columns([1, 1.2, 0.8, 1, 0.8, 1])
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
            value=float(row["upper"]),
            step=0.1,
            label_visibility="collapsed",
            key=f"threshold_upper_{row['symbol']}",
            disabled=not upper_enabled,
        )
        lower_enabled = cols[4].checkbox(
            f"{row['symbol']}_lower_enabled",
            value=bool(row.get("lower_enabled", True)),
            label_visibility="collapsed",
            key=f"threshold_lower_enabled_{row['symbol']}",
        )
        lower = cols[5].number_input(
            f"{row['symbol']}_lower",
            value=float(row["lower"]),
            step=0.1,
            label_visibility="collapsed",
            key=f"threshold_lower_{row['symbol']}",
            disabled=not lower_enabled,
        )
        threshold_updates[row["symbol"]] = {
            "upper": float(upper),
            "lower": float(lower),
            "upper_enabled": bool(upper_enabled),
            "lower_enabled": bool(lower_enabled),
        }

    save_thresholds = st.form_submit_button("保存金属阈值", use_container_width=True)
    reset_thresholds = st.form_submit_button("恢复默认阈值")

if save_thresholds:
    try:
        path = save_metals_thresholds(threshold_updates)
        updated_rows = get_metals_config_rows()
        record_config_changes(
            current_threshold_values,
            flatten_threshold_values(updated_rows),
            source="dashboard_gui",
            destination="local_override" if path.name.endswith(".local.json") else "shared_baseline",
        )
        st.success(f"金属阈值已保存到 {path.name}，后续策略轮次会立即生效，且不会被后续 `git pull` 覆盖。")
    except Exception as exc:
        st.error(f"保存金属阈值失败：{exc}")

if reset_thresholds:
    try:
        path = reset_metals_thresholds()
        updated_rows = get_metals_config_rows()
        record_config_changes(
            current_threshold_values,
            flatten_threshold_values(updated_rows),
            source="dashboard_gui",
            destination="shared_baseline",
        )
        st.success(f"金属阈值已恢复为仓库共享基线，当前使用 {path.name}。")
    except Exception as exc:
        st.error(f"恢复默认阈值失败：{exc}")

st.markdown("---")
st.subheader("最近配置变更")
config_history_rows = db_manager.get_recent_config_changes(limit=50)
if not config_history_rows:
    st.info("暂无配置变更记录")
else:
    history_df = pd.DataFrame(
        config_history_rows,
        columns=[
            "changed_at",
            "config_key",
            "old_value",
            "new_value",
            "source",
            "destination",
            "immediate_effect",
        ],
    ).rename(
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
    history_df["立即生效"] = history_df["立即生效"].map({1: "是", 0: "否"})
    st.dataframe(history_df, width="stretch", hide_index=True)

st.markdown("---")
st.subheader("当前模块配置")
st.json(get_gui_config_values())
