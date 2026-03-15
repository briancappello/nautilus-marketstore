"""Tests for nautilus_marketstore.providers module."""

from __future__ import annotations

import pytest
import pytest_asyncio

from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from nautilus_marketstore.config import MarketStoreInstrumentProviderConfig
from nautilus_marketstore.providers import MarketStoreInstrumentProvider


@pytest.fixture
def provider():
    return MarketStoreInstrumentProvider()


@pytest.fixture
def provider_with_config():
    config = MarketStoreInstrumentProviderConfig(load_all=True)
    return MarketStoreInstrumentProvider(config=config)


@pytest.fixture
def sample_instrument():
    return TestInstrumentProvider.ethusdt_binance()


class TestMarketStoreInstrumentProvider:
    def test_inherits_instrument_provider(self):
        assert issubclass(MarketStoreInstrumentProvider, InstrumentProvider)

    def test_create_without_config(self, provider):
        assert provider.count == 0

    def test_create_with_config(self, provider_with_config):
        assert provider_with_config.count == 0

    def test_add_instrument(self, provider, sample_instrument):
        provider.add(sample_instrument)
        assert provider.count == 1

    def test_find_instrument(self, provider, sample_instrument):
        provider.add(sample_instrument)
        found = provider.find(sample_instrument.id)
        assert found == sample_instrument

    def test_find_missing_returns_none(self, provider):
        missing_id = InstrumentId.from_str("UNKNOWN.EXCHANGE")
        result = provider.find(missing_id)
        assert result is None

    def test_list_all(self, provider, sample_instrument):
        provider.add(sample_instrument)
        all_instruments = provider.list_all()
        assert len(all_instruments) == 1
        assert sample_instrument in all_instruments

    def test_list_all_empty(self, provider):
        assert provider.list_all() == []

    def test_add_bulk(self, provider):
        instr1 = TestInstrumentProvider.ethusdt_binance()
        instr2 = TestInstrumentProvider.btcusdt_binance()
        provider.add_bulk([instr1, instr2])
        assert provider.count == 2

    @pytest.mark.asyncio
    async def test_load_all_async(self, provider, sample_instrument):
        provider.add(sample_instrument)
        await provider.load_all_async()
        # Should be a no-op, instruments already in the store
        assert provider.count == 1

    @pytest.mark.asyncio
    async def test_load_ids_async_existing(self, provider, sample_instrument):
        provider.add(sample_instrument)
        await provider.load_ids_async([sample_instrument.id])
        assert provider.count == 1

    @pytest.mark.asyncio
    async def test_load_ids_async_missing_logs_warning(self, provider, caplog):
        missing_id = InstrumentId.from_str("MISSING.EXCHANGE")
        import logging

        with caplog.at_level(logging.WARNING):
            await provider.load_ids_async([missing_id])
        assert "not found" in caplog.text

    @pytest.mark.asyncio
    async def test_load_async(self, provider, sample_instrument):
        provider.add(sample_instrument)
        await provider.load_async(sample_instrument.id)
        assert provider.count == 1

    @pytest.mark.asyncio
    async def test_initialize(self, provider, sample_instrument):
        provider.add(sample_instrument)
        await provider.initialize()
        assert provider.count == 1
