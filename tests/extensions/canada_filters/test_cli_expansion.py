"""
Tests for the ``--rec-area`` → campground auto-expansion helper used
by ``camply canada-campsites``.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pytest

from camply.containers.data_containers import CampgroundFacility
from camply.extensions.canada_filters.cli import _expand_rec_area_campgrounds


def _facility(
    facility_id: int, coordinates: Optional[Tuple[float, float]] = None
) -> CampgroundFacility:
    return CampgroundFacility(
        facility_name=f"Facility {facility_id}",
        recreation_area="Parks Canada",
        facility_id=facility_id,
        recreation_area_id=1,
        map_id=facility_id,
        coordinates=coordinates,
    )


@pytest.fixture()
def mock_find_campgrounds(monkeypatch) -> List[CampgroundFacility]:
    """Patch ``GoingToCamp.find_campgrounds`` to return fixed facilities."""
    # Toronto centre (43.6532, -79.3832).
    facilities = [
        _facility(101, (44.5, -78.5)),       # ~120 km — inside 300 km
        _facility(202, (43.9, -78.9)),       # ~50 km — inside
        _facility(303, (49.2, -123.1)),      # Vancouver — outside
        _facility(404, None),                # no coordinates
    ]

    def fake_find_campgrounds(self, **kwargs):
        return list(facilities)

    monkeypatch.setattr(
        "camply.extensions.canada_filters.cli.GoingToCamp.find_campgrounds",
        fake_find_campgrounds,
    )
    return facilities


def test_noop_when_campground_supplied(mock_find_campgrounds):
    result = _expand_rec_area_campgrounds(
        provider="GoingToCamp",
        rec_area=(1,),
        campground=(999,),
        centre=(43.6532, -79.3832),
        radius_km=300.0,
    )
    assert result == (999,)


def test_noop_for_non_going_to_camp_provider(mock_find_campgrounds):
    result = _expand_rec_area_campgrounds(
        provider="RecreationDotGov",
        rec_area=(1,),
        campground=(),
    )
    assert result == ()


def test_noop_when_rec_area_empty(mock_find_campgrounds):
    result = _expand_rec_area_campgrounds(
        provider="GoingToCamp",
        rec_area=(),
        campground=(),
    )
    assert result == ()


def test_expansion_returns_all_facility_ids_without_centre(mock_find_campgrounds):
    result = _expand_rec_area_campgrounds(
        provider="GoingToCamp",
        rec_area=(1,),
        campground=(),
    )
    assert set(result) == {101, 202, 303, 404}


def test_radius_prefilter_drops_distant_keeps_no_location_by_default(
    mock_find_campgrounds,
):
    # strict_radius defaults to False so unlocated facilities (404) are
    # KEPT alongside in-range located ones (101, 202). Out-of-range
    # 303 is still dropped.
    result = _expand_rec_area_campgrounds(
        provider="GoingToCamp",
        rec_area=(1,),
        campground=(),
        centre=(43.6532, -79.3832),
        radius_km=300.0,
    )
    assert set(result) == {101, 202, 404}


def test_radius_prefilter_drops_no_location_with_strict_radius(mock_find_campgrounds):
    result = _expand_rec_area_campgrounds(
        provider="GoingToCamp",
        rec_area=(1,),
        campground=(),
        centre=(43.6532, -79.3832),
        radius_km=300.0,
        strict_radius=True,
    )
    assert set(result) == {101, 202}


def test_exits_when_no_facilities_returned(monkeypatch):
    monkeypatch.setattr(
        "camply.extensions.canada_filters.cli.GoingToCamp.find_campgrounds",
        lambda self, **kwargs: [],
    )
    with pytest.raises(SystemExit):
        _expand_rec_area_campgrounds(
            provider="GoingToCamp",
            rec_area=(1,),
            campground=(),
        )
