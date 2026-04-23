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

def test_metals_conversion_and_thresholds():
    """测试金属换算逻辑与阈值配置热更新。"""
    logger.info("test_metals_conversion_and_thresholds_start")

    from fetchers.ak_metals import MetalsFetcher
    from strategies.metals_strategy import MetalsArbitrageStrategy
    from config.metals_thresholds import (
        get_effective_metal_threshold,
        load_metals_thresholds,
        reset_metals_thresholds,
        save_metals_thresholds,
    )

    fetcher = MetalsFetcher()
    xau_cny, xau_used_api = fetcher.convert_foreign_price(
        usd_price=3130.0,
        rate=6.9,
        unit_factor=31.1034768,
        foreign_cny=695.2,
        benchmark_name="COMEX黄金",
    )
    if round(xau_cny, 2) != 695.2 or not xau_used_api:
        print(f"❌ Metals Conversion: unexpected XAU conversion {(xau_cny, xau_used_api)}")
        return False

    xag_cny, xag_used_api = fetcher.convert_foreign_price(
        usd_price=31.5,
        rate=7.2,
        unit_factor=32.1507,
        foreign_cny=255.0,
        benchmark_name="COMEX白银",
    )
    if round(xag_cny, 2) != round(255.0 * 32.1507, 2) or not xag_used_api:
        print(f"❌ Metals Conversion: unexpected XAG conversion {(xag_cny, xag_used_api)}")
        return False

    hg_rate = fetcher.calculate_implied_rate(
        for_price_cny=67400.0,
        foreign_usd=460.0,
        unit_factor=22.0462,
        rate_direction="mul",
    )
    if not (6.5 <= hg_rate <= 6.8):
        print(f"❌ Metals Conversion: unexpected HG implied rate {hg_rate}")
        return False

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    metals_path = os.path.join(base_dir, "tests/fixtures/metals_sample.json")
    metals_data = fetcher.fetch_from_fixture(metals_path)
    strategy = MetalsArbitrageStrategy()
    original_thresholds = load_metals_thresholds()

    try:
        save_metals_thresholds(
            {
                **original_thresholds,
                "AU0": {"upper": 10.0, "lower": -10.0},
                "AG0": {"upper": 10.0, "lower": -10.0},
            }
        )
        if get_effective_metal_threshold("AU0")["upper"] != 10.0:
            print("❌ Metals Thresholds: hot reload not applied")
            return False
        muted_signals = strategy.evaluate(metals_data)
        if muted_signals:
            print(f"❌ Metals Thresholds: expected 0 muted signals, got {len(muted_signals)}")
            return False

        save_metals_thresholds(
            {
                **original_thresholds,
                "AU0": {"upper": 1.0, "lower": -1.0},
                "AG0": {"upper": 2.0, "lower": -2.0},
            }
        )
        active_signals = strategy.evaluate(metals_data)
    finally:
        save_metals_thresholds(original_thresholds)

    if len(active_signals) != 2:
        print(f"❌ Metals Thresholds: expected 2 active signals, got {len(active_signals)}")
        return False

    reset_metals_thresholds()
    logger.info("metals_conversion_and_thresholds_ok", signals=len(active_signals))
    print("✅ Metals Conversion & Thresholds: OK")
    return True

def test_legacy_metals_threshold_migration():
    """测试旧版金属阈值文件的显式迁移和字段兼容性。"""
    logger.info("test_legacy_metals_threshold_migration_start")

    from pathlib import Path
    import config.metals_thresholds as metals_config

    original_new_path_fn = metals_config.get_metals_thresholds_path
    original_local_path_fn = metals_config.get_local_metals_thresholds_path
    original_legacy_path_fn = metals_config.get_legacy_metals_thresholds_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        new_path = temp_root / "config" / "metals_thresholds.json"
        local_path = temp_root / "config" / "metals_thresholds.local.json"
        legacy_path = temp_root / "data" / "metals_thresholds.json"
        new_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)

        new_path.write_text(
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
        legacy_path.write_text(
            json.dumps(
                {
                    "AU0": {"upper": 1.0, "lower": -1.0},
                    "AG0": {"upper": 8.0, "lower": -8.0},
                    "REMOVED_SYMBOL": {"upper": 99.0, "lower": -99.0},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        metals_config.get_metals_thresholds_path = lambda: new_path
        metals_config.get_local_metals_thresholds_path = lambda: local_path
        metals_config.get_legacy_metals_thresholds_path = lambda: legacy_path
        metals_config._threshold_cache = None

        try:
            preview = metals_config.get_legacy_metals_thresholds_preview()
            if preview is None:
                print("❌ Metals Migration: expected migration preview")
                return False
            if len(preview["differences"]) != 1 or preview["differences"][0]["symbol"] != "AG0":
                print(f"❌ Metals Migration: unexpected diff preview {preview['differences']}")
                return False

            result = metals_config.migrate_legacy_metals_thresholds()
            if not result["migrated"] or result["count"] != 1:
                print(f"❌ Metals Migration: unexpected migrate result {result}")
                return False
            if legacy_path.exists():
                print("❌ Metals Migration: legacy file should be removed after migration")
                return False

            migrated = json.loads(local_path.read_text(encoding="utf-8"))
            if migrated["AG0"]["upper"] != 8.0 or migrated["AG0"]["lower"] != -8.0:
                print(f"❌ Metals Migration: AG0 not migrated correctly {migrated['AG0']}")
                return False
            if "REMOVED_SYMBOL" in migrated:
                print("❌ Metals Migration: removed symbol should not be kept")
                return False
            effective = metals_config.load_metals_thresholds(force_reload=True)
            if "PT0" not in effective:
                print("❌ Metals Migration: effective thresholds should still include new symbols")
                return False
        finally:
            metals_config.get_metals_thresholds_path = original_new_path_fn
            metals_config.get_local_metals_thresholds_path = original_local_path_fn
            metals_config.get_legacy_metals_thresholds_path = original_legacy_path_fn
            metals_config._threshold_cache = None

    logger.info("legacy_metals_threshold_migration_ok")
    print("✅ Legacy Metals Threshold Migration: OK")
    return True

def test_current_metals_threshold_file_compatibility():
    """测试当前 config/metals_thresholds.json 的旧结构兼容性。"""
    logger.info("test_current_metals_threshold_file_compatibility_start")

    from pathlib import Path
    import config.metals_thresholds as metals_config

    original_new_path_fn = metals_config.get_metals_thresholds_path
    original_local_path_fn = metals_config.get_local_metals_thresholds_path
    original_legacy_path_fn = metals_config.get_legacy_metals_thresholds_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        new_path = temp_root / "config" / "metals_thresholds.json"
        local_path = temp_root / "config" / "metals_thresholds.local.json"
        legacy_path = temp_root / "data" / "metals_thresholds.json"
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # 模拟同路径老版本: 缺少新金属、包含已删除金属、部分字段缺失
        new_path.write_text(
            json.dumps(
                {
                    "AU0": {"upper": 1.2},
                    "AG0": {"lower": -9.0},
                    "REMOVED_SYMBOL": {"upper": 99.0, "lower": -99.0},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        metals_config.get_metals_thresholds_path = lambda: new_path
        metals_config.get_local_metals_thresholds_path = lambda: local_path
        metals_config.get_legacy_metals_thresholds_path = lambda: legacy_path
        metals_config._threshold_cache = None

        try:
            normalized = metals_config.load_metals_thresholds(force_reload=True)
            if normalized["AU0"]["upper"] != 1.2 or normalized["AU0"]["lower"] != -1.0:
                print(f"❌ Metals Current Config: AU0 normalization mismatch {normalized['AU0']}")
                return False
            if normalized["AG0"]["upper"] != 2.0 or normalized["AG0"]["lower"] != -9.0:
                print(f"❌ Metals Current Config: AG0 normalization mismatch {normalized['AG0']}")
                return False
            if "REMOVED_SYMBOL" in normalized:
                print("❌ Metals Current Config: removed symbol should be discarded")
                return False
            if "PT0" not in normalized:
                print("❌ Metals Current Config: missing new symbol defaults")
                return False

            rewritten = json.loads(new_path.read_text(encoding="utf-8"))
            if "REMOVED_SYMBOL" in rewritten:
                print("❌ Metals Current Config: stale symbol should not remain after rewrite")
                return False
            if rewritten["PT0"]["upper"] != 2.0 or rewritten["PT0"]["lower"] != -2.0:
                print(f"❌ Metals Current Config: new symbol defaults missing {rewritten['PT0']}")
                return False
        finally:
            metals_config.get_metals_thresholds_path = original_new_path_fn
            metals_config.get_local_metals_thresholds_path = original_local_path_fn
            metals_config.get_legacy_metals_thresholds_path = original_legacy_path_fn
            metals_config._threshold_cache = None

    logger.info("current_metals_threshold_file_compatibility_ok")
    print("✅ Current Metals Threshold File Compatibility: OK")
    return True

