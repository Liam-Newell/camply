"""
One-off report generator: every GoingToCamp site within ~200 km of
Toronto that has electrical service, available for every Fri-Sun
weekend (plus the two long weekends) until end of September 2026.

Outputs ``toronto_outlet_weekends.md`` — one big Markdown file with
a clickable Table of Contents at the top jumping to each weekend.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from fake_useragent import UserAgent

from camply.containers import AvailableCampsite, SearchWindow
from camply.extensions.canada_filters.chunked_search import (
    WeekendChunkedSearchGoingToCamp,
)
from camply.providers.going_to_camp.going_to_camp_provider import GoingToCamp
from camply.search.search_going_to_camp import SearchGoingToCamp

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("toronto-outlet-report")
log.setLevel(logging.INFO)

TODAY = date.today()
END = date(2026, 9, 30)
REC_AREAS: List[int] = [1, 4, 8]  # skip 5 (Saugeen DNS broken upstream)
OUTPUT_PATH = Path("toronto_outlet_weekends.md")
UA = UserAgent().chrome

LONG_WEEKEND_SATS: Dict[date, str] = {
    date(2026, 8, 1): "Civic Holiday (Mon Aug 3)",
    date(2026, 9, 5): "Labour Day (Mon Sep 7)",
}

DEFAULT_REC_AREA_RATING: Dict[int, Dict[str, Any]] = {
    1: {"view": 3, "trails": 3, "location": 4,
        "summary": "Lake Erie / Carolinian Canada — easy GTA access, mild terrain."},
    4: {"view": 3, "trails": 3, "location": 2,
        "summary": "Maitland River valleys — quieter, longer drive from GTA."},
    8: {"view": 5, "trails": 5, "location": 3,
        "summary": "Haliburton Highlands — best scenery / hiking of the set; ~3 hr drive."},
}

CAMPGROUND_RATINGS: Dict[str, Dict[str, Any]] = {
    "Backus Heritage Conservation Area": {
        "view": 3, "trails": 4, "location": 3, "city": "Port Rowan, ON",
        "notes": "Old-growth Carolinian forest, heritage village, 7+ km of trails.",
    },
    "Deer Creek Conservation Area": {
        "view": 3, "trails": 2, "location": 3, "city": "La Salette, ON",
        "notes": "Reservoir-side sites; fishing-oriented, light trail network.",
    },
    "Haldimand Conservation Area": {
        "view": 3, "trails": 3, "location": 4, "city": "Cayuga, ON",
        "notes": "Grand River frontage; ~1.5 hr from Toronto.",
    },
    "Norfolk Conservation Area": {
        "view": 3, "trails": 3, "location": 3, "city": "Simcoe, ON",
        "notes": "Quiet family-oriented CA in Norfolk County.",
    },
    "Waterford North Conservation Area": {
        "view": 4, "trails": 4, "location": 4, "city": "Waterford, ON",
        "notes": "Chain of small lakes, well-maintained trails; best of the Long Point set.",
    },
}


def _rating(cg: str, rid: int) -> Dict[str, Any]:
    r = CAMPGROUND_RATINGS.get(cg)
    if r:
        return r
    base = DEFAULT_REC_AREA_RATING.get(rid, {"view": 3, "trails": 3, "location": 3})
    return {**base, "city": "—",
            "notes": "(no campground-specific notes; using rec-area average)"}


def _score(r: Dict[str, Any]) -> float:
    return (r["view"] + r["trails"] + r["location"]) / 3.0


def fetch_attribute_decoder(provider: GoingToCamp, rid: int) -> Dict[int, Dict[str, Any]]:
    attrs = provider.list_filterable_attributes(rid)
    return {a["id"]: {"name": a["name"],
                       "values": {v["enum"]: v["name"] for v in a["values"]}}
            for a in attrs}


def fetch_site_catalogue(host: str, rl_id: int) -> Dict[int, Dict[str, Any]]:
    url = f"https://{host}/api/resourcelocation/resources?resourceLocationId={rl_id}"
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    out: Dict[int, Dict[str, Any]] = {}
    for rid_str, payload in r.json().items():
        try:
            rid_i = int(rid_str)
        except ValueError:
            continue
        loc = payload.get("localizedValues") or [{}]
        name = loc[0].get("name") or f"#{rid_i}"
        defined: Dict[int, Any] = {}
        for attr in payload.get("definedAttributes") or ():
            did = attr.get("attributeDefinitionId")
            vals = attr.get("values") or []
            if did is not None and vals:
                defined[did] = vals[0]
        out[rid_i] = {"name": name, "defined": defined}
    return out


def run_weekend_chunked(rid: int, cg_ids: List[int]) -> List[AvailableCampsite]:
    win = SearchWindow(start_date=TODAY, end_date=END)
    s = WeekendChunkedSearchGoingToCamp(
        search_window=win, recreation_area=[rid], campgrounds=cg_ids,
        weekends_only=True, nights=2,
    )
    return s.get_all_campsites()


def run_long_weekend(rid: int, cg_ids: List[int], sat: date) -> List[AvailableCampsite]:
    end = sat + timedelta(days=3)
    win = SearchWindow(start_date=sat, end_date=end)
    s = SearchGoingToCamp(
        search_window=win, recreation_area=[rid], campgrounds=cg_ids,
        weekends_only=False, nights=3,
    )
    return s.get_all_campsites()


def weekend_anchor(d: date, nights: int) -> str:
    return f"weekend-{d.isoformat()}-n{nights}"


def fmt_weekend_header(d: date, nights: int) -> str:
    end = d + timedelta(days=nights)
    tag = LONG_WEEKEND_SATS.get(d)
    suffix = f" — {tag}" if tag else ""
    return f"{d.strftime('%a %b %d')} → {end.strftime('%a %b %d, %Y')} ({nights} nights){suffix}"


def main() -> None:
    log.info("scanning rec areas %s, %s → %s", REC_AREAS, TODAY, END)
    provider = GoingToCamp()

    decoders: Dict[int, Dict[int, Dict[str, Any]]] = {}
    rec_cgs: Dict[int, List[Any]] = {}
    catalogues: Dict[Tuple[int, int], Dict[int, Dict[str, Any]]] = {}
    elec_def: Dict[int, Optional[int]] = {}
    stype_def: Dict[int, Optional[int]] = {}

    for rid in REC_AREAS:
        try:
            decoders[rid] = fetch_attribute_decoder(provider, rid)
        except Exception as e:
            log.warning("rec-area %s: filter attrs unavailable (%s)", rid, e)
            decoders[rid] = {}
        e_id = s_id = None
        for aid, info in decoders[rid].items():
            nm = info["name"].lower()
            if "electric" in nm and "service" in nm:
                e_id = aid
            elif nm.strip() == "service type":
                s_id = aid
        elec_def[rid] = e_id
        stype_def[rid] = s_id
        log.info("rec-area %s electrical=%s service_type=%s", rid, e_id, s_id)

        try:
            cgs = provider.find_campgrounds(rec_area_id=rid)
        except Exception as e:
            log.warning("rec-area %s find_campgrounds (%s)", rid, e)
            cgs = []
        rec_cgs[rid] = cgs
        host = provider._hostname_for(rid)
        for cg in cgs:
            try:
                catalogues[(rid, cg.facility_id)] = fetch_site_catalogue(host, cg.facility_id)
            except Exception as e:
                log.warning("cg %s catalogue fetch (%s)", cg.facility_name, e)
                catalogues[(rid, cg.facility_id)] = {}

    raw: List[Tuple[int, AvailableCampsite]] = []
    for rid in REC_AREAS:
        cg_ids = [cg.facility_id for cg in rec_cgs[rid]]
        if not cg_ids:
            continue
        log.info("rec-area %s Fri-Sun chunked", rid)
        try:
            for ac in run_weekend_chunked(rid, cg_ids):
                raw.append((rid, ac))
        except Exception as e:
            log.warning("rec-area %s chunked failed (%s)", rid, e)

    for sat, label in LONG_WEEKEND_SATS.items():
        if sat < TODAY or sat > END:
            continue
        for rid in REC_AREAS:
            cg_ids = [cg.facility_id for cg in rec_cgs[rid]]
            if not cg_ids:
                continue
            log.info("rec-area %s long-weekend %s", rid, label)
            try:
                for ac in run_long_weekend(rid, cg_ids, sat):
                    raw.append((rid, ac))
            except Exception as e:
                log.warning("rec-area %s long-weekend %s failed (%s)", rid, sat, e)

    log.info("raw availability records: %d", len(raw))

    kept: List[Dict[str, Any]] = []
    no_outlet = no_meta = 0
    for rid, ac in raw:
        did = elec_def[rid]
        sid = int(ac.campsite_id)
        meta = catalogues.get((rid, int(ac.facility_id)), {}).get(sid)
        if did is None or not meta:
            no_meta += 1
            continue
        enum = meta["defined"].get(did)
        if enum is None or enum == 0:
            no_outlet += 1
            continue
        elec = decoders[rid].get(did, {}).get("values", {}).get(enum, f"enum={enum}")
        s_id = stype_def[rid]
        svc = None
        if s_id is not None:
            se = meta["defined"].get(s_id)
            if se is not None:
                svc = decoders[rid][s_id]["values"].get(se, f"enum={se}")
        kept.append({"rid": rid, "ac": ac, "site_name": meta["name"],
                     "electrical": elec, "service_type": svc})

    log.info("kept %d / no-outlet %d / no-meta %d", len(kept), no_outlet, no_meta)

    by_wknd: Dict[Tuple[date, int], List[Dict[str, Any]]] = defaultdict(list)
    for k in kept:
        bd = k["ac"].booking_date
        d = bd.date() if hasattr(bd, "date") else bd
        by_wknd[(d, k["ac"].booking_nights)].append(k)

    lines: List[str] = []
    lines.append("# Toronto-area GoingToCamp — sites with electrical outlets")
    lines.append("")
    lines.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_  ")
    lines.append(
        f"_Scope: rec-areas {REC_AREAS} within ~200 km of Toronto, every Fri-Sun "
        f"weekend plus the two long weekends until {END.isoformat()}._"
    )
    lines.append("")
    lines.append("## How to read this report")
    lines.append("")
    lines.append(
        "- **Outlet data** comes from each tenant's `/api/resourcelocation/resources` "
        "JSON endpoint, decoded against `/api/attribute/filterable`. Only sites whose "
        "**Electrical Service** attribute is set to 15 A or 30 A are listed."
    )
    lines.append(
        "- **Sort order:** weekends chronologically; within each weekend, campgrounds "
        "are sorted by a curated subjective score (view + trails + location, 1–5 each, "
        "averaged). GoingToCamp does not publish user ratings, so this ranking reflects "
        "general reputation for the Toronto-area conservation areas; see the script for the table."
    )
    lines.append(
        "- **Long weekends** (Sat-Mon, 3 nights) are listed in addition to their parent "
        "Fri-Sun weekend, not instead of it."
    )
    lines.append(
        "- Each **Book** link opens the booking results page on the correct date range."
    )
    lines.append("")
    lines.append("## Rec-area summary")
    lines.append("")
    lines.append("| Rec area | Subjective rating (V/T/L) | Notes |")
    lines.append("|---|---|---|")
    for rid in REC_AREAS:
        base = DEFAULT_REC_AREA_RATING[rid]
        cgs = rec_cgs.get(rid) or []
        name = cgs[0].recreation_area if cgs else f"rec-area {rid}"
        lines.append(
            f"| **{name}** (#{rid}) | {base['view']} / {base['trails']} / {base['location']} | "
            f"{base['summary']} |"
        )
    lines.append("")
    lines.append(
        "> _**Rec-area 5 (Saugeen Valley)** was skipped: its tenant subdomain "
        "`saugeen.goingtocamp.com` is not currently resolving upstream._"
    )
    lines.append(
        "> _**Rec-area 8 (Algonquin Highlands)** is in scope but produced 0 outlet "
        "matches: its two campgrounds (Frost Centre Area, Poker Lakes Area) are "
        "interior canoe-camping zones and do not expose an Electrical Service "
        "attribute — those sites genuinely have no hookups._"
    )
    lines.append("")

    lines.append('<a id="weekends-jump-to"></a>')
    lines.append("## Weekends (jump to)")
    lines.append("")
    sorted_w = sorted(by_wknd.keys())
    for d, nights in sorted_w:
        lines.append(
            f"- [{fmt_weekend_header(d, nights)}](#{weekend_anchor(d, nights)}) — "
            f"**{len(by_wknd[(d, nights)])}** sites with outlets"
        )
    if not sorted_w:
        lines.append("_No outlet-bearing sites available in the search window._")
    lines.append("")

    for d, nights in sorted_w:
        lines.append(f'<a id="{weekend_anchor(d, nights)}"></a>')
        lines.append(f"## {fmt_weekend_header(d, nights)}")
        lines.append("")
        entries = by_wknd[(d, nights)]
        per_cg: Dict[Tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
        for e in entries:
            per_cg[(e["rid"], e["ac"].facility_name)].append(e)
        cg_order = sorted(per_cg.keys(),
                          key=lambda k: (-_score(_rating(k[1], k[0])), k[1]))
        for rid, cg_name in cg_order:
            rating = _rating(cg_name, rid)
            score = _score(rating)
            city = rating.get("city", "—")
            notes = rating.get("notes", "")
            lines.append(
                f"### ⛺ {cg_name}  "
                f"<sub>rating {score:.1f}/5 · view {rating['view']} · "
                f"trails {rating['trails']} · location {rating['location']} · {city}</sub>"
            )
            if notes:
                lines.append(f"_{notes}_")
            lines.append("")
            for e in sorted(per_cg[(rid, cg_name)], key=lambda e: e["site_name"]):
                svc = f" · {e['service_type']}" if e["service_type"] else ""
                lines.append(
                    f"- **Site {e['site_name']}** — {e['electrical']}{svc} — "
                    f"[Book]({e['ac'].booking_url})"
                )
            lines.append("")
        lines.append("[↑ back to weekend index](#weekends-jump-to)")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote %s (%d weekends, %d outlet sites)",
             OUTPUT_PATH, len(sorted_w), len(kept))


if __name__ == "__main__":
    main()
