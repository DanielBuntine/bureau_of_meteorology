"""Fixtures for the Bureau of Meteorology tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bureau_of_meteorology.const import (
    CONF_FORECASTS_BASENAME,
    CONF_FORECASTS_CREATE,
    CONF_FORECASTS_DAYS,
    CONF_FORECASTS_MONITORED,
    CONF_OBSERVATIONS_BASENAME,
    CONF_OBSERVATIONS_CREATE,
    CONF_OBSERVATIONS_MONITORED,
    CONF_WARNINGS_BASENAME,
    CONF_WARNINGS_CREATE,
    CONF_WEATHER_NAME,
    DOMAIN,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"

GEOHASH = "r1r0fsn"
GEOHASH6 = GEOHASH[:6]

BASE = "https://api.weather.bom.gov.au/v1/locations"


def load_fixture(name: str) -> dict[str, Any]:
    """Return a recorded BOM API response."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    return


@pytest.fixture
def api_responses() -> dict[str, dict[str, Any]]:
    """Return the recorded responses keyed by the URL the collector requests."""
    return {
        f"{BASE}": load_fixture("search"),
        f"{BASE}/{GEOHASH}": load_fixture("location"),
        f"{BASE}/{GEOHASH6}/observations": load_fixture("observations"),
        f"{BASE}/{GEOHASH6}/forecasts/daily": load_fixture("forecasts_daily"),
        f"{BASE}/{GEOHASH6}/forecasts/hourly": load_fixture("forecasts_hourly"),
        f"{BASE}/{GEOHASH6}/warnings": load_fixture("warnings"),
    }


@pytest.fixture
def mock_api(api_responses):
    """Patch the collector's HTTP layer with the recorded responses."""

    async def _request(self, url: str, params: dict[str, str] | None = None):
        if url not in api_responses:
            raise AssertionError(f"Unexpected request to {url}")
        response = api_responses[url]
        # A test can register an exception to simulate an API error.
        if isinstance(response, Exception):
            raise response
        return response

    with patch(
        "custom_components.bureau_of_meteorology.PyBoM.collector.Collector._request",
        _request,
    ):
        yield api_responses


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a fully configured entry covering every entity type."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=GEOHASH,
        title="Melbourne",
        data={
            CONF_LATITUDE: -37.8136,
            CONF_LONGITUDE: 144.9631,
            CONF_WEATHER_NAME: "Melbourne",
            CONF_OBSERVATIONS_CREATE: True,
            CONF_OBSERVATIONS_BASENAME: "Melbourne",
            CONF_OBSERVATIONS_MONITORED: ["temp", "humidity", "dew_point"],
            CONF_FORECASTS_CREATE: True,
            CONF_FORECASTS_BASENAME: "Melbourne",
            CONF_FORECASTS_DAYS: 2,
            CONF_FORECASTS_MONITORED: ["temp_max", "short_text", "now_now_label"],
            CONF_WARNINGS_CREATE: True,
            CONF_WARNINGS_BASENAME: "Melbourne",
        },
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration and return its config entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
