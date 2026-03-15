"""Tests for nautilus_marketstore.constants module."""

from nautilus_trader.model.identifiers import ClientId

from nautilus_marketstore.constants import MARKETSTORE, MARKETSTORE_CLIENT_ID


class TestConstants:
    def test_marketstore_string(self):
        assert MARKETSTORE == "MARKETSTORE"

    def test_marketstore_client_id_type(self):
        assert isinstance(MARKETSTORE_CLIENT_ID, ClientId)

    def test_marketstore_client_id_value(self):
        assert MARKETSTORE_CLIENT_ID.value == "MARKETSTORE"
