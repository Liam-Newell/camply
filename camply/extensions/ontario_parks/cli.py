"""
``camply ontario-parks`` — Click subcommand targeting
``reservations.ontarioparks.ca``.

Reserve Ontario runs the same Aspira/CampIT booking SPA as every
GoingToCamp tenant, so the existing ``GoingToCamp`` provider and the
existing ``camply canada-campsites`` search/notification pipeline cover
it as-is. This thin subcommand just:

* preselects ``--rec-area 18`` (the synthetic rec-area assigned to the
  Ontario Parks tenant in :mod:`camply.providers.going_to_camp.rec_areas`),
* adds a ``--park NAME`` shortcut that substring-matches against the
  static catalogue in :mod:`camply.extensions.ontario_parks.parks` and
  expands to the right ``--campground`` IDs,
* defers everything else (date defaults, weekend chunking, radius and
  amenity filters, notifications, YAML config) to the existing
  ``canada-campsites`` command.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional, Tuple, Union

import click
from rich_click import RichCommand

from camply.cli import (
    CamplyContext,
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
    search_forever_argument,
    start_date_argument,
    yaml_config_argument,
)
from camply.extensions.canada_filters.cli import (
    canada_campsites,
    exclude_argument,
    group_only_argument,
    list_filters_argument,
    near_argument,
    near_place_argument,
    radius_km_argument,
    require_argument,
    search_once_argument,
    strict_radius_argument,
    weekend_chunking_argument,
    weekends_argument,
)
from camply.extensions.ontario_parks.parks import (
    ONTARIO_PARKS,
    ONTARIO_PARKS_REC_AREA_ID,
    resolve_parks,
)

logger = logging.getLogger(__name__)


park_argument = click.option(
    "--park",
    "park",
    multiple=True,
    type=str,
    metavar="NAME",
    help="Reserve Ontario park (substring match, repeatable). Examples: "
    "'Killbear', 'Algonquin' (matches every Algonquin sub-campground), "
    "'Bon Echo'. Resolved against the catalogue in "
    "camply.extensions.ontario_parks.parks.ONTARIO_PARKS. Pass --list-parks "
    "to see all known parks.",
)
list_parks_argument = click.option(
    "--list-parks",
    "list_parks",
    is_flag=True,
    default=False,
    help="Print the catalogue of known Reserve Ontario parks and exit.",
)


@camply_command_line.command("ontario-parks", cls=RichCommand)
@park_argument
@list_parks_argument
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
@click.pass_context
def ontario_parks(
    ctx: click.Context,
    debug: bool,
    park: Tuple[str, ...],
    list_parks: bool,
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
    Search Reserve Ontario (``reservations.ontarioparks.ca``) campsites.

    Reserve Ontario shares the GoingToCamp booking backend, so this is
    a thin wrapper around ``camply canada-campsites`` that preselects
    the Ontario Parks tenant (--rec-area 18) and adds a ``--park NAME``
    shortcut for picking individual parks by name.

    Examples
    --------
    Find every available outlet-equipped site at Killbear over the next
    four months::

        camply ontario-parks --park Killbear --require outlet

    Watch all Algonquin campgrounds for Civic Holiday long-weekend
    openings::

        camply ontario-parks --park Algonquin --start-date 2026-08-01 \\
            --end-date 2026-08-04 --nights 3

    All other flags behave exactly like ``camply canada-campsites``.
    """
    if list_parks:
        click.echo(f"Reserve Ontario — {len(ONTARIO_PARKS)} known parks:\n")
        for name, pid in sorted(ONTARIO_PARKS.items()):
            click.echo(f"  {pid:>13}  {name}")
        return

    campground_ids: list[Union[str, int]] = list(campground or ())
    if park:
        resolved, unmatched = resolve_parks(tuple(park))
        if unmatched:
            click.secho(
                f"ontario-parks: --park query(ies) matched nothing: "
                f"{', '.join(repr(u) for u in unmatched)}. "
                f"Run `camply ontario-parks --list-parks` to see "
                f"available names.",
                fg="red",
                err=True,
            )
            sys.exit(1)
        if not resolved:
            click.secho(
                "ontario-parks: no parks resolved from --park flags.",
                fg="red",
                err=True,
            )
            sys.exit(1)
        campground_ids.extend(resolved)
        logger.info(
            "ontario-parks: --park resolved to %d campground id(s): %s",
            len(resolved),
            resolved,
        )

    ctx.invoke(
        canada_campsites,
        debug=debug,
        rec_area=(ONTARIO_PARKS_REC_AREA_ID,),
        campground=tuple(campground_ids),
        campsite=campsite,
        start_date=start_date,
        end_date=end_date,
        weekends=weekends,
        nights=nights,
        continuous=continuous,
        polling_interval=polling_interval,
        notifications=notifications,
        notify_first_try=notify_first_try,
        search_forever=search_forever,
        watch=watch,
        yaml_config=yaml_config,
        offline_search=offline_search,
        offline_search_path=offline_search_path,
        equipment=equipment,
        equipment_id=equipment_id,
        day=day,
        near=near,
        near_place=near_place,
        radius_km=radius_km,
        require=require,
        exclude=exclude,
        group_only=group_only,
        strict_radius=strict_radius,
        list_filters=list_filters,
        weekend_chunking=weekend_chunking,
    )
