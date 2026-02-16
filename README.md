# Nautilus Trader & Marketstore integration

The two systems have complementary extension points that align well. Here's the concrete architecture:

### How It Would Work

```
External APIs (Binance, IB, Massive, etc.)
        |
        v
MarketStore BgWorker plugins (feeders)
        |
        v
MarketStore Storage Engine (writes to disk)
        |
        +---> StreamTrigger fires on write
        |         |
        |         v
        |     WebSocket /ws endpoint (msgpack-encoded)
        |         |
        |         v
        |   MarketStoreDataClient (custom NautilusTrader adapter)
        |     connects to ws://marketstore:5993/ws
        |     subscribes to ["*/*/*"] or specific patterns
        |     deserializes msgpack payload
        |     constructs QuoteTick / TradeTick / Bar objects
        |     calls self._handle_data(data)
        |         |
        |         v
        |   DataEngine.process --> Cache --> MessageBus --> Strategies/Actors
        |
        +---> pymarketstore client (for historical request/response)
              used by _request_bars(), _request_quote_ticks(), etc.
              returns pandas DataFrames, converted to Nautilus objects
```

### The Adapter You'd Write

A single Python file (~200-300 lines) implementing `LiveMarketDataClient`:

**`_connect()`**: 
- Instantiate a `pymarketstore` client for historical queries (gRPC or msgpack-rpc to `localhost:5993`)
- Open an asyncio WebSocket connection to `ws://marketstore:5993/ws`
- Send msgpack subscription message for the patterns matching configured instruments

**`_subscribe_bars()` / `_subscribe_trade_ticks()` / `_subscribe_quote_ticks()`**: 
- Track which instruments are subscribed
- Update the WebSocket subscription patterns accordingly (MarketStore supports glob patterns like `BTCUSDT/1Min/OHLCV`)

**WebSocket message handler (the hot path)**:
- Receive msgpack binary frames from MarketStore's `stream.so` trigger
- Each frame is `{"key": "BTCUSDT/1Min/OHLCV", "data": {Epoch, Open, High, Low, Close, Volume}}`
- Parse the key to determine the data type (OHLCV -> Bar, Tick -> TradeTick, etc.)
- Construct the Nautilus model object (`Bar(...)`, `TradeTick(...)`, `QuoteTick(...)`)
- Call `self._handle_data(data)` -- this is the single method that pushes into `DataEngine.process`

**`_request_bars()` / `_request_trade_ticks()`** (historical backfill):
- Use `pymarketstore.Client.query()` with time range parameters
- Returns a pandas DataFrame
- Convert rows to Nautilus `Bar` / `TradeTick` / `QuoteTick` objects
- Call `self._handle_bars(bar_type, bars, correlation_id, ...)` to send response to the engine

### Why This Works Cleanly

1. **MarketStore's stream trigger** (`stream.so`) already pushes every write to WebSocket subscribers with zero additional development on the MarketStore side. You just enable it in `mkts.yml`:

```yaml
triggers:
 - module: stream.so
   on: "*/*/*"
```

2. **NautilusTrader's adapter interface** is designed exactly for this pattern. Every existing adapter (Binance, Databento, etc.) does the same thing: receive data over a network connection, convert to Nautilus objects, call `self._handle_data()`. The interface at `live/data_client.py` gives you the asyncio event loop, task management, and all the plumbing.

3. **From Nautilus's perspective, it's indistinguishable from a direct exchange feed.** Strategies subscribe to instruments, the DataEngine routes subscribe commands to your adapter, your adapter manages the MarketStore WebSocket subscription, and data flows back through `_handle_data()` into the cache and message bus. No other component in the system knows or cares that MarketStore is in the middle.

4. **Historical + real-time in one adapter.** The `_request_*` methods handle backfill via `pymarketstore`'s query API (returns DataFrames), while the `_subscribe_*` methods handle live streaming via WebSocket. This is exactly how adapters like Databento work (HTTP for historical, WebSocket for live).

### Data Type Mapping

| MarketStore AttributeGroup | Nautilus Type | Conversion Complexity                                |
|----------------------------|---------------|------------------------------------------------------|
| `OHLCV` (bars)             | `Bar`         | Straightforward -- Epoch, O, H, L, C, V map directly |
| `Tick` (trades)            | `TradeTick`   | Need: price, size, aggressor_side, trade_id          |
| `Quote` (bid/ask)          | `QuoteTick`   | Need: bid_price, ask_price, bid_size, ask_size       |
| Custom schemas             | `CustomData`  | Use `@customdataclass` for anything non-standard     |

The main consideration is that MarketStore's native data model is column-oriented OHLCV bars and generic typed columns, while Nautilus has richer typed objects (e.g., `TradeTick` needs `aggressor_side` and `trade_id`). You'll need to ensure your MarketStore schemas include those extra fields when storing tick-level data. MarketStore supports arbitrary columns with types like `i8`, `f8`, `U16`, so this is achievable -- you just define the schema at `Create` time.

### What You'd Need to Build

| Component                        | Effort         | Notes                                                                 |
|----------------------------------|----------------|-----------------------------------------------------------------------|
| `MarketStoreDataClient` (Python) | ~200-300 lines | Subclass `LiveMarketDataClient`, implements connect/subscribe/request |
| `MarketStoreDataClientConfig`    | ~20 lines      | `msgspec.Struct` with host, port, stream patterns                     |
| `MarketStoreDataClientFactory`   | ~15 lines      | Boilerplate factory                                                   |
| `MarketStoreInstrumentProvider`  | ~50 lines      | Maps MarketStore symbols to Nautilus `Instrument` objects             |
| MarketStore schema design        | Config only    | Define TBK schemas for your data types                                |
| MarketStore `mkts.yml`           | Config only    | Enable `stream.so` trigger                                            |

Total: one Python module of ~300-400 lines plus configuration. No changes to either MarketStore or NautilusTrader core.
