"""
Reserve Ontario — known-park catalogue.

Maps each Ontario Parks ``resourceLocation`` name (as returned by the
live ``/api/resourceLocation`` endpoint on
``reservations.ontarioparks.ca``) to its negative-integer
``resourceLocationId``. Used by the ``--park`` shortcut of the
``camply ontario-parks`` CLI subcommand so users can write
``--park Killbear`` instead of ``--campground -2147483600``.

Names are taken verbatim from upstream's ``localizedValues[0].fullName``
(English). To refresh: run
``camply ontario-parks --refresh-parks`` and paste the output back here.
"""

from __future__ import annotations

#: All reservable Reserve Ontario parks (camp / group / overflow only).
#: Auto-generated from the live API on 2026-05-26.
ONTARIO_PARKS: dict[str, int] = {
    "Aaron Provincial Park": -2147483648,
    "Algonquin - Achray Campground / Sand Lake Gate": -2147483647,
    "Algonquin - Brent Campground": -2147483631,
    "Algonquin - Canisbay Lake Campground": -2147483627,
    "Algonquin - Kiosk Campground": -2147483599,
    "Algonquin - Lake Of Two Rivers Campground": -2147483596,
    "Algonquin - Mew Lake Campground": -2147483585,
    "Algonquin - Pog Lake and Kearney Lake Campground": -2147483567,
    "Algonquin - Rock Lake et Raccoon Lake": -2147483555,
    "Algonquin - Tea Lake Campground": -2147483533,
    "Algonquin - Whitefish Lake Campground": -2147483525,
    "Arrow Lake Provincial Park": -2147483642,
    "Arrowhead Provincial Park": -2147483641,
    "Awenda Provincial Park": -2147483639,
    "Balsam Lake Provincial Park": -2147483638,
    "Bass Lake Provincial Park": -2147483637,
    "Blue Lake Provincial Park": -2147483635,
    "Bon Echo Provincial Park": -2147483634,
    "Bonnechere Provincial Park": -2147483633,
    "Bronte Creek Provincial Park - Campground Area": -2147483630,
    "Caliper Lake Provincial Park": -2147483628,
    "Charleston Lake Provincial Park": -2147483625,
    "Chutes Provincial Park": -2147483624,
    "Craigleith Provincial Park": -2147483623,
    "Darlington Provincial Park": -2147483622,
    "Driftwood Provincial Park": -2147483620,
    "Earl Rowe Provincial Park": -2147483619,
    "Emily Provincial Park": -2147483618,
    "Esker Lakes Provincial Park": -2147483617,
    "Fairbank Provincial Park": -2147483616,
    "Ferris Provincial Park": -2147483615,
    "Finlayson Point Provincial Park": -2147483614,
    "Fitzroy Provincial Park": -2147483613,
    "Fushimi Lake Provincial Park": -2147483610,
    "Grundy Lake Provincial Park": -2147483609,
    "Halfway Lake Provincial Park": -2147483608,
    "Inverhuron Provincial Park": -2147483607,
    "Ivanhoe Lake Provincial Park": -2147483606,
    "Kakabeka Falls Provincial Park": -2147483605,
    "Kap-Kig-Iwan Provincial Park": -2147483604,
    "Kettle Lakes Provincial Park": -2147483602,
    "Killarney Provincial Park": -2147483601,
    "Killbear Provincial Park": -2147483600,
    "Lake St. Peter Provincial Park": -2147483595,
    "Lake Superior Provincial Park": -2147483646,
    "Long Point Provincial Park": -2147483593,
    "MacGregor Point Provincial Park": -2147483592,
    "MacLeod Provincial Park": -2147483521,
    "Mara Provincial Park": -2147483589,
    "Marten River Provincial Park": -2147483588,
    "Mikisew Provincial Park": -2147483584,
    "Missinaibi Provincial Park (Lake)": -2147483583,
    "Mississagi Provincial Park": -2147483581,
    "Murphys Point Provincial Park": -2147483580,
    "Nagagamisis Provincial Park": -2147483579,
    "Neys Provincial Park": -2147483578,
    "Oastler Lake Provincial Park": -2147483576,
    "Ojibway Provincial Park": -2147483573,
    "Pakwash Provincial Park": -2147483570,
    "Pancake Bay Provincial Park": -2147483569,
    "Parc Provincial McRae Point": -2147483586,
    "Parc Provincial Presqu'ile": -2147483563,
    "Pinery Provincial Park": -2147483568,
    "Point Farms Provincial Park": -2147483566,
    "Port Burwell Provincial Park": -2147483565,
    "Quetico Provincial Park": -2147483562,
    "Rainbow Falls Provincial Park": -2147483560,
    "Rene Brunelle Provincial Park": -2147483558,
    "Restoule Provincial Park": -2147483557,
    "Rideau River Provincial Park": -2147483556,
    "Rock Point Provincial Park": -2147483554,
    "Rondeau Provincial Park": -2147483553,
    "Rushing River Provincial Park": -2147483552,
    "Samuel de Champlain Provincial Park": -2147483551,
    "Sandbanks Provincial Park": -2147483549,
    "Sandbar Lake Provincial Park": -2147483548,
    "Sauble Falls Provincial Park": -2147483547,
    "Selkirk Provincial Park": -2147483546,
    "Sharbot Lake Provincial Park": -2147483545,
    "Sibbald Point Provincial Park": -2147483544,
    "Silent Lake Provincial Park": -2147483543,
    "Silver Falls Provincial Park": -2147483542,
    "Silver Lake Provincial Park": -2147483541,
    "Sioux Narrows Provincial Park": -2147483540,
    "Six Mile Lake Provincial Park": -2147483539,
    "Sleeping Giant Provincial Park": -2147483538,
    "Sturgeon Bay Provincial Park": -2147483535,
    "Turkey Point Provincial Park": -2147483531,
    "Voyageur Provincial Park": -2147483530,
    "Wakami Lake Provincial Park": -2147483528,
    "Wheatley Provincial Park": -2147483527,
    "White Lake Provincial Park": -2147483526,
    "Windy Lake Provincial Park": -2147483524,
}

#: The synthetic rec-area ID assigned to the whole Reserve Ontario
#: tenant in :mod:`camply.providers.going_to_camp.rec_areas`.
ONTARIO_PARKS_REC_AREA_ID: int = 18


def resolve_parks(queries: tuple[str, ...]) -> tuple[list[int], list[str]]:
    """
    Resolve user-supplied ``--park`` queries to ``resourceLocationId``s.

    Each query matches case-insensitively as a substring against the
    canonical park names. A query that matches multiple parks expands
    to every match (handy for ``--park Algonquin`` → all Algonquin
    campgrounds).

    Returns
    -------
    (ids, unmatched)
        ``ids`` is a de-duplicated list of resourceLocationIds; the
        order follows the first hit of each query. ``unmatched`` lists
        the input strings that produced zero hits.
    """
    ids: list[int] = []
    seen: set[int] = set()
    unmatched: list[str] = []
    for q in queries:
        needle = (q or "").strip().lower()
        if not needle:
            continue
        hits = [
            (name, pid)
            for name, pid in ONTARIO_PARKS.items()
            if needle in name.lower()
        ]
        if not hits:
            unmatched.append(q)
            continue
        for _name, pid in hits:
            if pid not in seen:
                seen.add(pid)
                ids.append(pid)
    return ids, unmatched
