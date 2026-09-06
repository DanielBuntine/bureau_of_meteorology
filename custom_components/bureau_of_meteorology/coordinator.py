"""Data update coordinator for the Bureau of Meteorology integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .PyBoM.collector import BomApiError, BomData, BomLocationError, Collector

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
DEBOUNCE_TIME = 60  # seconds

type BomConfigEntry = ConfigEntry[BomDataUpdateCoordinator]


class BomDataUpdateCoordinator(DataUpdateCoordinator[BomData]):
    """Coordinate a single refresh of every BOM resource for one location."""

    config_entry: BomConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: BomConfigEntry,
        collector: Collector,
    ) -> None:
        """Initialise the data update coordinator."""
        self.collector = collector
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=DEBOUNCE_TIME, immediate=True
            ),
        )

    async def _async_update_data(self) -> BomData:
        """Fetch the latest data from the BOM API."""
        try:
            return await self.collector.async_update()
        except BomLocationError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="bad_location",
            ) from err
        except BomApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
