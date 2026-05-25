"""
Boolean amenity toggles for the canada_filters extension.

Each toggle is a callable ``(AvailableCampsite) -> bool`` registered in
:data:`TOGGLE_REGISTRY` under a short keyword. Toggles inspect the
``campsite_type``, ``campsite_attributes`` and ``permitted_equipment``
fields that are already populated by camply's providers (notably
``GoingToCamp``, which stores attributes such as ``"Service Type"`` /
``"Has Electricity"`` / ``"Pets Allowed"`` on the
``site_attributes`` dict before they are flattened into
``AvailableCampsite.campsite_attributes``).

Adding a new toggle is a single ``register`` call — no core camply
files need to change.
"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Sequence

from camply.containers import AvailableCampsite

#: A predicate that returns ``True`` when a campsite satisfies a toggle.
TogglePredicate = Callable[[AvailableCampsite], bool]


def _attribute_strings(campsite: AvailableCampsite) -> List[str]:
    """
    Return a flat, lower-cased list of attribute-name + value strings.
    """
    out: List[str] = []
    site_type = getattr(campsite, "campsite_type", None)
    if site_type:
        out.append(str(site_type).lower())
    site_use = getattr(campsite, "campsite_use_type", None)
    if site_use:
        out.append(str(site_use).lower())
    site_name = getattr(campsite, "campsite_site_name", None)
    if site_name:
        out.append(str(site_name).lower())
    loop_name = getattr(campsite, "campsite_loop_name", None)
    if loop_name:
        out.append(str(loop_name).lower())
    facility_name = getattr(campsite, "facility_name", None)
    if facility_name:
        out.append(str(facility_name).lower())
    for attr in getattr(campsite, "campsite_attributes", None) or []:
        # ``RecDotGovAttribute`` instances expose ``attribute_name`` /
        # ``attribute_value``; GoingToCamp results may inject simple
        # ``(name, value)`` pairs as well. Be permissive.
        name = getattr(attr, "attribute_name", None)
        value = getattr(attr, "attribute_value", None)
        if name is None and value is None and isinstance(attr, (tuple, list)):
            name, value = (attr + (None, None))[:2]
        if name is not None:
            out.append(str(name).lower())
        if value is not None:
            out.append(str(value).lower())
    return out


def _any_keyword_matches(
    campsite: AvailableCampsite, keywords: Sequence[str]
) -> bool:
    haystack = _attribute_strings(campsite)
    needles = [kw.lower() for kw in keywords]
    return any(needle in chunk for chunk in haystack for needle in needles)


def _all_attr_value_truthy(
    campsite: AvailableCampsite, names: Sequence[str]
) -> bool:
    """
    Return True if any attribute whose name contains one of ``names``
    has a value that looks "truthy" ("yes", "true", "1", a positive
    number, or a non-empty string that is not "no"/"false"/"0").
    """
    lowered = [n.lower() for n in names]
    for attr in getattr(campsite, "campsite_attributes", None) or []:
        name = getattr(attr, "attribute_name", None)
        value = getattr(attr, "attribute_value", None)
        if name is None:
            continue
        name_l = str(name).lower()
        if not any(needle in name_l for needle in lowered):
            continue
        if value is None:
            continue
        v = str(value).strip().lower()
        if v in {"", "no", "false", "0", "none", "n/a", "na"}:
            continue
        return True
    return False


def _has_electric(campsite: AvailableCampsite) -> bool:
    """
    Match campsites that advertise an electrical hookup / outlet.

    Looks for keywords commonly used by ``GoingToCamp`` ("Electric",
    "Electrical", "Power", "Hydro", "30 amp", "50 amp", "15 amp",
    "Service Type: ... Electric") and Recreation.gov
    ("ELECTRICITY HOOKUP"). Falls back to keyword scan when no
    structured attribute is present.
    """
    if _all_attr_value_truthy(
        campsite,
        names=[
            "electric",
            "electricity",
            "hydro",
            "power",
            "amp",
        ],
    ):
        return True
    return _any_keyword_matches(
        campsite,
        keywords=[
            "electric",
            "electrical",
            "hydro",
            "30 amp",
            "50 amp",
            "15 amp",
            "20 amp",
            "full service",
            "full-service",
            "full hookup",
        ],
    )


def _has_water(campsite: AvailableCampsite) -> bool:
    """
    Match campsites with a water hookup or potable water on-site.
    """
    if _all_attr_value_truthy(campsite, names=["water"]):
        return True
    return _any_keyword_matches(
        campsite,
        keywords=["water hookup", "potable water", "water service", "full hookup"],
    )


def _has_sewer(campsite: AvailableCampsite) -> bool:
    if _all_attr_value_truthy(campsite, names=["sewer", "sewage"]):
        return True
    return _any_keyword_matches(
        campsite, keywords=["sewer", "sewage", "full hookup", "full service"]
    )


def _is_group_site(campsite: AvailableCampsite) -> bool:
    """
    Match group / large-party campsites.
    """
    return _any_keyword_matches(
        campsite, keywords=["group", "party site", "large group", "youth group"]
    )


def _is_pet_friendly(campsite: AvailableCampsite) -> bool:
    if _all_attr_value_truthy(campsite, names=["pet", "dog"]):
        return True
    return _any_keyword_matches(
        campsite, keywords=["pets allowed", "pet friendly", "dog friendly"]
    )


def _is_scenic(campsite: AvailableCampsite) -> bool:
    """
    Soft "nice view" toggle. Source data is inconsistent — best effort.
    """
    return _any_keyword_matches(
        campsite,
        keywords=[
            "view",
            "lake",
            "lakefront",
            "lake view",
            "waterfront",
            "river",
            "ocean",
            "beach",
            "mountain",
        ],
    )


def _has_shower(campsite: AvailableCampsite) -> bool:
    return _any_keyword_matches(
        campsite, keywords=["shower", "washroom", "comfort station"]
    )


def _has_fire_pit(campsite: AvailableCampsite) -> bool:
    return _any_keyword_matches(
        campsite, keywords=["fire pit", "fire ring", "firepit", "campfire"]
    )


#: Public registry of toggle keyword → predicate. The keyword is what
#: users type on the CLI / in YAML (``--require electric``).
TOGGLE_REGISTRY: Dict[str, TogglePredicate] = {
    "electric": _has_electric,
    "outlet": _has_electric,  # alias — what the user actually typed
    "power": _has_electric,
    "hydro": _has_electric,
    "water": _has_water,
    "sewer": _has_sewer,
    "group": _is_group_site,
    "pet_friendly": _is_pet_friendly,
    "pets": _is_pet_friendly,
    "scenic": _is_scenic,
    "view": _is_scenic,
    "shower": _has_shower,
    "fire_pit": _has_fire_pit,
}


def matches_toggle(campsite: AvailableCampsite, toggle: str) -> bool:
    """
    Look up ``toggle`` in :data:`TOGGLE_REGISTRY` and apply it.

    Unknown toggles raise ``KeyError`` so the CLI can surface a helpful
    error to the user.
    """
    predicate = TOGGLE_REGISTRY[toggle.lower()]
    return predicate(campsite)


def known_toggles() -> Iterable[str]:
    """
    Return the sorted list of registered toggle keywords.
    """
    return sorted(TOGGLE_REGISTRY.keys())
