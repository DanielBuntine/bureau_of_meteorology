"""Base entity for the Bureau of Meteorology integration."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MODEL_NAME, SHORT_ATTRIBUTION
from .coordinator import BomDataUpdateCoordinator


class BomEntity(CoordinatorEntity[BomDataUpdateCoordinator]):
    """Common behaviour for every BOM entity."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self, coordinator: BomDataUpdateCoordinator, location_name: str
    ) -> None:
        """Initialise the entity and its device."""
        super().__init__(coordinator)
        self.collector = coordinator.collector
        self.location_name = location_name
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, location_name)},
            manufacturer=SHORT_ATTRIBUTION,
            model=MODEL_NAME,
            name=location_name,
        )

    @property
    def tzinfo(self) -> ZoneInfo:
        """Return the local timezone reported by the BOM for this location."""
        return ZoneInfo(self.coordinator.data.timezone)
