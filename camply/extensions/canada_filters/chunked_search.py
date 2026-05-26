"""
Weekend-chunked GoingToCamp search.

The stock :class:`SearchGoingToCamp` issues one ``/api/availability/map``
call per :class:`SearchWindow`; that call returns a single yes/no for
the entire requested window, so ``--weekends`` and ``--nights`` end up
labelling every match with the full search horizon. This subclass
splits each :class:`SearchWindow` into one ``nights``-long sub-window
per Friday in the range and fans the per-campground availability calls
out concurrently (capped at 10) so each surfaced campsite carries the
specific weekend it is actually bookable on.

This module lives in ``camply.extensions.canada_filters`` so the
upstream ``camply campsites`` command keeps its existing one-shot
behaviour.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Tuple

from camply.containers import AvailableCampsite, SearchWindow
from camply.providers.going_to_camp.going_to_camp_provider import NON_GROUP_EQUIPMENT
from camply.search.search_going_to_camp import SearchGoingToCamp

logger = logging.getLogger(__name__)

FRIDAY = 4  # date.weekday(): Mon=0 .. Sun=6
DEFAULT_MAX_CONCURRENCY = 10


def _expand_into_weekend_windows(
    window: SearchWindow, nights: int
) -> List[SearchWindow]:
    """
    Return one :class:`SearchWindow` per Friday in ``window``.

    Each produced sub-window starts on a Friday and spans ``nights``
    days. Sub-windows whose end date would fall after the original
    window's ``end_date`` are clipped to ``end_date``.
    """
    # Coerce to a plain ``int`` — base_search occasionally hands us a
    # ``numpy.int64`` (post-clamping by ``_get_search_days``) which
    # ``datetime.timedelta`` refuses to accept.
    nights = int(nights) if nights else 1
    if nights <= 0:
        nights = 1
    start = window.get_current_start_date()
    end = window.end_date
    if end <= start:
        return []
    first_friday = start + timedelta(days=(FRIDAY - start.weekday()) % 7)
    out: List[SearchWindow] = []
    cursor = first_friday
    while cursor < end:
        sub_end = min(cursor + timedelta(days=nights), end)
        if sub_end > cursor:
            out.append(SearchWindow(start_date=cursor, end_date=sub_end))
        cursor += timedelta(days=7)
    return out


class WeekendChunkedSearchGoingToCamp(SearchGoingToCamp):
    """
    GoingToCamp search that fans per-weekend availability lookups out
    concurrently (capped at :data:`DEFAULT_MAX_CONCURRENCY`).

    Behaves identically to :class:`SearchGoingToCamp` when ``--weekends``
    is not in effect: callers should only swap this class in when they
    actually want weekend chunking.
    """

    max_concurrency: int = DEFAULT_MAX_CONCURRENCY

    def get_all_campsites(self) -> List[AvailableCampsite]:
        """
        Override the stock loop with a per-weekend fan-out.
        """
        # Build the (campground, sub_window) work list up front so the
        # asyncio surface only deals with bounded fan-out.
        tasks: List[Tuple[Any, SearchWindow]] = []
        for search_window in self.search_window:
            sub_windows = _expand_into_weekend_windows(
                search_window, self.nights or 1
            )
            if not sub_windows:
                continue
            for campground in self.campgrounds:
                for sub in sub_windows:
                    tasks.append((campground, sub))

        if not tasks:
            return []

        logger.info(
            "canada-campsites: weekend chunking %d campground(s) \u00d7 %d "
            "weekend window(s) = %d concurrent availability calls (cap=%d).",
            len(self.campgrounds),
            len(tasks) // max(len(self.campgrounds), 1),
            len(tasks),
            self.max_concurrency,
        )

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        sem = asyncio.Semaphore(self.max_concurrency)

        async def fetch(campground, sub_window: SearchWindow):
            async with sem:
                return await asyncio.to_thread(
                    self.campsite_finder.list_site_availability,
                    campground,
                    sub_window.start_date,
                    sub_window.end_date,
                    self.equipment_id,
                )

        async def run():
            return await asyncio.gather(
                *(fetch(cg, sw) for cg, sw in tasks),
                return_exceptions=True,
            )

        results = asyncio.run(run())
        return list(self._materialize(tasks, results))

    def _materialize(
        self,
        tasks: List[Tuple[Any, SearchWindow]],
        results: List[Any],
    ) -> List[AvailableCampsite]:
        """
        Convert raw availability results into :class:`AvailableCampsite`
        records, one per (site, weekend) pairing.
        """
        out: List[AvailableCampsite] = []
        rec_lookup_cache: Dict[int, Tuple[str, Any]] = {}
        for (campground, sub_window), sites in zip(tasks, results):
            if isinstance(sites, Exception):
                logger.debug(
                    "canada-campsites: availability lookup failed for "
                    "campground %s window %s\u2192%s: %s",
                    campground.facility_id,
                    sub_window.start_date,
                    sub_window.end_date,
                    sites,
                )
                continue
            if not sites:
                continue
            if self._recreation_area_id not in rec_lookup_cache:
                rec_lookup_cache[self._recreation_area_id] = (
                    self.campsite_finder.rec_area_lookup(
                        rec_area_id=self._recreation_area_id
                    )
                )
            rec_area_domain_name, rec_area = rec_lookup_cache[
                self._recreation_area_id
            ]
            nights = (sub_window.end_date - sub_window.start_date).days
            start_dt = datetime.combine(sub_window.start_date, time.min)
            end_dt = datetime.combine(sub_window.end_date, time.min)
            for site in sites:
                site_details = self.campsite_finder.get_site_details(
                    self._recreation_area_id, site.resource_id
                )
                if (
                    not site_details.get("minCapacity")
                    or not site_details.get("maxCapacity")
                ):
                    continue
                booking_url = self.campsite_finder.get_reservation_link(
                    rec_area_domain_name,
                    resource_location_id=campground.facility_id,
                    map_id=site.map_id,
                    equipment_id=NON_GROUP_EQUIPMENT,
                    sub_equipment_id=self.equipment_id,
                    party_size=1,
                    start_date=sub_window.start_date,
                    end_date=sub_window.end_date,
                )
                out.append(
                    AvailableCampsite(
                        campsite_id=site_details["resourceId"],
                        campsite_site_name=site_details["localizedValues"][0][
                            "name"
                        ],
                        booking_date=start_dt,
                        booking_end_date=end_dt,
                        booking_nights=nights,
                        campsite_loop_name="Unknown",
                        campsite_type=site_details["site_attributes"].get(
                            "Service Type", "Unknown"
                        ),
                        campsite_occupancy=(
                            site_details["minCapacity"],
                            site_details["maxCapacity"],
                        ),
                        campsite_use_type="N/A",
                        availability_status="Available",
                        recreation_area=rec_area.recreation_area,
                        recreation_area_id=self._recreation_area_id,
                        facility_name=campground.facility_name,
                        facility_id=campground.facility_id,
                        booking_url=booking_url,
                    )
                )
        return out


__all__ = [
    "WeekendChunkedSearchGoingToCamp",
    "_expand_into_weekend_windows",
    "DEFAULT_MAX_CONCURRENCY",
]
