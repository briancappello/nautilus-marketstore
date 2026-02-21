"""
Example: Multi-symbol EMA crossover backtest with volume health filter.

This runs a NautilusTrader backtest that:
- Trades multiple symbols using an EMA crossover strategy
- Applies a "health filter" at the start of each trading day per symbol
- Only trades a symbol if its median intraday volume over the last 10 days
  exceeds a configurable threshold (default: 200,000 shares)

Prerequisites:
    1. MarketStore running with historical 1-minute data loaded for the symbols.
    2. pip install nautilus_trader pymarketstore nautilus-marketstore
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from nautilus_marketstore import MarketStoreBacktestLoader


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VENUE = Venue("NASDAQ")

# Symbols to trade
SYMBOLS = ["A", "CAT", "AMD", "B"]

# Backtest period
START_DATE = "2024-01-01"
END_DATE = "2024-03-01"

# Health filter: minimum median intraday volume over last 10 days
MIN_MEDIAN_VOLUME = 200_000
LOOKBACK_DAYS = 10


# ---------------------------------------------------------------------------
# 1. Define instruments
# ---------------------------------------------------------------------------


def create_equity(symbol: str, venue: Venue) -> Equity:
    """Create an Equity instrument."""
    return Equity(
        instrument_id=InstrumentId(Symbol(symbol), venue),
        raw_symbol=Symbol(symbol),
        currency=Currency.from_str("USD"),
        price_precision=2,
        price_increment=Price(0.01, precision=2),
        lot_size=Quantity(1, precision=0),
        ts_event=0,
        ts_init=0,
    )


INSTRUMENTS = {symbol: create_equity(symbol, VENUE) for symbol in SYMBOLS}


# ---------------------------------------------------------------------------
# 2. Multi-symbol EMA crossover strategy with health filter
# ---------------------------------------------------------------------------


class MultiSymbolEMACrossoverConfig(StrategyConfig, frozen=True):
    """Configuration for the multi-symbol EMA crossover strategy."""

    symbols: tuple[str, ...] = tuple(SYMBOLS)
    venue: str = str(VENUE)
    fast_ema_period: int = 10
    slow_ema_period: int = 20
    trade_size: float = 100.0
    min_median_volume: float = MIN_MEDIAN_VOLUME
    lookback_days: int = LOOKBACK_DAYS


class MultiSymbolEMACrossoverStrategy(Strategy):
    """
    Multi-symbol EMA crossover strategy with daily volume health filter.

    For each symbol, at the start of each trading day:
    1. Calculate the median intraday volume over the last N days
    2. If the median exceeds the threshold, allow trading for that day
    3. Otherwise, skip trading that symbol for the day

    When trading is allowed:
    - Buy when fast EMA crosses above slow EMA
    - Sell/close when fast EMA crosses below slow EMA
    """

    def __init__(self, config: MultiSymbolEMACrossoverConfig) -> None:
        super().__init__(config)

        self._venue = Venue(config.venue)
        self._trade_size = Decimal(str(config.trade_size))
        self._min_median_volume = config.min_median_volume
        self._lookback_days = config.lookback_days

        # Per-symbol tracking
        self._bar_types: dict[InstrumentId, BarType] = {}
        self._instrument_ids: dict[str, InstrumentId] = {}

        # EMA indicators per symbol
        self._fast_emas: dict[InstrumentId, ExponentialMovingAverage] = {}
        self._slow_emas: dict[InstrumentId, ExponentialMovingAverage] = {}
        self._prev_fast: dict[InstrumentId, float | None] = {}
        self._prev_slow: dict[InstrumentId, float | None] = {}

        # Volume tracking for health filter
        # {instrument_id: {date: [volumes]}}
        self._daily_volumes: dict[InstrumentId, dict[date, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        # Health status per symbol per day
        # {instrument_id: {date: bool}}
        self._health_passed: dict[InstrumentId, dict[date, bool]] = defaultdict(dict)
        self._current_day: dict[InstrumentId, date | None] = {}

        # Initialize per-symbol data structures
        for symbol in config.symbols:
            instrument_id = InstrumentId(Symbol(symbol), self._venue)
            bar_type = BarType.from_str(
                f"{symbol}.{config.venue}-1-MINUTE-LAST-EXTERNAL"
            )

            self._bar_types[instrument_id] = bar_type
            self._instrument_ids[symbol] = instrument_id
            self._fast_emas[instrument_id] = ExponentialMovingAverage(
                config.fast_ema_period
            )
            self._slow_emas[instrument_id] = ExponentialMovingAverage(
                config.slow_ema_period
            )
            self._prev_fast[instrument_id] = None
            self._prev_slow[instrument_id] = None
            self._current_day[instrument_id] = None

    def on_start(self) -> None:
        """Subscribe to bar data for all symbols."""
        for instrument_id, bar_type in self._bar_types.items():
            self.register_indicator_for_bars(bar_type, self._fast_emas[instrument_id])
            self.register_indicator_for_bars(bar_type, self._slow_emas[instrument_id])
            self.subscribe_bars(bar_type)
            self.log.info(f"Subscribed to {bar_type}")

        self.log.info(
            f"Strategy started with {len(self._bar_types)} symbols, "
            f"health filter: median volume > {self._min_median_volume:,.0f} "
            f"over last {self._lookback_days} days"
        )

    def on_bar(self, bar: Bar) -> None:
        """Process each bar for volume tracking and trading signals."""
        instrument_id = bar.bar_type.instrument_id
        bar_date = datetime.fromtimestamp(bar.ts_event / 1e9).date()
        volume = float(bar.volume)

        # Track volume for health filter
        self._daily_volumes[instrument_id][bar_date].append(volume)

        # Check if this is a new trading day for this symbol
        if self._current_day[instrument_id] != bar_date:
            self._on_new_day(instrument_id, bar_date)
            self._current_day[instrument_id] = bar_date

        # Check if health filter passed for today
        if not self._health_passed[instrument_id].get(bar_date, False):
            return  # Skip trading for this symbol today

        # Check if EMAs are initialized
        fast_ema = self._fast_emas[instrument_id]
        slow_ema = self._slow_emas[instrument_id]

        if not fast_ema.initialized or not slow_ema.initialized:
            return

        # Get current EMA values
        fast = fast_ema.value
        slow = slow_ema.value
        prev_fast = self._prev_fast[instrument_id]
        prev_slow = self._prev_slow[instrument_id]

        # Detect crossovers
        if prev_fast is not None and prev_slow is not None:
            # Bullish crossover: fast crosses above slow
            if prev_fast <= prev_slow and fast > slow:
                self._on_bullish_crossover(instrument_id, bar)

            # Bearish crossover: fast crosses below slow
            elif prev_fast >= prev_slow and fast < slow:
                self._on_bearish_crossover(instrument_id, bar)

        # Store current values for next comparison
        self._prev_fast[instrument_id] = fast
        self._prev_slow[instrument_id] = slow

    def _on_new_day(self, instrument_id: InstrumentId, today: date) -> None:
        """
        Perform health check at the start of a new trading day.

        Calculates the median intraday volume over the last N days and
        determines if trading should be enabled for this symbol today.
        """
        symbol = instrument_id.symbol.value

        # Get volume data for the last N days (excluding today)
        daily_totals = []
        volumes_by_date = self._daily_volumes[instrument_id]

        for day_offset in range(1, self._lookback_days + 1):
            check_date = today - timedelta(days=day_offset)
            if check_date in volumes_by_date:
                # Sum all intraday volumes for that day
                day_total = sum(volumes_by_date[check_date])
                daily_totals.append(day_total)

        # Calculate median if we have enough data
        if len(daily_totals) >= 1:
            median_volume = statistics.median(daily_totals)
            health_passed = median_volume >= self._min_median_volume

            self._health_passed[instrument_id][today] = health_passed

            if health_passed:
                self.log.info(
                    f"[{symbol}] Health check PASSED for {today}: "
                    f"median volume = {median_volume:,.0f} "
                    f"(threshold: {self._min_median_volume:,.0f}, "
                    f"days: {len(daily_totals)})"
                )
            else:
                self.log.warning(
                    f"[{symbol}] Health check FAILED for {today}: "
                    f"median volume = {median_volume:,.0f} "
                    f"(threshold: {self._min_median_volume:,.0f}, "
                    f"days: {len(daily_totals)})"
                )
        else:
            # Not enough historical data yet, allow trading by default
            self._health_passed[instrument_id][today] = True
            self.log.info(
                f"[{symbol}] Health check SKIPPED for {today}: "
                f"insufficient data ({len(daily_totals)} days available, "
                f"need at least 1)"
            )

    def _on_bullish_crossover(self, instrument_id: InstrumentId, bar: Bar) -> None:
        """Handle bullish EMA crossover - go long."""
        symbol = instrument_id.symbol.value
        self.log.info(f"[{symbol}] BULLISH CROSSOVER at {bar.close}")

        # Check if we're already long
        if self.portfolio.is_net_long(instrument_id):
            self.log.debug(f"[{symbol}] Already long, skipping buy signal")
            return

        # Close any short position first
        if self.portfolio.is_net_short(instrument_id):
            self.close_all_positions(instrument_id)

        # Get the instrument
        instrument = self.cache.instrument(instrument_id)
        if instrument is None:
            self.log.warning(f"Instrument not found: {instrument_id}")
            return

        # Submit buy order
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=instrument.make_qty(self._trade_size),
            time_in_force=TimeInForce.GTC,
        )

        self.submit_order(order)
        self.log.info(f"[{symbol}] Submitted BUY order: {order.client_order_id}")

    def _on_bearish_crossover(self, instrument_id: InstrumentId, bar: Bar) -> None:
        """Handle bearish EMA crossover - close long position."""
        symbol = instrument_id.symbol.value
        self.log.info(f"[{symbol}] BEARISH CROSSOVER at {bar.close}")

        # Close any long position
        if self.portfolio.is_net_long(instrument_id):
            self.close_all_positions(instrument_id)
            self.log.info(f"[{symbol}] Closed long position")

    def on_stop(self) -> None:
        """Clean up when strategy stops."""
        self.log.info("Strategy stopping - closing all positions")

        for instrument_id in self._bar_types.keys():
            self.cancel_all_orders(instrument_id)
            self.close_all_positions(instrument_id)
            self.unsubscribe_bars(self._bar_types[instrument_id])

        # Log summary statistics
        self.log.info("=" * 60)
        self.log.info("Health Filter Summary:")
        for instrument_id in self._bar_types.keys():
            symbol = instrument_id.symbol.value
            health_results = self._health_passed[instrument_id]
            passed_days = sum(1 for v in health_results.values() if v)
            total_days = len(health_results)
            pct = (passed_days / total_days * 100) if total_days > 0 else 0
            self.log.info(
                f"  {symbol}: {passed_days}/{total_days} days passed ({pct:.1f}%)"
            )
        self.log.info("=" * 60)


# ---------------------------------------------------------------------------
# 3. Load data from MarketStore
# ---------------------------------------------------------------------------


def load_data_for_symbols(
    loader: MarketStoreBacktestLoader,
    symbols: list[str],
    venue: Venue,
    start: str,
    end: str,
) -> list[Bar]:
    """Load 1-minute bars for all symbols from MarketStore."""
    all_bars = []

    for symbol in symbols:
        instrument_id = InstrumentId(Symbol(symbol), venue)
        bars = loader.load_bars(
            instrument_id=instrument_id,
            timeframe="1Min",
            price_precision=2,
            size_precision=0,
            start=start,
            end=end,
        )
        print(f"Loaded {len(bars):,} bars for {symbol}")
        all_bars.extend(bars)

    # Sort all bars by timestamp to ensure correct processing order
    all_bars.sort(key=lambda b: b.ts_event)
    return all_bars


# ---------------------------------------------------------------------------
# 4. Run backtest
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("Multi-Symbol EMA Crossover Backtest with Health Filter")
    print("=" * 60)
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Health filter: median intraday volume > {MIN_MEDIAN_VOLUME:,}")
    print(f"Lookback: {LOOKBACK_DAYS} days")
    print("=" * 60)

    # Load data from MarketStore
    loader = MarketStoreBacktestLoader(endpoint="http://localhost:5993/rpc")
    all_bars = load_data_for_symbols(loader, SYMBOLS, VENUE, START_DATE, END_DATE)
    print(f"\nTotal bars loaded: {len(all_bars):,}")

    if not all_bars:
        print("ERROR: No data loaded. Make sure MarketStore is running with data.")
        return

    # Configure backtest engine
    engine = BacktestEngine(config=BacktestEngineConfig())

    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=Currency.from_str("USD"),
        starting_balances=[Money(1_000_000, Currency.from_str("USD"))],
    )

    # Add all instruments
    for instrument in INSTRUMENTS.values():
        engine.add_instrument(instrument)

    # Add all bar data
    engine.add_data(all_bars)

    # Add the strategy
    strategy_config = MultiSymbolEMACrossoverConfig(
        symbols=tuple(SYMBOLS),
        venue=str(VENUE),
        fast_ema_period=10,
        slow_ema_period=20,
        trade_size=100.0,
        min_median_volume=MIN_MEDIAN_VOLUME,
        lookback_days=LOOKBACK_DAYS,
    )
    strategy = MultiSymbolEMACrossoverStrategy(strategy_config)
    engine.add_strategy(strategy)

    # Run backtest
    print("\nRunning backtest...")
    engine.run()

    # Print results
    print("\n" + "=" * 60)
    print("Backtest Results")
    print("=" * 60)
    engine.trader.generate_order_fills_report()
    engine.trader.generate_positions_report()
    engine.trader.generate_account_report(VENUE)

    # Cleanup
    engine.dispose()


if __name__ == "__main__":
    main()
