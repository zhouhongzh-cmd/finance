from __future__ import annotations

from providers.ib_gateway import (
    IBConnectionParams,
    IBContractSpec,
    IBGatewayProvider,
    IBMarketSnapshot,
    IBResolvedContract,
)


class _FakeSettings:
    IB_DEFAULT_PROFILE = "remote"
    IB_REMOTE_HOST = "100.99.204.61"
    IB_REMOTE_PORT = 4001
    IB_REMOTE_CLIENT_ID = 60101
    IB_LOCAL_HOST = "127.0.0.1"
    IB_LOCAL_PORT = 4002
    IB_LOCAL_CLIENT_ID = 60102
    IB_GATEWAY_TIMEOUT_SECONDS = 15


class _FakeSession:
    def __init__(self, params: IBConnectionParams):
        self.params = params
        self.connected = False

    def connect_and_wait(self, params: IBConnectionParams) -> None:
        self.connected = True

    def disconnect_safely(self) -> None:
        self.connected = False

    def resolve_contract(self, spec: IBContractSpec, timeout_seconds: int):
        return [
            IBResolvedContract(
                key=spec.key,
                symbol=spec.symbol,
                sec_type=spec.sec_type,
                exchange=spec.exchange,
                primary_exchange=spec.primary_exchange,
                currency=spec.currency,
                local_symbol=spec.local_symbol or spec.symbol,
                trading_class=spec.trading_class,
                con_id=hash((spec.key, self.params.profile)) % 100000,
                last_trade_date_or_contract_month="20260529" if "future" in spec.key else "",
            )
        ]

    def request_market_data(self, resolved_contract: IBResolvedContract, timeout_seconds: int):
        price = 20000.0 if "future" in resolved_contract.key else 19888.0
        return IBMarketSnapshot(
            key=resolved_contract.key,
            symbol=resolved_contract.symbol,
            sec_type=resolved_contract.sec_type,
            exchange=resolved_contract.exchange,
            primary_exchange=resolved_contract.primary_exchange,
            currency=resolved_contract.currency,
            local_symbol=resolved_contract.local_symbol,
            trading_class=resolved_contract.trading_class,
            con_id=resolved_contract.con_id,
            last_price=price,
            close_price=price - 10,
            market_data_type=3,
            source="",
            raw_ticks={"price_4": price},
        )


def test_ib_provider_profile_selection():
    provider = IBGatewayProvider(
        settings_obj=_FakeSettings(),
        session_factory=lambda params: _FakeSession(params),
    )

    remote = provider.build_connection_params()
    local = provider.build_connection_params(profile="local")
    explicit = provider.build_connection_params(
        profile="remote",
        host="192.168.1.10",
        port=7497,
        client_id=77,
        timeout_seconds=30,
    )

    assert remote.profile == "remote"
    assert remote.host == "100.99.204.61"
    assert local.profile == "local"
    assert local.port == 4002
    assert explicit.host == "192.168.1.10"
    assert explicit.port == 7497
    assert explicit.client_id == 77
    assert explicit.timeout_seconds == 30


def test_ib_provider_index_pair_snapshot_uses_profile_source():
    provider = IBGatewayProvider(
        settings_obj=_FakeSettings(),
        session_factory=lambda params: _FakeSession(params),
    )

    pair = provider.get_index_pair_snapshot(
        asset_key="HSI",
        spot_spec=IBContractSpec(
            key="HSI_spot",
            symbol="HSI",
            sec_type="IND",
            exchange="HKFE",
            currency="HKD",
        ),
        future_spec=IBContractSpec(
            key="HSI_future",
            symbol="HSI",
            sec_type="CONTFUT",
            exchange="HKFE",
            currency="HKD",
        ),
        profile="local",
    )

    assert pair.profile == "local"
    assert pair.spot is not None
    assert pair.future is not None
    assert pair.spot.source == "ib.local.reqMktData"
    assert pair.future.source == "ib.local.reqMktData"
    assert pair.future.best_price == 20000.0
