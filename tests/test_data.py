"""Tests for nautilus_marketstore.data module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.model.data import (
    Bar,
    BarAggregation,
    BarSpecification,
    BarType,
    QuoteTick,
    TradeTick,
)
from nautilus_trader.model.enums import AggregationSource, PriceType
from nautilus_trader.model.identifiers import ClientId, InstrumentId, TraderId, Venue
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from nautilus_marketstore.config import MarketStoreDataClientConfig
from nautilus_marketstore.data import MarketStoreDataClient
from nautilus_marketstore.providers import MarketStoreInstrumentProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def clock():
    return LiveClock()


@pytest.fixture
def msgbus(clock):
    return MessageBus(trader_id=TraderId("TESTER-001"), clock=clock)


@pytest.fixture
def cache():
    return Cache(database=None)


@pytest.fixture
def instrument_provider():
    return MarketStoreInstrumentProvider()


@pytest.fixture
def config():
    return MarketStoreDataClientConfig(
        venue="BINANCE",
        price_precision=2,
        size_precision=4,
    )


@pytest.fixture
def client(event_loop, msgbus, cache, clock, instrument_provider, config):
    return MarketStoreDataClient(
        loop=event_loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        instrument_provider=instrument_provider,
        config=config,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestMarketStoreDataClientConstruction:
    def test_default_client_id(
        self, event_loop, msgbus, cache, clock, instrument_provider
    ):
        config = MarketStoreDataClientConfig()
        client = MarketStoreDataClient(
            loop=event_loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
            config=config,
        )
        assert client.id == ClientId("MARKETSTORE")

    def test_custom_client_name(
        self, event_loop, msgbus, cache, clock, instrument_provider
    ):
        config = MarketStoreDataClientConfig()
        client = MarketStoreDataClient(
            loop=event_loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
            config=config,
            name="CUSTOM",
        )
        assert client.id == ClientId("CUSTOM")

    def test_venue_from_config(self, client):
        assert client.venue == Venue("BINANCE")

    def test_subscriptions_initially_empty(self, client):
        assert client._subscribed_bars == {}
        assert client._subscribed_trades == {}
        assert client._subscribed_quotes == {}

    def test_stream_task_initially_none(self, client):
        assert client._stream_task is None


# ---------------------------------------------------------------------------
# _aggregation_to_timeframe
# ---------------------------------------------------------------------------


class TestAggregationToTimeframe:
    @pytest.mark.parametrize(
        "step, aggregation, expected",
        [
            (1, BarAggregation.SECOND, "1Sec"),
            (5, BarAggregation.SECOND, "5Sec"),
            (1, BarAggregation.MINUTE, "1Min"),
            (5, BarAggregation.MINUTE, "5Min"),
            (15, BarAggregation.MINUTE, "15Min"),
            (1, BarAggregation.HOUR, "1H"),
            (4, BarAggregation.HOUR, "4H"),
            (1, BarAggregation.DAY, "1D"),
        ],
    )
    def test_valid_conversions(self, step, aggregation, expected):
        result = MarketStoreDataClient._aggregation_to_timeframe(step, aggregation)
        assert result == expected

    def test_unsupported_aggregation_raises(self):
        with pytest.raises(ValueError, match="Unsupported BarAggregation"):
            MarketStoreDataClient._aggregation_to_timeframe(1, BarAggregation.TICK)


# ---------------------------------------------------------------------------
# WebSocket message handling
# ---------------------------------------------------------------------------


class TestOnWsMessage:
    def test_dispatches_bar(self, client):
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        bar_type = BarType(
            instrument_id,
            BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            AggregationSource.EXTERNAL,
        )
        tbk = "BTCUSDT/1Min/OHLCV"
        client._subscribed_bars[tbk] = (instrument_id, bar_type)

        data = {
            "Epoch": 1640995200,
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.5,
            "Volume": 500.0,
        }

        with patch.object(client, "_handle_data") as mock_handle:
            client._on_ws_message(tbk, data)
            mock_handle.assert_called_once()
            bar = mock_handle.call_args[0][0]
            assert isinstance(bar, Bar)
            assert bar.bar_type == bar_type

    def test_dispatches_trade_tick(self, client):
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        tbk = "BTCUSDT/1Sec/TICK"
        client._subscribed_trades[tbk] = instrument_id

        data = {
            "Epoch": 1640995200,
            "Price": 46000.0,
            "Size": 0.5,
            "Side": 1,
            "TradeID": 999,
        }

        with patch.object(client, "_handle_data") as mock_handle:
            client._on_ws_message(tbk, data)
            mock_handle.assert_called_once()
            tick = mock_handle.call_args[0][0]
            assert isinstance(tick, TradeTick)
            assert tick.instrument_id == instrument_id

    def test_dispatches_quote_tick(self, client):
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        tbk = "BTCUSDT/1Sec/QUOTE"
        client._subscribed_quotes[tbk] = instrument_id

        data = {
            "Epoch": 1640995200,
            "BidPrice": 45999.0,
            "AskPrice": 46001.0,
            "BidSize": 10.0,
            "AskSize": 8.0,
        }

        with patch.object(client, "_handle_data") as mock_handle:
            client._on_ws_message(tbk, data)
            mock_handle.assert_called_once()
            tick = mock_handle.call_args[0][0]
            assert isinstance(tick, QuoteTick)

    def test_unsubscribed_key_no_dispatch(self, client):
        with patch.object(client, "_handle_data") as mock_handle:
            client._on_ws_message("UNKNOWN/1Min/OHLCV", {"Epoch": 0})
            mock_handle.assert_not_called()

    def test_bar_dispatch_priority_over_trade(self, client):
        """If a key is in both _subscribed_bars and _subscribed_trades, bars take priority."""
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        bar_type = BarType(
            instrument_id,
            BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            AggregationSource.EXTERNAL,
        )
        tbk = "BTCUSDT/1Min/OHLCV"
        client._subscribed_bars[tbk] = (instrument_id, bar_type)
        client._subscribed_trades[tbk] = instrument_id

        data = {
            "Epoch": 1640995200,
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.5,
            "Volume": 500.0,
        }

        with patch.object(client, "_handle_data") as mock_handle:
            client._on_ws_message(tbk, data)
            mock_handle.assert_called_once()
            assert isinstance(mock_handle.call_args[0][0], Bar)
