"""Sensor platform for the Bureau of Meteorology integration."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import ATTR_ATTRIBUTION, ATTR_DATE, ATTR_STATE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_API_DEW_POINT,
    ATTR_API_MAX_TEMP,
    ATTR_API_MIN_TEMP,
    ATTR_API_UV_FORECAST,
    ATTRIBUTION,
    CONF_FORECASTS_BASENAME,
    CONF_FORECASTS_CREATE,
    CONF_FORECASTS_DAYS,
    CONF_FORECASTS_MONITORED,
    CONF_OBSERVATIONS_BASENAME,
    CONF_OBSERVATIONS_CREATE,
    CONF_OBSERVATIONS_MONITORED,
    CONF_WARNINGS_BASENAME,
    CONF_WARNINGS_CREATE,
    FORECAST_SENSOR_TYPES,
    NOW_LATER_KEYS,
    OBSERVATION_SENSOR_TYPES,
    WARNING_SENSOR_TYPES,
)
from .coordinator import BomConfigEntry, BomDataUpdateCoordinator
from .entity import BomEntity
from .PyBoM.helpers import calculate_dew_point

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

MAX_STATE_LENGTH = 251

# Values that are dicts of {time, value} rather than a plain reading.
TIMED_OBSERVATIONS = (ATTR_API_MAX_TEMP, ATTR_API_MIN_TEMP)


def _description(
    descriptions: tuple[SensorEntityDescription, ...], key: str
) -> SensorEntityDescription | None:
    """Return the description matching ``key``, if the component still has one."""
    return next((item for item in descriptions if item.key == key), None)


def _option(entry: BomConfigEntry, key: str, default: Any = None) -> Any:
    """Read a setting from options, falling back to the original entry data."""
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the BOM sensors for a config entry."""
    coordinator = config_entry.runtime_data
    entities: list[SensorBase] = []

    if _option(config_entry, CONF_OBSERVATIONS_CREATE) is True:
        basename = _option(config_entry, CONF_OBSERVATIONS_BASENAME)
        for sensor in _option(config_entry, CONF_OBSERVATIONS_MONITORED) or []:
            if description := _description(OBSERVATION_SENSOR_TYPES, sensor):
                entities.append(ObservationSensor(coordinator, basename, description))

    if _option(config_entry, CONF_FORECASTS_CREATE) is True:
        basename = _option(config_entry, CONF_FORECASTS_BASENAME)
        monitored = _option(config_entry, CONF_FORECASTS_MONITORED) or []
        for day in range(_option(config_entry, CONF_FORECASTS_DAYS, 0) + 1):
            for sensor in monitored:
                description = _description(FORECAST_SENSOR_TYPES, sensor)
                if description is None:
                    continue
                if sensor in NOW_LATER_KEYS:
                    if day == 0:
                        entities.append(
                            NowLaterSensor(coordinator, basename, description)
                        )
                else:
                    entities.append(
                        ForecastSensor(coordinator, basename, day, description)
                    )

    if _option(config_entry, CONF_WARNINGS_CREATE) is True:
        basename = _option(config_entry, CONF_WARNINGS_BASENAME) or _option(
            config_entry, CONF_FORECASTS_BASENAME
        )
        description = _description(WARNING_SENSOR_TYPES, "warnings")
        if basename is not None and description is not None:
            entities.append(WarningsSensor(coordinator, basename, description))

    async_add_entities(entities)


class SensorBase(BomEntity, SensorEntity):
    """Base representation of a BOM sensor."""

    def __init__(
        self,
        coordinator: BomDataUpdateCoordinator,
        location_name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, location_name)
        self.entity_description = description
        self.sensor_name = description.key

    def _parse_timestamp(self, value: str | None) -> datetime | None:
        """Parse an API timestamp into a timezone aware datetime."""
        if value is None:
            return None
        if (parsed := dt_util.parse_datetime(value)) is None:
            _LOGGER.debug("Could not parse %s as a timestamp", value)
            return None
        return parsed.astimezone(self.tzinfo)

    def _timestamped_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of an API metadata block with timestamps localised."""
        attributes: dict[str, Any] = {}
        for key, value in metadata.items():
            parsed = self._parse_timestamp(value) if isinstance(value, str) else None
            attributes[key] = parsed.isoformat() if parsed else value
        attributes[ATTR_ATTRIBUTION] = ATTRIBUTION
        return attributes


class ObservationSensor(SensorBase):
    """Representation of a BOM observation sensor."""

    def __init__(
        self,
        coordinator: BomDataUpdateCoordinator,
        location_name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, location_name, description)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-observation-{description.key}"
        )

    @property
    def available(self) -> bool:
        """Return whether the BOM is currently reporting this observation."""
        if not super().available:
            return False
        if self.sensor_name == ATTR_API_DEW_POINT:
            observation = self.coordinator.data.observation
            return (
                observation.get("temp") is not None
                and observation.get("humidity") is not None
            )
        return self.sensor_name in self.coordinator.data.observation

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        observation = self.coordinator.data.observation

        if self.sensor_name == ATTR_API_DEW_POINT:
            temperature = observation.get("temp")
            humidity = observation.get("humidity")
            if temperature is None or humidity is None:
                return None
            return calculate_dew_point(temperature, humidity)

        value = observation.get(self.sensor_name)
        if value is None:
            return None
        if self.sensor_name in TIMED_OBSERVATIONS:
            return value.get("value")
        if self.device_class is SensorDeviceClass.TIMESTAMP:
            return self._parse_timestamp(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the sensor."""
        data = self.coordinator.data
        attributes = self._timestamped_metadata(data.observations.get("metadata", {}))
        attributes.update(data.observation.get("station", {}))

        if self.sensor_name in TIMED_OBSERVATIONS:
            reading = data.observation.get(self.sensor_name) or {}
            if observed := self._parse_timestamp(reading.get("time")):
                attributes["time_observed"] = observed.isoformat()

        return attributes


class ForecastSensor(SensorBase):
    """Representation of a BOM forecast sensor for a single day."""

    def __init__(
        self,
        coordinator: BomDataUpdateCoordinator,
        location_name: str,
        day: int,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, location_name, description)
        self.day = day
        self._attr_translation_placeholders = {"day": str(day)}
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-forecast-{day}-{description.key}"
        )

    @property
    def _forecast(self) -> dict[str, Any] | None:
        """Return this sensor's forecast day, if the BOM still publishes it."""
        daily = self.coordinator.data.daily
        return daily[self.day] if self.day < len(daily) else None

    @property
    def available(self) -> bool:
        """Return whether a forecast exists this far out."""
        return super().available and self._forecast is not None

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if (forecast := self._forecast) is None:
            return None

        if self.sensor_name == ATTR_API_UV_FORECAST:
            return self._uv_forecast(forecast)

        value = forecast.get(self.sensor_name)

        if self.device_class is SensorDeviceClass.TIMESTAMP:
            return self._parse_timestamp(value)
        if self.sensor_name == "uv_category" and value is not None:
            return value.replace("veryhigh", "very high").title()
        if isinstance(value, str) and len(value) > MAX_STATE_LENGTH:
            # Home Assistant rejects states longer than 255 characters; the full
            # text is still available via the extended forecast attribute.
            return f"{value[:MAX_STATE_LENGTH]}..."
        return value

    def _uv_forecast(self, forecast: dict[str, Any]) -> str | None:
        """Build the human readable sun protection summary."""
        category = forecast.get("uv_category")
        if category is None:
            return None

        category = category.replace("veryhigh", "very high").title()
        max_index = forecast.get("uv_max_index")

        start_time = self._parse_timestamp(forecast.get("uv_start_time"))
        end_time = self._parse_timestamp(forecast.get("uv_end_time"))
        if start_time is None or end_time is None:
            return (
                "Sun protection not required, UV Index predicted to reach "
                f"{max_index} [{category}]"
            )

        return (
            f"Sun protection recommended from {_format_time(start_time)} to "
            f"{_format_time(end_time)}, UV Index predicted to reach "
            f"{max_index} [{category}]"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the sensor."""
        if (forecast := self._forecast) is None:
            return {}

        data = self.coordinator.data
        attributes = self._timestamped_metadata(
            data.daily_forecasts.get("metadata", {})
        )

        if forecast_date := self._parse_timestamp(forecast.get("date")):
            attributes[ATTR_DATE] = forecast_date.isoformat()

        if self.sensor_name == "fire_danger":
            category = forecast.get("fire_danger_category") or {}
            if colour := category.get("default_colour"):
                attributes["color_fill"] = colour
                attributes["color_text"] = (
                    "#ffffff" if category.get("text") == "Catastrophic" else "#000000"
                )

        if self.sensor_name.startswith("extended"):
            attributes[ATTR_STATE] = forecast.get("extended_text")

        return attributes


class NowLaterSensor(SensorBase):
    """Representation of a BOM now/later forecast sensor."""

    def __init__(
        self,
        coordinator: BomDataUpdateCoordinator,
        location_name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, location_name, description)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-nowlater-{description.key}"
        )

    @property
    def available(self) -> bool:
        """Return whether today's forecast is available."""
        return super().available and bool(self.coordinator.data.daily)

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        daily = self.coordinator.data.daily
        return daily[0].get(self.sensor_name) if daily else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the sensor."""
        return self._timestamped_metadata(
            self.coordinator.data.daily_forecasts.get("metadata", {})
        )


class WarningsSensor(SensorBase):
    """Representation of a BOM warnings sensor."""

    def __init__(
        self,
        coordinator: BomDataUpdateCoordinator,
        location_name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, location_name, description)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-warnings"

    @property
    def native_value(self) -> int:
        """Return the number of current warnings."""
        return len(self.coordinator.data.warning_list)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the sensor."""
        data = self.coordinator.data
        attributes = self._timestamped_metadata(data.warnings.get("metadata", {}))
        attributes["warnings"] = data.warning_list
        return attributes


def _format_time(value: datetime) -> str:
    """Format a time the way the BOM presents UV protection windows."""
    return value.strftime("%I:%M%p").lstrip("0").lower()
