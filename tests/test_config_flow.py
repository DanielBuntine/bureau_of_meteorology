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


async def _choose_coordinates(manager, flow_id: str, location=None) -> dict:
    """Take the "enter coordinates" branch of the opening menu."""
    await manager.async_configure(flow_id, {"next_step_id": "coordinates"})
    return await manager.async_configure(flow_id, location or LOCATION)


async def _walk_full_flow(hass: HomeAssistant, flow_id: str, options=False) -> dict:
    """Answer every step of the flow and return the final result."""
    manager = hass.config_entries.options if options else hass.config_entries.flow

    result = await _choose_coordinates(manager, flow_id)
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
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"

    result = await _walk_full_flow(hass, result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Melbourne"
    assert result["data"][CONF_WEATHER_NAME] == "Melbourne"
    assert result["data"][CONF_FORECASTS_DAYS] == 2
    assert result["result"].unique_id == GEOHASH


async def test_user_flow_with_null_station(
    hass: HomeAssistant, mock_api, api_responses
) -> None:
    """A null observation station must not break the observations step."""
    observations = api_responses[
        "https://api.weather.bom.gov.au/v1/locations/r1r0fs/observations"
    ]
    observations["data"]["station"] = None

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await _walk_full_flow(hass, result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_flow_skips_disabled_groups(hass: HomeAssistant, mock_api) -> None:
    """Declining every sensor group goes straight to creating the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    flow_id = result["flow_id"]

    await _choose_coordinates(hass.config_entries.flow, flow_id)
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
        result = await _choose_coordinates(
            hass.config_entries.flow,
            result["flow_id"],
            {CONF_LATITUDE: 51.5, CONF_LONGITUDE: -0.12},
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
        result = await _choose_coordinates(hass.config_entries.flow, result["flow_id"])

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
    result = await _choose_coordinates(hass.config_entries.flow, result["flow_id"])

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
    result = await _choose_coordinates(
        manager,
        result["flow_id"],
        {CONF_LATITUDE: SYDNEY[0], CONF_LONGITUDE: SYDNEY[1]},
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
    result = await _choose_coordinates(manager, result["flow_id"])
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
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "coordinates"}
    )
    schema_defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert schema_defaults[CONF_LATITUDE] == SYDNEY[0]


async def test_search_by_postcode(hass: HomeAssistant, mock_api) -> None:
    """A postcode search fills the coordinates in for the user."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    manager = hass.config_entries.flow

    result = await manager.async_configure(
        result["flow_id"], {"next_step_id": "search"}
    )
    assert result["step_id"] == "search"

    result = await manager.async_configure(result["flow_id"], {"search": "3000"})
    assert result["step_id"] == "pick"

    result = await manager.async_configure(result["flow_id"], {"location": GEOHASH})
    assert result["step_id"] == "weather_name"


async def test_search_offers_every_match(hass: HomeAssistant, mock_api) -> None:
    """Same-named suburbs are distinguishable by state and postcode."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    manager = hass.config_entries.flow

    await manager.async_configure(result["flow_id"], {"next_step_id": "search"})
    result = await manager.async_configure(result["flow_id"], {"search": "Coogee"})

    options = result["data_schema"].schema["location"].config["options"]
    assert [option["label"] for option in options] == [
        "Coogee, VIC 3000",
        "Coogee, NSW 2034",
    ]


async def test_search_with_no_matches(hass: HomeAssistant, mock_api) -> None:
    """A search that matches nothing says so instead of failing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    manager = hass.config_entries.flow

    await manager.async_configure(result["flow_id"], {"next_step_id": "search"})
    result = await manager.async_configure(result["flow_id"], {"search": "Nowhere"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "search"
    assert result["errors"] == {"base": "no_results"}


async def test_search_result_is_stored_as_coordinates(
    hass: HomeAssistant, mock_api
) -> None:
    """The entry ends up with coordinates, however the location was chosen."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    manager = hass.config_entries.flow
    flow_id = result["flow_id"]

    await manager.async_configure(flow_id, {"next_step_id": "search"})
    await manager.async_configure(flow_id, {"search": "3000"})
    await manager.async_configure(flow_id, {"location": GEOHASH})
    await manager.async_configure(flow_id, {CONF_WEATHER_NAME: "Melbourne"})
    result = await manager.async_configure(
        flow_id,
        {
            CONF_OBSERVATIONS_CREATE: False,
            CONF_FORECASTS_CREATE: False,
            CONF_WARNINGS_CREATE: False,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LATITUDE] == -37.81425476074219
    assert result["data"][CONF_LONGITUDE] == 144.96253967285156
    assert result["result"].unique_id == GEOHASH
