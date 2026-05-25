"""
Canada Filters — post-search middleware for camply.

This extension adds the ability to:

* Restrict campsite search results to a configurable radius (in km) of an
  arbitrary lat/lng (or a known Canadian city name).
* Apply boolean amenity toggles ("outlet", "electric", "water",
  "pet_friendly", "scenic", ...) over campsite attributes.
* Restrict (or exclude) group campsite areas.

The implementation is a *post-filter* applied to the list of
``AvailableCampsite`` instances returned by any existing
``BaseCampingSearch``. The core search and notification pipeline is
unchanged — every notifier (e.g. email, including multiple recipients
via ``EMAIL_TO_ADDRESS``) keeps working exactly as it does for the
built-in ``camply campsites`` command.

A new CLI command, ``camply canada-campsites``, exposes the filters.
The Canadian-focused ``GoingToCamp`` provider is used by default.
"""

# Importing the cli module registers the ``canada-campsites`` command
# on the main camply Click group as a side effect.
from camply.extensions.canada_filters import cli  # noqa: F401
from camply.extensions.canada_filters.attribute_filters import (
    TOGGLE_REGISTRY,
    matches_toggle,
)
from camply.extensions.canada_filters.geo import (
    CITY_COORDINATES,
    haversine_km,
    resolve_place,
)
from camply.extensions.canada_filters.pipeline import (
    FilterPipeline,
    GroupSiteFilter,
    RadiusFilter,
    ToggleFilter,
)
from camply.extensions.canada_filters.wrapped_search import FilteredCampingSearch

__all__ = [
    "CITY_COORDINATES",
    "FilterPipeline",
    "FilteredCampingSearch",
    "GroupSiteFilter",
    "RadiusFilter",
    "TOGGLE_REGISTRY",
    "ToggleFilter",
    "haversine_km",
    "matches_toggle",
    "resolve_place",
]
