"""BOM data collector that downloads observation, forecast and warning data."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
import logging
import time
from typing import Any

import aiohttp

from .const import (
    MAP_MDI_ICON,
    URL_BASE,
    URL_DAILY,
    URL_HOURLY,
    URL_OBSERVATIONS,
    URL_SEARCH,
    URL_WARNINGS,
    USER_AGENT,
)
from .helpers import flatten_dict, geohash_encode

_LOGGER = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds, exponential
MAX_CACHE_AGE = 86400  # 24 hours in seconds
REQUEST_TIMEOUT = 30  # seconds

# The location resource accepts a six or seven character geohash, but every
# sub-resource (observations, forecasts, warnings) rejects seven characters
# with HTTP 400. Look the location up at full precision, then truncate.
GEOHASH_LOCATION_LENGTH = 7
GEOHASH_SUBRESOURCE_LENGTH = 6


class BomApiError(Exception):
    """Raised when the BOM API cannot be reached or returns unusable data."""

    def __init__(self, message: str = "", status: int | None = None) -> None:
        """Store the HTTP status alongside the message, when there was one."""
        super().__init__(message)
        self.status = status


class BomLocationError(BomApiError):
    """Raised when coordinates fall outside the BOM coverage area."""


async def _get(
    session: aiohttp.ClientSession,
    url: str,
    params: dict[str, str] | None = None,
) -> Any:
    """Perform a single GET, raising BomApiError for anything unusable."""
    async with session.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
    ) as response:
        if response.status != 200:
            raise BomApiError(f"{url} returned HTTP {response.status}", response.status)
        return await response.json()


async def async_search_locations(
    session: aiohttp.ClientSession, query: str
) -> list[dict[str, Any]]:
    """Return BOM locations matching a place name, postcode or "lat,lon".

    The BOM's own search index, so a name resolves to exactly the location the
    Bureau would use. An empty list means nothing matched.
    """
    try:
        result = await _get(session, URL_SEARCH, {"search": query})
    except (aiohttp.ClientError, TimeoutError) as err:
        raise BomApiError(f"Could not search for a location: {err}") from err
    return result.get("data") or []


async def async_location_detail(
    session: aiohttp.ClientSession, geohash: str
) -> dict[str, Any]:
    """Return the full record for a geohash, including its coordinates."""
    try:
        result = await _get(session, URL_BASE + geohash)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise BomApiError(f"Could not look up {geohash}: {err}") from err
    return result.get("data") or {}


@dataclass
class BomData:
    """Snapshot of everything the collector fetched in one update."""

    locations: dict[str, Any] = field(default_factory=dict)
    observations: dict[str, Any] = field(default_factory=dict)
    daily_forecasts: dict[str, Any] = field(default_factory=dict)
    hourly_forecasts: dict[str, Any] = field(default_factory=dict)
    warnings: dict[str, Any] = field(default_factory=dict)

    @property
    def timezone(self) -> str:
        """Return the IANA timezone name reported for this location."""
        return self.locations.get("data", {}).get("timezone", "UTC")

    @property
    def location_name(self) -> str | None:
        """Return the BOM's own name for this location."""
        return self.locations.get("data", {}).get("name")

    @property
    def observation(self) -> dict[str, Any]:
        """Return the observation payload, or an empty dict."""
        return self.observations.get("data") or {}

    @property
    def daily(self) -> list[dict[str, Any]]:
        """Return the list of daily forecasts, or an empty list."""
        return self.daily_forecasts.get("data") or []

    @property
    def hourly(self) -> list[dict[str, Any]]:
        """Return the list of hourly forecasts, or an empty list."""
        return self.hourly_forecasts.get("data") or []

    @property
    def warning_list(self) -> list[dict[str, Any]]:
        """Return the list of active warnings, or an empty list."""
        return self.warnings.get("data") or []


class Collector:
    """Fetches and normalises data from the BOM weather API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        latitude: float,
        longitude: float,
    ) -> None:
        """Initialise the collector against a Home Assistant managed session."""
        self._session = session
        self.latitude = latitude
        self.longitude = longitude

        # Resolved lazily from the API on first use.
        self.geohash: str | None = None

        self.locations_data: dict[str, Any] | None = None
        self.observations_data: dict[str, Any] | None = None
        self.daily_forecasts_data: dict[str, Any] | None = None
        self.hourly_forecasts_data: dict[str, Any] | None = None
        self.warnings_data: dict[str, Any] | None = None

        self._cache: dict[str, tuple[dict[str, Any], float]] = {}

    @property
    def geohash6(self) -> str:
        """Return the six character geohash used for every sub-resource."""
        if self.geohash is None:
            raise BomApiError("Location has not been resolved yet")
        return self.geohash[:GEOHASH_SUBRESOURCE_LENGTH]

    async def _request(self, url: str, params: dict[str, str] | None = None) -> Any:
        """Perform a single GET, raising BomApiError for anything unusable."""
        return await _get(self._session, url, params)

    async def _fetch(self, url: str, cache_key: str) -> dict[str, Any]:
        """Fetch a resource, retrying transient failures and caching the result.

        Falls back to the last good response for this resource if it is still
        within MAX_CACHE_AGE, so a brief BOM outage does not blank every entity.
        """
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                data = await self._request(url)
            except BomApiError as err:
                # A 4xx is a bad request, not a blip -- retrying will not help.
                last_error = err
                if err.status is not None and err.status < 500:
                    break
            except (aiohttp.ClientError, TimeoutError) as err:
                last_error = err
            else:
                # The caller normalises this payload in place, so keep an
                # untouched copy: re-formatting an already-formatted response
                # would rewrite values such as rain_amount_range.
                self._cache[cache_key] = (copy.deepcopy(data), time.monotonic())
                return data

            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE**attempt
                _LOGGER.debug(
                    "Attempt %s/%s for %s failed (%s), retrying in %ss",
                    attempt + 1,
                    MAX_RETRIES,
                    cache_key,
                    last_error,
                    delay,
                )
                await asyncio.sleep(delay)

        cached = self._cache.get(cache_key)
        if cached is not None:
            data, timestamp = cached
            age = time.monotonic() - timestamp
            if age <= MAX_CACHE_AGE:
                _LOGGER.warning(
                    "Could not refresh %s (%s), using data from %s minutes ago",
                    cache_key,
                    last_error,
                    int(age / 60),
                )
                return copy.deepcopy(data)
            self._cache.pop(cache_key, None)

        status = last_error.status if isinstance(last_error, BomApiError) else None
        raise BomApiError(f"Could not fetch {cache_key}: {last_error}", status)

    async def async_resolve_location(self) -> None:
        """Resolve the configured coordinates to a BOM geohash.

        Uses the documented search endpoint so the geohash matches the one the
        BOM itself would pick, and falls back to encoding the coordinates
        locally if the search returns nothing useful.
        """
        try:
            result = await self._request(
                URL_SEARCH, params={"search": f"{self.latitude},{self.longitude}"}
            )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BomApiError(f"Could not search for location: {err}") from err

        matches = result.get("data") or []
        if matches and matches[0].get("geohash"):
            self.geohash = matches[0]["geohash"]
        else:
            # Outside the search index, but the coordinates may still be
            # covered -- fall back to a locally encoded geohash.
            self.geohash = geohash_encode(
                self.latitude, self.longitude, GEOHASH_LOCATION_LENGTH
            )
            _LOGGER.debug(
                "No search result for %s,%s, falling back to geohash %s",
                self.latitude,
                self.longitude,
                self.geohash,
            )

        try:
            self.locations_data = await self._fetch(
                URL_BASE + self.geohash, "locations"
            )
        except BomApiError as err:
            self.geohash = None
            # Only a definitive rejection means the coordinates are outside
            # coverage. A timeout or 5xx is transient, and reporting it as a
            # bad location would tell the user their valid Australian
            # coordinates are unsupported.
            if err.status in (400, 404):
                raise BomLocationError(
                    f"No BOM location for {self.latitude},{self.longitude}"
                ) from err
            raise

    def _format_observations(self, data: dict[str, Any]) -> None:
        """Flatten the nested wind and gust groups in an observation payload."""
        observation = data.get("data")
        if not observation:
            return
        flatten_dict(["wind", "gust", "max_gust"], observation)
        if station := observation.get("station"):
            observation["station_name"] = station.get("name")
            observation["station_distance"] = station.get("distance")

    def _resolve_icon(self, entry: dict[str, Any], is_night: bool | None) -> None:
        """Reconcile the icon descriptor with whether it is currently night."""
        descriptor = entry.get("icon_descriptor")
        if is_night and descriptor in {"sunny", "mostly_sunny"}:
            entry["icon_descriptor"] = "clear"
        elif not is_night and descriptor == "clear":
            entry["icon_descriptor"] = "sunny"
        entry["mdi_icon"] = MAP_MDI_ICON.get(entry.get("icon_descriptor"))

    def _format_rain_range(self, entry: dict[str, Any]) -> None:
        """Normalise the rain amount range into a single display string."""
        if entry.get("rain_amount_max") is None:
            entry["rain_amount_max"] = entry.get("rain_amount_min")
            entry["rain_amount_range"] = entry.get("rain_amount_min")
        else:
            # The en dash is deliberate; it matches how the BOM presents ranges.
            entry["rain_amount_range"] = (
                f"{entry['rain_amount_min']}–{entry['rain_amount_max']}"  # noqa: RUF001
            )

    def _format_daily_forecasts(self, data: dict[str, Any]) -> None:
        """Flatten and normalise the daily forecast payload."""
        for day, entry in enumerate(data.get("data") or []):
            flatten_dict(["amount"], entry.get("rain", {}))
            flatten_dict(["rain", "uv", "astronomical"], entry)

            if day == 0:
                flatten_dict(["now"], entry)
                self._resolve_icon(entry, entry.get("now_is_night"))
            else:
                entry["mdi_icon"] = MAP_MDI_ICON.get(entry.get("icon_descriptor"))

            self._format_rain_range(entry)

    def _format_hourly_forecasts(self, data: dict[str, Any]) -> None:
        """Flatten and normalise the hourly forecast payload."""
        for entry in data.get("data") or []:
            self._resolve_icon(entry, entry.get("is_night"))
            flatten_dict(["amount"], entry.get("rain", {}))
            flatten_dict(["rain", "wind"], entry)
            self._format_rain_range(entry)

    async def async_update(self) -> BomData:
        """Refresh every resource and return the resulting snapshot."""
        if self.geohash is None:
            await self.async_resolve_location()

        geohash = self.geohash6

        # The location resource only carries static metadata (name, timezone),
        # so it is fetched once when the geohash is resolved.
        observations, daily, hourly, warnings = await asyncio.gather(
            self._fetch(URL_BASE + geohash + URL_OBSERVATIONS, "observations"),
            self._fetch(URL_BASE + geohash + URL_DAILY, "daily_forecasts"),
            self._fetch(URL_BASE + geohash + URL_HOURLY, "hourly_forecasts"),
            self._fetch(URL_BASE + geohash + URL_WARNINGS, "warnings"),
        )

        self._format_observations(observations)
        self._format_daily_forecasts(daily)
        self._format_hourly_forecasts(hourly)

        self.observations_data = observations
        self.daily_forecasts_data = daily
        self.hourly_forecasts_data = hourly
        self.warnings_data = warnings

        return BomData(
            locations=self.locations_data or {},
            observations=observations,
            daily_forecasts=daily,
            hourly_forecasts=hourly,
            warnings=warnings,
        )
