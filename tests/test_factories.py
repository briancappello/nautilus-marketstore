"""Tests for nautilus_marketstore.factories module."""

from __future__ import annotations

import asyncio

import pytest

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.model.identifiers import ClientId, TraderId, Venue

from nautilus_marketstore.config import MarketStoreDataClientConfig
from nautilus_marketstore.data import MarketStoreDataClient
from nautilus_marketstore.factories import (
    MarketStoreLiveDataClientFactory,
    get_marketstore_instrument_provider,
)
from nautilus_marketstore.providers import MarketStoreInstrumentProvider


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def clock():
    return LiveClock()


@pytest.fixture
def msgbus(clock):
    return MessageBus(trader_id=TraderId("TESTER-001"), clock=clock)


@pytest.fixture
def cache():
    return Cache(database=None)


class TestGetMarketstoreInstrumentProvider:
    def test_returns_provider(self):
        provider = get_marketstore_instrument_provider(0)
        assert isinstance(provider, MarketStoreInstrumentProvider)

    def test_cached_returns_same_instance(self):
        # Clear the cache first
        get_marketstore_instrument_provider.cache_clear()
        p1 = get_marketstore_instrument_provider(42)
        p2 = get_marketstore_instrument_provider(42)
        assert p1 is p2

    def test_different_hash_returns_same_due_to_maxsize_1(self):
        """With lru_cache(1), only the most recent call is cached."""
        get_marketstore_instrument_provider.cache_clear()
        p1 = get_marketstore_instrument_provider(1)
        p2 = get_marketstore_instrument_provider(2)
        # p2 evicts p1 from cache, so they are different objects
        assert p1 is not p2


class TestMarketStoreLiveDataClientFactory:
    def test_create_returns_data_client(self, event_loop, msgbus, cache, clock):
        config = MarketStoreDataClientConfig()
        client = MarketStoreLiveDataClientFactory.create(
            loop=event_loop,
            name="MARKETSTORE",
            config=config,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        assert isinstance(client, MarketStoreDataClient)

    def test_create_with_custom_name(self, event_loop, msgbus, cache, clock):
        config = MarketStoreDataClientConfig()
        client = MarketStoreLiveDataClientFactory.create(
            loop=event_loop,
            name="CUSTOM_MS",
            config=config,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        assert client.id == ClientId("CUSTOM_MS")

    def test_create_with_custom_venue(self, event_loop, msgbus, cache, clock):
        config = MarketStoreDataClientConfig(venue="BINANCE")
        client = MarketStoreLiveDataClientFactory.create(
            loop=event_loop,
            name="MS",
            config=config,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        assert client.venue == Venue("BINANCE")
