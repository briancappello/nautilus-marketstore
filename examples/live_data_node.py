"""
Example: Live data node streaming from MarketStore.

This runs a NautilusTrader node in data-only mode (no trading), receiving
real-time bar data from MarketStore's WebSocket stream trigger.

Prerequisites:
    1. MarketStore running with stream.so trigger enabled in mkts.yml:

        triggers:
          - module: stream.so
            on: "*/*/*"

    2. Data being written to MarketStore (via bgworker plugins or external feeds).

    3. Install dependencies:
        pip install nautilus_trader pymarketstore nautilus-marketstore websockets
"""

from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.config import StrategyConfig

from nautilus_marketstore import (
    MARKETSTORE,
    MarketStoreDataClientConfig,
    MarketStoreLiveDataClientFactory,
    get_marketstore_instrument_provider,
)


# ---------------------------------------------------------------------------
# 1. Define the instrument(s) you expect from MarketStore
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


# ---------------------------------------------------------------------------
# 2. Register the instrument with the provider
# ---------------------------------------------------------------------------

provider = get_marketstore_instrument_provider(config_hash=0)
provider.add(AAPL)


# ---------------------------------------------------------------------------
# 3. Simple strategy that logs incoming bars
# ---------------------------------------------------------------------------

class BarPrinterConfig(StrategyConfig, frozen=True):
    instrument_id: str = "AAPL.NASDAQ"
    bar_type: str = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"


class BarPrinter(Strategy):
    def __init__(self, config: BarPrinterConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        from nautilus_trader.model.data import BarType
        self._bar_type = BarType.from_str(config.bar_type)

    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)
        self.log.info(f"Subscribed to {self._bar_type}")

    def on_bar(self, bar) -> None:
        self.log.info(f"BAR: {bar}")

    def on_stop(self) -> None:
        self.unsubscribe_bars(self._bar_type)


# ---------------------------------------------------------------------------
# 4. Configure and run the node
# ---------------------------------------------------------------------------

config = TradingNodeConfig(
    data_clients={
        MARKETSTORE: MarketStoreDataClientConfig(
            endpoint_rpc="http://localhost:5993/rpc",
            endpoint_ws="ws://localhost:5993/ws",
            venue="NASDAQ",
            price_precision=2,
            size_precision=0,
            # Subscribe to all streams -- the data client will filter by
            # active subscriptions
            stream_patterns=["*/*/*"],
        ),
    },
)

node = TradingNode(config=config)
node.add_data_client_factory(MARKETSTORE, MarketStoreLiveDataClientFactory)

node.trader.add_strategy(BarPrinter(BarPrinterConfig()))

node.build()
node.run()
