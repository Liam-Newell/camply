"""
``camply canada-campsites`` — Click subcommand for the canada_filters
extension.

This module imports the existing camply CLI machinery and registers a
new subcommand on the same ``camply_command_line`` Click group. The
existing ``camply campsites`` command is left untouched.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from typing import Optional, Tuple, Union

import click
from rich_click import RichCommand

from camply.cli import (
    _get_provider_kwargs_from_cli,
    _preferred_provider,
    _set_up_debug,
    camply_command_line,
    campground_argument,
    campsite_id_argument,
    continuous_argument,
    day_of_the_week_argument,
    debug_option,
    end_date_argument,
    equipment_argument,
    equipment_id_argument,
    nights_argument,
    notifications_argument,
    notify_first_try_argument,
    offline_search_argument,
    offline_search_path_argument,
    polling_interval_argument,
    rec_area_argument,
    search_forever_argument,
    start_date_argument,
    yaml_config_argument,
)
from camply.cli import CamplyContext
from camply.providers import GoingToCamp
from camply.search import CAMPSITE_SEARCH_PROVIDER
from camply.utils import yaml_utils

from camply.extensions.canada_filters.attribute_filters import TOGGLE_REGISTRY
from camply.extensions.canada_filters.geo import (
    haversine_km,
    parse_lat_lng,
    resolve_place,
)
from camply.extensions.canada_filters.pipeline import (
    FilterPipeline,
    GroupSiteFilter,
    RadiusFilter,
    ToggleFilter,
)
from camply.extensions.canada_filters.wrapped_search import FilteredCampingSearch
from camply.extensions.canada_filters.yaml_schema import load_pipeline_from_yaml

logger = logging.getLogger(__name__)

#: ``camply canada-campsites`` defaults to the Canadian-friendly
#: ``GoingToCamp`` provider so users do not have to remember it.
DEFAULT_CANADA_PROVIDER: str = GoingToCamp.__name__


near_argument = click.option(
    "--near",
    default=None,
    type=str,
    metavar="LAT,LNG",
    help='Centre of the radius filter, e.g. "43.6532,-79.3832" for Toronto.',
)
near_place_argument = click.option(
    "--near-place",
    default=None,
    type=str,
    metavar="CITY",
    help="Name of a known Canadian city (e.g. 'Toronto', 'Ottawa', "
    "'Vancouver') used as the centre of the radius filter. Use --near "
    "LAT,LNG for any other location.",
)
radius_km_argument = click.option(
    "--radius-km",
    default=100.0,
    show_default=True,
    type=click.FloatRange(min=0.0),
    help="Maximum distance (km) from --near / --near-place to keep.",
)
require_argument = click.option(
    "--require",
    multiple=True,
    type=click.Choice(sorted(TOGGLE_REGISTRY.keys()), case_sensitive=False),
    metavar="TOGGLE",
    help="Amenity toggle a campsite MUST have. Repeatable. Common: "
    "outlet/electric, water, group, scenic, pet_friendly, shower, fire_pit.",
)
exclude_argument = click.option(
    "--exclude",
    multiple=True,
    type=click.Choice(sorted(TOGGLE_REGISTRY.keys()), case_sensitive=False),
    metavar="TOGGLE",
    help="Amenity toggle a campsite must NOT have. Repeatable.",
)
group_only_argument = click.option(
    "--group-only/--no-group",
    "group_only",
    default=None,
    help="Restrict to group sites (--group-only) or exclude group sites "
    "(--no-group). Omit for no filtering.",
)
strict_radius_argument = click.option(
    "--strict-radius",
    "strict_radius",
    is_flag=True,
    default=False,
    show_default=True,
    help="Drop campgrounds whose provider did not include coordinates "
    "instead of keeping them (GoingToCamp populates `gpsCoordinates` "
    "sparsely, so keeping unlocated campgrounds is the default).",
)
list_filters_argument = click.option(
    "--list-filters",
    "list_filters",
    is_flag=True,
    default=False,
    help="List the attribute filters the live GoingToCamp site exposes "
    "for the given --rec-area (e.g. Electrical Service, Service Type) "
    "and exit without performing a search.",
)
# canada-campsites-specific overrides: opinionated defaults for the
# typical "find me a weekend in the next few months" use case.
weekends_argument = click.option(
    "--weekends/--any-day",
    "weekends",
    default=True,
    show_default=True,
    help="Only consider Fri/Sat nights (default). Pass --any-day to "
    "search every weekday too.",
)
search_once_argument = click.option(
    "--watch",
    "watch",
    is_flag=True,
    default=False,
    show_default=True,
    help="Continuously poll on the standard interval. Default is a "
    "single one-shot pass that exits as soon as the search finishes "
    "(no 'every N minutes' loop).",
)
weekend_chunking_argument = click.option(
    "--weekend-chunking/--no-weekend-chunking",
    "weekend_chunking",
    default=True,
    show_default=True,
    help="When --weekends is in effect, split the search horizon into "
    "one API call per Fri\u2013Sun window (fan-out capped at 10 concurrent). "
    "Booking URLs land on the actual weekend instead of the whole "
    "horizon. Pass --no-weekend-chunking to fall back to a single query.",
)
DEFAULT_HORIZON_DAYS = 120


def _default_date_range_if_missing(
    start_date: Tuple[str, ...],
    end_date: Tuple[str, ...],
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """
    Auto-fill ``--start-date`` and ``--end-date`` so canada-campsites runs
    out of the box with no date flags.

    Defaults are ``today`` and ``today + DEFAULT_HORIZON_DAYS``. If the
    caller supplied either flag explicitly, it is left untouched. Returns
    the (possibly augmented) tuples and logs a single INFO line when
    defaults are applied.
    """
    if start_date and end_date:
        return start_date, end_date
    today = date.today()
    horizon = today + timedelta(days=DEFAULT_HORIZON_DAYS)
    new_start = start_date or (today.isoformat(),)
    new_end = end_date or (horizon.isoformat(),)
    logger.info(
        "canada-campsites: defaulted date range to %s \u2192 %s "
        "(%d-day horizon). Pass --start-date / --end-date to override.",
        new_start[0],
        new_end[0],
        DEFAULT_HORIZON_DAYS,
    )
    return new_start, new_end



def _print_filter_taxonomy(rec_area: Tuple[Union[str, int]]) -> None:
    """
    Concurrently fetch the filterable-attribute taxonomy for each
    ``--rec-area`` value and print it, then return.

    Hits ``/api/attribute/filterable`` for each rec-area in parallel,
    capped at 10 concurrent requests via :class:`asyncio.Semaphore`.
    Each request runs in a worker thread because the underlying
    provider uses blocking ``requests``; the asyncio surface is only
    used to bound concurrency.
    """
    import asyncio

    from camply.providers.going_to_camp.going_to_camp_provider import GoingToCamp

    rec_area_ids: list[int] = []
    for raw in rec_area or ():
        try:
            rec_area_ids.append(int(raw))
        except (TypeError, ValueError):
            logger.error("--list-filters: unparseable --rec-area value %r", raw)
            sys.exit(1)
    if not rec_area_ids:
        logger.error(
            "--list-filters requires at least one --rec-area to know which "
            "GoingToCamp tenant to query."
        )
        sys.exit(1)

    provider = GoingToCamp()
    sem = asyncio.Semaphore(10)

    async def one(rec_id: int):
        async with sem:
            data = await asyncio.to_thread(provider.list_filterable_attributes, rec_id)
            return rec_id, data

    async def run():
        return await asyncio.gather(*(one(r) for r in rec_area_ids))

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    results = asyncio.run(run())

    for rec_id, attrs in results:
        click.echo(f"\n=== rec-area {rec_id}: {len(attrs)} filterable attributes ===")
        if not attrs:
            click.echo(
                "  (none — /api/attribute/filterable returned nothing or is "
                "unreachable for this tenant)"
            )
            continue
        for attr in attrs:
            values = ", ".join(f"{v['name']} (={v['enum']})" for v in attr["values"])
            click.echo(f"  [{attr['id']:>8}] {attr['name']}: {values or '(no enum values)'}")
    click.echo(
        "\nNote: GoingToCamp's per-resource attribute endpoint is currently "
        "unavailable, so camply cannot filter on these values server-side. "
        "Use the booking-URL links emitted by `camply canada-campsites` and "
        "narrow further on the live site."
    )


def _resolve_centre(
    near: Optional[str], near_place: Optional[str]
) -> Optional[Tuple[float, float]]:
    """
    Resolve ``--near`` / ``--near-place`` to a ``(lat, lng)`` tuple.

    Exits the process with a clear error when ``--near-place`` is
    supplied but unknown. Returns ``None`` when neither flag was set.
    """
    if near is not None:
        return parse_lat_lng(near)
    if near_place is not None:
        centre = resolve_place(near_place)
        if centre is None:
            logger.error(
                "Unknown --near-place %r. Provide explicit coordinates "
                "via --near LAT,LNG instead.",
                near_place,
            )
            sys.exit(1)
        return centre
    return None


def _expand_rec_area_campgrounds(
    provider: str,
    rec_area: Tuple[Union[str, int], ...],
    campground: Tuple[Union[str, int], ...],
    centre: Optional[Tuple[float, float]] = None,
    radius_km: Optional[float] = None,
    strict_radius: bool = False,
) -> Tuple[Union[str, int], ...]:
    """
    Auto-expand ``--rec-area`` into the matching campground IDs for
    ``GoingToCamp`` when the user did not pass ``--campground``.

    When ``centre`` + ``radius_km`` are supplied AND a campground
    exposes ``gpsCoordinates`` upstream, the campground is dropped
    from the expanded list if it lies outside the radius. Campgrounds
    without coordinates are kept by default (GoingToCamp populates
    ``gpsCoordinates`` very sparsely); pass ``strict_radius=True`` to
    drop them instead.
    """
    if provider != GoingToCamp.__name__:
        return campground
    if campground not in ((), [], None):
        return campground
    if rec_area in ((), [], None):
        return campground

    rec_area_ids = [int(value) for value in rec_area]
    finder = GoingToCamp()
    # Upstream find_campgrounds() silently honours only the first
    # rec_area_id in the list (it does ``make_list(...)[0]``), so we
    # iterate explicitly to actually cover every requested rec-area.
    facilities = []
    seen_ids: set = set()
    for rec_id in rec_area_ids:
        for facility in finder.find_campgrounds(rec_area_id=rec_id):
            if facility.facility_id in seen_ids:
                continue
            seen_ids.add(facility.facility_id)
            facilities.append(facility)
    total = len(facilities)

    if centre is not None and radius_km is not None:
        kept = []
        dropped_no_loc = 0
        dropped_too_far = 0
        kept_no_loc = 0
        for facility in facilities:
            coords = getattr(facility, "coordinates", None)
            if coords is None:
                # GoingToCamp populates gpsCoordinates very sparsely,
                # so default to keeping unlocated campgrounds unless
                # the user explicitly opts into --strict-radius.
                if strict_radius:
                    dropped_no_loc += 1
                else:
                    kept.append(facility)
                    kept_no_loc += 1
                continue
            if haversine_km(centre, coords) <= radius_km:
                kept.append(facility)
            else:
                dropped_too_far += 1
        facilities = kept
        logger.info(
            "canada-campsites: expanded rec-area %s into %d campgrounds "
            "(%d total, %d outside %.0f km, %d kept without coordinates, "
            "%d dropped without coordinates). GoingToCamp populates "
            "gpsCoordinates sparsely; pass --strict-radius to drop "
            "campgrounds with no coords.",
            rec_area_ids,
            len(facilities),
            total,
            dropped_too_far,
            radius_km,
            kept_no_loc,
            dropped_no_loc,
        )
    else:
        logger.info(
            "canada-campsites: expanded rec-area %s into %d campgrounds.",
            rec_area_ids,
            total,
        )

    if not facilities:
        logger.error(
            "canada-campsites: no campgrounds in rec-area %s survived "
            "expansion. Try increasing --radius-km, removing "
            "--strict-radius, or supplying --campground IDs.",
            rec_area_ids,
        )
        sys.exit(1)

    return tuple(facility.facility_id for facility in facilities)


def _pipeline_from_cli(
    near: Optional[str],
    near_place: Optional[str],
    radius_km: float,
    require: Tuple[str, ...],
    exclude: Tuple[str, ...],
    group_only: Optional[bool],
    strict_radius: bool,
) -> FilterPipeline:
    """
    Build a :class:`FilterPipeline` from canada-campsites CLI options.
    """
    pipeline = FilterPipeline()
    centre = _resolve_centre(near, near_place)
    if centre is not None:
        pipeline.add(
            RadiusFilter(
                center=centre,
                max_km=radius_km,
                drop_when_no_location=strict_radius,
            )
        )
    if require or exclude:
        pipeline.add(ToggleFilter(required=list(require), excluded=list(exclude)))
    if group_only is not None:
        pipeline.add(GroupSiteFilter(only_group=group_only))
    return pipeline


@camply_command_line.command("canada-campsites", cls=RichCommand)
@rec_area_argument
@campground_argument
@campsite_id_argument
@start_date_argument
@end_date_argument
@nights_argument
@weekends_argument
@day_of_the_week_argument
@notifications_argument
@continuous_argument
@search_forever_argument
@yaml_config_argument
@offline_search_argument
@offline_search_path_argument
@search_once_argument
@polling_interval_argument
@notify_first_try_argument
@equipment_argument
@equipment_id_argument
@near_argument
@near_place_argument
@radius_km_argument
@require_argument
@exclude_argument
@group_only_argument
@strict_radius_argument
@list_filters_argument
@weekend_chunking_argument
@debug_option
@click.pass_obj
def canada_campsites(
    context: CamplyContext,
    debug: bool,
    rec_area: Tuple[Union[str, int]],
    campground: Tuple[Union[str, int]],
    campsite: Tuple[Union[str, int]],
    start_date: Tuple[str],
    end_date: Tuple[str],
    weekends: bool,
    nights: int,
    continuous: bool,
    polling_interval: Optional[str],
    notifications: Tuple[str],
    notify_first_try: Optional[str],
    search_forever: Optional[str],
    watch: bool,
    yaml_config: Optional[str],
    offline_search: bool,
    offline_search_path: Optional[str],
    equipment: Tuple[Union[str, int]],
    equipment_id: Tuple[Union[str, int]],
    day: Optional[Tuple[str]],
    near: Optional[str],
    near_place: Optional[str],
    radius_km: float,
    require: Tuple[str, ...],
    exclude: Tuple[str, ...],
    group_only: Optional[bool],
    strict_radius: bool,
    list_filters: bool,
    weekend_chunking: bool,
) -> None:
    """
    Search Canadian campsites with radius + amenity post-filters.

    A wrapper around `camply campsites` that defaults to the
    ``GoingToCamp`` provider (covering Parks Canada, BC Parks, several
    Ontario regions, Nova Scotia, Manitoba, New Brunswick,
    Newfoundland & Labrador and Gatineau Park) and post-filters the
    results so only campsites within `--radius-km` of `--near` /
    `--near-place` that satisfy every `--require` toggle are kept.

    When only `--rec-area` is supplied (no `--campground`) the command
    auto-expands the rec-area into its full list of campgrounds. If
    `--near` / `--near-place` is set the expansion is also pre-filtered
    by great-circle distance using each campground's `gpsCoordinates`
    (where the provider exposes them). Because GoingToCamp populates
    `gpsCoordinates` very sparsely, campgrounds with no coordinates
    are kept by default; pass `--strict-radius` to drop them instead.

    All other arguments behave exactly like ``camply campsites``,
    including notification support (set ``EMAIL_TO_ADDRESS`` to a
    comma-separated list of addresses to email multiple people).
    """
    if context.debug is None:
        context.debug = debug
        _set_up_debug(debug=context.debug)

    if list_filters:
        _print_filter_taxonomy(rec_area)
        return

    # Apply canada-campsites' opinionated defaults: when the user doesn't
    # supply a date window, scan the next DEFAULT_HORIZON_DAYS days. Skip
    # for the YAML path; YAML files are expected to spell their dates out.
    if yaml_config is None:
        start_date, end_date = _default_date_range_if_missing(
            start_date, end_date
        )

    provider = DEFAULT_CANADA_PROVIDER
    if yaml_config is not None:
        yaml_provider, provider_kwargs, search_kwargs = (
            yaml_utils.yaml_file_to_arguments(file_path=yaml_config)
        )
        if yaml_provider:
            provider = yaml_provider
        provider = _preferred_provider(context, provider)
        pipeline = load_pipeline_from_yaml(yaml_config)
        # CLI overrides take precedence over the YAML block.
        cli_pipeline = _pipeline_from_cli(
            near=near,
            near_place=near_place,
            radius_km=radius_km,
            require=require,
            exclude=exclude,
            group_only=group_only,
            strict_radius=strict_radius,
        )
        if cli_pipeline:
            pipeline = cli_pipeline
        # Auto-expand rec-area → campgrounds for the YAML path too.
        provider_kwargs["campgrounds"] = list(
            _expand_rec_area_campgrounds(
                provider=provider,
                rec_area=tuple(provider_kwargs.get("recreation_area") or ()),
                campground=tuple(provider_kwargs.get("campgrounds") or ()),
                centre=_resolve_centre(near, near_place),
                radius_km=radius_km,
                strict_radius=strict_radius,
            )
        )
    else:
        provider = _preferred_provider(context, provider)
        rec_area_list = [str(r) for r in (rec_area or ())]
        # GoingToCamp serves one tenant per rec-area subdomain and its
        # SearchGoingToCamp class rejects more than one rec-area, so
        # split a multi-rec-area run into N independent searches and
        # aggregate the printed output. Skip the split when the user
        # explicitly pinned --campground (those IDs already imply a
        # single tenant).
        if (
            provider == DEFAULT_CANADA_PROVIDER
            and len(rec_area_list) > 1
            and not campground
        ):
            rec_area_batches: list[Tuple[Union[str, int], ...]] = [
                (r,) for r in rec_area_list
            ]
        else:
            rec_area_batches = [tuple(rec_area_list)] if rec_area_list else [()]

        pipeline = _pipeline_from_cli(
            near=near,
            near_place=near_place,
            radius_km=radius_km,
            require=require,
            exclude=exclude,
            group_only=group_only,
            strict_radius=strict_radius,
        )
        if not pipeline:
            logger.warning(
                "canada-campsites: no filters configured — results will be "
                "identical to `camply campsites --provider %s`.",
                provider,
            )
        else:
            logger.info(
                "canada-campsites: applying %d post-filter stage(s).",
                len(pipeline),
            )

        if len(rec_area_batches) > 1:
            logger.info(
                "canada-campsites: splitting %d rec-area(s) into %d independent "
                "GoingToCamp searches (one per tenant subdomain).",
                len(rec_area_list),
                len(rec_area_batches),
            )

        failed_rec_areas: list[str] = []
        for batch_idx, batch_rec_area in enumerate(rec_area_batches, start=1):
            if len(rec_area_batches) > 1:
                logger.info(
                    "canada-campsites: ── pass %d/%d (rec-area=%s) ──",
                    batch_idx,
                    len(rec_area_batches),
                    ",".join(batch_rec_area),
                )
            try:
                batch_campground = _expand_rec_area_campgrounds(
                    provider=provider,
                    rec_area=batch_rec_area,
                    campground=campground,
                    centre=_resolve_centre(near, near_place),
                    radius_km=radius_km,
                    strict_radius=strict_radius,
                )
            except SystemExit:
                # _expand_rec_area_campgrounds calls sys.exit(1) when a
                # rec-area expands to zero campgrounds; in a multi-pass
                # run, treat that as a soft failure for this rec-area.
                if len(rec_area_batches) == 1:
                    raise
                failed_rec_areas.append(",".join(batch_rec_area))
                continue
            except Exception:
                if len(rec_area_batches) == 1:
                    raise
                logger.warning(
                    "canada-campsites: rec-area %s expansion failed "
                    "(tenant unreachable or misconfigured upstream); "
                    "skipping.",
                    ",".join(batch_rec_area),
                )
                logger.debug(
                    "canada-campsites: rec-area %s expansion traceback",
                    ",".join(batch_rec_area),
                    exc_info=True,
                )
                failed_rec_areas.append(",".join(batch_rec_area))
                continue
            if not batch_campground:
                continue
            provider_kwargs, search_kwargs = _get_provider_kwargs_from_cli(
                rec_area=batch_rec_area,
                campground=batch_campground,
                campsite=campsite,
                start_date=start_date,
                end_date=end_date,
                weekends=weekends,
                nights=nights,
                provider=provider,
                continuous=continuous,
                polling_interval=polling_interval,
                notifications=notifications,
                notify_first_try=notify_first_try,
                search_forever=search_forever,
                search_once=False,
                offline_search=offline_search,
                offline_search_path=offline_search_path,
                equipment=equipment,
                equipment_id=equipment_id,
                day=day,
                yaml_config=yaml_config,
            )
            # canada-campsites is one-shot by default: bypass camply's
            # "Searching every N minutes" continuous loop unless --watch.
            if not watch:
                search_kwargs["continuous"] = False
                search_kwargs["search_once"] = False

            provider_class = CAMPSITE_SEARCH_PROVIDER[provider]
            # Swap in the chunked GoingToCamp search when the user is
            # actually asking for weekends; the upstream class issues a
            # single API call across the whole horizon and labels every
            # hit with the wrong weekend, so chunking is the only way
            # booking URLs land on the specific Fri–Sun the site is
            # bookable on.
            if (
                provider == DEFAULT_CANADA_PROVIDER
                and weekend_chunking
                and weekends
                and yaml_config is None
            ):
                from camply.extensions.canada_filters.chunked_search import (
                    WeekendChunkedSearchGoingToCamp,
                )

                provider_class = WeekendChunkedSearchGoingToCamp
            camping_finder = provider_class(**provider_kwargs)
            filtered = FilteredCampingSearch(wrapped=camping_finder, pipeline=pipeline)
            try:
                filtered.get_matching_campsites(**search_kwargs)
            except Exception:
                if len(rec_area_batches) == 1:
                    raise
                logger.warning(
                    "canada-campsites: rec-area %s search failed; "
                    "continuing with the remaining rec-areas.",
                    ",".join(batch_rec_area),
                )
                logger.debug(
                    "canada-campsites: rec-area %s search traceback",
                    ",".join(batch_rec_area),
                    exc_info=True,
                )
                failed_rec_areas.append(",".join(batch_rec_area))
        if failed_rec_areas:
            logger.warning(
                "canada-campsites: %d/%d rec-area(s) failed: %s",
                len(failed_rec_areas),
                len(rec_area_batches),
                ", ".join(failed_rec_areas),
            )
        return

    # YAML path falls through here: build kwargs the legacy way and run once.
    if not pipeline:
        logger.warning(
            "canada-campsites: no filters configured — results will be "
            "identical to `camply campsites --provider %s`.",
            provider,
        )
    else:
        logger.info(
            "canada-campsites: applying %d post-filter stage(s).",
            len(pipeline),
        )

    provider_class = CAMPSITE_SEARCH_PROVIDER[provider]
    if (
        provider == DEFAULT_CANADA_PROVIDER
        and weekend_chunking
        and weekends
        and yaml_config is None
    ):
        from camply.extensions.canada_filters.chunked_search import (
            WeekendChunkedSearchGoingToCamp,
        )

        provider_class = WeekendChunkedSearchGoingToCamp
    camping_finder = provider_class(**provider_kwargs)
    filtered = FilteredCampingSearch(wrapped=camping_finder, pipeline=pipeline)
    filtered.get_matching_campsites(**search_kwargs)
