"""
Optional YAML schema for the canada_filters extension.

Existing camply YAML files are read by ``camply.utils.yaml_utils`` and
keep working unchanged. This module reads the *same* YAML file a
second time, picks out a top-level ``filters:`` block and returns a
configured :class:`FilterPipeline`. If the file has no ``filters:``
block an empty pipeline is returned, which is a no-op when called.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from camply.utils.yaml_utils import read_yaml

from camply.extensions.canada_filters.attribute_filters import TOGGLE_REGISTRY
from camply.extensions.canada_filters.geo import parse_lat_lng, resolve_place
from camply.extensions.canada_filters.pipeline import (
    FilterPipeline,
    GroupSiteFilter,
    RadiusFilter,
    ToggleFilter,
)

logger = logging.getLogger(__name__)


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [piece.strip() for piece in value.split(",") if piece.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise TypeError(
        f"Expected list/string for amenity toggles, got {type(value).__name__}"
    )


def build_pipeline_from_dict(
    filters_block: Optional[Dict[str, Any]],
) -> FilterPipeline:
    """
    Build a :class:`FilterPipeline` from a parsed ``filters:`` mapping.

    Recognised keys:

    * ``near``: ``"lat,lng"`` string.
    * ``near_place``: human-readable Canadian city name.
    * ``radius_km``: numeric radius (defaults to 100).
    * ``require``: list of amenity toggles that must match.
    * ``exclude``: list of amenity toggles that must not match.
    * ``group_only``: ``true`` / ``false``. Omit for no-op.
    * ``drop_when_no_location``: defaults to ``true``.
    """
    pipeline = FilterPipeline()
    if not filters_block:
        return pipeline

    center: Optional[Tuple[float, float]] = None
    if "near" in filters_block and filters_block["near"]:
        center = parse_lat_lng(str(filters_block["near"]))
    elif "near_place" in filters_block and filters_block["near_place"]:
        place = str(filters_block["near_place"])
        center = resolve_place(place)
        if center is None:
            raise KeyError(
                f"Unknown place {place!r} — provide explicit "
                "coordinates via 'near: lat,lng'."
            )
    radius_km = float(filters_block.get("radius_km", 100))
    drop_no_loc = bool(filters_block.get("drop_when_no_location", True))
    if center is not None:
        pipeline.add(
            RadiusFilter(
                center=center,
                max_km=radius_km,
                drop_when_no_location=drop_no_loc,
            )
        )

    required = _normalize_list(filters_block.get("require"))
    excluded = _normalize_list(filters_block.get("exclude"))
    for toggle in required + excluded:
        if toggle.lower() not in TOGGLE_REGISTRY:
            raise KeyError(
                f"Unknown amenity toggle {toggle!r}. "
                f"Known: {sorted(TOGGLE_REGISTRY)}"
            )
    if required or excluded:
        pipeline.add(ToggleFilter(required=required, excluded=excluded))

    if "group_only" in filters_block and filters_block["group_only"] is not None:
        pipeline.add(GroupSiteFilter(only_group=bool(filters_block["group_only"])))

    return pipeline


def load_pipeline_from_yaml(file_path: str) -> FilterPipeline:
    """
    Read ``file_path`` and return a :class:`FilterPipeline` built from
    its top-level ``filters:`` block, or an empty pipeline when absent.
    """
    data = read_yaml(path=file_path) or {}
    return build_pipeline_from_dict(data.get("filters"))
