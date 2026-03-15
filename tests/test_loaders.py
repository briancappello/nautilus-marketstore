"""Tests for nautilus_marketstore.loaders module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from nautilus_trader.model.data import Bar, BarAggregation, QuoteTick, TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId

from nautilus_marketstore.loaders import MarketStoreBacktestLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INSTRUMENT_ID = InstrumentId.from_str("BTCUSDT.BINANCE")


def _make_ohlcv_df(n: int = 5, start: str = "2024-01-01") -> pd.DataFrame:
    """Create a sample OHLCV DataFrame as pymarketstore would return."""
    index = pd.date_range(start, periods=n, freq="min")
    return pd.DataFrame(
        {
            "Open": np.linspace(100, 100 + n, n),
            "High": np.linspace(101, 101 + n, n),
            "Low": np.linspace(99, 99 + n, n),
            "Close": np.linspace(100.5, 100.5 + n, n),
            "Volume": np.full(n, 1000.0),
        },
        index=index,
    )


def _make_tick_df(n: int = 5, start: str = "2024-01-01") -> pd.DataFrame:
    """Create a sample tick DataFrame."""
    index = pd.date_range(start, periods=n, freq="s")
    return pd.DataFrame(
        {
            "Price": np.linspace(100, 101, n),
            "Size": np.full(n, 1.0),
            "Side": np.ones(n, dtype=int),
            "TradeID": np.arange(1, n + 1),
        },
        index=index,
    )


def _make_quote_df(n: int = 5, start: str = "2024-01-01") -> pd.DataFrame:
    """Create a sample quote DataFrame."""
    index = pd.date_range(start, periods=n, freq="s")
    return pd.DataFrame(
        {
            "BidPrice": np.linspace(99.9, 100.0, n),
            "AskPrice": np.linspace(100.1, 100.2, n),
            "BidSize": np.full(n, 10.0),
            "AskSize": np.full(n, 15.0),
        },
        index=index,
    )


def _mock_query_reply(df: pd.DataFrame | None):
    """Create a mock QueryReply with a single DataSet."""
    reply = MagicMock()
    if df is None:
        reply.first.return_value = None
    else:
        dataset = MagicMock()
        dataset.df.return_value = df
        reply.first.return_value = dataset
    return reply


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMarketStoreBacktestLoaderConstruction:
    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_default_construction(self, mock_client_cls):
        loader = MarketStoreBacktestLoader()
        mock_client_cls.assert_called_once_with(
            endpoint="http://localhost:5993/rpc", grpc=False
        )

    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_custom_endpoint(self, mock_client_cls):
        loader = MarketStoreBacktestLoader(
            endpoint="http://custom:5993/rpc", use_grpc=True
        )
        mock_client_cls.assert_called_once_with(
            endpoint="http://custom:5993/rpc", grpc=True
        )


class TestLoadBars:
    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_returns_bars(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(_make_ohlcv_df(3))

        loader = MarketStoreBacktestLoader()
        bars = loader.load_bars(
            instrument_id=INSTRUMENT_ID,
            timeframe="1Min",
            price_precision=2,
            size_precision=2,
        )
        assert len(bars) == 3
        assert all(isinstance(b, Bar) for b in bars)

    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_returns_empty_on_no_data(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(None)

        loader = MarketStoreBacktestLoader()
        bars = loader.load_bars(
            instrument_id=INSTRUMENT_ID,
            timeframe="1Min",
            price_precision=2,
            size_precision=2,
        )
        assert bars == []

    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_passes_query_params(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(_make_ohlcv_df(1))

        loader = MarketStoreBacktestLoader()
        loader.load_bars(
            instrument_id=INSTRUMENT_ID,
            timeframe="5Min",
            price_precision=2,
            size_precision=2,
            start="2024-01-01",
            end="2024-06-01",
            limit=100,
        )

        mock_client.query.assert_called_once()
        params = mock_client.query.call_args[0][0]
        assert params.tbk == "BTCUSDT/5Min/OHLCV"
        assert params.limit == 100


class TestLoadTradeTicks:
    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_returns_trade_ticks(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(_make_tick_df(3))

        loader = MarketStoreBacktestLoader()
        ticks = loader.load_trade_ticks(
            instrument_id=INSTRUMENT_ID,
            price_precision=2,
            size_precision=2,
        )
        assert len(ticks) == 3
        assert all(isinstance(t, TradeTick) for t in ticks)

    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_returns_empty_on_no_data(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(None)

        loader = MarketStoreBacktestLoader()
        ticks = loader.load_trade_ticks(
            instrument_id=INSTRUMENT_ID,
            price_precision=2,
            size_precision=2,
        )
        assert ticks == []

    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_custom_timeframe_and_attrgroup(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(_make_tick_df(1))

        loader = MarketStoreBacktestLoader()
        loader.load_trade_ticks(
            instrument_id=INSTRUMENT_ID,
            price_precision=2,
            size_precision=2,
            timeframe="1Min",
            attrgroup="TRADES",
        )

        params = mock_client.query.call_args[0][0]
        assert params.tbk == "BTCUSDT/1Min/TRADES"


class TestLoadQuoteTicks:
    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_returns_quote_ticks(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(_make_quote_df(4))

        loader = MarketStoreBacktestLoader()
        ticks = loader.load_quote_ticks(
            instrument_id=INSTRUMENT_ID,
            price_precision=2,
            size_precision=2,
        )
        assert len(ticks) == 4
        assert all(isinstance(t, QuoteTick) for t in ticks)

    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_returns_empty_on_no_data(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(None)

        loader = MarketStoreBacktestLoader()
        ticks = loader.load_quote_ticks(
            instrument_id=INSTRUMENT_ID,
            price_precision=2,
            size_precision=2,
        )
        assert ticks == []


class TestBarGenerator:
    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_yields_chunks(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Two months of data, each query returns 5 bars
        mock_client.query.return_value = _mock_query_reply(_make_ohlcv_df(5))

        loader = MarketStoreBacktestLoader()
        gen = loader.bar_generator(
            instrument_id=INSTRUMENT_ID,
            timeframe="1Min",
            price_precision=2,
            size_precision=2,
            start="2024-01-01",
            end="2024-03-01",
            chunk_months=1,
        )

        chunks = list(gen)
        assert len(chunks) == 2  # Jan and Feb
        assert all(len(chunk) == 5 for chunk in chunks)
        assert all(isinstance(b, Bar) for chunk in chunks for b in chunk)

    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_skips_empty_chunks(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # First month has data, second returns None
        replies = [
            _mock_query_reply(_make_ohlcv_df(3)),
            _mock_query_reply(None),
        ]
        mock_client.query.side_effect = replies

        loader = MarketStoreBacktestLoader()
        gen = loader.bar_generator(
            instrument_id=INSTRUMENT_ID,
            timeframe="1Min",
            price_precision=2,
            size_precision=2,
            start="2024-01-01",
            end="2024-03-01",
            chunk_months=1,
        )

        chunks = list(gen)
        assert len(chunks) == 1
        assert len(chunks[0]) == 3


class TestTradeTickGenerator:
    @patch("nautilus_marketstore.loaders.pymkts.Client")
    def test_yields_chunks(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.return_value = _mock_query_reply(_make_tick_df(4))

        loader = MarketStoreBacktestLoader()
        gen = loader.trade_tick_generator(
            instrument_id=INSTRUMENT_ID,
            price_precision=2,
            size_precision=2,
            start="2024-01-01",
            end="2024-02-01",
            chunk_months=1,
        )

        chunks = list(gen)
        assert len(chunks) == 1
        assert len(chunks[0]) == 4
        assert all(isinstance(t, TradeTick) for t in chunks[0])
