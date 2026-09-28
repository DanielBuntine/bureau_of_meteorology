"""The Bureau of Meteorology integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
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
    NOW_LATER_KEYS,
)
from .coordinator import BomConfigEntry, BomDataUpdateCoordinator
from .PyBoM.collector import BomApiError, Collector

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.WEATHER]


def _weather_name(entry: ConfigEntry) -> str:
    """Return the configured name for the weather entities."""
    return entry.options.get(
        CONF_WEATHER_NAME, entry.data.get(CONF_WEATHER_NAME, "Home")
    )


def _option(entry: ConfigEntry, key: str, default=None):
    """Read a setting from options, falling back to the original entry data."""
    return entry.options.get(key, entry.data.get(key, default))


def _expected_entities(entry: ConfigEntry) -> dict[str, str]:
    """Map every unique ID this entry should own to its pre-1.4.0 equivalent.

    The old IDs were built from the user supplied basenames, which meant two
    entries for the same place collided. The new IDs are scoped to the config
    entry; this mapping is what lets existing entities keep their entity_id.
    """
    entry_id = entry.entry_id
    weather_name = _weather_name(entry)
    expected = {
        f"{entry_id}-weather": weather_name,
        f"{entry_id}-weather-hourly": f"{weather_name}_hourly",
    }

    if _option(entry, CONF_OBSERVATIONS_CREATE) is True:
        basename = _option(entry, CONF_OBSERVATIONS_BASENAME)
        for sensor in _option(entry, CONF_OBSERVATIONS_MONITORED) or []:
            expected[f"{entry_id}-observation-{sensor}"] = f"{basename}_{sensor}"

    if _option(entry, CONF_FORECASTS_CREATE) is True:
        basename = _option(entry, CONF_FORECASTS_BASENAME)
        monitored = _option(entry, CONF_FORECASTS_MONITORED) or []
        for day in range(_option(entry, CONF_FORECASTS_DAYS, 0) + 1):
            for sensor in monitored:
                if sensor in NOW_LATER_KEYS:
                    if day == 0:
                        expected[f"{entry_id}-nowlater-{sensor}"] = (
                            f"{basename}_{sensor}"
                        )
                else:
                    expected[f"{entry_id}-forecast-{day}-{sensor}"] = (
                        f"{basename}_{day}_{sensor}"
                    )

    if _option(entry, CONF_WARNINGS_CREATE) is True:
        basename = _option(entry, CONF_WARNINGS_BASENAME) or _option(
            entry, CONF_FORECASTS_BASENAME
        )
        if basename is not None:
            expected[f"{entry_id}-warnings"] = f"{basename}_warnings"

    return expected


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry."""
    _LOGGER.debug("Migrating from version %s", entry.version)

    if entry.version == 1:
        data = {**entry.data}
        if CONF_FORECASTS_BASENAME in data:
            data[CONF_WEATHER_NAME] = data[CONF_FORECASTS_BASENAME]
        # ConfigEntry attributes are read-only; the version has to be handed to
        # async_update_entry or Home Assistant raises AttributeError.
        hass.config_entries.async_update_entry(entry, data=data, version=2)

    _LOGGER.info("Migration to version %s successful", entry.version)
    return True


async def _migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-key entities from the old name based unique IDs to entry scoped ones."""
    old_to_new = {old: new for new, old in _expected_entities(entry).items()}
    entity_registry = er.async_get(hass)

    # A pre-1.4.0 release cannot see the entry scoped entities, so running one
    # and coming back leaves a name based duplicate (e.g. weather.home_2)
    # beside the original. Re-keying the duplicate would collide with the
    # original and fail setup, so drop it and keep the original entity_id.
    for registry_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        new_id = old_to_new.get(registry_entry.unique_id)
        if new_id is not None and entity_registry.async_get_entity_id(
            registry_entry.domain, DOMAIN, new_id
        ):
            _LOGGER.debug(
                "Removing %s, a duplicate of the entity with unique_id %s",
                registry_entry.entity_id,
                new_id,
            )
            entity_registry.async_remove(registry_entry.entity_id)

    @callback
    def _migrate(registry_entry: er.RegistryEntry) -> dict[str, str] | None:
        if (new_id := old_to_new.get(registry_entry.unique_id)) is None:
            return None
        _LOGGER.debug("Migrating unique_id %s to %s", registry_entry.unique_id, new_id)
        return {"new_unique_id": new_id}

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)


def _remove_stale_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop registry entries for sensors the user has since deselected.

    The previous implementation rebuilt entity_id strings by hand, so it deleted
    entities the user had renamed and missed any basename containing a space.
    Matching on unique_id avoids both problems.
    """
    entity_registry = er.async_get(hass)
    expected = set(_expected_entities(entry))

    for registry_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if registry_entry.unique_id not in expected:
            _LOGGER.debug("Removing %s from entity registry", registry_entry.entity_id)
            entity_registry.async_remove(registry_entry.entity_id)


def _remove_empty_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Detach devices that no longer have any entities, e.g. after a rename."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if not er.async_entries_for_device(
            entity_registry, device.id, include_disabled_entities=True
        ):
            _LOGGER.debug("Removing orphaned device: %s", device.name)
            device_registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )


async def async_setup_entry(hass: HomeAssistant, entry: BomConfigEntry) -> bool:
    """Set up the Bureau of Meteorology from a config entry."""
    collector = Collector(
        async_get_clientsession(hass),
        entry.data[CONF_LATITUDE],
        entry.data[CONF_LONGITUDE],
    )

    try:
        await collector.async_resolve_location()
    except BomApiError as err:
        raise ConfigEntryNotReady(
            f"Could not reach the Bureau of Meteorology: {err}"
        ) from err

    coordinator = BomDataUpdateCoordinator(hass, entry, collector)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Entries created before 1.4.0 have no unique ID, because the old config
    # flow never set one. Backfill it so the duplicate-location check and the
    # reconfigure flow work on upgraded installations too.
    if entry.unique_id is None:
        if any(
            other.unique_id == collector.geohash and other.entry_id != entry.entry_id
            for other in hass.config_entries.async_entries(DOMAIN)
        ):
            # Two pre-1.4.0 entries for one location: leave the second alone
            # rather than have both claim the same unique ID.
            _LOGGER.warning(
                "Not backfilling the unique ID for %s: another entry already "
                "covers this location",
                entry.title,
            )
        else:
            hass.config_entries.async_update_entry(entry, unique_id=collector.geohash)

    # Older versions wrote the coordinates into options as well as data, where
    # they would outrank a later Reconfigure. Data is the only source now.
    if CONF_LATITUDE in entry.options or CONF_LONGITUDE in entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={
                key: value
                for key, value in entry.options.items()
                if key not in (CONF_LATITUDE, CONF_LONGITUDE)
            },
        )

    await _migrate_unique_ids(hass, entry)
    _remove_stale_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Only now do the platforms know which device each entity belongs to, so a
    # device orphaned by a basename change is only detectable at this point.
    _remove_empty_devices(hass, entry)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: BomConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BomConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
