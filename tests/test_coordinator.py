"""Tests for the collector and the data update coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import aiohttp
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.bureau_of_meteorology.PyBoM.collector import (
    BomApiError,
    BomLocationError,
    Collector,
)
from custom_components.bureau_of_meteorology.PyBoM.helpers import (
    calculate_dew_point,
    geohash_encode,
)

from .conftest import GEOHASH, GEOHASH6


def test_geohash_precision() -> None:
    """The helper defaults to the seven characters the location endpoint wants."""
    assert len(geohash_encode(-37.8136, 144.9631)) == 7
    assert geohash_encode(-37.8136, 144.9631, 6) == "r1r0fs"


def test_dew_point() -> None:
    """The Tetens approximation matches known values."""
    assert calculate_dew_point(20.0, 50.0) == 9.3
    assert calculate_dew_point(13.6, 70.0) == 8.2


async def test_subresources_use_six_character_geohash(
    hass: HomeAssistant, setup_integration
) -> None:
    """Sub-resources are requested with six characters; seven returns HTTP 400."""
    collector = setup_integration.runtime_data.collector

    assert collector.geohash == GEOHASH
    assert len(collector.geohash) == 7
    assert collector.geohash6 == GEOHASH6
    assert len(collector.geohash6) == 6


async def test_coordinator_data_is_populated(
    hass: HomeAssistant, setup_integration
) -> None:
    """The coordinator holds real data rather than None."""
    data = setup_integration.runtime_data.data

    assert data is not None
    assert data.timezone == "Australia/Melbourne"
    assert data.observation["temp"] == 13.6
    assert len(data.daily) == 9
    assert len(data.hourly) == 6


async def test_entities_go_unavailable_on_update_failure(
    hass: HomeAssistant, setup_integration
) -> None:
    """A failed refresh marks entities unavailable instead of raising."""
    with patch(
        "custom_components.bureau_of_meteorology.PyBoM.collector.Collector."
        "async_update",
        side_effect=BomApiError("boom"),
    ):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10))
        await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.melbourne_current_temperature").state
        == STATE_UNAVAILABLE
    )


async def test_fetch_retries_then_uses_cache() -> None:
    """A transient failure falls back to the last good response."""
    collector = Collector(None, -37.8136, 144.9631)
    collector.geohash = GEOHASH
    collector._cache["observations"] = ({"data": {"temp": 1}}, 0.0)

    with (
        patch.object(
            Collector, "_request", AsyncMock(side_effect=aiohttp.ClientError())
        ),
        patch(
            "custom_components.bureau_of_meteorology.PyBoM.collector.asyncio.sleep",
            AsyncMock(),
        ),
        patch(
            "custom_components.bureau_of_meteorology.PyBoM.collector.time.monotonic",
            return_value=10.0,
        ),
    ):
        result = await collector._fetch("https://example.invalid", "observations")

    assert result == {"data": {"temp": 1}}


async def test_stale_cache_is_not_served() -> None:
    """Cached data older than MAX_CACHE_AGE is discarded rather than served."""
    collector = Collector(None, -37.8136, 144.9631)
    collector._cache["observations"] = ({"data": {"temp": 1}}, 0.0)

    with (
        patch.object(
            Collector, "_request", AsyncMock(side_effect=aiohttp.ClientError())
        ),
        patch(
            "custom_components.bureau_of_meteorology.PyBoM.collector.asyncio.sleep",
            AsyncMock(),
        ),
        patch(
            "custom_components.bureau_of_meteorology.PyBoM.collector.time.monotonic",
            return_value=999_999.0,
        ),
        pytest.raises(BomApiError),
    ):
        await collector._fetch("https://example.invalid", "observations")


async def test_client_error_is_not_retried() -> None:
    """A 4xx is a bad request, so it fails fast instead of retrying."""
    request = AsyncMock(side_effect=BomApiError("bad", status=400))

    collector = Collector(None, -37.8136, 144.9631)
    with patch.object(Collector, "_request", request), pytest.raises(BomApiError):
        await collector._fetch("https://example.invalid", "observations")

    assert request.await_count == 1


async def test_unknown_location_raises_location_error(mock_api, api_responses) -> None:
    """A location the BOM does not cover raises BomLocationError."""
    api_responses["https://api.weather.bom.gov.au/v1/locations"] = {"data": []}
    # With no search hit the collector falls back to a locally encoded geohash,
    # which the BOM rejects for a location it does not cover.
    api_responses["https://api.weather.bom.gov.au/v1/locations/gcpuvr2"] = BomApiError(
        "not found", status=404
    )

    collector = Collector(None, 51.5, -0.12)
    with pytest.raises(BomLocationError):
        await collector.async_resolve_location()


async def test_transient_failure_is_not_reported_as_bad_location(
    mock_api, api_responses
) -> None:
    """A 5xx on the location resource must not read as 'outside coverage'.

    Reporting a temporary outage as bad_location tells users their valid
    Australian coordinates are unsupported.
    """
    api_responses[f"https://api.weather.bom.gov.au/v1/locations/{GEOHASH}"] = (
        BomApiError("server error", status=503)
    )

    collector = Collector(None, -37.8136, 144.9631)
    with pytest.raises(BomApiError) as err:
        await collector.async_resolve_location()

    assert not isinstance(err.value, BomLocationError)


async def test_not_found_is_reported_as_bad_location(mock_api, api_responses) -> None:
    """A definitive rejection does mean the coordinates are not covered."""
    api_responses[f"https://api.weather.bom.gov.au/v1/locations/{GEOHASH}"] = (
        BomApiError("not found", status=404)
    )

    collector = Collector(None, -37.8136, 144.9631)
    with pytest.raises(BomLocationError):
        await collector.async_resolve_location()


async def test_cached_refresh_does_not_alter_forecast_values(mock_api) -> None:
    """Falling back to cache must not change already-formatted values.

    Formatting normalises the payload in place. If the cache held that same
    object, a second pass would turn a rain_amount_range of 0 into "0-0".
    """
    collector = Collector(None, -37.8136, 144.9631)
    await collector.async_resolve_location()

    first = await collector.async_update()
    # Day 2 is the first whose rain.amount.max is null.
    before = [day["rain_amount_range"] for day in first.daily]
    assert before[2] == 0

    with (
        patch.object(
            Collector, "_request", AsyncMock(side_effect=aiohttp.ClientError())
        ),
        patch(
            "custom_components.bureau_of_meteorology.PyBoM.collector.asyncio.sleep",
            AsyncMock(),
        ),
    ):
        second = await collector.async_update()

    assert [day["rain_amount_range"] for day in second.daily] == before
