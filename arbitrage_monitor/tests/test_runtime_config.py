"""
端到端集成测试脚本
验证调度器、策略、通知、数据库的完整链路
"""

import json
import sys
import os
import io
import tempfile
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from utils.logger import configure_logger
from utils.db_manager import DBManager
from utils.notifier import notifier

configure_logger()

from utils.logger import logger

def test_runtime_config_writer():
    """测试 GUI 配置回写本机 local JSON 的行为。"""
    logger.info("test_runtime_config_writer_start")

    from pathlib import Path
    from config.runtime import write_env_updates

    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "runtime_settings.local.json"
        config_path.write_text(
            json.dumps(
                {
                    "ENABLE_FUTURES_MONITOR": True,
                    "CB_YTM_THRESHOLD": 2.0,
                    "METALS_MORNING_START": "09:00",
                    "DATA_RETENTION_DAYS": 30,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        write_env_updates(
            {
                "ENABLE_FUTURES_MONITOR": False,
                "CB_YTM_THRESHOLD": 3.5,
                "FUTURES_WATCH_INTERVAL_SECONDS": 45,
                "METALS_MORNING_START": "08:30",
                "DATA_RETENTION_DAYS": 21,
            },
            env_path=config_path,
        )
        content = json.loads(config_path.read_text(encoding="utf-8"))

    if content["ENABLE_FUTURES_MONITOR"] is not False:
        print("❌ Runtime Config: bool value not updated")
        return False
    if content["CB_YTM_THRESHOLD"] != 3.5:
        print("❌ Runtime Config: existing numeric value not updated")
        return False
    if content["FUTURES_WATCH_INTERVAL_SECONDS"] != 45:
        print("❌ Runtime Config: missing appended key")
        return False
    if content["METALS_MORNING_START"] != "08:30":
        print("❌ Runtime Config: schedule window not updated")
        return False
    if content["DATA_RETENTION_DAYS"] != 21:
        print("❌ Runtime Config: retention days not persisted")
        return False

    logger.info("runtime_config_writer_ok")
    print("✅ Runtime Config Writer: OK")
    return True

def test_runtime_config_local_override():
    """测试本机 runtime local 配置优先于仓库共享基线。"""
    logger.info("test_runtime_config_local_override_start")

    from pathlib import Path
    import config.settings as settings_module

    original_shared_path = settings_module.SHARED_RUNTIME_CONFIG_PATH
    original_local_path = settings_module.LOCAL_RUNTIME_CONFIG_PATH

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "runtime_settings.json"
        local_path = temp_root / "config" / "runtime_settings.local.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)

        shared_path.write_text(
            json.dumps(
                {
                    "ENABLE_CONVERTIBLE_MONITOR": True,
                    "ENABLE_SENTIMENT_MONITOR": True,
                    "METALS_CRUISE_INTERVAL_MINUTES": 15,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        local_path.write_text(
            json.dumps(
                {
                    "ENABLE_CONVERTIBLE_MONITOR": False,
                    "METALS_CRUISE_INTERVAL_MINUTES": 21,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        settings_module.SHARED_RUNTIME_CONFIG_PATH = shared_path
        settings_module.LOCAL_RUNTIME_CONFIG_PATH = local_path
        probe = settings_module.Settings()

        try:
            effective = settings_module.load_effective_runtime_config(probe, force_reload=True)
        finally:
            settings_module.SHARED_RUNTIME_CONFIG_PATH = original_shared_path
            settings_module.LOCAL_RUNTIME_CONFIG_PATH = original_local_path

    if effective["ENABLE_CONVERTIBLE_MONITOR"] is not False:
        print("❌ Runtime Local Override: local bool override not applied")
        return False
    if effective["ENABLE_SENTIMENT_MONITOR"] is not True:
        print("❌ Runtime Local Override: shared value should remain when local missing")
        return False
    if effective["METALS_CRUISE_INTERVAL_MINUTES"] != 21:
        print("❌ Runtime Local Override: local interval override not applied")
        return False

    logger.info("runtime_config_local_override_ok")
    print("✅ Runtime Config Local Override: OK")
    return True

def test_futures_threshold_local_override():
    """测试期指分品种阈值支持共享基线叠加本机 local 覆盖。"""
    logger.info("test_futures_threshold_local_override_start")

    import config.futures_thresholds as futures_config

    original_shared_path_fn = futures_config.get_futures_thresholds_path
    original_local_path_fn = futures_config.get_local_futures_thresholds_path
    original_cache = futures_config._threshold_cache

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "futures_thresholds.json"
        local_path = temp_root / "config" / "futures_thresholds.local.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)

        shared_path.write_text(
            json.dumps(
                {
                    "IH": {
                        "backwardation_enabled": False,
                        "backwardation_threshold": 1.0,
                        "annualized_backwardation_threshold": 8.0,
                        "contango_enabled": False,
                        "contango_threshold": 1.0,
                        "annualized_contango_threshold": 8.0,
                    },
                    "IF": {
                        "backwardation_enabled": True,
                        "backwardation_threshold": 1.2,
                        "annualized_backwardation_threshold": 8.5,
                        "contango_enabled": True,
                        "contango_threshold": 1.2,
                        "annualized_contango_threshold": 8.5,
                    },
                    "IC": {
                        "backwardation_enabled": True,
                        "backwardation_threshold": 1.3,
                        "annualized_backwardation_threshold": 9.0,
                        "contango_enabled": True,
                        "contango_threshold": 1.3,
                        "annualized_contango_threshold": 9.0,
                    },
                    "IM": {
                        "backwardation_enabled": True,
                        "backwardation_threshold": 1.4,
                        "annualized_backwardation_threshold": 9.5,
                        "contango_enabled": True,
                        "contango_threshold": 1.4,
                        "annualized_contango_threshold": 9.5,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        local_path.write_text(
            json.dumps(
                {
                    "IF": {
                        "backwardation_enabled": False,
                        "backwardation_threshold": 2.2,
                        "annualized_backwardation_threshold": 12.5,
                        "contango_enabled": False,
                        "contango_threshold": 2.2,
                        "annualized_contango_threshold": 12.5,
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        futures_config.get_futures_thresholds_path = lambda: shared_path
        futures_config.get_local_futures_thresholds_path = lambda: local_path
        futures_config._threshold_cache = None

        try:
            effective = futures_config.load_futures_thresholds(force_reload=True)
        finally:
            futures_config.get_futures_thresholds_path = original_shared_path_fn
            futures_config.get_local_futures_thresholds_path = original_local_path_fn
            futures_config._threshold_cache = original_cache

    if effective["IF"]["backwardation_enabled"] is not False:
        print("❌ Futures Threshold Local Override: local enabled override not applied")
        return False
    if float(effective["IF"]["backwardation_threshold"]) != 2.2:
        print("❌ Futures Threshold Local Override: local percent threshold not applied")
        return False
    if float(effective["IH"]["annualized_backwardation_threshold"]) != 8.0:
        print("❌ Futures Threshold Local Override: shared value should remain when local missing")
        return False

    logger.info("futures_threshold_local_override_ok")
    print("✅ Futures Threshold Local Override: OK")
    return True

def test_metals_threshold_local_override():
    """测试本机金属阈值 local 文件优先于仓库共享基线。"""
    logger.info("test_metals_threshold_local_override_start")

    from pathlib import Path
    import config.metals_thresholds as metals_config

    original_new_path_fn = metals_config.get_metals_thresholds_path
    original_local_path_fn = metals_config.get_local_metals_thresholds_path
    original_legacy_path_fn = metals_config.get_legacy_metals_thresholds_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "metals_thresholds.json"
        local_path = temp_root / "config" / "metals_thresholds.local.json"
        legacy_path = temp_root / "data" / "metals_thresholds.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)

        shared_path.write_text(
            json.dumps(
                {
                    "AU0": {"upper": 1.0, "lower": -1.0},
                    "AG0": {"upper": 2.0, "lower": -2.0},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        local_path.write_text(
            json.dumps(
                {
                    "AG0": {"upper": 20.0, "lower": -20.0},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        metals_config.get_metals_thresholds_path = lambda: shared_path
        metals_config.get_local_metals_thresholds_path = lambda: local_path
        metals_config.get_legacy_metals_thresholds_path = lambda: legacy_path
        metals_config._threshold_cache = None

        try:
            effective = metals_config.load_metals_thresholds(force_reload=True)
        finally:
            metals_config.get_metals_thresholds_path = original_new_path_fn
            metals_config.get_local_metals_thresholds_path = original_local_path_fn
            metals_config.get_legacy_metals_thresholds_path = original_legacy_path_fn
            metals_config._threshold_cache = None

    if effective["AG0"]["upper"] != 20.0 or effective["AG0"]["lower"] != -20.0:
        print(f"❌ Metals Local Override: local AG0 override missing {effective['AG0']}")
        return False
    if effective["AU0"]["upper"] != 1.0 or effective["AU0"]["lower"] != -1.0:
        print(f"❌ Metals Local Override: shared AU0 baseline missing {effective['AU0']}")
        return False

    logger.info("metals_threshold_local_override_ok")
    print("✅ Metals Threshold Local Override: OK")
    return True

def test_premium_threshold_local_override():
    """测试 premium 阈值 local override 优先级。"""
    logger.info("test_premium_threshold_local_override_start")

    import config.premium_thresholds as premium_config

    original_shared_path_fn = premium_config.get_premium_thresholds_path
    original_local_path_fn = premium_config.get_local_premium_thresholds_path
    original_cache = premium_config._threshold_cache

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "premium_thresholds.json"
        local_path = temp_root / "config" / "premium_thresholds.local.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(
            json.dumps(
                {
                    "BTC_DELIVERY": {
                        "contango_threshold": 0.7,
                        "backwardation_threshold": 0.6,
                        "contango_enabled": True,
                        "backwardation_enabled": True,
                    },
                    "BTC_PERP": {
                        "contango_threshold": 0.5,
                        "backwardation_threshold": 0.5,
                        "contango_enabled": True,
                        "backwardation_enabled": True,
                    },
                    "A50": {
                        "contango_threshold": 0.5,
                        "backwardation_threshold": 0.5,
                        "contango_enabled": True,
                        "backwardation_enabled": True,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        local_path.write_text(
            json.dumps(
                {
                    "BTC_MONTHLY_NEXT": {
                        "contango_threshold": 1.6,
                        "backwardation_threshold": 1.4,
                        "contango_enabled": True,
                        "backwardation_enabled": False,
                    },
                    "BTC_PERP": {
                        "contango_threshold": 1.2,
                        "backwardation_threshold": 1.0,
                        "contango_enabled": False,
                        "backwardation_enabled": True,
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        premium_config.get_premium_thresholds_path = lambda: shared_path
        premium_config.get_local_premium_thresholds_path = lambda: local_path
        premium_config._threshold_cache = None

        try:
            btc = premium_config.get_effective_premium_threshold("BTC", "PERP")
            btc_delivery = premium_config.get_effective_premium_threshold("BTC", "QUARTERLY_CURRENT")
            a50 = premium_config.get_effective_premium_threshold("A50")
        finally:
            premium_config.get_premium_thresholds_path = original_shared_path_fn
            premium_config.get_local_premium_thresholds_path = original_local_path_fn
            premium_config._threshold_cache = original_cache

    if float(btc["contango_threshold"]) != 1.2 or bool(btc["contango_enabled"]) is not False:
        print(f"❌ Premium Threshold Override: BTC override mismatch {btc}")
        return False
    if (
        float(btc_delivery["contango_threshold"]) != 1.6
        or bool(btc_delivery["backwardation_enabled"]) is not False
    ):
        print(f"❌ Premium Threshold Override: BTC delivery override mismatch {btc_delivery}")
        return False
    if float(a50["contango_threshold"]) != 0.5 or float(a50["backwardation_threshold"]) != 0.5:
        print(f"❌ Premium Threshold Override: A50 shared fallback mismatch {a50}")
        return False

    logger.info("premium_threshold_local_override_ok")
    print("✅ Premium Threshold Local Override: OK")
    return True

def test_premium_threshold_delivery_mapping():
    """测试旧五桶配置到 PERP / DELIVERY 两档阈值的兼容映射。"""
    logger.info("test_premium_threshold_delivery_mapping_start")

    import config.premium_thresholds as premium_config

    original_shared_path_fn = premium_config.get_premium_thresholds_path
    original_local_path_fn = premium_config.get_local_premium_thresholds_path
    original_cache = premium_config._threshold_cache

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "premium_thresholds.json"
        local_path = temp_root / "config" / "premium_thresholds.local.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(
            json.dumps(
                {
                    "BTC_MONTHLY_CURRENT": {
                        "contango_threshold": 0.9,
                        "backwardation_threshold": 0.8,
                    },
                    "BTC_MONTHLY_NEXT": {
                        "contango_threshold": 1.1,
                        "backwardation_threshold": 1.0,
                    },
                    "BTC_PERP": {
                        "contango_threshold": 0.4,
                        "backwardation_threshold": 0.3,
                    },
                    "A50": {
                        "contango_threshold": 0.5,
                        "backwardation_threshold": 0.5,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        premium_config.get_premium_thresholds_path = lambda: shared_path
        premium_config.get_local_premium_thresholds_path = lambda: local_path
        premium_config._threshold_cache = None

        try:
            rows = premium_config.get_premium_config_rows()
            saved_path = premium_config.save_premium_thresholds(
                {
                    "BTC_DELIVERY": {
                        "upper_enabled": True,
                        "upper": 2.2,
                        "annualized_upper_enabled": True,
                        "annualized_upper": 12.0,
                        "lower_enabled": True,
                        "lower": -2.0,
                        "annualized_lower_enabled": True,
                        "annualized_lower": -12.0,
                    }
                }
            )
            saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
        finally:
            premium_config.get_premium_thresholds_path = original_shared_path_fn
            premium_config.get_local_premium_thresholds_path = original_local_path_fn
            premium_config._threshold_cache = original_cache

    crypto_btc_rows = [row for row in rows if row["asset_group"] == "BTC"]
    if {row["contract_bucket"] for row in crypto_btc_rows} != {"PERP", "DELIVERY"}:
        print(f"❌ Premium Threshold Delivery Mapping: unexpected BTC rows {crypto_btc_rows}")
        return False
    delivery_row = next(row for row in crypto_btc_rows if row["contract_bucket"] == "DELIVERY")
    if float(delivery_row["contango_threshold"]) != 0.9:
        print(f"❌ Premium Threshold Delivery Mapping: legacy delivery merge mismatch {delivery_row}")
        return False
    if set(saved_payload) != {"BTC_DELIVERY"}:
        print(f"❌ Premium Threshold Delivery Mapping: saved keys mismatch {saved_payload}")
        return False

    logger.info("premium_threshold_delivery_mapping_ok")
    print("✅ Premium Threshold Delivery Mapping: OK")
    return True

def test_config_audit_history():
    """测试配置审计记录。"""
    logger.info("test_config_audit_history_start")

    from config.audit import record_config_changes

    db = DBManager()
    key = f"TEST_CONFIG_{datetime.now().timestamp()}"
    try:
        changed = record_config_changes(
            {key: "old"},
            {key: "new"},
            source="dashboard_gui",
            destination="local_override",
        )
        if changed != 1:
            print(f"❌ Config Audit: expected 1 changed row, got {changed}")
            return False
        rows = [row for row in db.get_recent_config_changes(limit=20) if row[1] == key]
        if not rows:
            print("❌ Config Audit: missing persisted audit row")
            return False
        if rows[0][4] != "dashboard_gui" or rows[0][5] != "local_override":
            print(f"❌ Config Audit: unexpected source/destination {rows[0]}")
            return False
    finally:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM config_change_history WHERE config_key = ?", (key,))
            conn.commit()

    logger.info("config_audit_history_ok")
    print("✅ Config Audit History: OK")
    return True

