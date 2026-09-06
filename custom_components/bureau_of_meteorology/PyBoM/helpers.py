"""Helper functions for PyBoM."""

from __future__ import annotations

import math
from typing import Any

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def flatten_dict(keys: list[str], target: dict[str, Any]) -> dict[str, Any]:
    """Flatten the nested dicts at ``keys`` into ``target`` with prefixed names.

    Keys whose value is missing or ``None`` are skipped, leaving the flattened
    names absent so callers can tell "no data" from "zero".
    """
    for key in keys:
        if target.get(key) is None:
            continue
        for inner_key, value in target.pop(key).items():
            target[f"{key}_{inner_key}"] = value
    return target


def geohash_encode(latitude: float, longitude: float, precision: int = 7) -> str:
    """Encode coordinates as a geohash of the requested precision."""
    lat_interval = (-90.0, 90.0)
    lon_interval = (-180.0, 180.0)
    geohash: list[str] = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    even = True
    while len(geohash) < precision:
        if even:
            mid = (lon_interval[0] + lon_interval[1]) / 2
            if longitude > mid:
                ch |= bits[bit]
                lon_interval = (mid, lon_interval[1])
            else:
                lon_interval = (lon_interval[0], mid)
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2
            if latitude > mid:
                ch |= bits[bit]
                lat_interval = (mid, lat_interval[1])
            else:
                lat_interval = (lat_interval[0], mid)
        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(BASE32[ch])
            bit = 0
            ch = 0
    return "".join(geohash)


def calculate_dew_point(temperature: float, humidity: float) -> float:
    """Return the dew point for a temperature and relative humidity."""
    a, b = 17.27, 237.7  # Tetens equation constants
    saturation_factor = ((a * temperature) / (b + temperature)) + math.log(
        humidity / 100.0
    )
    return round((b * saturation_factor) / (a - saturation_factor), 1)
