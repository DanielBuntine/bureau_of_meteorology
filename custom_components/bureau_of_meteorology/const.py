"""Constants for the BOM integration."""

from typing import Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)

ATTRIBUTION: Final = "Data provided by the Australian Bureau of Meteorology"
SHORT_ATTRIBUTION: Final = "Australian Bureau of Meteorology"
MODEL_NAME: Final = "Weather Sensor"

CONF_WEATHER_NAME: Final = "weather_name"
CONF_FORECASTS_BASENAME: Final = "forecasts_basename"
CONF_FORECASTS_CREATE: Final = "forecasts_create"
CONF_FORECASTS_DAYS: Final = "forecasts_days"
CONF_FORECASTS_MONITORED: Final = "forecasts_monitored"
CONF_OBSERVATIONS_BASENAME: Final = "observations_basename"
CONF_OBSERVATIONS_CREATE: Final = "observations_create"
CONF_OBSERVATIONS_MONITORED: Final = "observations_monitored"
CONF_WARNINGS_CREATE: Final = "warnings_create"
CONF_WARNINGS_BASENAME: Final = "warnings_basename"

DOMAIN: Final = "bureau_of_meteorology"

MAP_CONDITION: Final = {
    "clear": "clear-night",
    "cloudy": "cloudy",
    "cyclone": "exceptional",
    "dust": "fog",
    "dusty": "fog",
    "fog": "fog",
    "frost": "snowy",
    "haze": "fog",
    "hazy": "fog",
    "heavy_shower": "rainy",
    "heavy_showers": "rainy",
    "light_rain": "rainy",
    "light_shower": "rainy",
    "light_showers": "rainy",
    "mostly_sunny": "sunny",
    "partly_cloudy": "partlycloudy",
    "rain": "rainy",
    "shower": "rainy",
    "showers": "rainy",
    "snow": "snowy",
    "storm": "lightning-rainy",
    "storms": "lightning-rainy",
    "sunny": "sunny",
    "tropical_cyclone": "exceptional",
    "wind": "windy",
    "windy": "windy",
    None: None,
}

ATTR_API_TEMP: Final = "temp"
ATTR_API_TEMP_FEELS_LIKE: Final = "temp_feels_like"
ATTR_API_MAX_TEMP: Final = "max_temp"
ATTR_API_MIN_TEMP: Final = "min_temp"
ATTR_API_RAIN_SINCE_9AM: Final = "rain_since_9am"
ATTR_API_HUMIDITY: Final = "humidity"
ATTR_API_WIND_SPEED_KILOMETRE: Final = "wind_speed_kilometre"
ATTR_API_WIND_SPEED_KNOT: Final = "wind_speed_knot"
ATTR_API_WIND_DIRECTION: Final = "wind_direction"
ATTR_API_GUST_SPEED_KILOMETRE: Final = "gust_speed_kilometre"
ATTR_API_GUST_SPEED_KNOT: Final = "gust_speed_knot"
ATTR_API_MAX_GUST_SPEED_KILOMETRE: Final = "max_gust_speed_kilometre"
ATTR_API_MAX_GUST_SPEED_KNOT: Final = "max_gust_speed_knot"
ATTR_API_MAX_GUST_TIME: Final = "max_gust_time"
ATTR_API_STATION_DISTANCE: Final = "station_distance"
ATTR_API_DEW_POINT: Final = "dew_point"

ATTR_API_TEMP_MAX: Final = "temp_max"
ATTR_API_TEMP_MIN: Final = "temp_min"
ATTR_API_EXTENDED_TEXT: Final = "extended_text"
ATTR_API_ICON_DESCRIPTOR: Final = "icon_descriptor"
ATTR_API_MDI_ICON: Final = "mdi_icon"
ATTR_API_SHORT_TEXT: Final = "short_text"
ATTR_API_UV_CATEGORY: Final = "uv_category"
ATTR_API_UV_MAX_INDEX: Final = "uv_max_index"
ATTR_API_UV_START_TIME: Final = "uv_start_time"
ATTR_API_UV_END_TIME: Final = "uv_end_time"
ATTR_API_UV_FORECAST: Final = "uv_forecast"
ATTR_API_RAIN_AMOUNT_MIN: Final = "rain_amount_min"
ATTR_API_RAIN_AMOUNT_MAX: Final = "rain_amount_max"
ATTR_API_RAIN_AMOUNT_RANGE: Final = "rain_amount_range"
ATTR_API_RAIN_CHANCE: Final = "rain_chance"
ATTR_API_FIRE_DANGER: Final = "fire_danger"
ATTR_API_NON_NOW_LABEL: Final = "now_now_label"
ATTR_API_NON_TEMP_NOW: Final = "now_temp_now"
ATTR_API_NOW_LATER_LABEL: Final = "now_later_label"
ATTR_API_NOW_TEMP_LATER: Final = "now_temp_later"
ATTR_API_ASTRONOMICAL_SUNRISE_TIME: Final = "astronomical_sunrise_time"
ATTR_API_ASTRONOMICAL_SUNSET_TIME: Final = "astronomical_sunset_time"
ATTR_API_WARNINGS: Final = "warnings"

# Forecast keys that only ever apply to today, and so are created once rather
# than once per forecast day.
NOW_LATER_KEYS: Final = frozenset(
    {
        ATTR_API_NON_NOW_LABEL,
        ATTR_API_NON_TEMP_NOW,
        ATTR_API_NOW_LATER_LABEL,
        ATTR_API_NOW_TEMP_LATER,
    }
)

SENSOR_LABELS: Final[dict[str, str]] = {
    "astronomical_sunrise_time": "Sunrise Time",
    "astronomical_sunset_time": "Sunset Time",
    "dew_point": "Dew Point",
    "extended_text": "Extended Forecast",
    "fire_danger": "Fire Danger",
    "gust_speed_kilometre": "Gust Speed km/h",
    "gust_speed_knot": "Gust Speed kn",
    "humidity": "Humidity",
    "icon_descriptor": "Icon Descriptor",
    "max_gust_speed_kilometre": "Maximum Gust Speed km/h",
    "max_gust_speed_knot": "Maximum Gust Speed kn",
    "max_gust_time": "Maximum Gust Time",
    "max_temp": "Todays Observed Maximum Temperature",
    "mdi_icon": "MDI Icon",
    "min_temp": "Todays Observed Minimum Temperature",
    "now_later_label": "Later Label",
    "now_now_label": "Now Label",
    "now_temp_later": "Later Temperature",
    "now_temp_now": "Now Temperature",
    "rain_amount_max": "Rain Amount Maximum",
    "rain_amount_min": "Rain Amount Minimum",
    "rain_amount_range": "Rain Amount Range",
    "rain_chance": "Rain Probability",
    "rain_since_9am": "Rain Since 9am",
    "short_text": "Short Summary Forecast",
    "station_distance": "Observation Station Distance",
    "temp": "Current Temperature",
    "temp_feels_like": "Current Feels Like Temperature",
    "temp_max": "Forecast Maximum Temperature",
    "temp_min": "Forecast Minimum Temperature",
    "uv_category": "UV Category",
    "uv_end_time": "UV Protection End Time",
    "uv_forecast": "UV Forecast Summary",
    "uv_max_index": "UV Maximum Index",
    "uv_start_time": "UV Protection Start Time",
    "warnings": "Warnings",
    "wind_direction": "Wind Direction",
    "wind_speed_kilometre": "Wind Speed km/h",
    "wind_speed_knot": "Wind Speed kn",
}

OBSERVATION_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_API_TEMP,
        translation_key="temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_TEMP_FEELS_LIKE,
        translation_key="temp_feels_like",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_MAX_TEMP,
        translation_key="max_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_MIN_TEMP,
        translation_key="min_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_RAIN_SINCE_9AM,
        translation_key="rain_since_9am",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key=ATTR_API_HUMIDITY,
        translation_key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_WIND_SPEED_KILOMETRE,
        translation_key="wind_speed_kilometre",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_WIND_SPEED_KNOT,
        translation_key="wind_speed_knot",
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_WIND_DIRECTION,
        translation_key="wind_direction",
    ),
    SensorEntityDescription(
        key=ATTR_API_GUST_SPEED_KILOMETRE,
        translation_key="gust_speed_kilometre",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_GUST_SPEED_KNOT,
        translation_key="gust_speed_knot",
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_MAX_GUST_SPEED_KILOMETRE,
        translation_key="max_gust_speed_kilometre",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_MAX_GUST_SPEED_KNOT,
        translation_key="max_gust_speed_knot",
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_API_MAX_GUST_TIME,
        translation_key="max_gust_time",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=ATTR_API_STATION_DISTANCE,
        translation_key="station_distance",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="dew_point",
        translation_key="dew_point",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

FORECAST_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_API_TEMP_MAX,
        translation_key="temp_max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key=ATTR_API_TEMP_MIN,
        translation_key="temp_min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key=ATTR_API_EXTENDED_TEXT,
        translation_key="extended_text",
    ),
    SensorEntityDescription(
        key=ATTR_API_ICON_DESCRIPTOR,
        translation_key="icon_descriptor",
    ),
    SensorEntityDescription(
        key=ATTR_API_MDI_ICON,
        translation_key="mdi_icon",
    ),
    SensorEntityDescription(
        key=ATTR_API_SHORT_TEXT,
        translation_key="short_text",
    ),
    SensorEntityDescription(
        key=ATTR_API_UV_CATEGORY,
        translation_key="uv_category",
    ),
    SensorEntityDescription(
        key=ATTR_API_UV_MAX_INDEX,
        translation_key="uv_max_index",
    ),
    SensorEntityDescription(
        key=ATTR_API_UV_START_TIME,
        translation_key="uv_start_time",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=ATTR_API_UV_END_TIME,
        translation_key="uv_end_time",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=ATTR_API_UV_FORECAST,
        translation_key="uv_forecast",
    ),
    SensorEntityDescription(
        key=ATTR_API_RAIN_AMOUNT_MIN,
        translation_key="rain_amount_min",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
    ),
    SensorEntityDescription(
        key=ATTR_API_RAIN_AMOUNT_MAX,
        translation_key="rain_amount_max",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
    ),
    SensorEntityDescription(
        key=ATTR_API_RAIN_AMOUNT_RANGE,
        translation_key="rain_amount_range",
    ),
    SensorEntityDescription(
        key=ATTR_API_RAIN_CHANCE,
        translation_key="rain_chance",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key=ATTR_API_FIRE_DANGER,
        translation_key="fire_danger",
    ),
    SensorEntityDescription(
        key=ATTR_API_NON_NOW_LABEL,
        translation_key="now_now_label",
    ),
    SensorEntityDescription(
        key=ATTR_API_NON_TEMP_NOW,
        translation_key="now_temp_now",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key=ATTR_API_NOW_LATER_LABEL,
        translation_key="now_later_label",
    ),
    SensorEntityDescription(
        key=ATTR_API_NOW_TEMP_LATER,
        translation_key="now_temp_later",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key=ATTR_API_ASTRONOMICAL_SUNRISE_TIME,
        translation_key="astronomical_sunrise_time",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=ATTR_API_ASTRONOMICAL_SUNSET_TIME,
        translation_key="astronomical_sunset_time",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

WARNING_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_API_WARNINGS,
        translation_key="warnings",
    ),
)
