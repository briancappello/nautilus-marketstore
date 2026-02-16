## NautilusTrader Repository Architecture Summary

### What It Is

**NautilusTrader** (v1.223.0 Python / v0.53.0 Rust) is an open-source, high-performance, production-grade **algorithmic trading platform** developed by Nautech Systems. It provides:

- An **event-driven backtesting engine** that replays historical data (quotes, trades, bars, order book) with nanosecond resolution
- A **live trading engine** that deploys the exact same strategy code to real markets with no modifications
- A **multi-venue, multi-asset-class** system supporting FX, Equities, Futures, Options, Crypto (CEX and DEX), DeFi, and Betting

The core design philosophy is **backtest-live parity**: strategies written once run identically in both environments, eliminating the traditional rewrite from research to production.

---

### Programming Languages

The codebase is a **tri-language hybrid**:

| Language               | File Count        | Role                                                                                         |
|------------------------|-------------------|----------------------------------------------------------------------------------------------|
| **Rust** (.rs)         | ~1,630 files      | Performance-critical core engine, networking (tokio async), adapters, infrastructure         |
| **Cython** (.pyx/.pxd) | ~106 + ~129 files | CPython C-extension modules bridging Rust to Python; performance-critical Python-facing code |
| **Python** (.py)       | ~445 + ~30 files  | High-level orchestration, configuration, strategies, adapters (some), live node management   |

- **Compiled shared objects** (.so): ~140 pre-built binaries in the package
- **PyO3** (via `pyo3` v0.27.2): Rust-to-Python bindings for the `nautilus_pyo3` module
- **Cython** (v3.2.4): Compiles `.pyx` files to C extension modules
- **FFI layer**: The `crates/core/src/ffi/` and `crates/model/src/ffi/` directories provide C-compatible function interfaces for the Cython layer

---

### Top-Level Directory Structure

```
nautilus_trader/          # Main Python/Cython package (installed as nautilus_trader)
crates/                   # Rust workspace (all core Rust crates)
python/                   # Pure Python PyO3 bindings and stubs (python/nautilus_trader/)
tests/                    # Python test suite
examples/                 # Backtest and strategy examples
docs/                     # Sphinx documentation sources
schema/                   # SQL schema files
scripts/                  # Build and utility scripts
.github/                  # CI/CD workflows
.docker/                  # Docker configuration
```

---

### Main Python/Cython Package (`nautilus_trader/`)

| Module               | Description                                                                                                                                                                                          | Primary Language         |
|----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------|
| **`core/`**          | Foundational primitives: UUID, datetime, math, FSM, correctness checks, message types. Contains `nautilus_pyo3` (the compiled Rust-to-Python bridge) and `core/rust/` Cython wrappers for Rust types | Cython + Rust (via PyO3) |
| **`model/`**         | Domain model: instruments, orders, positions, order book, events, identifiers, data types, currencies, venues, Greeks                                                                                | Cython (heavy)           |
| **`common/`**        | Shared infrastructure: Actor base class, Component, Clock, MessageBus, logging, generators, config, signal handling, data topic subscriptions                                                        | Cython + Python          |
| **`data/`**          | Data engine: aggregation (bar building), data client interface, data engine, messages                                                                                                                | Cython                   |
| **`execution/`**     | Execution engine: order matching core, execution client, emulator, manager, trailing stop logic, execution algorithms                                                                                | Cython                   |
| **`risk/`**          | Risk management engine and position sizing calculators                                                                                                                                               | Cython                   |
| **`cache/`**         | In-memory cache and cache database adapter (optional Redis backend), cache facade                                                                                                                    | Cython + Python          |
| **`portfolio/`**     | Portfolio management: position tracking, P&L, margin calculations                                                                                                                                    | Cython                   |
| **`trading/`**       | Strategy base class, Trader (strategy container), Controller, filters                                                                                                                                | Cython + Python          |
| **`backtest/`**      | Backtesting engine, simulated exchange, simulated data/execution clients, matching engine, backtest node                                                                                             | Cython + Python          |
| **`live/`**          | Live trading node, live data/execution/risk engines, retry logic, reconciliation, cancellation management                                                                                            | Python                   |
| **`accounting/`**    | Account management: margin models, account factories, calculators                                                                                                                                    | Cython                   |
| **`persistence/`**   | Data persistence: Parquet data catalog, data wranglers, streaming Feather writer, data loaders                                                                                                       | Cython + Python          |
| **`serialization/`** | Serialization: MsgSpec (msgpack) serializer, Arrow serialization                                                                                                                                     | Cython + Python          |
| **`analysis/`**      | Post-trade analysis: strategy analyzer, reporter, tearsheet generation                                                                                                                               | Python                   |
| **`indicators/`**    | Technical indicators: EMA, RSI, MACD, Bollinger Bands, ATR, Keltner, VWAP, Stochastics, ~30+ indicators                                                                                              | Cython                   |
| **`system/`**        | System kernel: `NautilusKernel` is the central wiring point that assembles Clock, MessageBus, Cache, DataEngine, ExecutionEngine, RiskEngine, Portfolio, Trader                                      | Python                   |
| **`adapters/`**      | Exchange/broker integrations (see below)                                                                                                                                                             | Python + Cython          |
| **`config/`**        | Configuration re-exports                                                                                                                                                                             | Python                   |
| **`test_kit/`**      | Test utilities: stubs, mocks, providers, test strategies                                                                                                                                             | Python                   |
| **`examples/`**      | Example strategies, indicators, and execution algorithms                                                                                                                                             | Python                   |

---

### Rust Crate Workspace (`crates/`)

The Rust crates mirror the Python module structure almost 1:1:

| Crate                     | Purpose                                                                                               |
|---------------------------|-------------------------------------------------------------------------------------------------------|
| `nautilus-core`           | Fundamental types: UUID, datetime/nanos, math, parsing, correctness, collections                      |
| `nautilus-model`          | Domain model: instruments, orders, positions, order book, identifiers, data types, accounts, events   |
| `nautilus-common`         | Actor/component framework, clock, message bus, logging, throttler, timer, exchange rate calculator    |
| `nautilus-data`           | Data engine core                                                                                      |
| `nautilus-execution`      | Execution engine core                                                                                 |
| `nautilus-risk`           | Risk engine core                                                                                      |
| `nautilus-backtest`       | Backtesting engine core                                                                               |
| `nautilus-live`           | Live engine core                                                                                      |
| `nautilus-network`        | HTTP client, WebSocket client, socket handling, TLS, rate limiters, retry/backoff (tokio-based async) |
| `nautilus-infrastructure` | Redis cache/msgbus backend, SQL (Postgres via sqlx) database backend                                  |
| `nautilus-persistence`    | Parquet/Arrow data persistence, DataFusion query engine                                               |
| `nautilus-serialization`  | Serialization (msgpack via rmp-serde, Arrow, Cap'n Proto)                                             |
| `nautilus-portfolio`      | Portfolio management                                                                                  |
| `nautilus-analysis`       | Post-trade analysis                                                                                   |
| `nautilus-indicators`     | Technical indicators in Rust                                                                          |
| `nautilus-trading`        | Trading strategy/controller framework                                                                 |
| `nautilus-system`         | System orchestration                                                                                  |
| `nautilus-cryptography`   | Cryptographic utilities (ed25519, etc.)                                                               |
| `nautilus-cli`            | Command-line interface                                                                                |
| `nautilus-pyo3`           | PyO3 Python bindings (the single compiled `.so` that exposes all Rust to Python)                      |
| `nautilus-testkit`        | Test utilities and stubs for Rust                                                                     |

---

### Adapter Integrations

Adapters exist in both Python (`nautilus_trader/adapters/`) and Rust (`crates/adapters/`):

| Adapter                    | Type                    | Status          |
|----------------------------|-------------------------|-----------------|
| **Binance**                | Crypto CEX              | Stable          |
| **BitMEX**                 | Crypto CEX              | Stable          |
| **Bybit**                  | Crypto CEX              | Stable          |
| **Coinbase International** | Crypto CEX              | Stable          |
| **OKX**                    | Crypto CEX              | Stable          |
| **Kraken**                 | Crypto CEX              | Beta            |
| **Deribit**                | Crypto CEX (options)    | Beta            |
| **dYdX v3/v4**             | Crypto DEX              | Stable/Building |
| **Hyperliquid**            | Crypto DEX              | Beta            |
| **Polymarket**             | Prediction Market       | Stable          |
| **Databento**              | Data Provider           | Stable          |
| **Tardis**                 | Crypto Data Provider    | Stable          |
| **Interactive Brokers**    | Brokerage (multi-venue) | Stable          |
| **Betfair**                | Sports Betting          | Stable          |
| **Architect AX**           | Perpetuals Exchange     | Building        |
| **Sandbox**                | Simulated adapter       | Internal        |

---

### Key Architectural Patterns

1. **System Kernel (`NautilusKernel`)**: The central orchestrator that wires together Clock, MessageBus, Cache, DataEngine, ExecutionEngine, RiskEngine, Portfolio, and Trader. Works in three environment modes: `BACKTEST`, `SANDBOX`, and `LIVE`.

2. **Event-Driven Message Bus**: All components communicate via a pub/sub MessageBus. Data events, order events, position events, and custom messages flow through a unified bus.

3. **Engine Pattern**: Each major subsystem (Data, Execution, Risk) has an "engine" that manages its domain, with separate implementations for backtest and live modes.

4. **Client-Adapter Pattern**: Exchange connectivity is abstracted via DataClient/ExecutionClient interfaces, with adapter-specific implementations translating between the NautilusTrader domain model and venue-specific APIs.

5. **Dual Persistence**: Optional Redis for real-time state persistence (cache + message bus), and Parquet/Arrow for historical data storage via a DataCatalog.

6. **Multi-precision Support**: Core value types (`Price`, `Quantity`, `Money`) support both 64-bit (standard) and 128-bit (high-precision) modes.

7. **Instrument Type System**: A rich hierarchy of instrument types covering equities, FX currency pairs, futures contracts/spreads, options contracts/spreads, crypto perpetuals/futures/options, CFDs, commodities, betting instruments, binary options, synthetics, and index instruments.

8. **Order Type System**: Comprehensive order types including Market, Limit, Stop-Market, Stop-Limit, Market-to-Limit, Market-if-Touched, Limit-if-Touched, Trailing-Stop-Market, Trailing-Stop-Limit, and order lists (contingency groups).


## NautilusTrader Data & Caching Architecture

### 1. CACHE SYSTEM (`nautilus_trader/cache/`)

**What it does:** The cache is the central **in-memory data store** for the entire trading system -- both market data and execution state. It provides fast, low-latency access to all runtime data needed by strategies, the data engine, and the execution engine.

**Architecture layers (4 classes):**

| File           | Class                                                  | Role                                                                                                |
|----------------|--------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| `base.pyx`     | `CacheFacade`                                          | Abstract read-only interface (methods for querying quotes, trades, bars, orders, positions, etc.)   |
| `facade.pyx`   | `CacheDatabaseFacade`                                  | Abstract interface for database persistence backends (load/add/update methods for all entity types) |
| `cache.pyx`    | `Cache` (extends `CacheFacade`)                        | **The concrete in-memory cache** -- Python dicts and deques storing all data                        |
| `database.pyx` | `CacheDatabaseAdapter` (extends `CacheDatabaseFacade`) | **Redis backend** -- wraps `nautilus_pyo3.RedisCacheDatabase`                                       |
| `adapter.py`   | `CachePostgresAdapter` (extends `CacheDatabaseFacade`) | **PostgreSQL backend** -- wraps `nautilus_pyo3.PostgresCacheDatabase`                               |

**What data it stores in-memory (from `cache.pyx` lines 120-142):**

- `_general: dict[str, bytes]` -- general key-value store
- `_currencies: dict[str, Currency]`
- `_instruments: dict[InstrumentId, Instrument]`
- `_synthetics: dict[InstrumentId, SyntheticInstrument]`
- `_order_books: dict[InstrumentId, OrderBook]`
- `_own_order_books: dict[InstrumentId, OwnOrderBook]`
- `_quote_ticks: dict[InstrumentId, deque[QuoteTick]]` (capped by `tick_capacity`, default 10,000)
- `_trade_ticks: dict[InstrumentId, deque[TradeTick]]` (capped by `tick_capacity`)
- `_mark_prices: dict[InstrumentId, deque[MarkPriceUpdate]]`
- `_index_prices: dict[InstrumentId, deque[IndexPriceUpdate]]`
- `_funding_rates: dict[InstrumentId, deque[FundingRateUpdate]]`
- `_bars: dict[BarType, deque[Bar]]` (capped by `bar_capacity`, default 10,000)
- `_accounts: dict[AccountId, Account]`
- `_orders: dict[ClientOrderId, Order]`
- `_order_lists: dict[OrderListId, OrderList]`
- `_positions: dict[PositionId, Position]`
- `_position_snapshots: dict[PositionId, list[bytes]]`
- `_greeks: dict[InstrumentId, object]`
- `_yield_curves: dict[str, object]`
- Plus ~25 index dictionaries for fast lookups (venue-to-orders, strategy-to-orders, etc.)

**Cache is primarily in-memory** -- but can optionally be backed by a persistent database. When a database is configured, the Cache:
- Loads state on startup via `cache_all()` (currencies, instruments, accounts, orders, positions)
- Writes through on mutations (adding orders, updating positions, etc.)

**Configuration** (`CacheConfig`): Controls tick/bar deque capacities, database connection, encoding format (msgpack/json), buffer intervals, and flush-on-start behavior.

---

### 2. DATA ENGINE (`nautilus_trader/data/`)

**What it is:** The `DataEngine` is the **central orchestrator of the data stack** -- it sits between `DataClient` instances (which connect to exchanges/brokers/data feeds) and the rest of the platform (strategies, indicators, etc.).

**Architecture pattern:** Fan-in/fan-out messaging:

```
DataClient(s) --> DataEngine --> MessageBus --> Strategies/Actors
                      |
                      v
                    Cache
```

**Key components:**

| File              | Class                                                                         | Role                                                         |
|-------------------|-------------------------------------------------------------------------------|--------------------------------------------------------------|
| `engine.pyx`      | `DataEngine`                                                                  | Central orchestrator; processes all data and routes commands |
| `client.pyx`      | `DataClient` / `MarketDataClient`                                             | Base classes for exchange/venue data adapters                |
| `messages.pyx`    | `DataCommand`, `SubscribeData`, `RequestData`, `DataResponse`, etc.           | Message types for the command/request/response protocol      |
| `aggregation.pyx` | `BarBuilder`, `BarAggregator`, `TimeBarAggregator`, `TickBarAggregator`, etc. | 13+ bar aggregator types for building bars from raw data     |

**How incoming data flows (from `_handle_data`, line 1987):**

1. Data arrives from a `DataClient` (live feed or backtest replay)
2. `DataEngine.process(data)` is called
3. Data is dispatched by type -- the engine handles:
   - `OrderBookDelta` / `OrderBookDeltas` / `OrderBookDepth10`
   - `QuoteTick`
   - `TradeTick`
   - `MarkPriceUpdate` / `IndexPriceUpdate` / `FundingRateUpdate`
   - `Bar`
   - `Instrument` / `InstrumentStatus` / `InstrumentClose`
   - `CustomData`
4. For each data type, the engine:
   - **Adds it to the Cache** (e.g., `self._cache.add_quote_tick(tick)`)
   - **Updates synthetic instruments** if applicable
   - **Publishes to the MessageBus** on a topic like `data.quotes.{instrument_id}`
   - **Feeds bar aggregators** (quotes/trades drive bar building)

**Subscribe/Unsubscribe protocol:** The engine handles ~12 subscription types (instruments, order books, quotes, trades, bars, mark prices, index prices, funding rates, instrument status, instrument close, and custom data). Each subscribe command is routed to the appropriate `DataClient`.

**Bar aggregation types supported (13+):**
- Time-based: MILLISECOND, SECOND, MINUTE, HOUR, DAY, WEEK, MONTH, YEAR
- Threshold-based: TICK, VOLUME, VALUE, RENKO
- Information-theoretic: TICK_IMBALANCE, TICK_RUNS, VOLUME_IMBALANCE, VOLUME_RUNS, VALUE_IMBALANCE, VALUE_RUNS

**Catalog integration:** The `DataEngine` can register `ParquetDataCatalog` instances (line 192, 360-374), enabling it to check existing catalog data timestamps when subscribing (avoiding re-downloading already-persisted data).

---

### 3. PERSISTENCE (`nautilus_trader/persistence/`)

**Two distinct persistence mechanisms exist:**

#### A. Cache Database Backends (for execution state)

| Backend        | Class                  | File                 | Description                                                                                                                                                                                                      |
|----------------|------------------------|----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Redis**      | `CacheDatabaseAdapter` | `cache/database.pyx` | Uses `nautilus_pyo3.RedisCacheDatabase` -- stores currencies, instruments, synthetics, accounts, orders, positions, actor/strategy state. Supports pipelined/batched writes and bulk reads. Requires Redis 6.2+. |
| **PostgreSQL** | `CachePostgresAdapter` | `cache/adapter.py`   | Uses `nautilus_pyo3.PostgresCacheDatabase` -- stores the same entity types plus quotes, trades, bars, signals, custom data, order/position snapshots.                                                            |

Both backends are implemented in Rust (via `nautilus_pyo3`) for performance.

`DatabaseConfig` (from `common/config.py`) supports:
- `type`: only `"redis"` documented (but Postgres is also available)
- `host`, `port`, `username`, `password`, `ssl`, `timeout`

#### B. Parquet Data Catalog (for market data persistence)

**`ParquetDataCatalog`** (`persistence/catalog/parquet.py`) -- a **file-based queryable data store** using Apache Parquet format:

- **Storage**: Parquet files organized by data type and instrument ID in a directory hierarchy
- **Filesystem support**: Local files, S3, GCS, Azure Blob, HTTP/WebDAV (via `fsspec`)
- **Query backends**: 
  - **Rust backend** (via `DataBackendSession` / DataFusion) for OrderBookDelta, OrderBookDepth10, QuoteTick, TradeTick, Bar, MarkPriceUpdate -- highest performance
  - **PyArrow backend** for all other types (instruments, events, custom data)
- **Writing**: Supports `write_data()` for batch writes, `StreamingFeatherWriter` for real-time streaming writes with file rotation (size-based, interval-based, or scheduled)
- **Features**: File consolidation, deduplication, timestamp-based filename management, disjoint interval validation

**Catalog hierarchy:** `BaseDataCatalog` (abstract, singleton) -> `ParquetDataCatalog` (concrete). Query API includes `instruments()`, `quote_ticks()`, `trade_ticks()`, `bars()`, `order_book_deltas()`, `order_book_depth10()`, `funding_rates()`, `custom_data()`, etc.

#### C. Data Wranglers

- `wranglers.pyx` -- Transform pandas DataFrames into Nautilus objects (QuoteTick, TradeTick, Bar, OrderBookDelta)
- `wranglers_v2.py` -- V2 wranglers
- `loaders.py` -- CSV loaders for tick and bar data

---

### 4. DATA MODELS (`nautilus_trader/model/`)

#### Market Data Types (from `model/data.pyx`):

| Class               | Description                                                            |
|---------------------|------------------------------------------------------------------------|
| `QuoteTick`         | Bid/ask price and size snapshot (level-1 quote)                        |
| `TradeTick`         | Individual trade execution (price, size, aggressor side, trade ID)     |
| `Bar`               | OHLCV candlestick with configurable aggregation                        |
| `BarSpecification`  | Defines how bars are aggregated (step, aggregation method, price type) |
| `BarType`           | Full bar definition (instrument + specification + source)              |
| `OrderBookDelta`    | Single order book change (add/update/delete/clear at a price level)    |
| `OrderBookDeltas`   | Batch of deltas (with F_LAST flag for atomic updates)                  |
| `OrderBookDepth10`  | Top-10 levels of bid/ask (snapshot)                                    |
| `BookOrder`         | Single order in the book (side, price, size, order_id)                 |
| `MarkPriceUpdate`   | Mark price for derivatives                                             |
| `IndexPriceUpdate`  | Index price for derivatives                                            |
| `FundingRateUpdate` | Funding rate for perpetual contracts                                   |
| `InstrumentStatus`  | Market status changes (trading halts, etc.)                            |
| `InstrumentClose`   | Closing/settlement prices                                              |
| `DataType`          | Metadata wrapper for generic/custom data types                         |
| `CustomData`        | User-defined data types (via `@customdataclass` decorator)             |

#### Order Book Model (`model/book.pyx`):
- `OrderBook` -- Full order book maintained by the Rust core (L1/L2/L3 book types). Supports applying deltas, snapshots, depth updates, fill simulation, integrity checks.

#### Instrument Types (from `model/instruments/`):

| Class                 | Description                                        |
|-----------------------|----------------------------------------------------|
| `Instrument`          | Abstract base class                                |
| `Equity`              | Stock/equity                                       |
| `CurrencyPair`        | FX pair                                            |
| `CryptoPerpetual`     | Crypto perpetual futures                           |
| `CryptoFuture`        | Crypto delivery futures                            |
| `CryptoOption`        | Crypto options                                     |
| `FuturesContract`     | Traditional futures                                |
| `FuturesSpread`       | Futures spreads                                    |
| `OptionContract`      | Traditional options                                |
| `OptionSpread`        | Options spreads                                    |
| `Cfd`                 | Contract for Difference                            |
| `Commodity`           | Commodities                                        |
| `BettingInstrument`   | Betting/prediction markets                         |
| `BinaryOption`        | Binary/digital options                             |
| `IndexInstrument`     | Market indices                                     |
| `SyntheticInstrument` | User-defined synthetic instruments (formula-based) |

#### Other Model Types:
- **Orders**: `model/orders/` -- Market, Limit, StopMarket, StopLimit, etc.
- **Events**: `model/events/` -- AccountState, OrderInitialized, OrderFilled, PositionOpened, PositionChanged, etc.
- **Position**: `model/position.pyx` -- Position tracking with PnL
- **Greeks**: `model/greeks_data.py` -- `GreeksData` (delta, gamma, vega, theta, vol, pnl), `YieldCurveData`
- **Custom Data**: `model/custom.py` -- `@customdataclass` decorator for user-defined data types with Arrow serialization

---

### 5. DATA CATALOG / DATA STORE CONCEPT

The **`ParquetDataCatalog`** is the long-running data store concept:

- It is a **singleton** (via `_CombinedMeta(Singleton, ABCMeta)`)
- Can be instantiated from environment variable (`NAUTILUS_PATH`), URI, or explicit path
- Supports both **reading** (query with time range, instrument filter, SQL WHERE clauses) and **writing** (batch writes, streaming writes with rotation)
- The `DataEngine` can register catalogs and use them to:
  - Determine what data already exists (avoid re-downloading)
  - Write new data from live or backtest runs
- `StreamingConfig` configures live/backtest run streaming to catalog in Feather format
- `DataCatalogConfig` configures catalog connections for the `DataEngine`

---

### Summary: How Data Flows Through the System

```
External Sources (Exchanges, Feeds)
        |
        v
  DataClient(s)  <-- venue-specific adapters (Binance, IB, etc.)
        |
        v
  DataEngine     <-- central orchestrator
   |        |
   v        v
 Cache    MessageBus  -->  Strategies / Actors / Indicators
   |
   v (optional)
 Database Backend (Redis or PostgreSQL)
   
                ParquetDataCatalog
                  |          ^
                  v          |
              Parquet Files (local, S3, GCS, Azure)
              (read for backtest / write from live + backtest)
```

**Three storage layers:**

| Layer                                 | Type                         | Purpose                                   | Data Stored                                                                                                                 |
|---------------------------------------|------------------------------|-------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| **In-memory Cache**                   | Python dicts/deques (Cython) | Ultra-low-latency runtime access          | Everything: instruments, quotes, trades, bars, order books, orders, positions, accounts                                     |
| **Cache Database** (Redis/PostgreSQL) | External database            | Execution state persistence, recovery     | Currencies, instruments, accounts, orders, positions, actor/strategy state; Postgres also stores quotes/trades/bars/signals |
| **Parquet Data Catalog**              | File-based (local/cloud)     | Historical market data storage & querying | All market data types, instruments, events; optimized for time-series queries                                               |


## NautilusTrader Networking, Serving, and API Capabilities -- Full Analysis

### 1. NETWORKING LAYER (`crates/network/`)

There is **no `nautilus_trader/network/` Python directory**. The networking layer is implemented entirely in **Rust** at `/home/brian/dev/nautilus_trader/crates/network/`. It provides **client-side only** networking:

| Component               | Source                                   | Purpose                                                                                           |
|-------------------------|------------------------------------------|---------------------------------------------------------------------------------------------------|
| **HTTP Client**         | `crates/network/src/http/client.rs`      | Async HTTP client built on `reqwest` with rate limiting, timeouts, and proxy support              |
| **WebSocket Client**    | `crates/network/src/websocket/client.rs` | WebSocket client with auto-reconnection, exponential backoff, split read/write, heartbeat support |
| **TCP Socket Client**   | `crates/network/src/socket/client.rs`    | Raw TCP client with TLS, auto-reconnection, split read/write                                      |
| **FIX Protocol Parser** | `crates/network/src/socket/fix.rs`       | FIX message buffer parser for `8=FIX...10=xxx` framing                                            |
| **Rate Limiter**        | `crates/network/src/ratelimiter/`        | Generic Cell Rate Algorithm (GCRA) rate limiter with per-endpoint quotas                          |
| **Backoff**             | `crates/network/src/backoff.rs`          | Exponential backoff for reconnection strategies                                                   |
| **TLS Utilities**       | `crates/network/src/tls.rs`              | TLS configuration from certificate directories                                                    |

All three network components (HTTP, WebSocket, TCP) are exposed to Python via PyO3 bindings in `crates/network/src/python/`.

**Key finding: All networking components are CLIENTS (outbound connections only). There are no server/listener implementations.**

---

### 2. HTTP/REST SERVER -- DOES NOT EXIST

After thorough searching:
- **No built-in HTTP server, REST API, or web server** exists anywhere in nautilus_trader.
- No imports of `FastAPI`, `flask`, `aiohttp.web`, `Starlette`, `uvicorn`, or any HTTP server framework.
- All references to "REST API" in the codebase are about **consuming** external REST APIs (Binance, Bybit, OKX, etc.) -- not serving one.
- The HTTP client (`HttpClient` in Rust) is strictly outbound: `reqwest`-based with rate limiting.

---

### 3. WEBSOCKET SERVER -- DOES NOT EXIST

- **No built-in WebSocket server** exists in the codebase.
- The only WebSocket server references are in **test fixtures** (`tests/integration_tests/network/conftest.py` at line 75: `fixture_websocket_server`) used to test the WebSocket client.
- All adapter WebSocket code (Binance, dYdX, Polymarket, etc.) is purely client-side, connecting to exchange WebSocket servers.

---

### 4. MESSAGE BUS / PUB-SUB INFRASTRUCTURE -- EXTENSIVE

This is the heart of the system. The `MessageBus` is a sophisticated in-process pub/sub system:

**Core Implementation** (`/home/brian/dev/nautilus_trader/crates/common/src/msgbus/`):

- **`core.rs`**: The `MessageBus` struct with two routing mechanisms:
  - **Typed routing** (`publish_quote`, `subscribe_quotes`, etc.): Zero-cost dispatch for known market data types. Handlers receive `&T` directly with no runtime type checking. 10x faster than Any-based routing on hot paths.
  - **Any-based routing** (`publish_any`, `subscribe_any`): Flexible dispatch for custom types and Python interop. Handlers receive `&dyn Any`.
  
- **`api.rs`**: Public API with free-standing functions wrapping the thread-local bus. Typed publish functions for: `QuoteTick`, `TradeTick`, `Bar`, `OrderBookDeltas`, `OrderBookDepth10`, `OrderBook`, `MarkPriceUpdate`, `IndexPriceUpdate`, `FundingRateUpdate`, `GreeksData`, `AccountState`, `OrderEventAny`, `PositionEvent`, plus DeFi types.

- **`typed_router.rs`**: `TopicRouter<T>` implementing topic-based pub/sub with wildcard matching (`*` and `?` patterns).

- **`switchboard.rs`**: Pre-defined topic hierarchies like `data.quotes.{venue}.{instrument_id}`.

- **`database.rs`**: `MessageBusDatabaseAdapter` trait for persistent backing.

- **Thread-local design**: Each thread gets its own `MessageBus` instance via `thread_local!` storage, avoiding synchronization overhead.

**Redis-Backed External Streaming** (`/home/brian/dev/nautilus_trader/crates/infrastructure/src/redis/msgbus.rs`):

The `RedisMessageBusDatabase` enables **cross-process message distribution via Redis Streams**:

- **Publishing**: Messages from the in-process bus are serialized and written to Redis Streams via `XADD`. Supports buffered/pipelined writing with configurable intervals, per-topic streams, and auto-trimming via `XTRIM MINID`.
- **Streaming (consumption)**: A background task uses `XREAD` with blocking to listen to configured `external_streams` keys, deserialize messages, and re-publish them on the local in-process message bus.
- **Heartbeats**: Optional periodic heartbeat messages for health monitoring.
- **Configuration** (`MessageBusConfig`):
  - `database`: Redis connection config
  - `stream_per_topic`: Separate Redis streams per topic (default true)
  - `external_streams`: List of Redis stream keys to listen to from other processes
  - `types_filter`: Types to exclude from external publishing
  - `streams_prefix`: Custom prefix for stream keys
  - `autotrim_mins`: Automatic stream trimming lookback window
  - `buffer_interval_ms`: Batching interval for writes

**How cross-process works** (in `node.py` lines 305-336, 368-374):
1. Node A publishes data internally -> MessageBus serializes it -> writes to Redis Streams
2. Node B configured with `external_streams` pointing to Node A's stream keys -> `RedisMessageBusDatabase.stream()` reads via `XREAD` -> deserializes -> calls `publish_bus_message()` -> re-publishes on Node B's local bus

---

### 5. LIVE DATA ADAPTERS/PROVIDERS

**Architecture** (data flow for live trading):

```
Exchange API (REST + WebSocket)
       |
       v
LiveMarketDataClient (adapter-specific, e.g. BinanceDataClient)
  - _connect(): establishes WS connections, REST sessions
  - _subscribe_*(): subscribes to specific data feeds
  - _handle_data(): pushes data to DataEngine
       |
       v
LiveDataEngine (queue-based async processing)
       |
       v
MessageBus (in-process pub/sub)
       |
       v
Strategies / Actors (subscribers)
```

**Base classes** (`/home/brian/dev/nautilus_trader/nautilus_trader/live/data_client.py`):
- `LiveDataClient`: For non-market/custom data feeds
- `LiveMarketDataClient`: For market data with full subscription API supporting: instruments, order book deltas/depth/snapshots, quote ticks, trade ticks, mark prices, index prices, funding rates, bars, instrument status, instrument close

**Factory pattern** (`/home/brian/dev/nautilus_trader/nautilus_trader/live/factories.py`):
- `LiveDataClientFactory.create()` / `LiveExecClientFactory.create()` -- abstract factories
- Each adapter provides concrete implementations

**Available Adapters** (18 exchange/data source integrations):

| Adapter                  | Data Client | Exec Client | Protocol                                  |
|--------------------------|-------------|-------------|-------------------------------------------|
| Binance (Spot + Futures) | Yes         | Yes         | REST + WebSocket                          |
| Bybit                    | Yes         | Yes         | REST + WebSocket                          |
| OKX                      | Yes         | Yes         | REST + WebSocket                          |
| dYdX (v3)                | Yes         | Yes         | REST + WebSocket + **gRPC**               |
| dYdX v4                  | Yes         | Yes         | REST + WebSocket + **gRPC** (Rust-backed) |
| Kraken                   | Yes         | Yes         | REST + WebSocket                          |
| Coinbase Intx            | Yes         | Yes         | REST + WebSocket                          |
| Interactive Brokers      | Yes         | Yes         | TWS API (TCP socket)                      |
| Polymarket               | Yes         | Yes         | REST + WebSocket                          |
| Betfair                  | Yes         | Yes         | REST + Streaming API                      |
| Databento                | Yes         | No          | Databento client                          |
| Tardis                   | Yes         | No          | Tardis Machine API                        |
| Deribit                  | Yes         | Yes         | REST + WebSocket                          |
| BitMEX                   | Yes         | Yes         | REST + WebSocket                          |
| Hyperliquid              | Yes         | Yes         | REST + WebSocket                          |
| Architect AX             | Yes         | Yes         | REST + WebSocket                          |
| Sandbox                  | No          | Yes         | Simulated                                 |

---

### 6. gRPC / ZMQ / OTHER RPC PATTERNS

- **gRPC**: Used exclusively by the **dYdX adapters** for order submission via Cosmos SDK transactions. The v3 adapter (`nautilus_trader/adapters/dydx/grpc/account.py`) uses Python `grpc.aio` with protobuf. The v4 adapter uses Rust-backed gRPC clients (`nautilus_pyo3.DydxGrpcClient`).
- **ZeroMQ / nanomsg / nng**: **Not used anywhere** in the codebase.
- **FIX Protocol**: Basic FIX message parsing exists in the TCP socket client (`crates/network/src/socket/fix.rs`), but it is a client-side parser, not a FIX server.

---

### 7. CAN THE SYSTEM SERVE DATA TO EXTERNAL CONSUMERS?

**Not directly.** There is no built-in HTTP server, WebSocket server, or any outward-facing API endpoint. However, there is an **indirect mechanism via Redis Streams**:

**Redis Streams as the external interface:**
- When `MessageBusConfig.database` is configured with Redis, the message bus publishes all internal messages (minus filtered types) to Redis Streams.
- Any external process that can read Redis Streams (using `XREAD`) can consume this data.
- Multiple NautilusTrader nodes can share data via the `external_streams` configuration.
- The `stream_per_topic` option creates separate Redis streams per data topic (e.g., `stream:data.quotes.BINANCE.BTCUSDT`), making selective consumption easy.
- Stream processors can be added via `TradingNode.add_stream_processor(callback)`.

**To serve data to external consumers, you would need to:**
1. Build a custom bridge service that reads from Redis Streams and exposes the data via HTTP/WebSocket/gRPC, OR
2. Have external consumers read Redis Streams directly, OR
3. Write a custom NautilusTrader `Actor` or strategy that embeds an HTTP/WebSocket server (e.g., using `aiohttp` or `FastAPI` on the same event loop) and publishes data received from the message bus.

---

### Summary Table

| Capability                           | Status                       | Details                                                                                 |
|--------------------------------------|------------------------------|-----------------------------------------------------------------------------------------|
| **Built-in HTTP/REST server**        | **NO**                       | No server framework exists; HTTP is client-only                                         |
| **Built-in WebSocket server**        | **NO**                       | WebSocket is client-only (for connecting to exchanges)                                  |
| **MessageBus / Pub-Sub**             | **YES -- Extensive**         | High-performance in-process bus with typed + Any-based routing, wildcard topic matching |
| **Cross-process messaging**          | **YES -- via Redis Streams** | `RedisMessageBusDatabase` writes/reads Redis Streams for inter-node communication       |
| **Live data adapters**               | **YES -- 18 adapters**       | Factory pattern with async clients for all major exchanges                              |
| **gRPC**                             | **Limited**                  | Only for dYdX Cosmos SDK transactions                                                   |
| **ZMQ / nanomsg**                    | **NO**                       | Not present                                                                             |
| **Serve data to external consumers** | **NOT BUILT-IN**             | Must build a bridge from Redis Streams or embed a server in a custom Actor              |


# Nautilus Trader: Extensibility & Integration Points

## 1. DATA ADAPTER ARCHITECTURE

### Class Hierarchy (4 layers)

```
DataClient (Cython, data/client.pyx)          -- Base for generic/custom data
  |-- MarketDataClient (Cython, data/client.pyx)  -- Base for market data (quotes, trades, books)
       |-- LiveDataClient (Python, live/data_client.py)          -- Async live generic data
       |-- LiveMarketDataClient (Python, live/data_client.py)    -- Async live market data
            |-- BinanceSpotDataClient, BybitDataClient, etc.     -- Concrete adapters
```

- **`DataClient`** (Cython): handles generic/custom data subscriptions and requests. Publishes data via `self._msgbus.send(endpoint="DataEngine.process", msg=data)`.
- **`MarketDataClient`** (Cython): extends DataClient with typed methods for instruments, quotes, trades, order books, bars, funding rates, mark/index prices, instrument status/close.
- **`LiveDataClient`** (Python): adds `asyncio` event loop, task management, connect/disconnect lifecycle. Wraps all subscribe/unsubscribe/request calls into `self.create_task(self._subscribe_xxx(...))`.
- **`LiveMarketDataClient`** (Python): the full async live market data client with ~30 override points.

### Factory Pattern

Every adapter must provide a **`LiveDataClientFactory`** subclass:

```
File: /home/brian/dev/nautilus_trader/nautilus_trader/live/factories.py

class LiveDataClientFactory:
    @staticmethod
    def create(loop, name, config, msgbus, cache, clock) -> LiveDataClient:
        raise NotImplementedError
```

The factory is registered on the `TradingNode` and called by `TradingNodeBuilder` to instantiate clients.

### How to Write a Custom Data Adapter

The repository includes an **official template** at:
- `/home/brian/dev/nautilus_trader/nautilus_trader/adapters/_template/data.py` -- data client template
- `/home/brian/dev/nautilus_trader/nautilus_trader/adapters/_template/execution.py` -- execution client template
- `/home/brian/dev/nautilus_trader/nautilus_trader/adapters/_template/providers.py` -- instrument provider template

The template shows exactly which methods to implement:

| Component                                   | Required Methods                                 | Optional Methods                                                                                                                                                                           |
|---------------------------------------------|--------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **`TemplateLiveDataClient`** (generic)      | `_connect`, `_disconnect`                        | `_subscribe`, `_unsubscribe`, `_request`                                                                                                                                                   |
| **`TemplateLiveMarketDataClient`** (market) | `_connect`, `_disconnect`                        | 30+ methods: `_subscribe_instruments`, `_subscribe_order_book_deltas`, `_subscribe_quote_ticks`, `_subscribe_trade_ticks`, `_subscribe_bars`, `_request_instrument`, `_request_bars`, etc. |
| **`TemplateInstrumentProvider`**            | `load_all_async`, `load_ids_async`, `load_async` | --                                                                                                                                                                                         |

To register a custom adapter on a `TradingNode`:
```python
node.add_data_client_factory("MY_ADAPTER", MyLiveDataClientFactory)
node.build()
```

---

## 2. EXISTING ADAPTERS

Found in `/home/brian/dev/nautilus_trader/nautilus_trader/adapters/`:

| Adapter             | Directory              | Data Factory Class                        |
|---------------------|------------------------|-------------------------------------------|
| Architect AX        | `architect_ax/`        | `AxLiveDataClientFactory`                 |
| Betfair             | `betfair/`             | `BetfairLiveDataClientFactory`            |
| Binance             | `binance/`             | `BinanceLiveDataClientFactory`            |
| BitMEX              | `bitmex/`              | `BitmexLiveDataClientFactory`             |
| Bybit               | `bybit/`               | `BybitLiveDataClientFactory`              |
| Coinbase IntX       | `coinbase_intx/`       | `CoinbaseIntxLiveDataClientFactory`       |
| Databento           | `databento/`           | `DatabentoLiveDataClientFactory`          |
| Deribit             | `deribit/`             | `DeribitLiveDataClientFactory`            |
| dYdX                | `dydx/`                | `DYDXLiveDataClientFactory`               |
| dYdX v4             | `dydx_v4/`             | `DYDXv4LiveDataClientFactory`             |
| Hyperliquid         | `hyperliquid/`         | `HyperliquidLiveDataClientFactory`        |
| Interactive Brokers | `interactive_brokers/` | `InteractiveBrokersLiveDataClientFactory` |
| Kraken              | `kraken/`              | `KrakenLiveDataClientFactory`             |
| OKX                 | `okx/`                 | `OKXLiveDataClientFactory`                |
| Polymarket          | `polymarket/`          | `PolymarketLiveDataClientFactory`         |
| Sandbox             | `sandbox/`             | (execution-only simulated venue)          |
| Tardis              | `tardis/`              | `TardisLiveDataClientFactory`             |
| **Template**        | `_template/`           | (reference implementation)                |

**18 adapters** total (17 real + 1 template). Each adapter follows a consistent structure:
- `config.py` -- adapter-specific config (extends `LiveDataClientConfig`)
- `factories.py` -- factory (extends `LiveDataClientFactory`)
- `data.py` or `data/` -- the data client implementation
- `execution.py` -- the execution client
- `providers.py` -- instrument provider
- Often: `http/`, `websocket/`, `common/`, `schemas/` sub-modules

---

## 3. DATAFRAME SUPPORT (Pandas / PyArrow / Polars)

### PyArrow (Primary Serialization Layer)

Arrow is the **core serialization format** for persistence and catalog operations:

- **`/home/brian/dev/nautilus_trader/nautilus_trader/serialization/arrow/serializer.py`**: Central `ArrowSerializer` class with `register_arrow()` function for registering custom types
- **`/home/brian/dev/nautilus_trader/nautilus_trader/serialization/arrow/schema.py`**: Arrow schemas for all Nautilus types
- **`/home/brian/dev/nautilus_trader/nautilus_trader/serialization/arrow/implementations/`**: Custom Arrow encoders/decoders for instruments, orders, positions, account state, etc.

The `register_arrow()` function is the extension point:
```python
register_arrow(
    data_cls=MyCustomType,
    schema=pa.schema(...),
    encoder=my_encoder_function,  # Data -> pa.RecordBatch
    decoder=my_decoder_function,  # pa.Table -> list[Data]
)
```

High-performance Rust-native types (OrderBookDelta, QuoteTick, TradeTick, Bar, etc.) serialize directly to Arrow record batches via `nautilus_pyo3` C bindings.

### Pandas (Deep Integration)

- **Data Wranglers** (`/home/brian/dev/nautilus_trader/nautilus_trader/persistence/wranglers_v2.py`): Every wrangler has a `from_pandas(df)` method that converts a `pd.DataFrame` into Nautilus objects (OrderBookDelta, QuoteTick, TradeTick, OrderBookDepth10, Bar).
- **Data Loaders** (`/home/brian/dev/nautilus_trader/nautilus_trader/persistence/loaders.py`): CSV/Parquet loaders that return `pd.DataFrame`.
- **Trader Reports** (`/home/brian/dev/nautilus_trader/nautilus_trader/trading/trader.py`): `generate_orders_report()`, `generate_order_fills_report()`, `generate_fills_report()`, `generate_positions_report()` all return `pd.DataFrame`.
- **Config system** supports `pd.DataFrame` as a config value via custom encoding/decoding hooks.

### Parquet Data Catalog

**`/home/brian/dev/nautilus_trader/nautilus_trader/persistence/catalog/parquet.py`** -- `ParquetDataCatalog` class:
- Uses `pyarrow.dataset` and `pyarrow.parquet` for reading/writing
- Supports `fsspec` filesystems (local, S3, Azure Blob, HTTP/WebDAV, memory)
- Has a Rust backend (`DataBackendSession`) for high-performance reads
- Full query support with time range filtering and PyArrow dataset expressions

### Polars

No direct Polars integration was found in the codebase. The DataFrame layer is exclusively pandas + pyarrow.

---

## 4. DATA-ONLY NODE (No Trading)

**Yes, this is fully supported and is a first-class pattern.** The proof is in the example:

**`/home/brian/dev/nautilus_trader/examples/live/binance/binance_data_tester.py`**:
```python
# Configure the trading node (data only, no execution)
config_node = TradingNodeConfig(
    data_clients={
        BINANCE: BinanceDataClientConfig(
            api_key=None,       # No API key needed for public data
            api_secret=None,
        ),
    },
    # No exec_clients - data only
)
```

How it works:
- `TradingNodeConfig.data_clients` and `exec_clients` are both `dict` with default `{}`
- You can configure `data_clients` only, omitting `exec_clients` entirely
- The `TradingNodeBuilder` will log a warning ("No exec_clients configuration found") but proceed normally
- You attach an **Actor** (not a Strategy) to consume data -- Actors cannot trade, they only observe
- The `DataTester` actor subscribes to instruments, order books, quotes, trades, bars, etc.
- The `StreamingConfig` can persist all received data to a Parquet catalog

Additionally, the **message bus external streaming** system (`MessageBusConfig.external_streams`) allows one node to publish data to Redis streams and another node to subscribe to those streams -- enabling a publisher/subscriber data distribution pattern.

---

## 5. CONFIGURATION / EXTENSION ARCHITECTURE

### Configuration System

All configuration uses **`msgspec.Struct`** (frozen, kw_only) via the base class:

**`NautilusConfig`** (`/home/brian/dev/nautilus_trader/nautilus_trader/common/config.py`):
- Immutable frozen structs (guaranteed thread-safe)
- JSON serialization/deserialization with custom encoding hooks
- JSON Schema generation via `json_schema()`
- Hash-based identity via `id` property
- Hierarchical: `NautilusConfig` -> `NautilusKernelConfig` -> `TradingNodeConfig`

The full config hierarchy:

```
NautilusConfig (base)
  |-- NautilusKernelConfig (core kernel: engines, cache, logging, streaming, strategies, actors)
  |    |-- TradingNodeConfig (live: adds data_clients, exec_clients, timeouts)
  |    |-- BacktestEngineConfig
  |-- LiveDataClientConfig (adapter data config base)
  |    |-- BinanceDataClientConfig, BybitDataClientConfig, etc.
  |-- LiveExecClientConfig (adapter execution config base)
  |-- ActorConfig, StrategyConfig, ControllerConfig
  |-- DatabaseConfig, MessageBusConfig, LoggingConfig
  |-- CacheConfig, StreamingConfig, DataCatalogConfig
  |-- RiskEngineConfig, DataEngineConfig, ExecEngineConfig
```

### Extension Points

| Extension Point                    | Mechanism                                                                               | Registration                                                                             |
|------------------------------------|-----------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| **Custom Data Adapter**            | Subclass `LiveDataClient` or `LiveMarketDataClient` + `LiveDataClientFactory`           | `node.add_data_client_factory(name, factory)`                                            |
| **Custom Execution Adapter**       | Subclass `LiveExecutionClient` + `LiveExecClientFactory`                                | `node.add_exec_client_factory(name, factory)`                                            |
| **Custom Data Types**              | Use `@customdataclass` decorator                                                        | Auto-registers Arrow + msgpack serialization                                             |
| **Custom Arrow Serialization**     | `register_arrow(data_cls, schema, encoder, decoder)`                                    | Module-level registration                                                                |
| **Custom Msgpack Serialization**   | `register_serializable_type(cls, to_dict, from_dict)`                                   | Module-level registration                                                                |
| **Custom Config Encoding**         | `register_config_encoding(type_, encoder)` / `register_config_decoding(type_, decoder)` | Module-level registration                                                                |
| **Custom Actors**                  | Subclass `Actor` + `ActorConfig`                                                        | Via `ImportableActorConfig` in kernel config, or `node.trader.add_actor()`               |
| **Custom Strategies**              | Subclass `Strategy` + `StrategyConfig`                                                  | Via `ImportableStrategyConfig` in kernel config, or `node.trader.add_strategy()`         |
| **Custom Execution Algorithms**    | Subclass `ExecAlgorithm` + `ExecAlgorithmConfig`                                        | Via `ImportableExecAlgorithmConfig`                                                      |
| **Controller (meta-orchestrator)** | Subclass `Controller` (extends `Actor`)                                                 | Via `ImportableControllerConfig`; can create/start/stop actors and strategies at runtime |
| **Signal Data Types**              | `generate_signal_class(name, value_type)`                                               | Dynamic class generation with auto-registration                                          |
| **Custom Instrument Provider**     | Subclass `InstrumentProvider`                                                           | Part of adapter factory                                                                  |

### Importable Config System (Dynamic Plugin Loading)

The `ImportableConfig` class enables full dynamic loading:

```python
class ImportableConfig(NautilusConfig):
    path: str         # "my_package.module:MyDataClientConfig"
    config: dict      # raw config dict
    factory: ImportableFactoryConfig | None  # "my_package.module:MyDataClientFactory"
```

This means adapters can be loaded from **any installed Python package** by dotted path -- a de facto plugin system without requiring a formal plugin registry. The `resolve_path()` function uses `importlib.import_module()` to load classes at runtime.

Similarly, `ImportableActorConfig`, `ImportableStrategyConfig`, `ImportableExecAlgorithmConfig`, and `ImportableControllerConfig` all follow this pattern.

### Message Bus + Redis Streaming

The `MessageBusConfig` supports:
- **Redis-backed persistence** of all messages
- **External stream publishing** -- any data/event type can be published to Redis streams
- **External stream subscription** (`external_streams`) -- a node can listen to streams published by another node
- **Heartbeat** for node health monitoring
- **Type filtering** to control what gets published
- **Stream-per-topic** or single-stream modes

This enables **multi-node architectures** where a data collector node publishes to Redis and trading nodes consume from it.

---

## Summary

| Question                              | Answer                                                                                                                                                                                                                                                                                                                          |
|---------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **How to write custom data adapters** | Subclass `LiveMarketDataClient` (or `LiveDataClient` for non-market data), implement `_connect`/`_disconnect` + desired subscribe/request methods. Create a `LiveDataClientFactory` subclass. Register on `TradingNode` via `add_data_client_factory()`. Official template at `adapters/_template/`.                            |
| **DataFrame support**                 | **Pandas**: deep integration (wranglers, loaders, reports). **PyArrow**: primary serialization layer for persistence/catalog, extensible via `register_arrow()`. **Polars**: not integrated.                                                                                                                                    |
| **Data-only node**                    | **Yes**, fully supported. Configure `TradingNodeConfig` with only `data_clients` (no `exec_clients`). Use Actors (not Strategies) to consume data. Streaming to Parquet catalog supported. See `examples/live/binance/binance_data_tester.py`.                                                                                  |
| **Configuration architecture**        | `msgspec.Struct`-based frozen config hierarchy. All configs JSON-serializable. Dynamic loading via `ImportableConfig` with dotted-path resolution. Custom encoding/decoding hooks. JSON Schema generation.                                                                                                                      |
| **Plugin system**                     | No formal plugin registry, but an **importable config** pattern (`path: "my.module:MyClass"`) enables loading any class from any installed package. Combined with `register_arrow()`, `register_serializable_type()`, and `register_config_encoding()` for type registration, this provides a complete extensibility framework. |
</task_result>
```
