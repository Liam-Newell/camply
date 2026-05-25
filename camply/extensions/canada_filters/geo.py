"""
Geographic helpers for the canada_filters extension.

Pure-Python (``math`` only) implementation of the haversine great-circle
distance, plus a small built-in lookup table of common Canadian cities
so users do not need to install or call out to an online geocoder when
running on a low-power server.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

#: Mean radius of the Earth, in kilometres.
EARTH_RADIUS_KM: float = 6371.0088

#: Lookup table of common Canadian cities, keyed by lower-cased name.
#: Values are ``(latitude, longitude)`` decimal degree tuples.
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "toronto": (43.6532, -79.3832),
    "ottawa": (45.4215, -75.6972),
    "montreal": (45.5019, -73.5674),
    "montréal": (45.5019, -73.5674),
    "quebec city": (46.8139, -71.2080),
    "québec city": (46.8139, -71.2080),
    "vancouver": (49.2827, -123.1207),
    "victoria": (48.4284, -123.3656),
    "calgary": (51.0447, -114.0719),
    "edmonton": (53.5461, -113.4938),
    "winnipeg": (49.8951, -97.1384),
    "halifax": (44.6488, -63.5752),
    "st johns": (47.5615, -52.7126),
    "st. john's": (47.5615, -52.7126),
    "fredericton": (45.9636, -66.6431),
    "charlottetown": (46.2382, -63.1311),
    "saskatoon": (52.1332, -106.6700),
    "regina": (50.4452, -104.6189),
    "yellowknife": (62.4540, -114.3718),
    "whitehorse": (60.7212, -135.0568),
    "iqaluit": (63.7467, -68.5170),
    "kingston": (44.2312, -76.4860),
    "hamilton": (43.2557, -79.8711),
    "london": (42.9849, -81.2453),
    "windsor": (42.3149, -83.0364),
    "barrie": (44.3894, -79.6903),
    "sudbury": (46.4917, -80.9930),
    "thunder bay": (48.3809, -89.2477),
    "north bay": (46.3091, -79.4608),
    "kitchener": (43.4516, -80.4925),
    "guelph": (43.5448, -80.2482),
    "peterborough": (44.3091, -78.3197),
    "kelowna": (49.8880, -119.4960),
    "kamloops": (50.6745, -120.3273),
    "banff": (51.1784, -115.5708),
}


def haversine_km(
    point_a: Tuple[float, float], point_b: Tuple[float, float]
) -> float:
    """
    Great-circle distance between two ``(lat, lng)`` points, in kilometres.

    Parameters
    ----------
    point_a, point_b : Tuple[float, float]
        ``(latitude, longitude)`` in decimal degrees.

    Returns
    -------
    float
        Distance in kilometres.
    """
    lat1, lon1 = point_a
    lat2, lon2 = point_b
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.asin(min(1.0, math.sqrt(a)))
    return EARTH_RADIUS_KM * c


def parse_lat_lng(value: str) -> Tuple[float, float]:
    """
    Parse a ``"lat,lng"`` string into a tuple of floats.

    Raises
    ------
    ValueError
        If the string cannot be parsed into exactly two floats.
    """
    parts = [piece.strip() for piece in value.split(",")]
    if len(parts) != 2:
        raise ValueError(
            f"Expected 'lat,lng' (got {value!r}). "
            "Example: '43.6532,-79.3832' for Toronto."
        )
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise ValueError(
            f"Could not parse coordinates from {value!r}: {exc}"
        ) from exc


def resolve_place(name: str) -> Optional[Tuple[float, float]]:
    """
    Resolve a place name to ``(lat, lng)`` using :data:`CITY_COORDINATES`.

    The lookup is case- and whitespace-insensitive. Returns ``None`` when
    the name is not in the built-in table — callers should then fall back
    to ``--near`` lat/lng input.
    """
    if name is None:
        return None
    key = name.strip().lower()
    return CITY_COORDINATES.get(key)
