"""
Shared conversion functions: MarketStore data -> Nautilus types.

Used by both the live adapter (WebSocket streaming) and the backtest loader
(pymarketstore query results). All timestamp handling assumes MarketStore
stores epochs as int64 seconds with an optional int32 Nanoseconds column.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarAggregation
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MarketStore timeframe string -> Nautilus BarAggregation mapping
# ---------------------------------------------------------------------------

_TIMEFRAME_MAP: dict[str, tuple[int, BarAggregation]] = {
    "1Sec": (1, BarAggregation.SECOND),
    "5Sec": (5, BarAggregation.SECOND),
    "10Sec": (10, BarAggregation.SECOND),
    "15Sec": (15, BarAggregation.SECOND),
    "30Sec": (30, BarAggregation.SECOND),
    "1Min": (1, BarAggregation.MINUTE),
    "2Min": (2, BarAggregation.MINUTE),
    "3Min": (3, BarAggregation.MINUTE),
    "5Min": (5, BarAggregation.MINUTE),
    "10Min": (10, BarAggregation.MINUTE),
    "15Min": (15, BarAggregation.MINUTE),
    "20Min": (20, BarAggregation.MINUTE),
    "30Min": (30, BarAggregation.MINUTE),
    "1H": (1, BarAggregation.HOUR),
    "2H": (2, BarAggregation.HOUR),
    "4H": (4, BarAggregation.HOUR),
    "6H": (6, BarAggregation.HOUR),
    "8H": (8, BarAggregation.HOUR),
    "12H": (12, BarAggregation.HOUR),
    "1D": (1, BarAggregation.DAY),
}


def parse_timeframe(timeframe: str) -> tuple[int, BarAggregation]:
    """
    Parse a MarketStore timeframe string into (step, BarAggregation).

    Parameters
    ----------
    timeframe : str
        MarketStore timeframe (e.g., "1Min", "5Min", "1H", "1D").

    Returns
    -------
    tuple[int, BarAggregation]

    Raises
    ------
    ValueError
        If the timeframe string is not recognized.

    """
    result = _TIMEFRAME_MAP.get(timeframe)
    if result is None:
        raise ValueError(
            f"Unsupported MarketStore timeframe '{timeframe}'. "
            f"Supported: {sorted(_TIMEFRAME_MAP.keys())}"
        )
    return result


def make_bar_type(
    instrument_id: InstrumentId,
    timeframe: str,
    price_type: PriceType = PriceType.LAST,
) -> BarType:
    """
    Construct a Nautilus ``BarType`` from a MarketStore timeframe string.

    Parameters
    ----------
    instrument_id : InstrumentId
        The instrument identifier.
    timeframe : str
        MarketStore timeframe (e.g., "1Min").
    price_type : PriceType, default ``LAST``
        The price type for the bar specification.

    Returns
    -------
    BarType

    """
    step, aggregation = parse_timeframe(timeframe)
    bar_spec = BarSpecification(step, aggregation, price_type)
    return BarType(instrument_id, bar_spec, AggregationSource.EXTERNAL)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _epoch_to_nanos(epoch_sec: int | float, nanoseconds: int = 0) -> int:
    """Convert epoch seconds + optional nanoseconds remainder to uint64 nanos."""
    return int(epoch_sec) * 1_000_000_000 + int(nanoseconds)


# ---------------------------------------------------------------------------
# Single-row conversions (used by live WebSocket streaming)
# ---------------------------------------------------------------------------

def ws_payload_to_bar(
    data: dict[str, Any],
    bar_type: BarType,
    price_precision: int,
    size_precision: int,
    ts_init: int,
) -> Bar:
    """
    Convert a MarketStore WebSocket stream payload ``data`` dict to a Nautilus Bar.

    The ``data`` dict has scalar column values, e.g.::

        {"Epoch": 1640995200, "Open": 100.0, "High": 101.0, ...}

    Parameters
    ----------
    data : dict
        The ``data`` field from the WebSocket ``Payload`` message.
    bar_type : BarType
        The bar type to assign.
    price_precision : int
        Decimal precision for prices.
    size_precision : int
        Decimal precision for volume.
    ts_init : int
        The initialization timestamp in nanoseconds.

    Returns
    -------
    Bar

    """
    ts_event = _epoch_to_nanos(data["Epoch"], data.get("Nanoseconds", 0))
    return Bar(
        bar_type=bar_type,
        open=Price(float(data["Open"]), price_precision),
        high=Price(float(data["High"]), price_precision),
        low=Price(float(data["Low"]), price_precision),
        close=Price(float(data["Close"]), price_precision),
        volume=Quantity(float(data["Volume"]), size_precision),
        ts_event=ts_event,
        ts_init=ts_init,
    )


def ws_payload_to_trade_tick(
    data: dict[str, Any],
    instrument_id: InstrumentId,
    price_precision: int,
    size_precision: int,
    ts_init: int,
) -> TradeTick:
    """
    Convert a MarketStore WebSocket stream payload to a Nautilus TradeTick.

    Expected columns: Epoch, Price, Size, and optionally Side and TradeID.

    Parameters
    ----------
    data : dict
        The ``data`` field from the WebSocket ``Payload`` message.
    instrument_id : InstrumentId
        The instrument identifier.
    price_precision : int
        Decimal precision for the price.
    size_precision : int
        Decimal precision for the size.
    ts_init : int
        The initialization timestamp in nanoseconds.

    Returns
    -------
    TradeTick

    """
    ts_event = _epoch_to_nanos(data["Epoch"], data.get("Nanoseconds", 0))

    # Determine aggressor side from the "Side" column if present
    raw_side = data.get("Side")
    if raw_side is None or raw_side == 0:
        aggressor_side = AggressorSide.NO_AGGRESSOR
    elif raw_side == 1:
        aggressor_side = AggressorSide.BUYER
    elif raw_side == 2:
        aggressor_side = AggressorSide.SELLER
    else:
        aggressor_side = AggressorSide.NO_AGGRESSOR

    trade_id_str = str(data.get("TradeID", data.get("Epoch", 0)))

    return TradeTick(
        instrument_id=instrument_id,
        price=Price(float(data["Price"]), price_precision),
        size=Quantity(float(data["Size"]), size_precision),
        aggressor_side=aggressor_side,
        trade_id=TradeId(trade_id_str),
        ts_event=ts_event,
        ts_init=ts_init,
    )


def ws_payload_to_quote_tick(
    data: dict[str, Any],
    instrument_id: InstrumentId,
    price_precision: int,
    size_precision: int,
    ts_init: int,
) -> QuoteTick:
    """
    Convert a MarketStore WebSocket stream payload to a Nautilus QuoteTick.

    Expected columns: Epoch, BidPrice, AskPrice, BidSize, AskSize.

    Parameters
    ----------
    data : dict
        The ``data`` field from the WebSocket ``Payload`` message.
    instrument_id : InstrumentId
        The instrument identifier.
    price_precision : int
        Decimal precision for prices.
    size_precision : int
        Decimal precision for sizes.
    ts_init : int
        The initialization timestamp in nanoseconds.

    Returns
    -------
    QuoteTick

    """
    ts_event = _epoch_to_nanos(data["Epoch"], data.get("Nanoseconds", 0))
    return QuoteTick(
        instrument_id=instrument_id,
        bid_price=Price(float(data["BidPrice"]), price_precision),
        ask_price=Price(float(data["AskPrice"]), price_precision),
        bid_size=Quantity(float(data["BidSize"]), size_precision),
        ask_size=Quantity(float(data["AskSize"]), size_precision),
        ts_event=ts_event,
        ts_init=ts_init,
    )


# ---------------------------------------------------------------------------
# DataFrame conversions (used by backtest loader and request_* methods)
# ---------------------------------------------------------------------------

def df_to_bars(
    df: pd.DataFrame,
    bar_type: BarType,
    price_precision: int,
    size_precision: int,
) -> list[Bar]:
    """
    Convert a pandas DataFrame (from pymarketstore query) to a list of Nautilus Bars.

    The DataFrame is expected to have a ``DatetimeIndex`` (from ``DataSet.df()``)
    and columns: Open, High, Low, Close, Volume.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame from ``pymarketstore`` query result.
    bar_type : BarType
        The bar type to assign to all bars.
    price_precision : int
        Decimal precision for prices.
    size_precision : int
        Decimal precision for volume.

    Returns
    -------
    list[Bar]

    """
    bars = []
    for ts, row in df.iterrows():
        ts_nanos = int(pd.Timestamp(ts).value)  # pandas Timestamp.value is nanoseconds
        bars.append(
            Bar(
                bar_type=bar_type,
                open=Price(float(row["Open"]), price_precision),
                high=Price(float(row["High"]), price_precision),
                low=Price(float(row["Low"]), price_precision),
                close=Price(float(row["Close"]), price_precision),
                volume=Quantity(float(row["Volume"]), size_precision),
                ts_event=ts_nanos,
                ts_init=ts_nanos,
            )
        )
    return bars


def df_to_trade_ticks(
    df: pd.DataFrame,
    instrument_id: InstrumentId,
    price_precision: int,
    size_precision: int,
) -> list[TradeTick]:
    """
    Convert a pandas DataFrame to a list of Nautilus TradeTicks.

    Expected columns: Price, Size. Optional: Side, TradeID.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame from ``pymarketstore`` query result.
    instrument_id : InstrumentId
        The instrument identifier.
    price_precision : int
        Decimal precision for prices.
    size_precision : int
        Decimal precision for sizes.

    Returns
    -------
    list[TradeTick]

    """
    ticks = []
    has_side = "Side" in df.columns
    has_trade_id = "TradeID" in df.columns

    for ts, row in df.iterrows():
        ts_nanos = int(pd.Timestamp(ts).value)

        if has_side:
            raw_side = int(row["Side"])
            if raw_side == 1:
                aggressor_side = AggressorSide.BUYER
            elif raw_side == 2:
                aggressor_side = AggressorSide.SELLER
            else:
                aggressor_side = AggressorSide.NO_AGGRESSOR
        else:
            aggressor_side = AggressorSide.NO_AGGRESSOR

        trade_id_val = str(int(row["TradeID"])) if has_trade_id else str(ts_nanos)

        ticks.append(
            TradeTick(
                instrument_id=instrument_id,
                price=Price(float(row["Price"]), price_precision),
                size=Quantity(float(row["Size"]), size_precision),
                aggressor_side=aggressor_side,
                trade_id=TradeId(trade_id_val),
                ts_event=ts_nanos,
                ts_init=ts_nanos,
            )
        )
    return ticks


def df_to_quote_ticks(
    df: pd.DataFrame,
    instrument_id: InstrumentId,
    price_precision: int,
    size_precision: int,
) -> list[QuoteTick]:
    """
    Convert a pandas DataFrame to a list of Nautilus QuoteTicks.

    Expected columns: BidPrice, AskPrice, BidSize, AskSize.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame from ``pymarketstore`` query result.
    instrument_id : InstrumentId
        The instrument identifier.
    price_precision : int
        Decimal precision for prices.
    size_precision : int
        Decimal precision for sizes.

    Returns
    -------
    list[QuoteTick]

    """
    ticks = []
    for ts, row in df.iterrows():
        ts_nanos = int(pd.Timestamp(ts).value)
        ticks.append(
            QuoteTick(
                instrument_id=instrument_id,
                bid_price=Price(float(row["BidPrice"]), price_precision),
                ask_price=Price(float(row["AskPrice"]), price_precision),
                bid_size=Quantity(float(row["BidSize"]), size_precision),
                ask_size=Quantity(float(row["AskSize"]), size_precision),
                ts_event=ts_nanos,
                ts_init=ts_nanos,
            )
        )
    return ticks
