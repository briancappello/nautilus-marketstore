"""
Factory for creating MarketStore live data clients.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.live.factories import LiveDataClientFactory

from nautilus_marketstore.config import MarketStoreDataClientConfig
from nautilus_marketstore.data import MarketStoreDataClient
from nautilus_marketstore.providers import MarketStoreInstrumentProvider


@lru_cache(1)
def get_marketstore_instrument_provider(
    config_hash: int,
) -> MarketStoreInstrumentProvider:
    """
    Get or create a cached MarketStoreInstrumentProvider singleton.

    Parameters
    ----------
    config_hash : int
        Hash of the instrument provider config (for cache keying).

    Returns
    -------
    MarketStoreInstrumentProvider

    """
    return MarketStoreInstrumentProvider()


class MarketStoreLiveDataClientFactory(LiveDataClientFactory):
    """
    Factory for creating ``MarketStoreDataClient`` instances.

    This factory is registered on a ``TradingNode`` via::

        node.add_data_client_factory("MARKETSTORE", MarketStoreLiveDataClientFactory)

    """

    @staticmethod
    def create(  # type: ignore[override]
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: MarketStoreDataClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> MarketStoreDataClient:
        """
        Create a new MarketStore data client.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop for the client.
        name : str
            The client name/ID.
        config : MarketStoreDataClientConfig
            The configuration.
        msgbus : MessageBus
            The message bus.
        cache : Cache
            The cache.
        clock : LiveClock
            The clock.

        Returns
        -------
        MarketStoreDataClient

        """
        provider = get_marketstore_instrument_provider(
            config_hash=hash(config.instrument_provider) if config.instrument_provider else 0,
        )

        return MarketStoreDataClient(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            name=name,
        )
