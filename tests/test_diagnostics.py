"""Tests for diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.bureau_of_meteorology.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redacts_location(
    hass: HomeAssistant, setup_integration
) -> None:
    """Coordinates and the geohash are redacted from diagnostics output."""
    result = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert result["last_update_success"] is True
    assert result["entry"]["data"]["latitude"] == "**REDACTED**"
    assert result["entry"]["data"]["longitude"] == "**REDACTED**"
    assert result["data"]["locations"]["data"]["geohash"] == "**REDACTED**"
    assert result["data"]["observations"]["data"]["temp"] == 13.6
