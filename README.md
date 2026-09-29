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

You will first be asked how to set your location. You can **search for a suburb
or postcode** (for example `Blackburn` or `3130`) and pick from the matches, or
enter latitude and longitude manually — the manual form defaults to your Home
zone. Searching uses the Bureau's own location index, so you get the same place
the BoM website would use for that name.

You are then asked for a name for the weather entities, and which observation,
forecast and warning sensors you would like to create.

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

## Upgrading from 1.3.x

Requires Home Assistant 2025.2.0 or later. Existing entities are migrated
automatically, so your entity IDs, history and automations are unchanged.
Friendly names do change: sensors now use their full descriptive name (for
example `Melbourne Current Temperature` rather than `Melbourne Temp`).

Going back to a 1.3.x release afterwards creates duplicate entities with a `_2`
suffix, because those releases identify entities differently. Upgrading again
removes the duplicates and restores the originals.

## Release Notes

See the [releases page][releases].

[releases]: https://github.com/bremor/bureau_of_meteorology/releases
