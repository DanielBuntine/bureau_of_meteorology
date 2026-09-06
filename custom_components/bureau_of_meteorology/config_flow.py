"""Config flow for the Bureau of Meteorology integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

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
    FORECAST_SENSOR_TYPES,
    OBSERVATION_SENSOR_TYPES,
    SENSOR_LABELS,
)
from .PyBoM.collector import BomApiError, BomLocationError, Collector

_LOGGER = logging.getLogger(__name__)

MAX_FORECAST_DAYS = 7


def _entry_for_geohash(hass, geohash: str, exclude_entry_id: str) -> bool:
    """Return whether another config entry already covers this geohash."""
    return any(
        entry.unique_id == geohash and entry.entry_id != exclude_entry_id
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


def _sensor_choices(descriptions) -> dict[str, str]:
    """Return the multi-select options for a set of sensor descriptions."""
    return {
        description.key: SENSOR_LABELS.get(description.key, description.key)
        for description in descriptions
    }


class BomFlowSteps:
    """The steps shared by the config flow and the options flow.

    Both flows ask exactly the same six questions; only the defaults they
    prefill and what they do with the answers differ.
    """

    collector: Collector
    data: dict[str, Any]

    def _default(self, key: str, fallback: Any) -> Any:
        """Return the value to prefill for ``key``."""
        raise NotImplementedError

    async def _async_finish(self) -> ConfigFlowResult:
        """Persist the collected answers."""
        raise NotImplementedError

    async def _async_check_location(self, user_input: dict[str, Any]) -> str | None:
        """Resolve the coordinates, returning an error key on failure."""
        self.collector = Collector(
            async_get_clientsession(self.hass),
            user_input[CONF_LATITUDE],
            user_input[CONF_LONGITUDE],
        )
        try:
            await self.collector.async_resolve_location()
            await self.collector.async_update()
        except BomLocationError:
            _LOGGER.debug("No BOM coverage for %s", user_input)
            return "bad_location"
        except BomApiError as err:
            _LOGGER.debug("Could not reach the BOM API: %s", err)
            return "cannot_connect"
        return None

    async def _async_step_location(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Ask for the coordinates and validate them against the BOM."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if error := await self._async_check_location(user_input):
                errors["base"] = error
            else:
                self.data = dict(user_input)
                return await self.async_step_weather_name()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_LATITUDE,
                    default=self._default(CONF_LATITUDE, self.hass.config.latitude),
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE,
                    default=self._default(CONF_LONGITUDE, self.hass.config.longitude),
                ): cv.longitude,
            }
        )
        return self.async_show_form(
            step_id=step_id, data_schema=data_schema, errors=errors
        )

    async def async_step_weather_name(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask what to call the weather entities."""
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_sensors_create()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_WEATHER_NAME,
                    default=self._default(
                        CONF_WEATHER_NAME, self.collector.locations_data["data"]["name"]
                    ),
                ): str,
            }
        )
        return self.async_show_form(step_id="weather_name", data_schema=data_schema)

    async def async_step_sensors_create(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which groups of sensors to create."""
        if user_input is not None:
            self.data.update(user_input)
            return await self._async_next_step()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_OBSERVATIONS_CREATE,
                    default=self._default(CONF_OBSERVATIONS_CREATE, True),
                ): bool,
                vol.Required(
                    CONF_FORECASTS_CREATE,
                    default=self._default(CONF_FORECASTS_CREATE, True),
                ): bool,
                vol.Required(
                    CONF_WARNINGS_CREATE,
                    default=self._default(CONF_WARNINGS_CREATE, True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="sensors_create", data_schema=data_schema)

    async def _async_next_step(self, after: str | None = None) -> ConfigFlowResult:
        """Advance to the next enabled step, skipping the disabled groups."""
        order = ["observations", "forecasts", "warnings"]
        start = order.index(after) + 1 if after else 0

        for group in order[start:]:
            if group == "observations" and self.data.get(CONF_OBSERVATIONS_CREATE):
                return await self.async_step_observations_monitored()
            if group == "forecasts" and self.data.get(CONF_FORECASTS_CREATE):
                return await self.async_step_forecasts_monitored()
            if group == "warnings" and self.data.get(CONF_WARNINGS_CREATE):
                return await self.async_step_warnings_basename()

        return await self._async_finish()

    async def async_step_observations_monitored(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which observation sensors to create."""
        if user_input is not None:
            self.data.update(user_input)
            return await self._async_next_step("observations")

        station = self.collector.observations_data["data"].get("station", {})
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_OBSERVATIONS_BASENAME,
                    default=self._default(
                        CONF_OBSERVATIONS_BASENAME, station.get("name")
                    ),
                ): str,
                vol.Required(
                    CONF_OBSERVATIONS_MONITORED,
                    default=self._default(CONF_OBSERVATIONS_MONITORED, []),
                ): cv.multi_select(_sensor_choices(OBSERVATION_SENSOR_TYPES)),
            }
        )
        return self.async_show_form(
            step_id="observations_monitored", data_schema=data_schema
        )

    async def async_step_forecasts_monitored(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which forecast sensors to create, and for how many days."""
        if user_input is not None:
            self.data.update(user_input)
            return await self._async_next_step("forecasts")

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_FORECASTS_BASENAME,
                    default=self._default(
                        CONF_FORECASTS_BASENAME,
                        self.collector.locations_data["data"]["name"],
                    ),
                ): str,
                vol.Required(
                    CONF_FORECASTS_MONITORED,
                    default=self._default(CONF_FORECASTS_MONITORED, []),
                ): cv.multi_select(_sensor_choices(FORECAST_SENSOR_TYPES)),
                vol.Required(
                    CONF_FORECASTS_DAYS,
                    default=self._default(CONF_FORECASTS_DAYS, 0),
                ): vol.All(vol.Coerce(int), vol.Range(0, MAX_FORECAST_DAYS)),
            }
        )
        return self.async_show_form(
            step_id="forecasts_monitored", data_schema=data_schema
        )

    async def async_step_warnings_basename(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask what to call the warnings sensor."""
        if user_input is not None:
            self.data.update(user_input)
            return await self._async_finish()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_WARNINGS_BASENAME,
                    default=self._default(
                        CONF_WARNINGS_BASENAME,
                        self.collector.locations_data["data"]["name"],
                    ),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="warnings_basename", data_schema=data_schema
        )


class BomConfigFlow(BomFlowSteps, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Bureau of Meteorology."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialise the config flow."""
        self.data = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Return the options flow handler."""
        return BomOptionsFlow()

    def _default(self, key: str, fallback: Any) -> Any:
        """Prefill from Home Assistant's own defaults."""
        return fallback

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        return await self._async_step_location("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the location of an existing entry to be changed."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            if error := await self._async_check_location(user_input):
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=self._location_schema(entry.data),
                    errors={"base": error},
                )
            # Moving an entry to a new place is the point of this flow, so the
            # unique ID moves with it rather than blocking the change.
            if _entry_for_geohash(self.hass, self.collector.geohash, entry.entry_id):
                return self.async_abort(reason="already_configured")
            return self.async_update_reload_and_abort(
                entry,
                data_updates=dict(user_input),
                unique_id=self.collector.geohash,
            )

        return self.async_show_form(
            step_id="reconfigure", data_schema=self._location_schema(entry.data)
        )

    def _location_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        """Return the coordinate schema prefilled from ``defaults``."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_LATITUDE,
                    default=defaults.get(CONF_LATITUDE, self.hass.config.latitude),
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE,
                    default=defaults.get(CONF_LONGITUDE, self.hass.config.longitude),
                ): cv.longitude,
            }
        )

    async def _async_check_location(self, user_input: dict[str, Any]) -> str | None:
        """Resolve the location, then guard against configuring it twice."""
        if error := await super()._async_check_location(user_input):
            return error
        if self.source != SOURCE_RECONFIGURE:
            await self.async_set_unique_id(self.collector.geohash)
            self._abort_if_unique_id_configured()
        return None

    async def _async_finish(self) -> ConfigFlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=self.collector.locations_data["data"]["name"], data=self.data
        )


class BomOptionsFlow(BomFlowSteps, OptionsFlow):
    """Handle reconfiguring an existing Bureau of Meteorology entry."""

    def __init__(self) -> None:
        """Initialise the options flow."""
        self.data = {}

    def _default(self, key: str, fallback: Any) -> Any:
        """Prefill from the entry's current options, then its original data."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, fallback)
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        return await self._async_step_location("init", user_input)

    async def _async_finish(self) -> ConfigFlowResult:
        """Store the answers, keeping the coordinates where setup reads them."""
        # async_setup_entry reads the coordinates from entry.data, so writing
        # them only to options would silently discard a location change.
        geohash = self.collector.geohash
        if _entry_for_geohash(self.hass, geohash, self.config_entry.entry_id):
            return self.async_abort(reason="already_configured")

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **self.config_entry.data,
                CONF_LATITUDE: self.data[CONF_LATITUDE],
                CONF_LONGITUDE: self.data[CONF_LONGITUDE],
            },
            # Keep the unique ID pointing at the location actually configured,
            # so it neither reserves the old place nor blocks a reconfigure.
            unique_id=geohash,
        )
        # Coordinates belong to entry.data alone. Storing them in options too
        # would let a stale option value outrank a later Reconfigure and quietly
        # move the entry back.
        return self.async_create_entry(
            data={
                key: value
                for key, value in self.data.items()
                if key not in (CONF_LATITUDE, CONF_LONGITUDE)
            }
        )
