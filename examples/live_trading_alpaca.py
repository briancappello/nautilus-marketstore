"""
Example: Live trading with MarketStore data and Alpaca execution.

This runs a NautilusTrader live trading node that:
- Receives real-time bar data from MarketStore (via WebSocket stream trigger)
- Executes trades through Alpaca's trading API

Prerequisites:
    1. MarketStore running with stream.so trigger enabled in mkts.yml:

        triggers:
          - module: stream.so
            on: "*/*/*"

    2. Data being written to MarketStore (via bgworker plugins or external feeds).

    3. Alpaca account with API keys (paper or live).

    4. Install dependencies:
        pip install nautilus_trader pymarketstore nautilus-marketstore

    5. Install nautilus-alpaca from the sibling directory:
        pip install -e ../nautilus-alpaca

Environment variables:
    ALPACA_API_KEY_PAPER: Your Alpaca paper trading API key
    ALPACA_API_SECRET_PAPER: Your Alpaca paper trading API secret
    ALPACA_API_KEY_LIVE: Your Alpaca live trading API key (optional)
    ALPACA_API_SECRET_LIVE: Your Alpaca live trading API secret (optional)
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

from nautilus_trader.config import StrategyConfig, TradingNodeConfig
from nautilus_trader.core.message import Event
from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import PositionOpened, PositionChanged
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

# MarketStore data adapter
from nautilus_marketstore import (
    MARKETSTORE,
    MarketStoreDataClientConfig,
    MarketStoreLiveDataClientFactory,
    get_marketstore_instrument_provider,
)

# Alpaca execution adapter (from sibling repo)
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "nautilus-alpaca")
)
from alpaca_adapter.config import (
    AlpacaCredentialsConfig,
    AlpacaInstrumentProviderConfig,
    AlpacaLiveExecutionClientConfig,
)
from alpaca_adapter.execution import AlpacaLiveExecutionClient
from alpaca_adapter.providers import AlpacaInstrumentProvider
from alpaca_adapter.core import ALPACA, ALPACA_VENUE


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Alpaca credentials from environment
ALPACA_CREDENTIALS = AlpacaCredentialsConfig(
    live_api_key=os.getenv("ALPACA_API_KEY_LIVE", ""),
    live_api_secret=os.getenv("ALPACA_API_SECRET_LIVE", ""),
    paper_api_key=os.getenv("ALPACA_API_KEY_PAPER", ""),
    paper_api_secret=os.getenv("ALPACA_API_SECRET_PAPER", ""),
    mode="paper",  # Change to "live" for real trading
)

# Venue configuration
MARKETSTORE_VENUE = Venue("NASDAQ")  # Venue for data from MarketStore

# The instrument we'll trade
SYMBOL = "AAPL"


# ---------------------------------------------------------------------------
# 1. Define the instrument
# ---------------------------------------------------------------------------

# For MarketStore data, we define the instrument with the MarketStore venue
AAPL_DATA = Equity(
    instrument_id=InstrumentId(Symbol(SYMBOL), MARKETSTORE_VENUE),
    raw_symbol=Symbol(SYMBOL),
    currency=Currency.from_str("USD"),
    price_precision=2,
    price_increment=Price(0.01, precision=2),
    lot_size=Quantity(1, precision=0),
    ts_event=0,
    ts_init=0,
)

# For Alpaca execution, we need the instrument with the Alpaca venue
AAPL_EXEC = Equity(
    instrument_id=InstrumentId(Symbol(SYMBOL), ALPACA_VENUE),
    raw_symbol=Symbol(SYMBOL),
    currency=Currency.from_str("USD"),
    price_precision=2,
    price_increment=Price(0.01, precision=2),
    lot_size=Quantity(1, precision=0),
    ts_event=0,
    ts_init=0,
)


# ---------------------------------------------------------------------------
# 2. Register instruments with providers
# ---------------------------------------------------------------------------

# MarketStore provider (for data)
marketstore_provider = get_marketstore_instrument_provider(config_hash=0)
marketstore_provider.add(AAPL_DATA)


# ---------------------------------------------------------------------------
# 3. Simple EMA crossover strategy
# ---------------------------------------------------------------------------


class EMACrossoverConfig(StrategyConfig, frozen=True):
    """Configuration for the EMA crossover strategy."""

    data_instrument_id: str = f"{SYMBOL}.{MARKETSTORE_VENUE}"
    exec_instrument_id: str = f"{SYMBOL}.{ALPACA}"
    bar_type: str = f"{SYMBOL}.{MARKETSTORE_VENUE}-1-MINUTE-LAST-EXTERNAL"
    fast_ema_period: int = 10
    slow_ema_period: int = 20
    trade_size: float = 10.0  # Number of shares to trade


class EMACrossoverStrategy(Strategy):
    """
    A simple EMA crossover strategy for demonstration.

    When the fast EMA crosses above the slow EMA, buy.
    When the fast EMA crosses below the slow EMA, sell.

    This strategy uses MarketStore for market data and Alpaca for execution.
    """

    def __init__(self, config: EMACrossoverConfig) -> None:
        super().__init__(config)

        # Parse instrument IDs
        self._data_instrument_id = InstrumentId.from_str(config.data_instrument_id)
        self._exec_instrument_id = InstrumentId.from_str(config.exec_instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._trade_size = Decimal(str(config.trade_size))

        # Create indicators
        self._fast_ema = ExponentialMovingAverage(config.fast_ema_period)
        self._slow_ema = ExponentialMovingAverage(config.slow_ema_period)

        # Track previous EMA values for crossover detection
        self._prev_fast = None
        self._prev_slow = None

    def on_start(self) -> None:
        """Called when the strategy starts."""
        # Register indicators with the bar type
        self.register_indicator_for_bars(self._bar_type, self._fast_ema)
        self.register_indicator_for_bars(self._bar_type, self._slow_ema)

        # Subscribe to bar data from MarketStore
        self.subscribe_bars(self._bar_type)

        self.log.info(f"Strategy started - subscribing to {self._bar_type}")
        self.log.info(f"Data instrument: {self._data_instrument_id}")
        self.log.info(f"Execution instrument: {self._exec_instrument_id}")

    def on_bar(self, bar: Bar) -> None:
        """Called when a new bar is received."""
        # Check if indicators are ready
        if not self._fast_ema.initialized or not self._slow_ema.initialized:
            self.log.info(
                f"Waiting for indicators to initialize... "
                f"Fast EMA count: {self._fast_ema.count}, "
                f"Slow EMA count: {self._slow_ema.count}"
            )
            return

        fast = self._fast_ema.value
        slow = self._slow_ema.value

        self.log.info(f"Bar: {bar.close} | Fast EMA: {fast:.4f} | Slow EMA: {slow:.4f}")

        # Detect crossovers
        if self._prev_fast is not None and self._prev_slow is not None:
            # Bullish crossover: fast crosses above slow
            if self._prev_fast <= self._prev_slow and fast > slow:
                self._on_bullish_crossover(bar)

            # Bearish crossover: fast crosses below slow
            elif self._prev_fast >= self._prev_slow and fast < slow:
                self._on_bearish_crossover(bar)

        # Store current values for next comparison
        self._prev_fast = fast
        self._prev_slow = slow

    def _on_bullish_crossover(self, bar: Bar) -> None:
        """Handle bullish EMA crossover - go long."""
        self.log.info("BULLISH CROSSOVER detected!")

        # Check if we're already long
        if self.portfolio.is_net_long(self._exec_instrument_id):
            self.log.info("Already long, skipping buy signal")
            return

        # Close any short position first
        if self.portfolio.is_net_short(self._exec_instrument_id):
            self.close_all_positions(self._exec_instrument_id)

        # Get the execution instrument
        instrument = self.cache.instrument(self._exec_instrument_id)
        if instrument is None:
            self.log.warning(f"Instrument not found: {self._exec_instrument_id}")
            return

        # Submit buy order
        order = self.order_factory.market(
            instrument_id=self._exec_instrument_id,
            order_side=OrderSide.BUY,
            quantity=instrument.make_qty(self._trade_size),
            time_in_force=TimeInForce.DAY,
        )

        self.submit_order(order)
        self.log.info(f"Submitted BUY order: {order.client_order_id}")

    def _on_bearish_crossover(self, bar: Bar) -> None:
        """Handle bearish EMA crossover - go short or close long."""
        self.log.info("BEARISH CROSSOVER detected!")

        # Close any long position
        if self.portfolio.is_net_long(self._exec_instrument_id):
            self.close_all_positions(self._exec_instrument_id)
            self.log.info("Closed long position")

    def on_event(self, event: Event) -> None:
        """Handle events like position changes."""
        if isinstance(event, (PositionOpened, PositionChanged)):
            self.log.info(f"Position event: {event}")

    def on_stop(self) -> None:
        """Called when the strategy stops."""
        self.log.info("Strategy stopping - closing all positions")

        # Cancel all open orders
        self.cancel_all_orders(self._exec_instrument_id)

        # Close all positions
        self.close_all_positions(self._exec_instrument_id)

        # Unsubscribe from data
        self.unsubscribe_bars(self._bar_type)


# ---------------------------------------------------------------------------
# 4. Alpaca execution client factory
# ---------------------------------------------------------------------------


class AlpacaLiveExecClientFactory:
    """Factory for creating Alpaca live execution clients."""

    @staticmethod
    def create(
        loop,
        name,
        config: AlpacaLiveExecutionClientConfig,
        msgbus,
        cache,
        clock,
    ) -> AlpacaLiveExecutionClient:
        """Create an Alpaca live execution client."""
        provider_config = AlpacaInstrumentProviderConfig(
            credentials=config.credentials,
            load_all=False,
        )
        provider = AlpacaInstrumentProvider(config=provider_config)

        # Pre-add the instrument we'll trade
        provider.add(AAPL_EXEC)

        return AlpacaLiveExecutionClient(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            name=name,
        )


# ---------------------------------------------------------------------------
# 5. Configure and run the trading node
# ---------------------------------------------------------------------------


def main():
    # Validate credentials
    if not ALPACA_CREDENTIALS.api_key or not ALPACA_CREDENTIALS.api_secret:
        print("ERROR: Alpaca API credentials not set!")
        print("Please set the following environment variables:")
        print("  ALPACA_API_KEY_PAPER")
        print("  ALPACA_API_SECRET_PAPER")
        sys.exit(1)

    # Configure the trading node
    config = TradingNodeConfig(
        trader_id="LIVE-001",
        log_level="INFO",
        # Data client: MarketStore
        data_clients={
            MARKETSTORE: MarketStoreDataClientConfig(
                endpoint_rpc="http://localhost:5993/rpc",
                endpoint_ws="ws://localhost:5993/ws",
                venue=str(MARKETSTORE_VENUE),
                price_precision=2,
                size_precision=0,
                stream_patterns=["*/*/*"],
            ),
        },
        # Execution client: Alpaca
        exec_clients={
            ALPACA: AlpacaLiveExecutionClientConfig(
                credentials=ALPACA_CREDENTIALS,
            ),
        },
        timeout_connection=30.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )

    # Create the trading node
    node = TradingNode(config=config)

    # Register client factories
    node.add_data_client_factory(MARKETSTORE, MarketStoreLiveDataClientFactory)
    node.add_exec_client_factory(ALPACA, AlpacaLiveExecClientFactory)

    # Add the strategy
    strategy = EMACrossoverStrategy(EMACrossoverConfig())
    node.trader.add_strategy(strategy)

    # Build and run
    node.build()

    print("=" * 60)
    print("Live Trading Node Starting")
    print("=" * 60)
    print(f"Data source: MarketStore ({MARKETSTORE_VENUE})")
    print(f"Execution: Alpaca ({ALPACA_CREDENTIALS.mode} mode)")
    print(f"Trading: {SYMBOL}")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    print("=" * 60)

    try:
        node.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        node.dispose()


if __name__ == "__main__":
    main()
