"""
MarketStore instrument provider.

MarketStore does not store instrument definitions -- it only stores
time-series column data. Instruments must be provided explicitly via
configuration. This provider accepts pre-built Instrument objects and
registers them for use by the data client and trading node.
"""

from __future__ import annotations

import logging

from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument

from nautilus_marketstore.config import MarketStoreInstrumentProviderConfig


logger = logging.getLogger(__name__)


class MarketStoreInstrumentProvider(InstrumentProvider):
    """
    Instrument provider for MarketStore.

    Since MarketStore has no concept of instrument definitions, instruments
    must be added externally before the provider is initialized. Use
    ``add()`` or ``add_bulk()`` to register instruments, then the provider's
    ``initialize()`` will make them available to the data client.

    Parameters
    ----------
    config : MarketStoreInstrumentProviderConfig, optional
        The provider configuration.

    """

    def __init__(
        self,
        config: MarketStoreInstrumentProviderConfig | None = None,
    ) -> None:
        super().__init__(config=config)

    async def load_all_async(
        self,
        filters: dict | None = None,
    ) -> None:
        """
        Load all instruments.

        Since instruments are pre-registered via ``add()`` / ``add_bulk()``,
        this is a no-op. The instruments are already in ``self._instruments``.
        """
        count = len(self._instruments)
        logger.info("MarketStoreInstrumentProvider: %d instruments loaded", count)

    async def load_ids_async(
        self,
        instrument_ids: list[InstrumentId],
        filters: dict | None = None,
    ) -> None:
        """
        Load instruments by IDs.

        Filters the already-registered instruments to only the requested IDs.
        Logs a warning for any IDs not found.
        """
        for iid in instrument_ids:
            if iid not in self._instruments:
                logger.warning(
                    "MarketStoreInstrumentProvider: instrument %s not found "
                    "(must be added via add() before initialization)",
                    iid,
                )

    async def load_async(
        self,
        instrument_id: InstrumentId,
        filters: dict | None = None,
    ) -> None:
        """Load a single instrument by ID."""
        await self.load_ids_async([instrument_id], filters)
