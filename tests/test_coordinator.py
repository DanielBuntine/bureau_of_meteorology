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
    BomData,
    BomLocationError,
    Collector,
)

from .conftest import GEOHASH, GEOHASH6

# The geohash and dew point helpers are covered in tests/test_helpers.py.


def _collector() -> Collector:
    """Return a collector that is never used to make a request."""
    return Collector(AsyncMock(), -12.463763, 130.844398)


def test_daily_forecasts_are_flattened_and_normalised() -> None:
    """The first day honours ``now.is_night``; later days keep their descriptor."""
    collector = _collector()
    data = {
        "data": [
            {
                "icon_descriptor": "sunny",
                "rain": {"amount": {"min": 2, "max": 5}, "chance": 60},
                "uv": {"category": "high"},
                "astronomical": {"sunrise_time": "06:00"},
                "now": {"is_night": True},
            },
            {
                "icon_descriptor": "sunny",
                "rain": {"amount": {"min": 0, "max": None}, "chance": 10},
                "uv": {"category": "low"},
                "astronomical": {"sunrise_time": "06:01"},
            },
        ]
    }

    collector._format_daily_forecasts(data)
    today, later = data["data"]

    assert today["icon_descriptor"] == "clear"
    assert today["mdi_icon"] == "mdi:weather-night"
    assert today["rain_chance"] == 60
    assert today["rain_amount_min"] == 2
    assert today["rain_amount_max"] == 5
    assert today["rain_amount_range"] == "2–5"  # noqa: RUF001
    assert today["uv_category"] == "high"
    assert today["astronomical_sunrise_time"] == "06:00"
    assert today["now_is_night"] is True

    # Only day zero has a "now" block, so later days are left as forecast.
    assert later["icon_descriptor"] == "sunny"
    assert later["mdi_icon"] == "mdi:weather-sunny"
    assert later["rain_amount_min"] == 0
    # A missing maximum collapses onto the minimum rather than reading as a range.
    assert later["rain_amount_max"] == 0
    assert later["rain_amount_range"] == 0
    assert later["uv_category"] == "low"


def test_hourly_forecasts_are_flattened_and_normalised() -> None:
    """Each hour reconciles its own icon against its own ``is_night`` flag."""
    collector = _collector()
    data = {
        "data": [
            {
                "icon_descriptor": "mostly_sunny",
                "is_night": True,
                "rain": {"amount": {"min": 1, "max": 3}, "chance": 80},
                "wind": {"speed_kilometre": 10},
            },
            {
                "icon_descriptor": "clear",
                "is_night": False,
                "rain": {"amount": {"min": 4, "max": None}, "chance": 20},
                "wind": {"speed_knot": 8},
            },
        ]
    }

    collector._format_hourly_forecasts(data)
    first, second = data["data"]

    assert first["icon_descriptor"] == "clear"
    assert first["mdi_icon"] == "mdi:weather-night"
    assert first["rain_amount_min"] == 1
    assert first["rain_amount_max"] == 3
    assert first["rain_amount_range"] == "1–3"  # noqa: RUF001
    assert first["rain_chance"] == 80
    assert first["wind_speed_kilometre"] == 10

    # "clear" during the day is really "sunny".
    assert second["icon_descriptor"] == "sunny"
    assert second["mdi_icon"] == "mdi:weather-sunny"
    assert second["rain_amount_min"] == 4
    assert second["rain_amount_max"] == 4
    assert second["rain_amount_range"] == 4
    assert second["rain_chance"] == 20
    assert second["wind_speed_knot"] == 8


def test_null_blocks_are_tolerated() -> None:
    """The BOM sends null for absent blocks; formatting must not raise."""
    collector = _collector()
    daily = {
        "data": [
            {"icon_descriptor": "sunny", "rain": None, "now": None, "uv": None},
            {"icon_descriptor": "cloudy", "rain": None, "astronomical": None},
        ]
    }
    hourly = {"data": [{"icon_descriptor": "sunny", "rain": None, "wind": None}]}
    observations = {"data": {"temp": 20.1, "station": None, "wind": None}}

    collector._format_daily_forecasts(daily)
    collector._format_hourly_forecasts(hourly)
    collector._format_observations(observations)

    assert daily["data"][1]["rain_amount_range"] is None
    assert daily["data"][1]["mdi_icon"] == "mdi:weather-cloudy"
    assert hourly["data"][0]["rain_amount_max"] is None
    assert "station_name" not in observations["data"]


def test_null_location_data_falls_back() -> None:
    """A location payload of {"data": null} still yields a usable timezone."""
    data = BomData(locations={"data": None})

    assert data.timezone == "UTC"
    assert data.location_name is None


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
