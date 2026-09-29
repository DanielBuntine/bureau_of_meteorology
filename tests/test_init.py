"""Tests for setup, unload and migration."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bureau_of_meteorology.const import (
    CONF_FORECASTS_BASENAME,
    CONF_OBSERVATIONS_BASENAME,
    CONF_WARNINGS_BASENAME,
    CONF_WEATHER_NAME,
    DOMAIN,
)
from custom_components.bureau_of_meteorology.PyBoM.collector import BomApiError

from .conftest import GEOHASH


async def test_setup_and_unload(hass: HomeAssistant, setup_integration) -> None:
    """The entry loads, exposes a coordinator and unloads cleanly."""
    entry = setup_integration
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.data.location_name == "Melbourne"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_api_unavailable(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An unreachable API leaves the entry in a retrying state, not failed."""
    config_entry.add_to_hass(hass)

    with patch(
        "custom_components.bureau_of_meteorology.PyBoM.collector.Collector._request",
        side_effect=BomApiError("boom"),
    ):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_migrate_v1_entry(hass: HomeAssistant, mock_api) -> None:
    """A version 1 entry gains a weather name and is bumped to version 2."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={
            CONF_LATITUDE: -37.8136,
            CONF_LONGITUDE: 144.9631,
            CONF_FORECASTS_BASENAME: "Melbourne",
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert entry.data[CONF_WEATHER_NAME] == "Melbourne"


async def test_unique_id_migration(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """Entities registered under the old name based IDs keep their entity_id."""
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    existing = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "Melbourne_temp",
        config_entry=config_entry,
        suggested_object_id="melbourne_temp",
    )
    weather = registry.async_get_or_create(
        "weather",
        DOMAIN,
        "Melbourne",
        config_entry=config_entry,
        suggested_object_id="melbourne",
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    migrated = registry.async_get(existing.entity_id)
    assert migrated is not None
    assert migrated.unique_id == f"{config_entry.entry_id}-observation-temp"

    migrated_weather = registry.async_get(weather.entity_id)
    assert migrated_weather is not None
    assert migrated_weather.unique_id == f"{config_entry.entry_id}-weather"


async def test_unique_id_migration_after_downgrade(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """Returning from a 1.3.x release keeps the original entity.

    That release cannot see the entry scoped weather entity, so it registers a
    name based duplicate as weather.melbourne_2. Re-keying the duplicate would
    collide with the original and fail setup of the whole entry.
    """
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    original = registry.async_get_or_create(
        "weather",
        DOMAIN,
        f"{config_entry.entry_id}-weather",
        config_entry=config_entry,
        suggested_object_id="melbourne",
    )
    duplicate = registry.async_get_or_create(
        "weather",
        DOMAIN,
        "Melbourne",
        config_entry=config_entry,
        suggested_object_id="melbourne",
    )
    assert duplicate.entity_id == "weather.melbourne_2"

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert registry.async_get(duplicate.entity_id) is None
    assert registry.async_get(original.entity_id) is not None
    assert hass.states.get("weather.melbourne").state != STATE_UNAVAILABLE


async def test_stale_entities_removed(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """A sensor the user has deselected is dropped from the registry."""
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    stale = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{config_entry.entry_id}-observation-rain_since_9am",
        config_entry=config_entry,
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(stale.entity_id) is None


async def test_renamed_entity_survives(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """Renaming an entity no longer causes it to be deleted on reload."""
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    entity = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{config_entry.entry_id}-observation-temp",
        config_entry=config_entry,
        suggested_object_id="my_custom_name",
    )
    assert entity.entity_id == "sensor.my_custom_name"

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get("sensor.my_custom_name") is not None


async def test_unique_id_is_geohash(hass: HomeAssistant, setup_integration) -> None:
    """The entry is keyed on the BOM geohash so duplicates can be detected."""
    assert setup_integration.unique_id == GEOHASH


async def test_pre_1_4_entry_gains_unique_id(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """Entries created by 1.3.x have no unique ID; setup backfills it.

    The old config flow never called async_set_unique_id, and those entries
    were already version 2, so no migration runs for them.
    """
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, unique_id=None)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.unique_id == GEOHASH


async def test_orphaned_device_removed_after_rename(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """Renaming every basename must not leave the old device behind."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)

    def device_names() -> set[str]:
        return {
            device.name
            for device in dr.async_entries_for_config_entry(
                device_registry, config_entry.entry_id
            )
        }

    assert device_names() == {"Melbourne"}

    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.data,
            CONF_WEATHER_NAME: "Renamed",
            CONF_OBSERVATIONS_BASENAME: "Renamed",
            CONF_FORECASTS_BASENAME: "Renamed",
            CONF_WARNINGS_BASENAME: "Renamed",
        },
    )
    await hass.async_block_till_done()

    assert device_names() == {"Renamed"}


async def test_user_disabled_entity_survives_reload(
    hass: HomeAssistant, setup_integration
) -> None:
    """A user-disabled entity stays registered and stays disabled."""
    entry = setup_integration
    registry = er.async_get(hass)

    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}-observation-humidity"
    )
    assert entity_id is not None
    registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    after = registry.async_get(entity_id)
    assert after is not None
    assert after.disabled_by is er.RegistryEntryDisabler.USER


async def test_legacy_coordinates_removed_from_options(
    hass: HomeAssistant, mock_api, config_entry: MockConfigEntry
) -> None:
    """Coordinates written into options by older versions are cleaned out."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            CONF_LATITUDE: -33.8688,
            CONF_LONGITUDE: 151.2093,
            CONF_WEATHER_NAME: "Melbourne",
        },
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert CONF_LATITUDE not in config_entry.options
    assert CONF_LONGITUDE not in config_entry.options
    assert config_entry.options[CONF_WEATHER_NAME] == "Melbourne"
    # The entry still uses the coordinates from data.
    assert config_entry.data[CONF_LATITUDE] == -37.8136
