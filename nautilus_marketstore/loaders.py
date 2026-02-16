"""
Backtest data loading utilities.

Provides functions to query MarketStore and return Nautilus data objects
suitable for ``BacktestEngine.add_data()`` or ``add_data_iterator()``.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime

import pymarketstore as pymkts

from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.identifiers import InstrumentId

from nautilus_marketstore.parsing import (
    df_to_bars,
    df_to_quote_ticks,
    df_to_trade_ticks,
    make_bar_type,
)


logger = logging.getLogger(__name__)


class MarketStoreBacktestLoader:
    """
    Loads historical data from MarketStore for use in NautilusTrader backtests.

    Parameters
    ----------
    endpoint : str
        The MarketStore RPC endpoint (e.g., ``"http://localhost:5993/rpc"``).
    use_grpc : bool, default False
        If True, use gRPC transport instead of msgpack-rpc.

    Examples
    --------
    One-shot loading::

        loader = MarketStoreBacktestLoader("http://localhost:5993/rpc")
        bars = loader.load_bars(
            instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
            timeframe="1Min",
            start="2024-01-01",
            end="2024-06-01",
            price_precision=2,
            size_precision=6,
        )
        engine.add_data(bars)

    Streaming (memory-efficient)::

        gen = loader.bar_generator(
            instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
            timeframe="1Min",
            start="2024-01-01",
            end="2024-12-31",
            price_precision=2,
            size_precision=6,
            chunk_months=1,
        )
        engine.add_data_iterator("mkts_bars", gen)

    """

    def __init__(
        self,
        endpoint: str = "http://localhost:5993/rpc",
        use_grpc: bool = False,
    ) -> None:
        self._client = pymkts.Client(endpoint=endpoint, grpc=use_grpc)

    # -- ONE-SHOT LOADERS ---------------------------------------------------------

    def load_bars(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        price_precision: int,
        size_precision: int,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        """
        Load OHLCV bars from MarketStore.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument identifier (symbol taken from ``instrument_id.symbol``).
        timeframe : str
            MarketStore timeframe (e.g., ``"1Min"``, ``"1H"``, ``"1D"``).
        price_precision : int
            Decimal precision for prices.
        size_precision : int
            Decimal precision for volume.
        start : str or datetime, optional
            Start time for the query.
        end : str or datetime, optional
            End time for the query.
        limit : int, optional
            Maximum number of records to return.

        Returns
        -------
        list[Bar]

        """
        symbol = instrument_id.symbol.value
        bar_type = make_bar_type(instrument_id, timeframe)

        params = pymkts.Params(
            symbols=symbol,
            timeframe=timeframe,
            attrgroup="OHLCV",
            start=start,
            end=end,
            limit=limit,
        )

        reply = self._client.query(params)
        dataset = reply.first()
        if dataset is None:
            logger.warning("No OHLCV data for %s/%s/OHLCV", symbol, timeframe)
            return []

        df = dataset.df()
        bars = df_to_bars(df, bar_type, price_precision, size_precision)
        logger.info("Loaded %d bars for %s", len(bars), bar_type)
        return bars

    def load_trade_ticks(
        self,
        instrument_id: InstrumentId,
        price_precision: int,
        size_precision: int,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit: int | None = None,
        timeframe: str = "1Sec",
        attrgroup: str = "TICK",
    ) -> list[TradeTick]:
        """
        Load trade ticks from MarketStore.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument identifier.
        price_precision : int
            Decimal precision for prices.
        size_precision : int
            Decimal precision for sizes.
        start : str or datetime, optional
            Start time.
        end : str or datetime, optional
            End time.
        limit : int, optional
            Maximum number of records.
        timeframe : str, default "1Sec"
            MarketStore timeframe for tick data.
        attrgroup : str, default "TICK"
            MarketStore attribute group for tick data.

        Returns
        -------
        list[TradeTick]

        """
        symbol = instrument_id.symbol.value
        params = pymkts.Params(
            symbols=symbol,
            timeframe=timeframe,
            attrgroup=attrgroup,
            start=start,
            end=end,
            limit=limit,
        )

        reply = self._client.query(params)
        dataset = reply.first()
        if dataset is None:
            logger.warning("No tick data for %s/%s/%s", symbol, timeframe, attrgroup)
            return []

        df = dataset.df()
        ticks = df_to_trade_ticks(df, instrument_id, price_precision, size_precision)
        logger.info("Loaded %d trade ticks for %s", len(ticks), instrument_id)
        return ticks

    def load_quote_ticks(
        self,
        instrument_id: InstrumentId,
        price_precision: int,
        size_precision: int,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit: int | None = None,
        timeframe: str = "1Sec",
        attrgroup: str = "QUOTE",
    ) -> list[QuoteTick]:
        """
        Load quote ticks from MarketStore.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument identifier.
        price_precision : int
            Decimal precision for prices.
        size_precision : int
            Decimal precision for sizes.
        start : str or datetime, optional
            Start time.
        end : str or datetime, optional
            End time.
        limit : int, optional
            Maximum number of records.
        timeframe : str, default "1Sec"
            MarketStore timeframe for quote data.
        attrgroup : str, default "QUOTE"
            MarketStore attribute group for quote data.

        Returns
        -------
        list[QuoteTick]

        """
        symbol = instrument_id.symbol.value
        params = pymkts.Params(
            symbols=symbol,
            timeframe=timeframe,
            attrgroup=attrgroup,
            start=start,
            end=end,
            limit=limit,
        )

        reply = self._client.query(params)
        dataset = reply.first()
        if dataset is None:
            logger.warning("No quote data for %s/%s/%s", symbol, timeframe, attrgroup)
            return []

        df = dataset.df()
        ticks = df_to_quote_ticks(df, instrument_id, price_precision, size_precision)
        logger.info("Loaded %d quote ticks for %s", len(ticks), instrument_id)
        return ticks

    # -- GENERATORS (for BacktestEngine.add_data_iterator) -------------------------

    def bar_generator(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        price_precision: int,
        size_precision: int,
        start: str | datetime,
        end: str | datetime,
        chunk_months: int = 1,
    ) -> Generator[list[Bar], None, None]:
        """
        Yield bars in monthly chunks for memory-efficient backtest loading.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument identifier.
        timeframe : str
            MarketStore timeframe (e.g., "1Min").
        price_precision : int
            Decimal precision for prices.
        size_precision : int
            Decimal precision for volume.
        start : str or datetime
            Start time.
        end : str or datetime
            End time.
        chunk_months : int, default 1
            Number of months per chunk.

        Yields
        ------
        list[Bar]
            A chunk of bars for one time period.

        """
        import pandas as pd

        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        bar_type = make_bar_type(instrument_id, timeframe)
        symbol = instrument_id.symbol.value

        current = start_ts
        while current < end_ts:
            chunk_end = current + pd.DateOffset(months=chunk_months)
            if chunk_end > end_ts:
                chunk_end = end_ts

            params = pymkts.Params(
                symbols=symbol,
                timeframe=timeframe,
                attrgroup="OHLCV",
                start=current.isoformat(),
                end=chunk_end.isoformat(),
            )

            reply = self._client.query(params)
            dataset = reply.first()
            if dataset is not None:
                df = dataset.df()
                if not df.empty:
                    bars = df_to_bars(
                        df, bar_type, price_precision, size_precision
                    )
                    logger.info(
                        "Yielding %d bars for %s [%s -> %s]",
                        len(bars), bar_type, current, chunk_end,
                    )
                    yield bars

            current = chunk_end

    def trade_tick_generator(
        self,
        instrument_id: InstrumentId,
        price_precision: int,
        size_precision: int,
        start: str | datetime,
        end: str | datetime,
        chunk_months: int = 1,
        timeframe: str = "1Sec",
        attrgroup: str = "TICK",
    ) -> Generator[list[TradeTick], None, None]:
        """
        Yield trade ticks in monthly chunks for memory-efficient loading.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument identifier.
        price_precision : int
            Decimal precision for prices.
        size_precision : int
            Decimal precision for sizes.
        start : str or datetime
            Start time.
        end : str or datetime
            End time.
        chunk_months : int, default 1
            Number of months per chunk.
        timeframe : str, default "1Sec"
            MarketStore timeframe for tick data.
        attrgroup : str, default "TICK"
            MarketStore attribute group.

        Yields
        ------
        list[TradeTick]

        """
        import pandas as pd

        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        symbol = instrument_id.symbol.value

        current = start_ts
        while current < end_ts:
            chunk_end = current + pd.DateOffset(months=chunk_months)
            if chunk_end > end_ts:
                chunk_end = end_ts

            params = pymkts.Params(
                symbols=symbol,
                timeframe=timeframe,
                attrgroup=attrgroup,
                start=current.isoformat(),
                end=chunk_end.isoformat(),
            )

            reply = self._client.query(params)
            dataset = reply.first()
            if dataset is not None:
                df = dataset.df()
                if not df.empty:
                    ticks = df_to_trade_ticks(
                        df, instrument_id, price_precision, size_precision
                    )
                    logger.info(
                        "Yielding %d trade ticks for %s [%s -> %s]",
                        len(ticks), instrument_id, current, chunk_end,
                    )
                    yield ticks

            current = chunk_end
