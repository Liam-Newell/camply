"""
Pipeline of post-search filters for the canada_filters extension.

A :class:`FilterPipeline` is an ordered list of
``(List[AvailableCampsite]) -> List[AvailableCampsite]`` callables.
Three built-in filters are provided; users (or future extensions) can
register additional ones simply by appending callables to the
pipeline.

The pipeline runs *after* camply's normal availability search returns
its results, so no provider, search or notification code is modified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from camply.containers import AvailableCampsite

from camply.extensions.canada_filters.attribute_filters import (
    TOGGLE_REGISTRY,
    matches_toggle,
)
from camply.extensions.canada_filters.geo import haversine_km

logger = logging.getLogger(__name__)

#: A stage of the pipeline.
FilterStage = Callable[[List[AvailableCampsite]], List[AvailableCampsite]]


@dataclass
class RadiusFilter:
    """
    Keep only campsites within ``max_km`` of ``center`` (``(lat, lng)``).

    Parameters
    ----------
    center : Tuple[float, float]
        ``(latitude, longitude)`` of the user's location.
    max_km : float
        Maximum great-circle distance, in kilometres.
    drop_when_no_location : bool
        When ``True`` (the default) campsites without coordinates are
        dropped — they cannot be evaluated. When ``False`` they are
        kept (useful for providers whose ``location`` field is empty
        but where the user trusts the upstream rec-area filter).
    """

    center: Tuple[float, float]
    max_km: float
    drop_when_no_location: bool = True

    def __call__(
        self, campsites: List[AvailableCampsite]
    ) -> List[AvailableCampsite]:
        kept: List[AvailableCampsite] = []
        dropped_no_loc = 0
        dropped_too_far = 0
        for site in campsites:
            location = getattr(site, "location", None)
            lat = getattr(location, "latitude", None) if location else None
            lng = getattr(location, "longitude", None) if location else None
            if lat is None or lng is None:
                if self.drop_when_no_location:
                    dropped_no_loc += 1
                    continue
                kept.append(site)
                continue
            distance = haversine_km(self.center, (lat, lng))
            if distance <= self.max_km:
                kept.append(site)
            else:
                dropped_too_far += 1
        logger.debug(
            "RadiusFilter(center=%s, max_km=%.1f): kept=%d, "
            "dropped_too_far=%d, dropped_no_location=%d",
            self.center,
            self.max_km,
            len(kept),
            dropped_too_far,
            dropped_no_loc,
        )
        return kept


@dataclass
class ToggleFilter:
    """
    Keep only campsites matching every keyword in ``required`` and none
    of the keywords in ``excluded``.
    """

    required: Sequence[str] = field(default_factory=tuple)
    excluded: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for toggle in tuple(self.required) + tuple(self.excluded):
            if toggle.lower() not in TOGGLE_REGISTRY:
                raise KeyError(
                    f"Unknown amenity toggle: {toggle!r}. "
                    f"Known toggles: {sorted(TOGGLE_REGISTRY)}"
                )

    def __call__(
        self, campsites: List[AvailableCampsite]
    ) -> List[AvailableCampsite]:
        kept: List[AvailableCampsite] = []
        for site in campsites:
            if any(not matches_toggle(site, t) for t in self.required):
                continue
            if any(matches_toggle(site, t) for t in self.excluded):
                continue
            kept.append(site)
        logger.debug(
            "ToggleFilter(required=%s, excluded=%s): %d -> %d",
            list(self.required),
            list(self.excluded),
            len(campsites),
            len(kept),
        )
        return kept


@dataclass
class GroupSiteFilter:
    """
    Restrict to group sites (``only_group=True``) or exclude them
    (``only_group=False``). When ``only_group`` is ``None`` the filter
    is a no-op.
    """

    only_group: Optional[bool] = None

    def __call__(
        self, campsites: List[AvailableCampsite]
    ) -> List[AvailableCampsite]:
        if self.only_group is None:
            return list(campsites)
        kept = [
            site
            for site in campsites
            if matches_toggle(site, "group") is bool(self.only_group)
        ]
        logger.debug(
            "GroupSiteFilter(only_group=%s): %d -> %d",
            self.only_group,
            len(campsites),
            len(kept),
        )
        return kept


@dataclass
class FilterPipeline:
    """
    Ordered collection of :data:`FilterStage` callables.

    Calling the pipeline on a list of campsites runs every stage in
    order, returning the final filtered list. Stages can be added at
    construction time or later via :meth:`add`.
    """

    stages: List[FilterStage] = field(default_factory=list)

    def add(self, stage: FilterStage) -> "FilterPipeline":
        """
        Append a stage and return ``self`` so calls can chain.
        """
        self.stages.append(stage)
        return self

    def __call__(
        self, campsites: Iterable[AvailableCampsite]
    ) -> List[AvailableCampsite]:
        result = list(campsites)
        for stage in self.stages:
            result = list(stage(result))
        return result

    def __bool__(self) -> bool:
        return bool(self.stages)

    def __len__(self) -> int:
        return len(self.stages)
