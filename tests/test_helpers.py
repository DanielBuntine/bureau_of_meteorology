"""Tests for the PyBoM helper functions.

Several cases here are carried over from the upstream
``tests/test_pybom_helpers_and_formatters.py``, which was written against the
pre-1.4.0 architecture and could not survive the rewrite.
"""

from __future__ import annotations

import pytest

from custom_components.bureau_of_meteorology.PyBoM.helpers import (
    calculate_dew_point,
    flatten_dict,
    geohash_encode,
)


@pytest.mark.parametrize(
    ("latitude", "longitude", "precision", "expected"),
    [
        (-12.463763, 130.844398, 7, "qvv117j"),
        (-12.463302612304688, 130.84510803222656, 7, "qvv117n"),
        (0, 0, 6, "7zzzzz"),
        (-37.8136, 144.9631, 6, "r1r0fs"),
    ],
)
def test_geohash_encode_known_values(latitude, longitude, precision, expected):
    assert geohash_encode(latitude, longitude, precision) == expected


def test_geohash_encode_defaults_to_seven_characters():
    assert len(geohash_encode(-37.8136, 144.9631)) == 7


def test_flatten_dict_mutates_in_place():
    payload = {"amount": {"min": 2, "max": 5}, "chance": 40}
    result = flatten_dict(["amount"], payload)

    assert result is payload
    assert payload == {"chance": 40, "amount_min": 2, "amount_max": 5}


def test_flatten_dict_leaves_none_values_alone():
    """A ``None`` branch is left in place rather than flattened away.

    Callers need to tell "the BOM sent no data" apart from "the BOM sent zero".
    """
    payload = {"amount": None, "chance": 40}
    flatten_dict(["amount"], payload)

    assert payload == {"amount": None, "chance": 40}


def test_flatten_dict_ignores_missing_keys():
    payload = {"chance": 40}
    flatten_dict(["amount"], payload)

    assert payload == {"chance": 40}


@pytest.mark.parametrize(
    ("temperature", "humidity", "expected"),
    [
        (25, 50, 13.8),
        (30, 80, 26.2),
        (20, 60, 12.0),
        (20.0, 50.0, 9.3),
        (13.6, 70.0, 8.2),
    ],
)
def test_calculate_dew_point_matches_tetens_formula(temperature, humidity, expected):
    assert calculate_dew_point(temperature, humidity) == expected
