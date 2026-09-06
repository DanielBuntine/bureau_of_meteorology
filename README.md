# Bureau of Meteorology Custom Component

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![GitHub Release](https://img.shields.io/github/v/release/bremor/bureau_of_meteorology?style=for-the-badge)
![GitHub License](https://img.shields.io/github/license/bremor/bureau_of_meteorology?style=for-the-badge)
![Maintenance](https://img.shields.io/maintenance/yes/2026?style=for-the-badge)

## **This integration only supports locations within Australia.**

This Home Assistant custom component uses the [Bureau of Meteorology (BOM)](http://www.bom.gov.au) as a source for weather information.

**Requires Home Assistant 2025.2.0 or later.**

## Installation (There are two methods, with HACS or manual)

Install via HACS (default store) or install manually by copying the files in a new 'custom_components/bureau_of_meteorology' directory.

## Configuration

After you have installed the custom component (see above):

1. Goto the `Configuration` -> `Integrations` page.
2. On the bottom right of the page, click on the `+ Add Integration` sign to add an integration.
3. Search for `Bureau of Meteorology`. (If you don't see it, try refreshing your browser page to reload the cache.)
4. Click `Submit` so add the integration.

You will be asked for the latitude and longitude to use (defaulting to your Home
zone), a name for the weather entities, and then which observation, forecast and
warning sensors you would like to create.

To change any of these later, use `Configure` on the integration. To move the
integration to a different location, use `Reconfigure`.

## What you get

| Entity | Description |
| --- | --- |
| `weather.<name>` | Current conditions plus a nine day forecast. |
| `weather.<name>_hourly` | Current conditions plus a three day hourly forecast. |
| Observation sensors | Temperature, apparent temperature, today's observed max/min, humidity, dew point, rain since 9am, wind and gust speed/direction, maximum gust, and the distance to the reporting station. |
| Forecast sensors | Per day: max/min temperature, short and extended text, icon, UV, rain amount and chance, fire danger, and sunrise/sunset times. |
| Warnings sensor | A count of current warnings, with the full list as an attribute. |

Forecasts are served through the `weather.get_forecasts` action. The weather
entities expose current temperature, apparent temperature, dew point, humidity,
wind speed, wind gust speed and wind bearing.

## Troubleshooting

Please set your logging for the custom_component to debug:

```yaml
logger:
  default: warn
  logs:
    custom_components.bureau_of_meteorology: debug
```

### Notes

1. This integration will not refresh data faster than once every 5 minutes.
2. All feature requests, issues and questions are welcome.

## Release Notes

Older release notes are on the [releases page][releases].

### 1.4.0 - Modernisation for current Home Assistant

Home Assistant compatibility:
- Requires Home Assistant 2025.2.0 or later.
- Moved to `ConfigEntry.runtime_data`, a dedicated coordinator module, and a
  shared entity base class.
- Entities now use `has_entity_name` with translated names and icons, so they
  are named consistently and can be translated.
- Unique IDs are now scoped to the config entry. Existing entities are migrated
  automatically, so **your entity IDs, history and automations are unchanged**.
  Friendly names do change: sensors now use their full descriptive name (for
  example `Melbourne Current Temperature` rather than `Melbourne Temp`).
- Added a reconfigure flow, diagnostics, and duplicate location detection.
- Dropped the `iso8601` dependency in favour of Home Assistant's own utilities.

Fixes:
- Forecast timestamps are now timezone aware. They were previously emitted
  without an offset, leaving forecast times ambiguous.
- Forecast minimum temperature and wind gust speed now reach the weather card.
  They were being passed in fields Home Assistant no longer reads.
- Migrating a version 1 config entry no longer fails.
- Changing the location via `Configure` now actually takes effect.
- Renaming an entity no longer causes it to be deleted on the next reload.
- Sensors with no data are now correctly unavailable instead of reporting the
  literal string `unavailable`.
- Timestamp sensors now emit real timestamps rather than strings.
- Removed three overlapping rate limits that could leave the coordinator with
  no data, and a listener leak on reload.

New:
- Weather entities expose apparent temperature and dew point; hourly forecasts
  add dew point and apparent temperature.
- New sensors for maximum gust speed, maximum gust time, and the distance to
  the observation station.
- The location is now resolved through the BOM's own search endpoint at full
  geohash precision.
- Added a test suite plus hassfest, HACS and lint checks in CI.

[releases]: https://github.com/bremor/bureau_of_meteorology/releases
