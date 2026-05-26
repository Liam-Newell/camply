"""
Reserve Ontario (``reservations.ontarioparks.ca``) extension for camply.

``reservations.ontarioparks.ca`` is the same Aspira/CampIT booking
backend that powers every GoingToCamp tenant, so this extension does
not introduce a new provider. Instead it:

* registers the Ontario Parks tenant as ``RecreationArea`` id 18 in
  :mod:`camply.providers.going_to_camp.rec_areas`,
* ships a curated, name-keyed catalogue of all reservable Reserve
  Ontario parks in :mod:`camply.extensions.ontario_parks.parks`,
* exposes a thin ``camply ontario-parks`` CLI subcommand that wraps
  the existing ``camply canada-campsites`` pipeline with a friendly
  ``--park NAME`` shortcut.
"""

# Importing the cli module registers the ``ontario-parks`` command on
# the main camply Click group as a side effect.
from camply.extensions.ontario_parks import cli  # noqa: F401
from camply.extensions.ontario_parks.parks import (
    ONTARIO_PARKS,
    ONTARIO_PARKS_REC_AREA_ID,
    resolve_parks,
)

__all__ = [
    "ONTARIO_PARKS",
    "ONTARIO_PARKS_REC_AREA_ID",
    "resolve_parks",
]
