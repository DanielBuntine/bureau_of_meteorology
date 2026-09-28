"""Tests for the weather platform."""

from __future__ import annotations

from homeassistant.components.weather import (
    ATTR_FORECAST_TIME,
    SERVICE_GET_FORECASTS,
)
from homeassistant.components.weather import (
    DOMAIN as WEATHER_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _forecast(hass: HomeAssistant, entity_id: str, forecast_type: str) -> list:
    """Call weather.get_forecasts and return the forecast list."""
    result = await hass.services.async_call(
        WEATHER_DOMAIN,
        SERVICE_GET_FORECASTS,
        {ATTR_ENTITY_ID: entity_id, "type": forecast_type},
        blocking=True,
        return_response=True,
    )
    return result[entity_id]["forecast"]


async def test_weather_entities_created(hass: HomeAssistant, setup_integration) -> None:
    """Both a daily and an hourly weather entity are created."""
    daily = hass.states.get("weather.melbourne")
    hourly = hass.states.get("weather.melbourne_hourly")

    assert daily is not None
    assert hourly is not None
    assert daily.attributes["friendly_name"] == "Melbourne"
    assert hourly.attributes["friendly_name"] == "Melbourne Hourly"


async def test_current_conditions(hass: HomeAssistant, setup_integration) -> None:
    """Current observations are exposed, including dew point and feels-like."""
    state = hass.states.get("weather.melbourne")

    assert state.attributes["temperature"] == 13.6
    assert state.attributes["apparent_temperature"] == 13.2
    assert state.attributes["humidity"] == 70
    assert state.attributes["wind_bearing"] == "CALM"
    assert state.attributes["wind_gust_speed"] == 6.0
    assert state.attributes["dew_point"] == 8.2


async def test_daily_forecast_is_timezone_aware(
    hass: HomeAssistant, setup_integration
) -> None:
    """Forecast timestamps carry an offset, as RFC 3339 requires."""
    forecast = await _forecast(hass, "weather.melbourne", "daily")

    assert len(forecast) == 9
    for entry in forecast:
        parsed = dt_util.parse_datetime(entry[ATTR_FORECAST_TIME])
        assert parsed is not None
        assert parsed.tzinfo is not None


async def test_daily_forecast_carries_templow(
    hass: HomeAssistant, setup_integration
) -> None:
    """Templow reaches the forecast, which the legacy key silently dropped."""
    forecast = await _forecast(hass, "weather.melbourne", "daily")

    # The BOM omits the minimum for the current day once it has passed.
    assert "templow" not in forecast[0]
    assert forecast[1]["templow"] == 11.0
    assert forecast[1]["temperature"] == 14.0


async def test_hourly_forecast_fields(hass: HomeAssistant, setup_integration) -> None:
    """Hourly forecasts carry gust speed and dew point in their native fields."""
    forecast = await _forecast(hass, "weather.melbourne_hourly", "hourly")

    assert len(forecast) == 6
    first = forecast[0]
    assert first["wind_gust_speed"] == 17.0
    assert first["dew_point"] == 11.0
    assert first["apparent_temperature"] == 11.0
    assert first["wind_speed"] == 9.0
    assert first["wind_bearing"] == "SW"
    assert first["humidity"] == 87
    assert first["uv_index"] == 0


async def test_weather_survives_null_blocks(
    hass: HomeAssistant, mock_api, api_responses, config_entry: MockConfigEntry
) -> None:
    """Null station and rain blocks from the BOM must not take the entity down."""
    base = "https://api.weather.bom.gov.au/v1/locations/r1r0fs"
    api_responses[f"{base}/observations"]["data"]["station"] = None
    api_responses[f"{base}/forecasts/daily"]["data"][1]["rain"] = None
    api_responses[f"{base}/forecasts/hourly"]["data"][0]["rain"] = None

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("weather.melbourne")
    assert state.state != STATE_UNAVAILABLE
    assert state.attributes["temperature"] == 13.6

    daily = await _forecast(hass, "weather.melbourne", "daily")
    assert len(daily) == 9
    assert daily[1].get("precipitation") is None
    assert daily[1]["temperature"] == 14.0

    hourly = await _forecast(hass, "weather.melbourne_hourly", "hourly")
    assert len(hourly) == 6
    assert hourly[0].get("precipitation") is None
