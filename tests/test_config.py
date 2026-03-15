"""Tests for nautilus_marketstore.config module."""

from __future__ import annotations

import pytest

from nautilus_trader.common.config import InstrumentProviderConfig
from nautilus_trader.live.config import LiveDataClientConfig

from nautilus_marketstore.config import (
    MarketStoreDataClientConfig,
    MarketStoreInstrumentProviderConfig,
)


class TestMarketStoreInstrumentProviderConfig:
    def test_inherits_instrument_provider_config(self):
        assert issubclass(MarketStoreInstrumentProviderConfig, InstrumentProviderConfig)

    def test_default_values(self):
        config = MarketStoreInstrumentProviderConfig()
        assert config.load_all is True
        assert config.load_ids is None
        assert config.filters is None
        assert config.log_warnings is True

    def test_custom_values(self):
        config = MarketStoreInstrumentProviderConfig(
            load_all=False,
            log_warnings=False,
        )
        assert config.load_all is False
        assert config.log_warnings is False

    def test_frozen(self):
        config = MarketStoreInstrumentProviderConfig()
        with pytest.raises(AttributeError):
            config.load_all = False


class TestMarketStoreDataClientConfig:
    def test_inherits_live_data_client_config(self):
        assert issubclass(MarketStoreDataClientConfig, LiveDataClientConfig)

    def test_default_values(self):
        config = MarketStoreDataClientConfig()
        assert config.endpoint_rpc == "http://localhost:5993/rpc"
        assert config.endpoint_ws == "ws://localhost:5993/ws"
        assert config.use_grpc is False
        assert config.venue == "MARKETSTORE"
        assert config.stream_patterns is None
        assert config.price_precision == 8
        assert config.size_precision == 8
        assert config.reconnect_delay_secs == 3.0

    def test_custom_values(self):
        config = MarketStoreDataClientConfig(
            endpoint_rpc="http://example.com:5993/rpc",
            endpoint_ws="ws://example.com:5993/ws",
            use_grpc=True,
            venue="BINANCE",
            stream_patterns=["*/*/*"],
            price_precision=2,
            size_precision=4,
            reconnect_delay_secs=5.0,
        )
        assert config.endpoint_rpc == "http://example.com:5993/rpc"
        assert config.endpoint_ws == "ws://example.com:5993/ws"
        assert config.use_grpc is True
        assert config.venue == "BINANCE"
        assert config.stream_patterns == ["*/*/*"]
        assert config.price_precision == 2
        assert config.size_precision == 4
        assert config.reconnect_delay_secs == 5.0

    def test_frozen(self):
        config = MarketStoreDataClientConfig()
        with pytest.raises(AttributeError):
            config.venue = "OTHER"

    def test_has_instrument_provider_field(self):
        """LiveDataClientConfig provides an instrument_provider field."""
        config = MarketStoreDataClientConfig()
        assert hasattr(config, "instrument_provider")
