"""
Tests for ``camply.extensions.canada_filters``.
"""

from __future__ import annotations

import datetime
from typing import List

import pytest

from camply.containers import AvailableCampsite
from camply.containers.base_container import RecDotGovAttribute
from camply.containers.data_containers import CampsiteLocation
from camply.exceptions import CampsiteNotFoundError
from camply.extensions.canada_filters import (
    CITY_COORDINATES,
    FilterPipeline,
    FilteredCampingSearch,
    GroupSiteFilter,
    RadiusFilter,
    TOGGLE_REGISTRY,
    ToggleFilter,
    haversine_km,
    resolve_place,
)
from camply.extensions.canada_filters.yaml_schema import build_pipeline_from_dict


def _make_campsite(
    *,
    campsite_id: int = 1,
    latitude: float = None,
    longitude: float = None,
    campsite_type: str = "Standard",
    attributes: List[tuple] = None,
    site_name: str = "Test Site",
) -> AvailableCampsite:
    """Build an AvailableCampsite with optional location/attributes."""
    location = None
    if latitude is not None and longitude is not None:
        location = CampsiteLocation(latitude=latitude, longitude=longitude)
    attrs = []
    for name, value in attributes or []:
        attrs.append(
            RecDotGovAttribute(
                attribute_category="standard",
                attribute_id=0,
                attribute_name=name,
                attribute_value=value,
            )
        )
    return AvailableCampsite(
        campsite_id=campsite_id,
        booking_date=datetime.datetime(2026, 7, 1),
        booking_end_date=datetime.datetime(2026, 7, 2),
        booking_nights=1,
        campsite_site_name=site_name,
        campsite_loop_name="Loop A",
        campsite_type=campsite_type,
        campsite_occupancy=(1, 4),
        campsite_use_type="Overnight",
        availability_status="Available",
        recreation_area="Test Rec Area",
        recreation_area_id=99,
        facility_name="Test Facility",
        facility_id=42,
        booking_url="https://example.com/book",
        location=location,
        permitted_equipment=[],
        campsite_attributes=attrs,
    )


# ---------------------------------------------------------------------------
# geo
# ---------------------------------------------------------------------------

def test_haversine_toronto_ottawa_distance_is_about_352km() -> None:
    toronto = CITY_COORDINATES["toronto"]
    ottawa = CITY_COORDINATES["ottawa"]
    distance = haversine_km(toronto, ottawa)
    # Well-known ~352 km — allow generous tolerance.
    assert 340 < distance < 365


def test_haversine_identity_is_zero() -> None:
    toronto = CITY_COORDINATES["toronto"]
    assert haversine_km(toronto, toronto) == pytest.approx(0.0, abs=1e-9)


def test_resolve_place_is_case_insensitive() -> None:
    assert resolve_place("TORONTO") == CITY_COORDINATES["toronto"]
    assert resolve_place("  toronto ") == CITY_COORDINATES["toronto"]
    assert resolve_place("nowhere-ville") is None


# ---------------------------------------------------------------------------
# RadiusFilter
# ---------------------------------------------------------------------------

def test_radius_filter_keeps_inside_drops_outside() -> None:
    toronto = CITY_COORDINATES["toronto"]
    inside = _make_campsite(
        campsite_id=1, latitude=44.0, longitude=-79.5  # ~40 km from Toronto
    )
    outside = _make_campsite(
        campsite_id=2,
        latitude=CITY_COORDINATES["ottawa"][0],
        longitude=CITY_COORDINATES["ottawa"][1],
    )
    f = RadiusFilter(center=toronto, max_km=100.0)
    result = f([inside, outside])
    assert [c.campsite_id for c in result] == [1]


def test_radius_filter_drops_unknown_location_by_default() -> None:
    f = RadiusFilter(center=CITY_COORDINATES["toronto"], max_km=100.0)
    no_loc = _make_campsite(campsite_id=3)
    assert f([no_loc]) == []


def test_radius_filter_keeps_unknown_location_when_requested() -> None:
    f = RadiusFilter(
        center=CITY_COORDINATES["toronto"],
        max_km=100.0,
        drop_when_no_location=False,
    )
    no_loc = _make_campsite(campsite_id=3)
    assert [c.campsite_id for c in f([no_loc])] == [3]


# ---------------------------------------------------------------------------
# ToggleFilter / attribute_filters
# ---------------------------------------------------------------------------

def test_outlet_toggle_matches_electric_attribute() -> None:
    site = _make_campsite(
        campsite_id=10,
        attributes=[("Has Electricity", "Yes"), ("Service Type", "30 amp Electric")],
    )
    f = ToggleFilter(required=["outlet"])
    assert f([site]) == [site]


def test_outlet_toggle_rejects_no_electric() -> None:
    site = _make_campsite(
        campsite_id=11, attributes=[("Service Type", "Unserviced")]
    )
    assert ToggleFilter(required=["electric"])([site]) == []


def test_exclude_toggle_rejects_matching_sites() -> None:
    group = _make_campsite(campsite_id=20, campsite_type="Group Tent Site")
    standard = _make_campsite(campsite_id=21, campsite_type="Standard")
    f = ToggleFilter(excluded=["group"])
    assert [c.campsite_id for c in f([group, standard])] == [21]


def test_unknown_toggle_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        ToggleFilter(required=["does-not-exist"])


def test_known_toggles_include_user_keywords() -> None:
    for kw in ("outlet", "electric", "group", "scenic", "water"):
        assert kw in TOGGLE_REGISTRY


# ---------------------------------------------------------------------------
# GroupSiteFilter
# ---------------------------------------------------------------------------

def test_group_filter_only_group_keeps_groups() -> None:
    group = _make_campsite(campsite_id=30, campsite_type="Large Group Site")
    standard = _make_campsite(campsite_id=31, campsite_type="Standard")
    assert [c.campsite_id for c in GroupSiteFilter(only_group=True)([group, standard])] == [30]


def test_group_filter_no_group_drops_groups() -> None:
    group = _make_campsite(campsite_id=30, campsite_type="Large Group Site")
    standard = _make_campsite(campsite_id=31, campsite_type="Standard")
    assert [c.campsite_id for c in GroupSiteFilter(only_group=False)([group, standard])] == [31]


def test_group_filter_none_is_noop() -> None:
    sites = [
        _make_campsite(campsite_id=30, campsite_type="Large Group Site"),
        _make_campsite(campsite_id=31, campsite_type="Standard"),
    ]
    assert GroupSiteFilter(only_group=None)(sites) == sites


# ---------------------------------------------------------------------------
# FilterPipeline
# ---------------------------------------------------------------------------

def test_pipeline_runs_stages_in_order() -> None:
    toronto = CITY_COORDINATES["toronto"]
    nearby_electric = _make_campsite(
        campsite_id=100,
        latitude=44.0,
        longitude=-79.5,
        attributes=[("Has Electricity", "Yes")],
    )
    nearby_no_electric = _make_campsite(
        campsite_id=101, latitude=44.0, longitude=-79.5
    )
    far_electric = _make_campsite(
        campsite_id=102,
        latitude=CITY_COORDINATES["vancouver"][0],
        longitude=CITY_COORDINATES["vancouver"][1],
        attributes=[("Has Electricity", "Yes")],
    )
    pipeline = (
        FilterPipeline()
        .add(RadiusFilter(center=toronto, max_km=100.0))
        .add(ToggleFilter(required=["outlet"]))
    )
    result = pipeline([nearby_electric, nearby_no_electric, far_electric])
    assert [c.campsite_id for c in result] == [100]


def test_empty_pipeline_is_falsy_and_noop() -> None:
    pipeline = FilterPipeline()
    assert not pipeline
    assert pipeline([]) == []
    site = _make_campsite()
    assert pipeline([site]) == [site]


# ---------------------------------------------------------------------------
# YAML schema
# ---------------------------------------------------------------------------

def test_yaml_schema_builds_pipeline_with_radius_and_toggles() -> None:
    pipeline = build_pipeline_from_dict(
        {
            "near_place": "Toronto",
            "radius_km": 50,
            "require": ["outlet"],
            "group_only": False,
        }
    )
    assert len(pipeline) == 3  # radius, toggle, group


def test_yaml_schema_unknown_place_raises() -> None:
    with pytest.raises(KeyError):
        build_pipeline_from_dict({"near_place": "atlantis"})


def test_yaml_schema_empty_returns_empty_pipeline() -> None:
    assert len(build_pipeline_from_dict(None)) == 0
    assert len(build_pipeline_from_dict({})) == 0


# ---------------------------------------------------------------------------
# FilteredCampingSearch
# ---------------------------------------------------------------------------

class _FakeSearch:
    """Minimal stand-in for a ``BaseCampingSearch``."""

    def __init__(self, results):
        self._results = list(results)
        self.campsites_found = set()
        self.assembled = []

    def _search_matching_campsites_available(
        self, log=False, verbose=False, raise_error=False
    ):
        if not self._results and raise_error:
            raise CampsiteNotFoundError("nothing")
        return list(self._results)

    def assemble_availabilities(self, matching_data, log=False, verbose=False):
        self.assembled.extend(matching_data)


def test_filtered_search_applies_pipeline() -> None:
    toronto = CITY_COORDINATES["toronto"]
    inside = _make_campsite(campsite_id=1, latitude=44.0, longitude=-79.5)
    outside = _make_campsite(
        campsite_id=2,
        latitude=CITY_COORDINATES["vancouver"][0],
        longitude=CITY_COORDINATES["vancouver"][1],
    )
    fake = _FakeSearch([inside, outside])
    pipeline = FilterPipeline([RadiusFilter(center=toronto, max_km=100.0)])
    wrapper = FilteredCampingSearch(wrapped=fake, pipeline=pipeline)
    result = wrapper._filtered_inner_search(log=False, raise_error=False)
    assert [c.campsite_id for c in result] == [1]


def test_filtered_search_raises_when_pipeline_empties_results() -> None:
    far = _make_campsite(
        campsite_id=2,
        latitude=CITY_COORDINATES["vancouver"][0],
        longitude=CITY_COORDINATES["vancouver"][1],
    )
    fake = _FakeSearch([far])
    pipeline = FilterPipeline(
        [RadiusFilter(center=CITY_COORDINATES["toronto"], max_km=100.0)]
    )
    wrapper = FilteredCampingSearch(wrapped=fake, pipeline=pipeline)
    with pytest.raises(CampsiteNotFoundError):
        wrapper._filtered_inner_search(log=False, raise_error=True)


def test_filtered_search_syncs_campsites_found_after_filter() -> None:
    toronto = CITY_COORDINATES["toronto"]
    inside = _make_campsite(campsite_id=1, latitude=44.0, longitude=-79.5)
    outside = _make_campsite(
        campsite_id=2,
        latitude=CITY_COORDINATES["vancouver"][0],
        longitude=CITY_COORDINATES["vancouver"][1],
    )
    fake = _FakeSearch([inside, outside])
    # Simulate the wrapped search having already "found" both sites in
    # a previous polling cycle (e.g. via offline storage).
    fake.campsites_found.update({inside, outside})
    pipeline = FilterPipeline([RadiusFilter(center=toronto, max_km=100.0)])
    wrapper = FilteredCampingSearch(wrapped=fake, pipeline=pipeline)
    wrapper._filtered_inner_search(log=False, raise_error=False)
    # Outside Toronto must no longer count as "found" since the user
    # never wants to be notified about it.
    assert inside in fake.campsites_found
    assert outside not in fake.campsites_found


def test_filtered_search_proxies_attribute_access() -> None:
    fake = _FakeSearch([])
    fake.custom_attribute = "hello"
    wrapper = FilteredCampingSearch(wrapped=fake, pipeline=FilterPipeline())
    assert wrapper.custom_attribute == "hello"
