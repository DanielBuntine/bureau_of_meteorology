"""Diagnostics support for the Bureau of Meteorology integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .coordinator import BomConfigEntry

TO_REDACT = {CONF_LATITUDE, CONF_LONGITUDE, "latitude", "longitude", "geohash"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BomConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(
            {
                "locations": data.locations,
                "observations": data.observations,
                "daily_forecasts": data.daily_forecasts,
                "hourly_forecasts": data.hourly_forecasts,
                "warnings": data.warnings,
            },
            TO_REDACT,
        ),
    }
