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
    search_once_argument,
    start_date_argument,
    weekends_argument,
    yaml_config_argument,
)
from camply.cli import CamplyContext
from camply.providers import GoingToCamp
from camply.search import CAMPSITE_SEARCH_PROVIDER
from camply.utils import yaml_utils

from camply.extensions.canada_filters.attribute_filters import TOGGLE_REGISTRY
from camply.extensions.canada_filters.geo import parse_lat_lng, resolve_place
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
keep_without_location_argument = click.option(
    "--keep-without-location",
    is_flag=True,
    default=False,
    show_default=True,
    help="Keep campsites whose provider did not include coordinates "
    "instead of dropping them from the radius filter.",
)


def _pipeline_from_cli(
    near: Optional[str],
    near_place: Optional[str],
    radius_km: float,
    require: Tuple[str, ...],
    exclude: Tuple[str, ...],
    group_only: Optional[bool],
    keep_without_location: bool,
) -> FilterPipeline:
    """
    Build a :class:`FilterPipeline` from canada-campsites CLI options.
    """
    pipeline = FilterPipeline()
    centre = None
    if near is not None:
        centre = parse_lat_lng(near)
    elif near_place is not None:
        centre = resolve_place(near_place)
        if centre is None:
            logger.error(
                "Unknown --near-place %r. Provide explicit coordinates "
                "via --near LAT,LNG instead.",
                near_place,
            )
            sys.exit(1)
    if centre is not None:
        pipeline.add(
            RadiusFilter(
                center=centre,
                max_km=radius_km,
                drop_when_no_location=not keep_without_location,
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
@keep_without_location_argument
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
    search_once: bool,
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
    keep_without_location: bool,
) -> None:
    """
    Search Canadian campsites with radius + amenity post-filters.

    A wrapper around `camply campsites` that defaults to the
    ``GoingToCamp`` provider (covering Parks Canada, BC Parks, several
    Ontario regions, Nova Scotia, Manitoba, New Brunswick,
    Newfoundland & Labrador and Gatineau Park) and post-filters the
    results so only campsites within `--radius-km` of `--near` /
    `--near-place` that satisfy every `--require` toggle are kept.

    All other arguments behave exactly like ``camply campsites``,
    including notification support (set ``EMAIL_TO_ADDRESS`` to a
    comma-separated list of addresses to email multiple people).
    """
    if context.debug is None:
        context.debug = debug
        _set_up_debug(debug=context.debug)

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
            keep_without_location=keep_without_location,
        )
        if cli_pipeline:
            pipeline = cli_pipeline
    else:
        provider = _preferred_provider(context, provider)
        provider_kwargs, search_kwargs = _get_provider_kwargs_from_cli(
            rec_area=rec_area,
            campground=campground,
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
            search_once=search_once,
            offline_search=offline_search,
            offline_search_path=offline_search_path,
            equipment=equipment,
            equipment_id=equipment_id,
            day=day,
            yaml_config=yaml_config,
        )
        pipeline = _pipeline_from_cli(
            near=near,
            near_place=near_place,
            radius_km=radius_km,
            require=require,
            exclude=exclude,
            group_only=group_only,
            keep_without_location=keep_without_location,
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

    provider_class = CAMPSITE_SEARCH_PROVIDER[provider]
    camping_finder = provider_class(**provider_kwargs)
    filtered = FilteredCampingSearch(wrapped=camping_finder, pipeline=pipeline)
    filtered.get_matching_campsites(**search_kwargs)
