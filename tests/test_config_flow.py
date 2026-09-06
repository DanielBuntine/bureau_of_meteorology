"""Tests for the config, options and reconfigure flows."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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
from custom_components.bureau_of_meteorology.PyBoM.collector import (
    BomApiError,
    BomLocationError,
)

from .conftest import GEOHASH, GEOHASH_2, SYDNEY

LOCATION = {CONF_LATITUDE: -37.8136, CONF_LONGITUDE: 144.9631}


async def _walk_full_flow(hass: HomeAssistant, flow_id: str, options=False) -> dict:
    """Answer every step of the flow and return the final result."""
    manager = hass.config_entries.options if options else hass.config_entries.flow

    result = await manager.async_configure(flow_id, LOCATION)
    assert result["step_id"] == "weather_name"

    result = await manager.async_configure(flow_id, {CONF_WEATHER_NAME: "Melbourne"})
    assert result["step_id"] == "sensors_create"

    result = await manager.async_configure(
        flow_id,
        {
            CONF_OBSERVATIONS_CREATE: True,
            CONF_FORECASTS_CREATE: True,
            CONF_WARNINGS_CREATE: True,
        },
    )
    assert result["step_id"] == "observations_monitored"

    result = await manager.async_configure(
        flow_id,
        {
            CONF_OBSERVATIONS_BASENAME: "Melbourne",
            CONF_OBSERVATIONS_MONITORED: ["temp"],
        },
    )
    assert result["step_id"] == "forecasts_monitored"

    result = await manager.async_configure(
        flow_id,
        {
            CONF_FORECASTS_BASENAME: "Melbourne",
            CONF_FORECASTS_MONITORED: ["temp_max"],
            CONF_FORECASTS_DAYS: 2,
        },
    )
    assert result["step_id"] == "warnings_basename"

    return await manager.async_configure(flow_id, {CONF_WARNINGS_BASENAME: "Melbourne"})


async def test_full_user_flow(hass: HomeAssistant, mock_api) -> None:
    """The happy path creates an entry keyed on the BOM geohash."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await _walk_full_flow(hass, result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Melbourne"
    assert result["data"][CONF_WEATHER_NAME] == "Melbourne"
    assert result["data"][CONF_FORECASTS_DAYS] == 2
    assert result["result"].unique_id == GEOHASH


async def test_flow_skips_disabled_groups(hass: HomeAssistant, mock_api) -> None:
    """Declining every sensor group goes straight to creating the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    flow_id = result["flow_id"]

    await hass.config_entries.flow.async_configure(flow_id, LOCATION)
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_WEATHER_NAME: "Melbourne"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_OBSERVATIONS_CREATE: False,
            CONF_FORECASTS_CREATE: False,
            CONF_WARNINGS_CREATE: False,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_bad_location(hass: HomeAssistant) -> None:
    """Coordinates outside the BOM coverage area are reported to the user."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.bureau_of_meteorology.PyBoM.collector."
        "Collector.async_resolve_location",
        side_effect=BomLocationError,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LATITUDE: 51.5, CONF_LONGITUDE: -0.12}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "bad_location"}


async def test_cannot_connect(hass: HomeAssistant) -> None:
    """An unreachable API is reported without aborting the flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.bureau_of_meteorology.PyBoM.collector."
        "Collector.async_resolve_location",
        side_effect=BomApiError("boom"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOCATION
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_location_aborts(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """Adding the same location twice aborts instead of colliding."""
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOCATION)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_persists_location_to_data(
    hass: HomeAssistant, setup_integration
) -> None:
    """Changing the location writes it where async_setup_entry reads it."""
    entry = setup_integration

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"

    result = await _walk_full_flow(hass, result["flow_id"], options=True)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Setup reads coordinates from data, so options alone would be ignored.
    assert entry.data[CONF_LATITUDE] == LOCATION[CONF_LATITUDE]
    assert entry.data[CONF_LONGITUDE] == LOCATION[CONF_LONGITUDE]
    assert entry.options[CONF_FORECASTS_DAYS] == 2


async def test_reconfigure_flow(hass: HomeAssistant, setup_integration) -> None:
    """The location of an existing entry can be changed in place."""
    entry = setup_integration

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOCATION)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_LATITUDE] == LOCATION[CONF_LATITUDE]


async def test_reconfigure_moves_to_a_new_location(
    hass: HomeAssistant, setup_integration
) -> None:
    """Reconfigure genuinely moves the entry, taking the unique ID with it."""
    entry = setup_integration
    assert entry.unique_id == GEOHASH

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_LATITUDE: SYDNEY[0], CONF_LONGITUDE: SYDNEY[1]},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_LATITUDE] == SYDNEY[0]
    assert entry.unique_id == GEOHASH_2


async def test_reconfigure_rejects_a_location_already_configured(
    hass: HomeAssistant, setup_integration
) -> None:
    """Moving onto a location another entry already owns is refused."""
    other = MockConfigEntry(domain=DOMAIN, version=2, unique_id=GEOHASH_2)
    other.add_to_hass(hass)

    result = await setup_integration.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_LATITUDE: SYDNEY[0], CONF_LONGITUDE: SYDNEY[1]},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert setup_integration.unique_id == GEOHASH


async def test_options_flow_move_updates_unique_id(
    hass: HomeAssistant, setup_integration
) -> None:
    """Changing location via Configure keeps the unique ID truthful."""
    entry = setup_integration

    result = await hass.config_entries.options.async_init(entry.entry_id)
    manager = hass.config_entries.options
    result = await manager.async_configure(
        result["flow_id"], {CONF_LATITUDE: SYDNEY[0], CONF_LONGITUDE: SYDNEY[1]}
    )
    result = await manager.async_configure(
        result["flow_id"], {CONF_WEATHER_NAME: "Sydney"}
    )
    result = await manager.async_configure(
        result["flow_id"],
        {
            CONF_OBSERVATIONS_CREATE: False,
            CONF_FORECASTS_CREATE: False,
            CONF_WARNINGS_CREATE: False,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_LATITUDE] == SYDNEY[0]
    assert entry.unique_id == GEOHASH_2


async def test_options_flow_does_not_store_coordinates(
    hass: HomeAssistant, setup_integration
) -> None:
    """Coordinates belong to entry.data; options must not shadow them."""
    entry = setup_integration
    manager = hass.config_entries.options

    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], LOCATION)
    result = await manager.async_configure(
        result["flow_id"], {CONF_WEATHER_NAME: "Melbourne"}
    )
    result = await manager.async_configure(
        result["flow_id"],
        {
            CONF_OBSERVATIONS_CREATE: False,
            CONF_FORECASTS_CREATE: False,
            CONF_WARNINGS_CREATE: False,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_LATITUDE not in entry.options
    assert CONF_LONGITUDE not in entry.options
    assert entry.data[CONF_LATITUDE] == LOCATION[CONF_LATITUDE]


async def test_reconfigure_is_not_undone_by_stale_options(
    hass: HomeAssistant, setup_integration
) -> None:
    """A move via Reconfigure survives reopening Configure."""
    entry = setup_integration

    result = await entry.start_reconfigure_flow(hass)
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_LATITUDE: SYDNEY[0], CONF_LONGITUDE: SYDNEY[1]},
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_LATITUDE] == SYDNEY[0]
    assert CONF_LATITUDE not in entry.options

    # The Configure form must prefill the location the entry actually uses.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema_defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert schema_defaults[CONF_LATITUDE] == SYDNEY[0]
