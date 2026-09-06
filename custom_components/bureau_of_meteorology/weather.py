"""Weather platform for the Bureau of Meteorology integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfLength, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_WEATHER_NAME, MAP_CONDITION
from .coordinator import BomConfigEntry, BomDataUpdateCoordinator
from .entity import BomEntity
from .PyBoM.helpers import calculate_dew_point

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the BOM weather entities for a config entry."""
    coordinator = config_entry.runtime_data
    location_name = config_entry.options.get(
        CONF_WEATHER_NAME, config_entry.data.get(CONF_WEATHER_NAME, "Home")
    )

    async_add_entities(
        [
            WeatherDaily(coordinator, location_name),
            WeatherHourly(coordinator, location_name),
        ]
    )


class WeatherBase(BomEntity, WeatherEntity):
    """Base representation of a BOM weather entity."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS

    def _parse_datetime(self, value: str) -> str | None:
        """Return an API timestamp as a timezone aware ISO 8601 string.

        Home Assistant expects RFC 3339 here; emitting a naive timestamp leaves
        the forecast time ambiguous.
        """
        if (parsed := dt_util.parse_datetime(value)) is None:
            return None
        return parsed.astimezone(self.tzinfo).isoformat()

    @property
    def _today(self) -> dict[str, Any]:
        """Return today's forecast, which drives the current condition."""
        daily = self.coordinator.data.daily
        return daily[0] if daily else {}

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        return MAP_CONDITION.get(self._today.get("icon_descriptor"))

    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.coordinator.data.observation.get("temp")

    @property
    def native_apparent_temperature(self) -> float | None:
        """Return the current apparent temperature."""
        return self.coordinator.data.observation.get("temp_feels_like")

    @property
    def native_dew_point(self) -> float | None:
        """Return the dew point derived from the current observation."""
        observation = self.coordinator.data.observation
        temperature = observation.get("temp")
        humidity = observation.get("humidity")
        if temperature is None or humidity is None:
            return None
        return calculate_dew_point(temperature, humidity)

    @property
    def humidity(self) -> float | None:
        """Return the current humidity."""
        return self.coordinator.data.observation.get("humidity")

    @property
    def native_wind_speed(self) -> float | None:
        """Return the current wind speed."""
        return self.coordinator.data.observation.get("wind_speed_kilometre")

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Return the current wind gust speed."""
        return self.coordinator.data.observation.get("gust_speed_kilometre")

    @property
    def wind_bearing(self) -> str | None:
        """Return the current wind bearing."""
        return self.coordinator.data.observation.get("wind_direction")


class WeatherDaily(WeatherBase):
    """Representation of a BOM daily weather entity."""

    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY
    # Takes the device name, matching the pre-1.4.0 entity name.
    _attr_name = None

    def __init__(
        self, coordinator: BomDataUpdateCoordinator, location_name: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, location_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-weather"

    async def async_forecast_daily(self) -> list[Forecast]:
        """Return the daily forecast."""
        return [
            Forecast(
                datetime=self._parse_datetime(day["date"]),
                condition=MAP_CONDITION.get(day.get("icon_descriptor")),
                native_temperature=day.get("temp_max"),
                native_templow=day.get("temp_min"),
                native_precipitation=day.get("rain_amount_max"),
                precipitation_probability=day.get("rain_chance"),
                uv_index=day.get("uv_max_index"),
            )
            for day in self.coordinator.data.daily
        ]


class WeatherHourly(WeatherBase):
    """Representation of a BOM hourly weather entity."""

    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY
    _attr_translation_key = "hourly"

    def __init__(
        self, coordinator: BomDataUpdateCoordinator, location_name: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, location_name)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-weather-hourly"

    async def async_forecast_hourly(self) -> list[Forecast]:
        """Return the hourly forecast."""
        return [
            Forecast(
                datetime=self._parse_datetime(hour["time"]),
                condition=MAP_CONDITION.get(hour.get("icon_descriptor")),
                native_temperature=hour.get("temp"),
                native_apparent_temperature=hour.get("temp_feels_like"),
                native_dew_point=hour.get("dew_point"),
                native_precipitation=hour.get("rain_amount_max"),
                precipitation_probability=hour.get("rain_chance"),
                wind_bearing=hour.get("wind_direction"),
                native_wind_speed=hour.get("wind_speed_kilometre"),
                native_wind_gust_speed=hour.get("wind_gust_speed_kilometre"),
                humidity=hour.get("relative_humidity"),
                uv_index=hour.get("uv"),
            )
            for hour in self.coordinator.data.hourly
        ]
