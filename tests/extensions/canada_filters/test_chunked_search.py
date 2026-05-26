"""
Tests for the per-weekend window expansion used by canada-campsites'
chunked GoingToCamp search.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from camply.containers import SearchWindow
from camply.extensions.canada_filters.chunked_search import (
    FRIDAY,
    _expand_into_weekend_windows,
)


def _window(start: date, end: date) -> SearchWindow:
    return SearchWindow(start_date=start, end_date=end)


def test_expansion_emits_one_window_per_friday():
    # 2026-06-05 is a Friday; 2026-08-31 is a Monday. 13 Fridays between.
    window = _window(date(2026, 6, 5), date(2026, 8, 31))
    subs = _expand_into_weekend_windows(window, nights=2)
    assert len(subs) == 13
    for sub in subs:
        assert sub.start_date.weekday() == FRIDAY
        assert sub.end_date - sub.start_date == timedelta(days=2)


def test_expansion_clips_trailing_window():
    # Last Friday is 2026-06-12; with nights=7 the sub-window would end
    # on 2026-06-19, but the search window ends on 2026-06-15.
    window = _window(date(2026, 6, 5), date(2026, 6, 15))
    subs = _expand_into_weekend_windows(window, nights=7)
    assert [s.start_date for s in subs] == [date(2026, 6, 5), date(2026, 6, 12)]
    assert subs[-1].end_date == date(2026, 6, 15)


def test_expansion_handles_non_friday_start():
    # Start on a Wednesday; first Friday is 2 days later.
    window = _window(date(2026, 6, 3), date(2026, 6, 30))
    subs = _expand_into_weekend_windows(window, nights=2)
    assert subs[0].start_date == date(2026, 6, 5)
    for sub in subs:
        assert sub.start_date.weekday() == FRIDAY


def test_expansion_empty_when_end_before_start():
    window = _window(date(2026, 6, 5), date(2026, 6, 5))
    assert _expand_into_weekend_windows(window, nights=2) == []


def test_expansion_coerces_zero_nights_to_one():
    window = _window(date(2026, 6, 5), date(2026, 6, 12))
    subs = _expand_into_weekend_windows(window, nights=0)
    assert subs and (subs[0].end_date - subs[0].start_date) == timedelta(days=1)


@pytest.mark.parametrize("nights", [1, 2, 3])
def test_expansion_respects_nights(nights):
    window = _window(date(2026, 6, 5), date(2026, 7, 31))
    subs = _expand_into_weekend_windows(window, nights=nights)
    for sub in subs[:-1]:  # last one may be clipped
        assert sub.end_date - sub.start_date == timedelta(days=nights)
