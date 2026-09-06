"""Tests for the sensor platform."""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bureau_of_meteorology.const import (
    CONF_OBSERVATIONS_MONITORED,
    DOMAIN,
)


async def test_observation_sensors(hass: HomeAssistant, setup_integration) -> None:
    """Observation sensors report the value from the API."""
    assert hass.states.get("sensor.melbourne_current_temperature").state == "13.6"
    assert hass.states.get("sensor.melbourne_humidity").state == "70"


async def test_dew_point_is_calculated(hass: HomeAssistant, setup_integration) -> None:
    """Dew point is derived from temperature and humidity."""
    assert hass.states.get("sensor.melbourne_dew_point").state == "8.2"


async def test_forecast_sensors_per_day(hass: HomeAssistant, setup_integration) -> None:
    """A forecast sensor is created for each configured day."""
    for day in range(3):
        state = hass.states.get(f"sensor.melbourne_forecast_maximum_temperature_{day}")
        assert state is not None, f"day {day} missing"
        assert state.state not in (None, STATE_UNAVAILABLE)

    assert hass.states.get("sensor.melbourne_forecast_maximum_temperature_3") is None


async def test_warnings_sensor(hass: HomeAssistant, setup_integration) -> None:
    """The warnings sensor counts warnings and lists them as an attribute."""
    state = hass.states.get("sensor.melbourne_warnings")

    assert state.state.isdigit()
    assert isinstance(state.attributes["warnings"], list)
    assert "attribution" in state.attributes


async def test_warnings_attributes_do_not_mutate_source(
    hass: HomeAssistant, setup_integration
) -> None:
    """Reading attributes must not write back into the coordinator's data."""
    state = hass.states.get("sensor.melbourne_warnings")
    assert "warnings" in state.attributes

    metadata = setup_integration.runtime_data.data.warnings["metadata"]
    assert "warnings" not in metadata
    assert "attribution" not in metadata


async def test_now_later_sensor(hass: HomeAssistant, setup_integration) -> None:
    """The now/later sensors are created once, not once per day."""
    assert hass.states.get("sensor.melbourne_now_label") is not None
    assert hass.states.get("sensor.melbourne_now_label_1") is None


async def test_timestamp_sensor_is_a_datetime(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """Timestamp sensors emit a parseable datetime, not a raw API string."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            "forecasts_monitored": ["astronomical_sunrise_time"],
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.melbourne_sunrise_time_0")
    assert state is not None
    parsed = dt_util.parse_datetime(state.state)
    assert parsed is not None
    assert parsed.tzinfo is not None


async def test_missing_observation_is_unavailable(
    hass: HomeAssistant, mock_api, api_responses, config_entry: MockConfigEntry
) -> None:
    """A reading the BOM is not publishing is unavailable, not the string."""
    observations = api_responses[
        "https://api.weather.bom.gov.au/v1/locations/r1r0fs/observations"
    ]
    observations["data"] = {
        key: value
        for key, value in observations["data"].items()
        if key not in ("wind", "gust")
    }

    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_OBSERVATIONS_MONITORED: ["wind_direction"]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.melbourne_wind_direction")
    assert state.state == STATE_UNAVAILABLE


async def test_unique_ids_are_entry_scoped(
    hass: HomeAssistant, setup_integration
) -> None:
    """Every entity's unique ID is prefixed with the config entry ID."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, setup_integration.entry_id)

    assert entries
    for entry in entries:
        assert entry.unique_id.startswith(setup_integration.entry_id)


async def test_new_observation_sensors_available(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """The previously unused max_gust and station distance fields are exposed."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            CONF_OBSERVATIONS_MONITORED: [
                "max_gust_speed_kilometre",
                "max_gust_time",
                "station_distance",
            ],
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.melbourne_maximum_gust_speed_km_h").state == "35"
    assert dt_util.parse_datetime(
        hass.states.get("sensor.melbourne_maximum_gust_time").state
    )

    # Diagnostic and disabled by default, so only the registry entry exists.
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{config_entry.entry_id}-observation-station_distance"
    )
    assert entity_id is not None
    assert registry.async_get(entity_id).disabled_by is not None


async def test_uv_forecast_summary(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """The UV summary reports the protection window in local time."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            "forecasts_monitored": ["uv_forecast", "uv_category"],
            "forecasts_days": 1,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Day 0 has no UV data at this time of year, so there is nothing to report.
    assert hass.states.get("sensor.melbourne_uv_forecast_summary_0").state == (
        STATE_UNKNOWN
    )

    assert hass.states.get("sensor.melbourne_uv_forecast_summary_1").state == (
        "Sun protection recommended from 10:10am to 2:30pm, "
        "UV Index predicted to reach 4 [Moderate]"
    )
    assert hass.states.get("sensor.melbourne_uv_category_1").state == "Moderate"


async def test_uv_forecast_without_protection_window(
    hass: HomeAssistant, mock_api, api_responses, config_entry: MockConfigEntry
) -> None:
    """With no start time the summary says protection is not required."""
    daily = api_responses[
        "https://api.weather.bom.gov.au/v1/locations/r1r0fs/forecasts/daily"
    ]
    daily["data"][0]["uv"] = {
        "category": "veryhigh",
        "max_index": 9,
        "start_time": None,
        "end_time": None,
    }

    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            "forecasts_monitored": ["uv_forecast"],
            "forecasts_days": 0,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.melbourne_uv_forecast_summary_0").state == (
        "Sun protection not required, UV Index predicted to reach 9 [Very High]"
    )


async def test_fire_danger_colours(
    hass: HomeAssistant, mock_api, api_responses, config_entry: MockConfigEntry
) -> None:
    """Fire danger exposes the BOM's own fill colour and a readable text colour."""
    daily = api_responses[
        "https://api.weather.bom.gov.au/v1/locations/r1r0fs/forecasts/daily"
    ]
    daily["data"][0]["fire_danger"] = "Catastrophic"
    daily["data"][0]["fire_danger_category"] = {
        "text": "Catastrophic",
        "default_colour": "#FF0000",
        "dark_mode_colour": "#FF0000",
    }

    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            "forecasts_monitored": ["fire_danger"],
            "forecasts_days": 0,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.melbourne_fire_danger_0")
    assert state.state == "Catastrophic"
    assert state.attributes["color_fill"] == "#FF0000"
    assert state.attributes["color_text"] == "#ffffff"


async def test_long_forecast_text_is_truncated(
    hass: HomeAssistant, mock_api, api_responses, config_entry: MockConfigEntry
) -> None:
    """Text longer than a state can hold is truncated but kept as an attribute."""
    daily = api_responses[
        "https://api.weather.bom.gov.au/v1/locations/r1r0fs/forecasts/daily"
    ]
    daily["data"][0]["extended_text"] = "A" * 400

    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            "forecasts_monitored": ["extended_text"],
            "forecasts_days": 0,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.melbourne_extended_forecast_0")
    assert len(state.state) < 255
    assert state.state.endswith("...")
    assert state.attributes["state"] == "A" * 400
