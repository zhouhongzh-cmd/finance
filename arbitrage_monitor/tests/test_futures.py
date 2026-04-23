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

def test_futures_dual_threshold_trigger():
    """测试期指贴水率阈值和年化贴水率阈值必须同时触发才报警。"""
    logger.info("test_futures_dual_threshold_trigger_start")

    from models.market_data import FuturesData
    from strategies.futures_strategy import FuturesDiscountStrategy
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
                    product: {
                        "backwardation_enabled": True,
                        "backwardation_threshold": 1.0,
                        "annualized_backwardation_threshold": 20.0,
                        "contango_enabled": True,
                        "contango_threshold": 1.0,
                        "annualized_contango_threshold": 20.0,
                    }
                    for product in ("IH", "IF", "IC", "IM")
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
            strategy = FuturesDiscountStrategy()
            percent_only = strategy.evaluate(
                [
                    FuturesData(
                        symbol="IF2604",
                        timestamp=datetime.now(),
                        price=3500,
                        spot_price=3540,
                        discount_rate=1.2,
                        product_code="IF",
                        days_to_maturity=40,
                    )
                ]
            )
            annualized_only = strategy.evaluate(
                [
                    FuturesData(
                        symbol="IC2606",
                        timestamp=datetime.now(),
                        price=5100,
                        spot_price=5120,
                        discount_rate=0.4,
                        product_code="IC",
                        days_to_maturity=5,
                    )
                ]
            )
            none_triggered = strategy.evaluate(
                [
                    FuturesData(
                        symbol="IH2604",
                        timestamp=datetime.now(),
                        price=2400,
                        spot_price=2410,
                        discount_rate=0.2,
                        product_code="IH",
                        days_to_maturity=20,
                    )
                ]
            )
            both_triggered = strategy.evaluate(
                [
                    FuturesData(
                        symbol="IM2604",
                        timestamp=datetime.now(),
                        price=5200,
                        spot_price=5300,
                        discount_rate=2.2,
                        product_code="IM",
                        days_to_maturity=20,
                    )
                ]
            )
        finally:
            futures_config.get_futures_thresholds_path = original_shared_path_fn
            futures_config.get_local_futures_thresholds_path = original_local_path_fn
            futures_config._threshold_cache = original_cache

    if percent_only:
        print(f"❌ Futures Dual Threshold: percent-only sample should not trigger, got {len(percent_only)}")
        return False
    if annualized_only:
        print(f"❌ Futures Dual Threshold: annualized-only sample should not trigger, got {len(annualized_only)}")
        return False
    if none_triggered:
        print("❌ Futures Dual Threshold: non-triggering sample should not alert")
        return False
    if len(both_triggered) != 1:
        print(f"❌ Futures Dual Threshold: expected dual trigger, got {len(both_triggered)}")
        return False
    if "同时满足" not in both_triggered[0].message:
        print("❌ Futures Dual Threshold: signal message missing dual-threshold wording")
        return False
    if "普通贴水阈值" not in both_triggered[0].message or "年化贴水阈值" not in both_triggered[0].message:
        print("❌ Futures Dual Threshold: signal message missing threshold detail")
        return False

    logger.info("futures_dual_threshold_trigger_ok")
    print("✅ Futures Dual Threshold: OK")
    return True

def test_strategy_threshold_hot_reload():
    """测试策略阈值热更新后立即影响判定。"""
    logger.info("test_strategy_threshold_hot_reload_start")

    from datetime import datetime
    from config.settings import settings
    from models.market_data import SentimentData
    from strategies.sentiment_strategy import SentimentStrategy

    original = {
        "SENTIMENT_HOT_SCORE_THRESHOLD": settings.SENTIMENT_HOT_SCORE_THRESHOLD,
        "SENTIMENT_PULSE_THRESHOLD": settings.SENTIMENT_PULSE_THRESHOLD,
        "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD": settings.ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD,
        "ENABLE_SENTIMENT_PULSE_THRESHOLD": settings.ENABLE_SENTIMENT_PULSE_THRESHOLD,
    }

    try:
        settings.apply_updates(
            {
                "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD": True,
                "ENABLE_SENTIMENT_PULSE_THRESHOLD": True,
                "SENTIMENT_HOT_SCORE_THRESHOLD": 500,
                "SENTIMENT_PULSE_THRESHOLD": -0.5,
            }
        )
        data = [
            SentimentData(
                symbol="TEST001",
                timestamp=datetime.now(),
                name="TEST001",
                hot_score=600,
                sentiment_pulse=-0.6,
                rank=1,
            )
        ]
        signals = SentimentStrategy().evaluate(data)
    finally:
        settings.apply_updates(original)

    if len(signals) != 2:
        print(f"❌ Strategy Hot Reload: expected 2 signals, got {len(signals)}")
        return False

    logger.info("strategy_threshold_hot_reload_ok", signals=len(signals))
    print("✅ Strategy Hot Reload: OK")
    return True

def test_active_futures_contract_generation():
    """测试季月场景下仍能生成 4 档有效合约。"""
    logger.info("test_active_futures_contract_generation_start")

    from datetime import date
    from fetchers.ak_futures import get_active_contracts

    contracts = get_active_contracts(today=date(2026, 3, 15))
    by_product: dict[str, list[str]] = {}
    for symbol, _, _ in contracts:
        by_product.setdefault(symbol[:2], []).append(symbol)

    expected = {
        "IF": ["IF2603", "IF2604", "IF2606", "IF2609"],
        "IH": ["IH2603", "IH2604", "IH2606", "IH2609"],
        "IC": ["IC2603", "IC2604", "IC2606", "IC2609"],
        "IM": ["IM2603", "IM2604", "IM2606", "IM2609"],
    }

    for product_code, expected_symbols in expected.items():
        actual = by_product.get(product_code)
        if actual != expected_symbols:
            print(
                f"❌ Active Contracts: {product_code} expected {expected_symbols}, got {actual}"
            )
            return False

    logger.info("active_futures_contract_generation_ok", contracts=len(contracts))
    print("✅ Active Contracts: quarter-month generation OK")
    return True

def test_futures_margin_enrichment():
    """测试期指保证金比例解析、落库和行情补全。"""
    logger.info("test_futures_margin_enrichment_start")

    from fetchers.futures_margin import FuturesMarginFetcher, futures_margin_fetcher
    from fetchers.ak_futures import futures_fetcher
    from models.market_data import FuturesMarginData

    fetcher = FuturesMarginFetcher()
    list_html = '<a href="/bzjjzdtb/92035.jhtml">2026年3月13日结算保证金及涨跌停板</a>'
    detail_url = fetcher._extract_latest_cicc_detail_url(list_html)
    if detail_url != "https://www.ciccwmf.cn/bzjjzdtb/92035.jhtml":
        print(f"❌ Futures Margin: unexpected detail url {detail_url}")
        return False

    detail_html = """
    <table>
      <tr><th>交易所</th><th>品种</th><th>保证金标准</th></tr>
      <tr><td>中金所</td><td>沪深300期货IF</td><td>14%</td></tr>
      <tr><td>中金所</td><td>上证50期货IH</td><td>14%</td></tr>
      <tr><td>中金所</td><td>中证500期货IC</td><td>15%</td></tr>
      <tr><td>中金所</td><td>中证1000期货IM</td><td>15%</td></tr>
    </table>
    """
    ratios = fetcher._extract_cicc_margin_ratios(detail_html)
    if ratios != {"IF": 14.0, "IH": 14.0, "IC": 15.0, "IM": 15.0}:
        print(f"❌ Futures Margin: unexpected parsed ratios {ratios}")
        return False

    sample_html = "<table><tr><td>交易保证金标准</td><td>8%</td></tr></table>"
    ratio = fetcher._extract_margin_ratio(sample_html)
    if ratio != 8.0:
        print(f"❌ Futures Margin: unexpected parsed ratio {ratio}")
        return False

    now = datetime.now()
    db = DBManager()
    db.save_futures_margin_snapshots(
        [
            FuturesMarginData(
                symbol="IF",
                timestamp=now,
                margin_ratio=12.0,
                source="test",
                source_url="https://example.com/if",
            ),
            FuturesMarginData(
                symbol="IC",
                timestamp=now,
                margin_ratio=14.0,
                source="test",
                source_url="https://example.com/ic",
            ),
        ]
    )

    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM futures_margin_snapshot
            WHERE product_code IN ('IF', 'IC') AND fetched_at = ?
            """,
            (now.isoformat(),),
        )
        snapshot_count = cursor.fetchone()[0]
    if snapshot_count != 2:
        print(
            "❌ Futures Margin: expected 2 inserted snapshots for current test run, "
            f"got {snapshot_count}"
        )
        return False

    original_get_latest_margin_ratio = futures_margin_fetcher.get_latest_margin_ratio
    futures_margin_fetcher.get_latest_margin_ratio = lambda product_code: {
        "IF": 12.0,
        "IC": 14.0,
    }.get(product_code, original_get_latest_margin_ratio(product_code))
    try:
        data = futures_fetcher.fetch_from_fixture("tests/fixtures/futures_sample.json")
    finally:
        futures_margin_fetcher.get_latest_margin_ratio = original_get_latest_margin_ratio

    if not data:
        print("❌ Futures Margin: no futures data loaded")
        return False

    first = data[0]
    second = data[1]
    if first.product_code != "IF" or round(first.margin_ratio, 2) != 12.0:
        print(f"❌ Futures Margin: unexpected IF margin {first.margin_ratio}")
        return False
    if round(first.notional_per_lot, 2) != round(first.price * 300, 2):
        print(f"❌ Futures Margin: unexpected IF notional {first.notional_per_lot}")
        return False
    if round(first.margin_required_per_lot, 2) != round(first.notional_per_lot * 0.12, 2):
        print(
            "❌ Futures Margin: unexpected IF margin required "
            f"{first.margin_required_per_lot}"
        )
        return False

    if second.product_code != "IC" or round(second.margin_ratio, 2) != 14.0:
        print(f"❌ Futures Margin: unexpected IC margin {second.margin_ratio}")
        return False

    logger.info(
        "futures_margin_enriched",
        if_margin=first.margin_ratio,
        ic_margin=second.margin_ratio,
    )
    print(
        "✅ Futures Margin: "
        f"IF={first.margin_ratio:.2f}% margin={first.margin_required_per_lot:.0f}, "
        f"IC={second.margin_ratio:.2f}%"
    )
    return True

def test_spot_index_fallback_parser():
    """测试新浪指数备源解析。"""
    logger.info("test_spot_index_fallback_parser_start")

    from fetchers.ak_futures import FuturesFetcher

    fetcher = FuturesFetcher()
    sample = (
        'var hq_str_sh000300="沪深300,4669.0619,4687.5601,4669.1400,4707.4194,4659.4979,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-03-13,15:35:29,00,";\n'
        'var hq_str_sh000016="上证50,2961.7335,2971.5612,2956.8468,2977.8417,2951.7012,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-03-13,15:35:41,00,";\n'
        'var hq_str_sh000905="中证500,8317.7799,8359.4721,8239.7980,8371.7157,8217.9686,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-03-13,15:35:35,00,";\n'
        'var hq_str_sz399852="中证1000,8297.913,8335.908,8214.293,8350.917,8196.374,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-03-13,15:00:42,00,";'
    )
    parsed = fetcher._parse_sina_index_response(sample)
    expected = {
        "000300": 4669.14,
        "000016": 2956.8468,
        "000905": 8239.798,
        "000852": 8214.293,
    }
    if parsed != expected:
        print(f"❌ Spot Index Fallback: expected {expected}, got {parsed}")
        return False

    logger.info("spot_index_fallback_parser_ok", count=len(parsed))
    print("✅ Spot Index Fallback: parser OK")
    return True

