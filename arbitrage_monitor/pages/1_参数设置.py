import streamlit as st

from config.settings import settings
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
        enable_convertible = st.toggle(
            "启用可转债监控", value=current["ENABLE_CONVERTIBLE_MONITOR"]
        )
        enable_sentiment = st.toggle("启用舆情监控", value=current["ENABLE_SENTIMENT_MONITOR"])
        enable_metals = st.toggle("启用金属套利监控", value=current["ENABLE_METALS_MONITOR"])
    with col2:
        futures_threshold = st.number_input(
            "期指年化贴水率阈值 (%)",
            min_value=0.0,
            max_value=1000.0,
            value=float(current["FUTURES_DISCOUNT_RATE_THRESHOLD"]),
            step=0.5,
        )
        cb_negative_premium = st.number_input(
            "转债负溢价阈值 (%)",
            min_value=-100.0,
            max_value=100.0,
            value=float(current["CB_NEGATIVE_PREMIUM_THRESHOLD"]),
            step=0.1,
        )
        cb_safe_price = st.number_input(
            "转债安全价格上限",
            min_value=0.0,
            max_value=1000.0,
            value=float(current["CB_SAFE_PRICE_THRESHOLD"]),
            step=1.0,
        )
        cb_double_low = st.number_input(
            "双低阈值",
            min_value=0.0,
            max_value=1000.0,
            value=float(current["CB_DOUBLE_LOW_THRESHOLD"]),
            step=1.0,
        )
        cb_ytm = st.number_input(
            "税前 YTM 下限 (%)",
            min_value=-100.0,
            max_value=1000.0,
            value=float(current["CB_YTM_THRESHOLD"]),
            step=0.1,
        )
        sentiment_hot_score = st.number_input(
            "舆情热度异常阈值",
            min_value=0,
            max_value=100_000_000,
            value=int(current["SENTIMENT_HOT_SCORE_THRESHOLD"]),
            step=100_000,
        )
        sentiment_pulse = st.number_input(
            "舆情情绪脉冲阈值",
            min_value=-100.0,
            max_value=100.0,
            value=float(current["SENTIMENT_PULSE_THRESHOLD"]),
            step=0.1,
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
    updates = {
        "ENABLE_FUTURES_MONITOR": enable_futures,
        "ENABLE_CONVERTIBLE_MONITOR": enable_convertible,
        "ENABLE_SENTIMENT_MONITOR": enable_sentiment,
        "ENABLE_METALS_MONITOR": enable_metals,
        "FUTURES_DISCOUNT_RATE_THRESHOLD": futures_threshold,
        "CB_NEGATIVE_PREMIUM_THRESHOLD": cb_negative_premium,
        "CB_SAFE_PRICE_THRESHOLD": cb_safe_price,
        "CB_DOUBLE_LOW_THRESHOLD": cb_double_low,
        "CB_YTM_THRESHOLD": cb_ytm,
        "SENTIMENT_HOT_SCORE_THRESHOLD": int(sentiment_hot_score),
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
                result = migrate_legacy_metals_thresholds()
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
with st.form("metals_threshold_form"):
    st.markdown("**当前阈值**")
    st.write("代码 | 名称 | 上阈值(%) | 下阈值(%)")
    threshold_updates: dict[str, dict[str, float]] = {}
    for row in threshold_rows:
        cols = st.columns([1, 1.2, 1, 1])
        cols[0].markdown(f"`{row['symbol']}`")
        cols[1].markdown(row["name"])
        upper = cols[2].number_input(
            f"{row['symbol']}_upper",
            value=float(row["upper"]),
            step=0.1,
            label_visibility="collapsed",
            key=f"threshold_upper_{row['symbol']}",
        )
        lower = cols[3].number_input(
            f"{row['symbol']}_lower",
            value=float(row["lower"]),
            step=0.1,
            label_visibility="collapsed",
            key=f"threshold_lower_{row['symbol']}",
        )
        threshold_updates[row["symbol"]] = {"upper": float(upper), "lower": float(lower)}

    save_thresholds = st.form_submit_button("保存金属阈值", use_container_width=True)
    reset_thresholds = st.form_submit_button("恢复默认阈值")

if save_thresholds:
    try:
        path = save_metals_thresholds(threshold_updates)
        st.success(f"金属阈值已保存到 {path.name}，后续策略轮次会立即生效，且不会被后续 `git pull` 覆盖。")
    except Exception as exc:
        st.error(f"保存金属阈值失败：{exc}")

if reset_thresholds:
    try:
        path = reset_metals_thresholds()
        st.success(f"金属阈值已恢复为仓库共享基线，当前使用 {path.name}。")
    except Exception as exc:
        st.error(f"恢复默认阈值失败：{exc}")

st.markdown("---")
st.subheader("当前模块配置")
st.json(get_gui_config_values())
