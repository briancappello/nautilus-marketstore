"""
Example: Memory-efficient backtest using streaming data from MarketStore.

Uses the generator/iterator pattern to load data in monthly chunks,
avoiding loading the entire dataset into memory.

Prerequisites:
    1. MarketStore running with historical data loaded.
    2. pip install nautilus_trader pymarketstore nautilus-marketstore
"""

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

from nautilus_marketstore import MarketStoreBacktestLoader


# ---------------------------------------------------------------------------
# 1. Define instrument
# ---------------------------------------------------------------------------

VENUE = Venue("NASDAQ")

AAPL = Equity(
    instrument_id=InstrumentId(Symbol("AAPL"), VENUE),
    raw_symbol=Symbol("AAPL"),
    currency=Currency.from_str("USD"),
    price_precision=2,
    price_increment=Price(0.01, precision=2),
    lot_size=Quantity(1, precision=0),
    ts_event=0,
    ts_init=0,
)

INSTRUMENT_ID = AAPL.id


# ---------------------------------------------------------------------------
# 2. Create a streaming generator from MarketStore
# ---------------------------------------------------------------------------

loader = MarketStoreBacktestLoader(endpoint="http://localhost:5993/rpc")

bar_gen = loader.bar_generator(
    instrument_id=INSTRUMENT_ID,
    timeframe="1Min",
    price_precision=2,
    size_precision=0,
    start="2024-01-01",
    end="2024-12-31",
    chunk_months=1,  # Load one month at a time
)


# ---------------------------------------------------------------------------
# 3. Simple strategy
# ---------------------------------------------------------------------------

class BarCounterConfig(StrategyConfig, frozen=True):
    bar_type: str = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"


class BarCounter(Strategy):
    def __init__(self, config: BarCounterConfig) -> None:
        super().__init__(config)
        self._bar_type = BarType.from_str(config.bar_type)
        self._count = 0

    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)

    def on_bar(self, bar) -> None:
        self._count += 1
        if self._count % 1000 == 0:
            self.log.info(f"Processed {self._count} bars, latest: {bar.close}")

    def on_stop(self) -> None:
        self.log.info(f"Total bars processed: {self._count}")


# ---------------------------------------------------------------------------
# 4. Configure and run backtest with streaming data
# ---------------------------------------------------------------------------

engine = BacktestEngine(config=BacktestEngineConfig())

engine.add_venue(
    venue=VENUE,
    oms_type=OmsType.NETTING,
    account_type=AccountType.CASH,
    base_currency=Currency.from_str("USD"),
    starting_balances=[Money(100_000, Currency.from_str("USD"))],
)

engine.add_instrument(AAPL)

# Use the generator for memory-efficient loading
engine.add_data_iterator("marketstore_bars", bar_gen)

engine.add_strategy(BarCounter(BarCounterConfig()))

engine.run()
engine.dispose()
