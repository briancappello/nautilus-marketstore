"""
MarketStore live data client for NautilusTrader.

Provides real-time streaming via MarketStore's WebSocket ``/ws`` endpoint
and historical data via the pymarketstore query API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pymarketstore as pymkts
from pymarketstore.async_stream import AsyncStreamConn

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.enums import LogColor
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import RequestBars
from nautilus_trader.data.messages import RequestData
from nautilus_trader.data.messages import RequestInstrument
from nautilus_trader.data.messages import RequestInstruments
from nautilus_trader.data.messages import RequestQuoteTicks
from nautilus_trader.data.messages import RequestTradeTicks
from nautilus_trader.data.messages import SubscribeBars
from nautilus_trader.data.messages import SubscribeData
from nautilus_trader.data.messages import SubscribeInstrument
from nautilus_trader.data.messages import SubscribeInstruments
from nautilus_trader.data.messages import SubscribeQuoteTicks
from nautilus_trader.data.messages import SubscribeTradeTicks
from nautilus_trader.data.messages import UnsubscribeBars
from nautilus_trader.data.messages import UnsubscribeData
from nautilus_trader.data.messages import UnsubscribeInstrument
from nautilus_trader.data.messages import UnsubscribeInstruments
from nautilus_trader.data.messages import UnsubscribeQuoteTicks
from nautilus_trader.data.messages import UnsubscribeTradeTicks
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Venue

from nautilus_marketstore.config import MarketStoreDataClientConfig
from nautilus_marketstore.constants import MARKETSTORE
from nautilus_marketstore.parsing import (
    df_to_bars,
    df_to_quote_ticks,
    df_to_trade_ticks,
    make_bar_type,
    ws_payload_to_bar,
    ws_payload_to_quote_tick,
    ws_payload_to_trade_tick,
)
from nautilus_marketstore.providers import MarketStoreInstrumentProvider


logger = logging.getLogger(__name__)


class MarketStoreDataClient(LiveMarketDataClient):
    """
    NautilusTrader live data client for MarketStore.

    Provides:
    - Real-time data streaming via MarketStore's WebSocket trigger plugin.
    - Historical data queries via pymarketstore's query API.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop for the client.
    msgbus : MessageBus
        The message bus for the client.
    cache : Cache
        The cache for the client.
    clock : LiveClock
        The clock for the client.
    instrument_provider : MarketStoreInstrumentProvider
        The instrument provider.
    config : MarketStoreDataClientConfig
        The configuration for the client.
    name : str, optional
        The custom client name/ID.

    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: MarketStoreInstrumentProvider,
        config: MarketStoreDataClientConfig,
        name: str | None = None,
    ) -> None:
        venue = Venue(config.venue)
        super().__init__(
            loop=loop,
            client_id=ClientId(name or MARKETSTORE),
            venue=venue,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
            config=config,
        )

        self._config = config
        self._venue = venue
        self._price_precision = config.price_precision
        self._size_precision = config.size_precision

        # pymarketstore query client (sync -- runs in thread executor for async)
        self._mkts_client = pymkts.Client(
            endpoint=config.endpoint_rpc,
            grpc=config.use_grpc,
        )

        # Async WebSocket streaming
        self._stream_conn = AsyncStreamConn(
            endpoint=config.endpoint_ws,
            reconnect_delay=config.reconnect_delay_secs,
        )
        self._stream_task: asyncio.Task | None = None

        # Subscription tracking: maps TBK pattern -> set of instrument_ids
        self._subscribed_bars: dict[str, tuple[InstrumentId, BarType]] = {}
        self._subscribed_trades: dict[str, InstrumentId] = {}
        self._subscribed_quotes: dict[str, InstrumentId] = {}

        # Register the universal handler for all stream messages
        self._stream_conn.register(r".*", self._on_ws_message)

    # -- CONNECTION ---------------------------------------------------------------

    async def _connect(self) -> None:
        self._log.info("Initializing instrument provider...")
        await self._instrument_provider.initialize()

        # Publish all instruments to the DataEngine
        for instrument in self._instrument_provider.list_all():
            self._handle_data(instrument)
            self._log.info(
                f"Published instrument {instrument.id}",
                LogColor.BLUE,
            )

        # Start WebSocket streaming if patterns are configured
        patterns = self._config.stream_patterns
        if patterns:
            self._log.info(
                f"Starting WebSocket stream with patterns: {patterns}"
            )
            self._stream_task = self._loop.create_task(
                self._stream_conn.run(patterns),
                name="marketstore_ws_stream",
            )

    async def _disconnect(self) -> None:
        if self._stream_task is not None:
            await self._stream_conn.stop()
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        self._log.info("MarketStore data client disconnected")

    # -- WEBSOCKET MESSAGE HANDLING -----------------------------------------------

    def _on_ws_message(self, key: str, data: dict[str, Any]) -> None:
        """
        Handle an incoming WebSocket stream message from MarketStore.

        Dispatches to the appropriate converter based on the attribute group
        in the TBK key and what subscriptions are active.

        Parameters
        ----------
        key : str
            The TimeBucketKey (e.g., "BTCUSDT/1Min/OHLCV").
        data : dict
            The column data (scalar values for one row).

        """
        ts_init = self._clock.timestamp_ns()

        # Try bars first (OHLCV attribute group)
        if key in self._subscribed_bars:
            instrument_id, bar_type = self._subscribed_bars[key]
            bar = ws_payload_to_bar(
                data=data,
                bar_type=bar_type,
                price_precision=self._price_precision,
                size_precision=self._size_precision,
                ts_init=ts_init,
            )
            self._handle_data(bar)
            return

        # Try trade ticks
        if key in self._subscribed_trades:
            instrument_id = self._subscribed_trades[key]
            tick = ws_payload_to_trade_tick(
                data=data,
                instrument_id=instrument_id,
                price_precision=self._price_precision,
                size_precision=self._size_precision,
                ts_init=ts_init,
            )
            self._handle_data(tick)
            return

        # Try quote ticks
        if key in self._subscribed_quotes:
            instrument_id = self._subscribed_quotes[key]
            tick = ws_payload_to_quote_tick(
                data=data,
                instrument_id=instrument_id,
                price_precision=self._price_precision,
                size_precision=self._size_precision,
                ts_init=ts_init,
            )
            self._handle_data(tick)
            return

        # Unrecognized key -- log at debug level (could be from a broad pattern)
        self._log.debug(f"Received unsubscribed stream key: {key}")

    # -- SUBSCRIBE ----------------------------------------------------------------

    async def _subscribe(self, command: SubscribeData) -> None:
        self._log.warning(
            f"Generic subscribe not implemented for MarketStore: {command.data_type}"
        )

    async def _subscribe_instruments(self, command: SubscribeInstruments) -> None:
        pass  # All instruments are published on connect

    async def _subscribe_instrument(self, command: SubscribeInstrument) -> None:
        instrument = self._instrument_provider.find(command.instrument_id)
        if instrument:
            self._handle_data(instrument)

    async def _subscribe_bars(self, command: SubscribeBars) -> None:
        bar_type = command.bar_type
        instrument_id = bar_type.instrument_id
        symbol = instrument_id.symbol.value

        # Derive the MarketStore TBK from the bar type
        step = bar_type.spec.step
        aggregation = bar_type.spec.aggregation
        timeframe = self._aggregation_to_timeframe(step, aggregation)
        tbk = f"{symbol}/{timeframe}/OHLCV"

        self._subscribed_bars[tbk] = (instrument_id, bar_type)
        self._log.info(f"Subscribed bars: {tbk} -> {bar_type}")

        # If stream is not started with static patterns, dynamically subscribe
        await self._ensure_ws_stream(tbk)

    async def _subscribe_trade_ticks(self, command: SubscribeTradeTicks) -> None:
        instrument_id = command.instrument_id
        symbol = instrument_id.symbol.value
        tbk = f"{symbol}/1Sec/TICK"

        self._subscribed_trades[tbk] = instrument_id
        self._log.info(f"Subscribed trade ticks: {tbk}")
        await self._ensure_ws_stream(tbk)

    async def _subscribe_quote_ticks(self, command: SubscribeQuoteTicks) -> None:
        instrument_id = command.instrument_id
        symbol = instrument_id.symbol.value
        tbk = f"{symbol}/1Sec/QUOTE"

        self._subscribed_quotes[tbk] = instrument_id
        self._log.info(f"Subscribed quote ticks: {tbk}")
        await self._ensure_ws_stream(tbk)

    # -- UNSUBSCRIBE --------------------------------------------------------------

    async def _unsubscribe(self, command: UnsubscribeData) -> None:
        pass

    async def _unsubscribe_instruments(self, command: UnsubscribeInstruments) -> None:
        pass

    async def _unsubscribe_instrument(self, command: UnsubscribeInstrument) -> None:
        pass

    async def _unsubscribe_bars(self, command: UnsubscribeBars) -> None:
        bar_type = command.bar_type
        instrument_id = bar_type.instrument_id
        symbol = instrument_id.symbol.value
        step = bar_type.spec.step
        aggregation = bar_type.spec.aggregation
        timeframe = self._aggregation_to_timeframe(step, aggregation)
        tbk = f"{symbol}/{timeframe}/OHLCV"
        self._subscribed_bars.pop(tbk, None)
        self._log.info(f"Unsubscribed bars: {tbk}")

    async def _unsubscribe_trade_ticks(self, command: UnsubscribeTradeTicks) -> None:
        instrument_id = command.instrument_id
        symbol = instrument_id.symbol.value
        tbk = f"{symbol}/1Sec/TICK"
        self._subscribed_trades.pop(tbk, None)

    async def _unsubscribe_quote_ticks(self, command: UnsubscribeQuoteTicks) -> None:
        instrument_id = command.instrument_id
        symbol = instrument_id.symbol.value
        tbk = f"{symbol}/1Sec/QUOTE"
        self._subscribed_quotes.pop(tbk, None)

    # -- REQUESTS (historical data via pymarketstore) ------------------------------

    async def _request(self, request: RequestData) -> None:
        self._log.warning(
            f"Generic request not implemented for MarketStore: {request.data_type}"
        )

    async def _request_instrument(self, request: RequestInstrument) -> None:
        instrument = self._instrument_provider.find(request.instrument_id)
        if instrument:
            self._handle_data(instrument)

    async def _request_instruments(self, request: RequestInstruments) -> None:
        for instrument in self._instrument_provider.list_all():
            self._handle_data(instrument)

    async def _request_bars(self, request: RequestBars) -> None:
        bar_type = request.bar_type
        instrument_id = bar_type.instrument_id
        symbol = instrument_id.symbol.value
        step = bar_type.spec.step
        aggregation = bar_type.spec.aggregation
        timeframe = self._aggregation_to_timeframe(step, aggregation)

        params = pymkts.Params(
            symbols=symbol,
            timeframe=timeframe,
            attrgroup="OHLCV",
            start=request.start.isoformat() if request.start else None,
            end=request.end.isoformat() if request.end else None,
            limit=request.limit if request.limit else None,
        )

        # Run the synchronous pymarketstore query in a thread executor
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, self._mkts_client.query, params)

        dataset = reply.first()
        if dataset is None:
            self._log.warning(f"No data returned for bars request: {bar_type}")
            self._handle_bars(
                bar_type=bar_type,
                bars=[],
                correlation_id=request.id,
                start=request.start,
                end=request.end,
                params=request.params,
            )
            return

        df = dataset.df()
        bars = df_to_bars(df, bar_type, self._price_precision, self._size_precision)
        self._log.info(f"Received {len(bars)} bars for {bar_type}")

        self._handle_bars(
            bar_type=bar_type,
            bars=bars,
            correlation_id=request.id,
            start=request.start,
            end=request.end,
            params=request.params,
        )

    async def _request_trade_ticks(self, request: RequestTradeTicks) -> None:
        instrument_id = request.instrument_id
        symbol = instrument_id.symbol.value

        params = pymkts.Params(
            symbols=symbol,
            timeframe="1Sec",
            attrgroup="TICK",
            start=request.start.isoformat() if request.start else None,
            end=request.end.isoformat() if request.end else None,
            limit=request.limit if request.limit else None,
        )

        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, self._mkts_client.query, params)

        dataset = reply.first()
        if dataset is None:
            self._log.warning(f"No data returned for trade ticks: {instrument_id}")
            self._handle_trade_ticks(
                instrument_id=instrument_id,
                ticks=[],
                correlation_id=request.id,
                start=request.start,
                end=request.end,
                params=request.params,
            )
            return

        df = dataset.df()
        ticks = df_to_trade_ticks(
            df, instrument_id, self._price_precision, self._size_precision
        )
        self._log.info(f"Received {len(ticks)} trade ticks for {instrument_id}")

        self._handle_trade_ticks(
            instrument_id=instrument_id,
            ticks=ticks,
            correlation_id=request.id,
            start=request.start,
            end=request.end,
            params=request.params,
        )

    async def _request_quote_ticks(self, request: RequestQuoteTicks) -> None:
        instrument_id = request.instrument_id
        symbol = instrument_id.symbol.value

        params = pymkts.Params(
            symbols=symbol,
            timeframe="1Sec",
            attrgroup="QUOTE",
            start=request.start.isoformat() if request.start else None,
            end=request.end.isoformat() if request.end else None,
            limit=request.limit if request.limit else None,
        )

        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, self._mkts_client.query, params)

        dataset = reply.first()
        if dataset is None:
            self._log.warning(f"No data returned for quote ticks: {instrument_id}")
            self._handle_quote_ticks(
                instrument_id=instrument_id,
                ticks=[],
                correlation_id=request.id,
                start=request.start,
                end=request.end,
                params=request.params,
            )
            return

        df = dataset.df()
        ticks = df_to_quote_ticks(
            df, instrument_id, self._price_precision, self._size_precision
        )
        self._log.info(f"Received {len(ticks)} quote ticks for {instrument_id}")

        self._handle_quote_ticks(
            instrument_id=instrument_id,
            ticks=ticks,
            correlation_id=request.id,
            start=request.start,
            end=request.end,
            params=request.params,
        )

    # -- HELPERS ------------------------------------------------------------------

    async def _ensure_ws_stream(self, tbk: str) -> None:
        """
        Ensure the WebSocket stream is running. If using static patterns
        (configured via ``stream_patterns``), this is a no-op. If no stream
        is active, starts one with all currently subscribed TBK patterns.
        """
        if self._config.stream_patterns:
            # Static patterns already cover this
            return

        # Collect all active subscription patterns
        all_patterns = set()
        all_patterns.update(self._subscribed_bars.keys())
        all_patterns.update(self._subscribed_trades.keys())
        all_patterns.update(self._subscribed_quotes.keys())

        if not all_patterns:
            return

        # Restart the stream with updated patterns
        if self._stream_task is not None:
            await self._stream_conn.stop()
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass

        patterns = sorted(all_patterns)
        self._log.info(f"(Re)starting WebSocket stream with patterns: {patterns}")
        self._stream_task = self._loop.create_task(
            self._stream_conn.run(patterns),
            name="marketstore_ws_stream",
        )

    @staticmethod
    def _aggregation_to_timeframe(step: int, aggregation) -> str:
        """Convert Nautilus BarAggregation + step to MarketStore timeframe string."""
        from nautilus_trader.model.data import BarAggregation

        _AGG_MAP = {
            BarAggregation.SECOND: "Sec",
            BarAggregation.MINUTE: "Min",
            BarAggregation.HOUR: "H",
            BarAggregation.DAY: "D",
        }
        suffix = _AGG_MAP.get(aggregation)
        if suffix is None:
            raise ValueError(
                f"Unsupported BarAggregation for MarketStore: {aggregation}"
            )
        return f"{step}{suffix}"
