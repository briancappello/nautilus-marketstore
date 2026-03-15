"""Tests for nautilus_marketstore.parsing module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nautilus_trader.model.data import (
    Bar,
    BarAggregation,
    BarSpecification,
    BarType,
    QuoteTick,
    TradeTick,
)
from nautilus_trader.model.enums import AggressorSide, AggregationSource, PriceType
from nautilus_trader.model.identifiers import InstrumentId, TradeId
from nautilus_trader.model.objects import Price, Quantity

from nautilus_marketstore.parsing import (
    _epoch_to_nanos,
    df_to_bars,
    df_to_quote_ticks,
    df_to_trade_ticks,
    make_bar_type,
    parse_timeframe,
    ws_payload_to_bar,
    ws_payload_to_quote_tick,
    ws_payload_to_trade_tick,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

INSTRUMENT_ID = InstrumentId.from_str("BTCUSDT.BINANCE")


# ---------------------------------------------------------------------------
# parse_timeframe
# ---------------------------------------------------------------------------


class TestParseTimeframe:
    @pytest.mark.parametrize(
        "timeframe, expected_step, expected_agg",
        [
            ("1Sec", 1, BarAggregation.SECOND),
            ("5Sec", 5, BarAggregation.SECOND),
            ("10Sec", 10, BarAggregation.SECOND),
            ("15Sec", 15, BarAggregation.SECOND),
            ("30Sec", 30, BarAggregation.SECOND),
            ("1Min", 1, BarAggregation.MINUTE),
            ("2Min", 2, BarAggregation.MINUTE),
            ("3Min", 3, BarAggregation.MINUTE),
            ("5Min", 5, BarAggregation.MINUTE),
            ("10Min", 10, BarAggregation.MINUTE),
            ("15Min", 15, BarAggregation.MINUTE),
            ("20Min", 20, BarAggregation.MINUTE),
            ("30Min", 30, BarAggregation.MINUTE),
            ("1H", 1, BarAggregation.HOUR),
            ("2H", 2, BarAggregation.HOUR),
            ("4H", 4, BarAggregation.HOUR),
            ("6H", 6, BarAggregation.HOUR),
            ("8H", 8, BarAggregation.HOUR),
            ("12H", 12, BarAggregation.HOUR),
            ("1D", 1, BarAggregation.DAY),
        ],
    )
    def test_all_supported_timeframes(self, timeframe, expected_step, expected_agg):
        step, agg = parse_timeframe(timeframe)
        assert step == expected_step
        assert agg == expected_agg

    def test_unsupported_timeframe_raises(self):
        with pytest.raises(ValueError, match="Unsupported MarketStore timeframe"):
            parse_timeframe("1W")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_timeframe("")

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            parse_timeframe("INVALID")


# ---------------------------------------------------------------------------
# make_bar_type
# ---------------------------------------------------------------------------


class TestMakeBarType:
    def test_default_price_type(self):
        bar_type = make_bar_type(INSTRUMENT_ID, "1Min")
        assert bar_type.instrument_id == INSTRUMENT_ID
        assert bar_type.spec.step == 1
        assert bar_type.spec.aggregation == BarAggregation.MINUTE
        assert bar_type.spec.price_type == PriceType.LAST
        assert bar_type.aggregation_source == AggregationSource.EXTERNAL

    def test_custom_price_type(self):
        bar_type = make_bar_type(INSTRUMENT_ID, "5Min", price_type=PriceType.MID)
        assert bar_type.spec.price_type == PriceType.MID

    def test_hourly_timeframe(self):
        bar_type = make_bar_type(INSTRUMENT_ID, "4H")
        assert bar_type.spec.step == 4
        assert bar_type.spec.aggregation == BarAggregation.HOUR

    def test_daily_timeframe(self):
        bar_type = make_bar_type(INSTRUMENT_ID, "1D")
        assert bar_type.spec.step == 1
        assert bar_type.spec.aggregation == BarAggregation.DAY

    def test_unsupported_timeframe_raises(self):
        with pytest.raises(ValueError):
            make_bar_type(INSTRUMENT_ID, "1W")


# ---------------------------------------------------------------------------
# _epoch_to_nanos
# ---------------------------------------------------------------------------


class TestEpochToNanos:
    def test_integer_epoch(self):
        result = _epoch_to_nanos(1640995200)
        assert result == 1640995200_000000000

    def test_epoch_with_nanoseconds(self):
        result = _epoch_to_nanos(1640995200, 500)
        assert result == 1640995200_000000500

    def test_float_epoch_truncates(self):
        result = _epoch_to_nanos(1640995200.9)
        assert result == 1640995200_000000000

    def test_zero_epoch(self):
        result = _epoch_to_nanos(0)
        assert result == 0

    def test_zero_with_nanoseconds(self):
        result = _epoch_to_nanos(0, 42)
        assert result == 42


# ---------------------------------------------------------------------------
# ws_payload_to_bar
# ---------------------------------------------------------------------------


class TestWsPayloadToBar:
    def test_basic_bar_conversion(self):
        data = {
            "Epoch": 1640995200,
            "Open": 46000.0,
            "High": 46500.0,
            "Low": 45800.0,
            "Close": 46200.0,
            "Volume": 1234.5,
        }
        bar_type = make_bar_type(INSTRUMENT_ID, "1Min")
        bar = ws_payload_to_bar(data, bar_type, 2, 4, 9999)

        assert isinstance(bar, Bar)
        assert bar.bar_type == bar_type
        assert bar.open == Price(46000.0, 2)
        assert bar.high == Price(46500.0, 2)
        assert bar.low == Price(45800.0, 2)
        assert bar.close == Price(46200.0, 2)
        assert bar.volume == Quantity(1234.5, 4)
        assert bar.ts_event == 1640995200_000000000
        assert bar.ts_init == 9999

    def test_bar_with_nanoseconds(self):
        data = {
            "Epoch": 1640995200,
            "Nanoseconds": 123456,
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.5,
            "Volume": 500.0,
        }
        bar_type = make_bar_type(INSTRUMENT_ID, "5Min")
        bar = ws_payload_to_bar(data, bar_type, 8, 8, 0)

        assert bar.ts_event == 1640995200_000123456


# ---------------------------------------------------------------------------
# ws_payload_to_trade_tick
# ---------------------------------------------------------------------------


class TestWsPayloadToTradeTick:
    def test_trade_with_buyer_side(self):
        data = {
            "Epoch": 1640995200,
            "Price": 46000.0,
            "Size": 0.5,
            "Side": 1,
            "TradeID": 12345,
        }
        tick = ws_payload_to_trade_tick(data, INSTRUMENT_ID, 2, 4, 9999)

        assert isinstance(tick, TradeTick)
        assert tick.instrument_id == INSTRUMENT_ID
        assert tick.price == Price(46000.0, 2)
        assert tick.size == Quantity(0.5, 4)
        assert tick.aggressor_side == AggressorSide.BUYER
        assert tick.trade_id == TradeId("12345")
        assert tick.ts_event == 1640995200_000000000
        assert tick.ts_init == 9999

    def test_trade_with_seller_side(self):
        data = {
            "Epoch": 1640995200,
            "Price": 100.0,
            "Size": 1.0,
            "Side": 2,
            "TradeID": 99,
        }
        tick = ws_payload_to_trade_tick(data, INSTRUMENT_ID, 2, 2, 0)
        assert tick.aggressor_side == AggressorSide.SELLER

    def test_trade_with_no_side(self):
        data = {
            "Epoch": 1640995200,
            "Price": 100.0,
            "Size": 1.0,
        }
        tick = ws_payload_to_trade_tick(data, INSTRUMENT_ID, 2, 2, 0)
        assert tick.aggressor_side == AggressorSide.NO_AGGRESSOR

    def test_trade_with_zero_side(self):
        data = {
            "Epoch": 1640995200,
            "Price": 100.0,
            "Size": 1.0,
            "Side": 0,
        }
        tick = ws_payload_to_trade_tick(data, INSTRUMENT_ID, 2, 2, 0)
        assert tick.aggressor_side == AggressorSide.NO_AGGRESSOR

    def test_trade_with_unknown_side_value(self):
        data = {
            "Epoch": 1640995200,
            "Price": 100.0,
            "Size": 1.0,
            "Side": 99,
        }
        tick = ws_payload_to_trade_tick(data, INSTRUMENT_ID, 2, 2, 0)
        assert tick.aggressor_side == AggressorSide.NO_AGGRESSOR

    def test_trade_id_fallback_to_epoch(self):
        data = {
            "Epoch": 1640995200,
            "Price": 100.0,
            "Size": 1.0,
        }
        tick = ws_payload_to_trade_tick(data, INSTRUMENT_ID, 2, 2, 0)
        assert tick.trade_id == TradeId("1640995200")

    def test_trade_with_nanoseconds(self):
        data = {
            "Epoch": 1640995200,
            "Nanoseconds": 500,
            "Price": 100.0,
            "Size": 1.0,
        }
        tick = ws_payload_to_trade_tick(data, INSTRUMENT_ID, 2, 2, 0)
        assert tick.ts_event == 1640995200_000000500


# ---------------------------------------------------------------------------
# ws_payload_to_quote_tick
# ---------------------------------------------------------------------------


class TestWsPayloadToQuoteTick:
    def test_basic_quote_conversion(self):
        data = {
            "Epoch": 1640995200,
            "BidPrice": 45999.0,
            "AskPrice": 46001.0,
            "BidSize": 10.5,
            "AskSize": 8.3,
        }
        tick = ws_payload_to_quote_tick(data, INSTRUMENT_ID, 2, 4, 9999)

        assert isinstance(tick, QuoteTick)
        assert tick.instrument_id == INSTRUMENT_ID
        assert tick.bid_price == Price(45999.0, 2)
        assert tick.ask_price == Price(46001.0, 2)
        assert tick.bid_size == Quantity(10.5, 4)
        assert tick.ask_size == Quantity(8.3, 4)
        assert tick.ts_event == 1640995200_000000000
        assert tick.ts_init == 9999

    def test_quote_with_nanoseconds(self):
        data = {
            "Epoch": 1640995200,
            "Nanoseconds": 42,
            "BidPrice": 100.0,
            "AskPrice": 100.1,
            "BidSize": 5.0,
            "AskSize": 5.0,
        }
        tick = ws_payload_to_quote_tick(data, INSTRUMENT_ID, 2, 2, 0)
        assert tick.ts_event == 1640995200_000000042


# ---------------------------------------------------------------------------
# df_to_bars
# ---------------------------------------------------------------------------


class TestDfToBars:
    def _make_bar_df(self, n: int = 3) -> pd.DataFrame:
        index = pd.date_range("2024-01-01", periods=n, freq="min")
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

    def test_correct_number_of_bars(self):
        df = self._make_bar_df(5)
        bar_type = make_bar_type(INSTRUMENT_ID, "1Min")
        bars = df_to_bars(df, bar_type, 2, 2)
        assert len(bars) == 5

    def test_bar_type_assigned(self):
        df = self._make_bar_df(1)
        bar_type = make_bar_type(INSTRUMENT_ID, "1Min")
        bars = df_to_bars(df, bar_type, 2, 2)
        assert bars[0].bar_type == bar_type

    def test_ohlcv_values(self):
        index = pd.to_datetime(["2024-01-01 00:00:00"])
        df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [105.0],
                "Low": [95.0],
                "Close": [102.0],
                "Volume": [5000.0],
            },
            index=index,
        )
        bar_type = make_bar_type(INSTRUMENT_ID, "1Min")
        bars = df_to_bars(df, bar_type, 2, 2)

        bar = bars[0]
        assert bar.open == Price(100.0, 2)
        assert bar.high == Price(105.0, 2)
        assert bar.low == Price(95.0, 2)
        assert bar.close == Price(102.0, 2)
        assert bar.volume == Quantity(5000.0, 2)

    def test_timestamps(self):
        ts = pd.Timestamp("2024-01-01 12:00:00")
        df = pd.DataFrame(
            {
                "Open": [1.0],
                "High": [2.0],
                "Low": [0.5],
                "Close": [1.5],
                "Volume": [100.0],
            },
            index=[ts],
        )
        bar_type = make_bar_type(INSTRUMENT_ID, "1Min")
        bars = df_to_bars(df, bar_type, 2, 2)
        assert bars[0].ts_event == ts.value  # nanoseconds
        assert bars[0].ts_init == ts.value

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        bar_type = make_bar_type(INSTRUMENT_ID, "1Min")
        bars = df_to_bars(df, bar_type, 2, 2)
        assert bars == []

    def test_precision_applied(self):
        index = pd.to_datetime(["2024-01-01"])
        df = pd.DataFrame(
            {
                "Open": [100.123456],
                "High": [101.123456],
                "Low": [99.123456],
                "Close": [100.623456],
                "Volume": [999.987654],
            },
            index=index,
        )
        bar_type = make_bar_type(INSTRUMENT_ID, "1Min")
        bars = df_to_bars(df, bar_type, 4, 3)
        bar = bars[0]
        assert bar.open == Price(100.123456, 4)
        assert bar.volume == Quantity(999.987654, 3)


# ---------------------------------------------------------------------------
# df_to_trade_ticks
# ---------------------------------------------------------------------------


class TestDfToTradeTicks:
    def test_basic_conversion(self):
        index = pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 00:00:01"])
        df = pd.DataFrame(
            {
                "Price": [100.0, 101.0],
                "Size": [1.0, 2.0],
                "Side": [1, 2],
                "TradeID": [1001, 1002],
            },
            index=index,
        )
        ticks = df_to_trade_ticks(df, INSTRUMENT_ID, 2, 2)
        assert len(ticks) == 2

        assert ticks[0].price == Price(100.0, 2)
        assert ticks[0].size == Quantity(1.0, 2)
        assert ticks[0].aggressor_side == AggressorSide.BUYER
        assert ticks[0].trade_id == TradeId("1001")

        assert ticks[1].aggressor_side == AggressorSide.SELLER
        assert ticks[1].trade_id == TradeId("1002")

    def test_without_side_column(self):
        index = pd.to_datetime(["2024-01-01"])
        df = pd.DataFrame({"Price": [100.0], "Size": [1.0]}, index=index)
        ticks = df_to_trade_ticks(df, INSTRUMENT_ID, 2, 2)
        assert ticks[0].aggressor_side == AggressorSide.NO_AGGRESSOR

    def test_without_trade_id_column(self):
        index = pd.to_datetime(["2024-01-01"])
        df = pd.DataFrame({"Price": [100.0], "Size": [1.0]}, index=index)
        ticks = df_to_trade_ticks(df, INSTRUMENT_ID, 2, 2)
        # Should fall back to string of ts_nanos
        ts_nanos = int(pd.Timestamp("2024-01-01").value)
        assert ticks[0].trade_id == TradeId(str(ts_nanos))

    def test_side_zero_is_no_aggressor(self):
        index = pd.to_datetime(["2024-01-01"])
        df = pd.DataFrame({"Price": [100.0], "Size": [1.0], "Side": [0]}, index=index)
        ticks = df_to_trade_ticks(df, INSTRUMENT_ID, 2, 2)
        assert ticks[0].aggressor_side == AggressorSide.NO_AGGRESSOR

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["Price", "Size"])
        ticks = df_to_trade_ticks(df, INSTRUMENT_ID, 2, 2)
        assert ticks == []


# ---------------------------------------------------------------------------
# df_to_quote_ticks
# ---------------------------------------------------------------------------


class TestDfToQuoteTicks:
    def test_basic_conversion(self):
        index = pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 00:00:01"])
        df = pd.DataFrame(
            {
                "BidPrice": [99.9, 100.0],
                "AskPrice": [100.1, 100.2],
                "BidSize": [10.0, 20.0],
                "AskSize": [15.0, 25.0],
            },
            index=index,
        )
        ticks = df_to_quote_ticks(df, INSTRUMENT_ID, 2, 2)
        assert len(ticks) == 2

        assert ticks[0].bid_price == Price(99.9, 2)
        assert ticks[0].ask_price == Price(100.1, 2)
        assert ticks[0].bid_size == Quantity(10.0, 2)
        assert ticks[0].ask_size == Quantity(15.0, 2)

    def test_timestamps(self):
        ts = pd.Timestamp("2024-06-15 10:30:00")
        df = pd.DataFrame(
            {
                "BidPrice": [50.0],
                "AskPrice": [50.1],
                "BidSize": [100.0],
                "AskSize": [200.0],
            },
            index=[ts],
        )
        ticks = df_to_quote_ticks(df, INSTRUMENT_ID, 2, 2)
        assert ticks[0].ts_event == ts.value
        assert ticks[0].ts_init == ts.value

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["BidPrice", "AskPrice", "BidSize", "AskSize"])
        ticks = df_to_quote_ticks(df, INSTRUMENT_ID, 2, 2)
        assert ticks == []
