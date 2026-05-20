from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from utils.logger import logger

try:
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.wrapper import EWrapper
except Exception as exc:  # pragma: no cover - exercised through runtime fallback
    EClient = object  # type: ignore[assignment]
    EWrapper = object  # type: ignore[assignment]
    Contract = None  # type: ignore[assignment]
    _IBAPI_IMPORT_ERROR = exc
else:
    _IBAPI_IMPORT_ERROR = None


MARKET_LAST_TICKS = (4, 68)
MARKET_CLOSE_TICKS = (9, 75)
MARKET_EVENT_TICKS = MARKET_LAST_TICKS + MARKET_CLOSE_TICKS


@dataclass(frozen=True)
class IBConnectionParams:
    profile: str
    host: str
    port: int
    client_id: int
    timeout_seconds: int

    @property
    def source_name(self) -> str:
        return f"ib.{self.profile}.reqMktData"


@dataclass(frozen=True)
class IBContractSpec:
    key: str
    symbol: str
    sec_type: str
    exchange: str
    currency: str
    primary_exchange: str = ""
    local_symbol: str = ""
    trading_class: str = ""
    last_trade_date_or_contract_month: str = ""
    include_expired: bool = False


@dataclass(frozen=True)
class IBResolvedContract:
    key: str
    symbol: str
    sec_type: str
    exchange: str
    primary_exchange: str
    currency: str
    local_symbol: str
    trading_class: str
    con_id: int
    last_trade_date_or_contract_month: str = ""


@dataclass(frozen=True)
class IBMarketSnapshot:
    key: str
    symbol: str
    sec_type: str
    exchange: str
    primary_exchange: str
    currency: str
    local_symbol: str
    trading_class: str
    con_id: int
    last_price: float | None
    close_price: float | None
    market_data_type: int | None
    source: str
    raw_ticks: dict[str, Any] = field(default_factory=dict)

    @property
    def best_price(self) -> float | None:
        if self.last_price not in (None, 0):
            return self.last_price
        if self.close_price not in (None, 0):
            return self.close_price
        return None


@dataclass(frozen=True)
class IBIndexPairSnapshot:
    asset_key: str
    profile: str
    spot: IBMarketSnapshot | None
    future: IBMarketSnapshot | None


class _IBApiSession(EWrapper, EClient):
    def __init__(self, timeout_seconds: int):
        if _IBAPI_IMPORT_ERROR is not None:
            raise RuntimeError(f"ibapi import failed: {_IBAPI_IMPORT_ERROR}")
        EClient.__init__(self, self)
        self.timeout_seconds = timeout_seconds
        self.next_id: int | None = None
        self._next_id_event = threading.Event()
        self._req_id = 1
        self._req_lock = threading.Lock()
        self._contract_events: dict[int, threading.Event] = {}
        self._contract_rows: dict[int, list[IBResolvedContract]] = {}
        self._market_events: dict[int, threading.Event] = {}
        self._market_rows: dict[int, dict[str, Any]] = {}
        self.errors: list[tuple[int, int, str]] = []

    def connectAck(self):
        logger.info("ib_connect_ack")

    def nextValidId(self, orderId):
        self.next_id = orderId
        self._next_id_event.set()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        self.errors.append((int(reqId), int(errorCode), str(errorString)))
        if reqId in self._contract_events:
            self._contract_events[reqId].set()
        if reqId in self._market_events:
            self._market_events[reqId].set()

    def contractDetails(self, reqId, contractDetails):
        contract = contractDetails.contract
        self._contract_rows.setdefault(reqId, []).append(
            IBResolvedContract(
                key="",
                symbol=str(contract.symbol or ""),
                sec_type=str(contract.secType or ""),
                exchange=str(contract.exchange or ""),
                primary_exchange=str(contract.primaryExchange or ""),
                currency=str(contract.currency or ""),
                local_symbol=str(contract.localSymbol or ""),
                trading_class=str(contract.tradingClass or ""),
                con_id=int(contract.conId or 0),
                last_trade_date_or_contract_month=str(
                    contract.lastTradeDateOrContractMonth or ""
                ),
            )
        )

    def contractDetailsEnd(self, reqId):
        event = self._contract_events.get(reqId)
        if event is not None:
            event.set()

    def marketDataType(self, reqId, marketDataType):
        self._market_rows.setdefault(reqId, {})["market_data_type"] = int(marketDataType)

    def tickPrice(self, reqId, tickType, price, attrib):
        self._market_rows.setdefault(reqId, {})[f"price_{tickType}"] = float(price)
        if tickType in MARKET_EVENT_TICKS and price not in (None, 0):
            event = self._market_events.get(reqId)
            if event is not None:
                event.set()

    def tickSize(self, reqId, tickType, size):
        self._market_rows.setdefault(reqId, {})[f"size_{tickType}"] = int(size)

    def tickString(self, reqId, tickType, value):
        self._market_rows.setdefault(reqId, {})[f"str_{tickType}"] = str(value)
        if tickType in MARKET_EVENT_TICKS and value:
            event = self._market_events.get(reqId)
            if event is not None:
                event.set()

    def connect_and_wait(self, params: IBConnectionParams) -> None:
        self.connect(params.host, params.port, clientId=params.client_id)
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        if not self._next_id_event.wait(params.timeout_seconds):
            raise TimeoutError(
                f"Timed out waiting for IB nextValidId from {params.host}:{params.port}"
            )

    def disconnect_safely(self) -> None:
        try:
            self.disconnect()
        except Exception:
            logger.warning("ib_disconnect_failed")

    def next_request_id(self) -> int:
        with self._req_lock:
            req_id = self._req_id
            self._req_id += 1
            return req_id

    def resolve_contract(self, spec: IBContractSpec, timeout_seconds: int) -> list[IBResolvedContract]:
        if Contract is None:
            raise RuntimeError("ibapi Contract is unavailable")
        req_id = self.next_request_id()
        event = threading.Event()
        self._contract_events[req_id] = event
        contract = Contract()
        contract.symbol = spec.symbol
        contract.secType = spec.sec_type
        contract.exchange = spec.exchange
        contract.currency = spec.currency
        contract.primaryExchange = spec.primary_exchange
        contract.localSymbol = spec.local_symbol
        contract.tradingClass = spec.trading_class
        contract.lastTradeDateOrContractMonth = spec.last_trade_date_or_contract_month
        contract.includeExpired = spec.include_expired
        self.reqContractDetails(req_id, contract)
        event.wait(timeout_seconds)
        rows = self._contract_rows.get(req_id, [])
        return [
            IBResolvedContract(
                key=spec.key,
                symbol=row.symbol,
                sec_type=row.sec_type,
                exchange=row.exchange,
                primary_exchange=row.primary_exchange,
                currency=row.currency,
                local_symbol=row.local_symbol,
                trading_class=row.trading_class,
                con_id=row.con_id,
                last_trade_date_or_contract_month=row.last_trade_date_or_contract_month,
            )
            for row in rows
        ]

    def request_market_data(
        self,
        resolved_contract: IBResolvedContract,
        timeout_seconds: int,
    ) -> IBMarketSnapshot:
        if Contract is None:
            raise RuntimeError("ibapi Contract is unavailable")
        req_id = self.next_request_id()
        event = threading.Event()
        self._market_events[req_id] = event
        contract = Contract()
        contract.conId = resolved_contract.con_id
        contract.symbol = resolved_contract.symbol
        contract.secType = resolved_contract.sec_type
        contract.exchange = resolved_contract.exchange or resolved_contract.primary_exchange
        contract.primaryExchange = resolved_contract.primary_exchange
        contract.currency = resolved_contract.currency
        contract.localSymbol = resolved_contract.local_symbol
        contract.tradingClass = resolved_contract.trading_class
        self.reqMarketDataType(3)
        self.reqMktData(req_id, contract, "", False, False, [])
        event.wait(timeout_seconds)
        try:
            self.cancelMktData(req_id)
        except Exception:
            logger.warning("ib_cancel_mkt_data_failed", req_id=req_id)
        row = self._market_rows.get(req_id, {})
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
            last_price=_pick_first_float(row, *[f"price_{tick}" for tick in MARKET_LAST_TICKS]),
            close_price=_pick_first_float(row, *[f"price_{tick}" for tick in MARKET_CLOSE_TICKS]),
            market_data_type=_safe_int(row.get("market_data_type")),
            source="",
            raw_ticks=dict(row),
        )


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def _pick_first_float(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        try:
            if value not in (None, ""):
                return float(value)
        except Exception:
            continue
    return None


class IBGatewayProvider:
    def __init__(
        self,
        *,
        settings_obj=settings,
        session_factory: Callable[[IBConnectionParams], Any] | None = None,
    ):
        self.settings = settings_obj
        self._session_factory = session_factory

    def build_connection_params(
        self,
        *,
        profile: str | None = None,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        timeout_seconds: int | None = None,
    ) -> IBConnectionParams:
        resolved_profile = (profile or self.settings.IB_DEFAULT_PROFILE).lower()
        if resolved_profile not in {"remote", "local"}:
            raise ValueError(f"Unsupported IB profile: {resolved_profile}")

        prefix = "IB_REMOTE" if resolved_profile == "remote" else "IB_LOCAL"
        resolved_host = host or str(getattr(self.settings, f"{prefix}_HOST"))
        resolved_port = int(port or getattr(self.settings, f"{prefix}_PORT"))
        resolved_client_id = int(client_id or getattr(self.settings, f"{prefix}_CLIENT_ID"))
        resolved_timeout = int(timeout_seconds or self.settings.IB_GATEWAY_TIMEOUT_SECONDS)
        return IBConnectionParams(
            profile=resolved_profile,
            host=resolved_host,
            port=resolved_port,
            client_id=resolved_client_id,
            timeout_seconds=resolved_timeout,
        )

    def tcp_probe(self, *, profile: str | None = None, host: str | None = None, port: int | None = None) -> tuple[bool, str | None, IBConnectionParams]:
        params = self.build_connection_params(profile=profile, host=host, port=port)
        try:
            with socket.create_connection((params.host, params.port), timeout=min(params.timeout_seconds, 5)):
                return True, None, params
        except Exception as exc:
            return False, str(exc), params

    def resolve_contracts(
        self,
        contract_specs: Iterable[IBContractSpec],
        *,
        profile: str | None = None,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, list[IBResolvedContract]]:
        params = self.build_connection_params(
            profile=profile,
            host=host,
            port=port,
            client_id=client_id,
            timeout_seconds=timeout_seconds,
        )
        results: dict[str, list[IBResolvedContract]] = {}

        def runner(session: Any) -> None:
            for spec in contract_specs:
                results[spec.key] = session.resolve_contract(spec, params.timeout_seconds)

        self._run_with_session(params, runner)
        return results

    def get_market_snapshot(
        self,
        resolved_contract: IBResolvedContract,
        *,
        profile: str | None = None,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        timeout_seconds: int | None = None,
    ) -> IBMarketSnapshot:
        params = self.build_connection_params(
            profile=profile,
            host=host,
            port=port,
            client_id=client_id,
            timeout_seconds=timeout_seconds,
        )
        snapshot: IBMarketSnapshot | None = None

        def runner(session: Any) -> None:
            nonlocal snapshot
            snapshot = session.request_market_data(resolved_contract, params.timeout_seconds)

        self._run_with_session(params, runner)
        if snapshot is None:
            raise RuntimeError("IB market snapshot request returned no data")
        return self._with_source(snapshot, params.source_name)

    def get_index_pair_snapshot(
        self,
        *,
        asset_key: str,
        spot_spec: IBContractSpec,
        future_spec: IBContractSpec,
        profile: str | None = None,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        timeout_seconds: int | None = None,
    ) -> IBIndexPairSnapshot:
        params = self.build_connection_params(
            profile=profile,
            host=host,
            port=port,
            client_id=client_id,
            timeout_seconds=timeout_seconds,
        )
        resolved: dict[str, IBMarketSnapshot | None] = {
            spot_spec.key: None,
            future_spec.key: None,
        }

        def runner(session: Any) -> None:
            for spec in (spot_spec, future_spec):
                contracts = session.resolve_contract(spec, params.timeout_seconds)
                if not contracts:
                    logger.warning(
                        "ib_contract_missing",
                        asset_key=asset_key,
                        contract_key=spec.key,
                        profile=params.profile,
                    )
                    continue
                resolved_contract = contracts[0]
                resolved[spec.key] = self._with_source(
                    session.request_market_data(resolved_contract, params.timeout_seconds),
                    params.source_name,
                )

        self._run_with_session(params, runner)
        return IBIndexPairSnapshot(
            asset_key=asset_key,
            profile=params.profile,
            spot=resolved.get(spot_spec.key),
            future=resolved.get(future_spec.key),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _run_with_session(self, params: IBConnectionParams, callback: Callable[[Any], None]) -> None:
        session = self._create_session(params)
        try:
            session.connect_and_wait(params)
            callback(session)
        finally:
            session.disconnect_safely()

    def _create_session(self, params: IBConnectionParams) -> Any:
        if self._session_factory is not None:
            return self._session_factory(params)
        return _IBApiSession(timeout_seconds=params.timeout_seconds)

    @staticmethod
    def _with_source(snapshot: IBMarketSnapshot, source_name: str) -> IBMarketSnapshot:
        return IBMarketSnapshot(
            key=snapshot.key,
            symbol=snapshot.symbol,
            sec_type=snapshot.sec_type,
            exchange=snapshot.exchange,
            primary_exchange=snapshot.primary_exchange,
            currency=snapshot.currency,
            local_symbol=snapshot.local_symbol,
            trading_class=snapshot.trading_class,
            con_id=snapshot.con_id,
            last_price=snapshot.last_price,
            close_price=snapshot.close_price,
            market_data_type=snapshot.market_data_type,
            source=source_name,
            raw_ticks=snapshot.raw_ticks,
        )


ib_gateway_provider = IBGatewayProvider()
