#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from providers.ib_gateway import IBContractSpec, ib_gateway_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Test IB Gateway API connectivity")
    parser.add_argument("--profile", choices=("remote", "local"), default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--client-id", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--with-hsi", action="store_true")
    args = parser.parse_args()

    params = ib_gateway_provider.build_connection_params(
        profile=args.profile,
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        timeout_seconds=args.timeout,
    )
    print(
        "PROFILE",
        params.profile,
        "HOST",
        params.host,
        "PORT",
        params.port,
        "CLIENT_ID",
        params.client_id,
        "TIMEOUT",
        params.timeout_seconds,
    )

    print("== TCP ==")
    ok, err, _ = ib_gateway_provider.tcp_probe(
        profile=args.profile,
        host=args.host,
        port=args.port,
    )
    if ok:
        print(f"TCP_OK {params.host}:{params.port}")
    else:
        print(f"TCP_FAIL {params.host}:{params.port} {err}")
        return 1

    if not args.with_hsi:
        print("SKIP_HSI use --with-hsi to query HSI IND/CONTFUT")
        return 0

    print("== HSI ==")
    spot_spec = IBContractSpec(
        key="HSI_spot",
        symbol="HSI",
        sec_type="IND",
        exchange="HKFE",
        currency="HKD",
    )
    future_spec = IBContractSpec(
        key="HSI_future",
        symbol="HSI",
        sec_type="CONTFUT",
        exchange="HKFE",
        currency="HKD",
    )

    contracts = ib_gateway_provider.resolve_contracts(
        [spot_spec, future_spec],
        profile=args.profile,
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        timeout_seconds=args.timeout,
    )
    for spec_key, rows in contracts.items():
        print(f"CONTRACTS {spec_key} {len(rows)}")
        for row in rows:
            print(
                "CONTRACT",
                spec_key,
                row.symbol,
                row.sec_type,
                row.exchange,
                row.primary_exchange,
                row.currency,
                row.local_symbol,
                row.trading_class,
                row.con_id,
            )

    pair = ib_gateway_provider.get_index_pair_snapshot(
        asset_key="HSI",
        spot_spec=spot_spec,
        future_spec=future_spec,
        profile=args.profile,
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        timeout_seconds=args.timeout,
    )
    for label, snapshot in (("spot", pair.spot), ("future", pair.future)):
        if snapshot is None:
            print(f"SNAPSHOT_MISSING {label}")
            continue
        print(
            "SNAPSHOT",
            label,
            snapshot.symbol,
            snapshot.sec_type,
            snapshot.local_symbol,
            snapshot.last_price,
            snapshot.close_price,
            snapshot.market_data_type,
            snapshot.source,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
