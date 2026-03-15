from __future__ import annotations

from nautilus_trader.common.config import InstrumentProviderConfig
from nautilus_trader.live.config import LiveDataClientConfig


class MarketStoreInstrumentProviderConfig(InstrumentProviderConfig, frozen=True):
    """
    Configuration for the MarketStore instrument provider.

    Instruments cannot be auto-discovered from MarketStore (it stores raw
    column data, not instrument definitions). Instead, instruments are defined
    explicitly in this config and registered with the provider.
    """

    load_all: bool = True


class MarketStoreDataClientConfig(LiveDataClientConfig, frozen=True):
    """
    Configuration for the MarketStore live data client.

    Parameters
    ----------
    endpoint_rpc : str
        The MarketStore RPC endpoint (e.g., "http://localhost:5993/rpc").
    endpoint_ws : str
        The MarketStore WebSocket streaming endpoint (e.g., "ws://localhost:5993/ws").
    use_grpc : bool
        If True, use gRPC transport instead of msgpack-rpc for queries.
    venue : str
        The venue name to associate with data from this MarketStore instance.
        Becomes part of the InstrumentId (e.g., "BTCUSDT.{venue}").
    stream_patterns : list[str] | None
        WebSocket stream subscription patterns (e.g., ["*/*/*"]).
        If None, subscriptions are managed per-instrument dynamically.
    price_precision : int
        Default decimal precision for prices.
    size_precision : int
        Default decimal precision for sizes/quantities.
    reconnect_delay_secs : float
        Delay in seconds before attempting to reconnect the WebSocket.
    """

    endpoint_rpc: str = "http://localhost:5993/rpc"
    endpoint_ws: str = "ws://localhost:5993/ws"
    use_grpc: bool = False
    venue: str = "MARKETSTORE"
    stream_patterns: list[str] | None = None
    price_precision: int = 8
    size_precision: int = 8
    reconnect_delay_secs: float = 3.0
