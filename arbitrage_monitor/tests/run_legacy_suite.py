from __future__ import annotations

import sys
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parents[1]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from tests.test_snapshot_storage import (
    test_alert_history_append_only,
    test_db_manager,
    test_db_indexes_initialized,
    test_latest_snapshot_readers,
    test_snapshot_deduplication,
)
from tests.test_notification import test_full_pipeline, test_notifier
from tests.test_runtime_config import (
    test_config_audit_history,
    test_futures_threshold_local_override,
    test_metals_threshold_local_override,
    test_premium_threshold_delivery_mapping,
    test_premium_threshold_local_override,
    test_runtime_config_local_override,
    test_runtime_config_writer,
)
from tests.test_futures import (
    test_active_futures_contract_generation,
    test_futures_dual_threshold_trigger,
    test_futures_margin_enrichment,
    test_spot_index_fallback_parser,
    test_strategy_threshold_hot_reload,
)
from tests.test_convertible import test_convertible_fallback_estimation, test_convertible_status_filter
from tests.test_sentiment import test_sentiment_name_lookup
from tests.test_metals import (
    test_current_metals_threshold_file_compatibility,
    test_legacy_metals_threshold_migration,
    test_metals_conversion_and_thresholds,
)
from tests.test_premium import test_premium_module_integration
from tests.test_scheduler import (
    test_cooldown_restore_roundtrip,
    test_module_schedule_windows,
    test_scheduler_imports,
    test_scheduler_runtime_settings_sync,
)
from tests.test_dashboard import test_dashboard_table_ordering
from tests.test_retention_and_ops import (
    test_job_run_status_tracking,
    test_retention_cleanup,
    test_source_health_tracking,
    test_storage_maintenance_reclaims_freelist,
)
from tests.test_fetchers_and_strategies import (
    test_fetchers_mock,
    test_mode_enable_switches,
    test_strategies,
    test_strategy_enable_switches,
    test_threshold_enable_switches,
)
from utils.logger import logger


def main():
    print("\n" + "=" * 60)
    print("🧪 套利监控系统 - 端到端集成测试")
    print("=" * 60 + "\n")

    tests = [
        ("Database Manager", test_db_manager),
        ("Notifier", test_notifier),
        ("Runtime Config Writer", test_runtime_config_writer),
        ("Runtime Config Local Override", test_runtime_config_local_override),
        ("Futures Dual Threshold", test_futures_dual_threshold_trigger),
        ("Strategy Hot Reload", test_strategy_threshold_hot_reload),
        ("Strategy Enable Switches", test_strategy_enable_switches),
        ("Mode Enable Switches", test_mode_enable_switches),
        ("Threshold Enable Switches", test_threshold_enable_switches),
        ("DB Indexes Initialized", test_db_indexes_initialized),
        ("Alert History Append Only", test_alert_history_append_only),
        ("Snapshot Deduplication", test_snapshot_deduplication),
        ("Latest Snapshot Readers", test_latest_snapshot_readers),
        ("Scheduler Runtime Sync", test_scheduler_runtime_settings_sync),
        ("Cooldown Restore", test_cooldown_restore_roundtrip),
        ("Retention Cleanup", test_retention_cleanup),
        ("Storage Maintenance", test_storage_maintenance_reclaims_freelist),
        ("Fetchers (Mock)", test_fetchers_mock),
        ("Strategies", test_strategies),
        ("Metals Conversion", test_metals_conversion_and_thresholds),
        ("Dashboard Table Ordering", test_dashboard_table_ordering),
        ("Legacy Metals Migration", test_legacy_metals_threshold_migration),
        ("Current Metals Config Compatibility", test_current_metals_threshold_file_compatibility),
        ("Metals Threshold Local Override", test_metals_threshold_local_override),
        ("Futures Threshold Local Override", test_futures_threshold_local_override),
        ("Premium Threshold Local Override", test_premium_threshold_local_override),
        ("Premium Threshold Delivery Mapping", test_premium_threshold_delivery_mapping),
        ("Source Health Tracking", test_source_health_tracking),
        ("Config Audit History", test_config_audit_history),
        ("Job Run Status Tracking", test_job_run_status_tracking),
        ("Convertible Fallback", test_convertible_fallback_estimation),
        ("Convertible Status Filter", test_convertible_status_filter),
        ("Sentiment Name Lookup", test_sentiment_name_lookup),
        ("Futures Margin", test_futures_margin_enrichment),
        ("Active Contracts", test_active_futures_contract_generation),
        ("Spot Index Fallback", test_spot_index_fallback_parser),
        ("Module Schedule Windows", test_module_schedule_windows),
        ("Premium Module Integration", test_premium_module_integration),
        ("Scheduler Imports", test_scheduler_imports),
        ("Full Pipeline", test_full_pipeline),
    ]

    passed = 0
    failed = 0
    skipped = 0

    for name, test_func in tests:
        try:
            result = test_func()
            if result is True:
                passed += 1
            elif result == "SKIP":
                skipped += 1
            else:
                failed += 1
        except Exception as exc:
            logger.error("test_failed", test=name, error=str(exc), exc_info=True)
            print(f"❌ {name}: EXCEPTION - {exc}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"📊 测试结果：{passed} 通过，{failed} 失败，{skipped} 跳过")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
