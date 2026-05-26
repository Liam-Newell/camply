# Reserve Ontario / Ontario Parks 🇨🇦

The `camply ontario-parks` command targets
[`reservations.ontarioparks.ca`](https://reservations.ontarioparks.ca/),
the booking system for every reservable Ontario provincial park —
Algonquin, Killbear, Killarney, Bon Echo, Sandbanks, Arrowhead,
Frontenac, Silent Lake, MacGregor Point, Awenda, Restoule, Sibbald
Point, and 80+ more.

Reserve Ontario runs the **same Aspira/CampIT backend** as every
GoingToCamp tenant, so under the hood this command is a thin wrapper
around [`canada-campsites`](canada_campsites.md): same provider, same
weekend chunking, same notification pipeline, same radius + amenity
post-filters. It just preselects `--rec-area 18` (the synthetic
rec-area assigned to the Ontario Parks tenant) and adds a
`--park NAME` shortcut so you don't have to memorise
`resourceLocationId`s like `-2147483600`.

This extension ships with `camply` itself
([`camply.extensions.ontario_parks`](https://github.com/juftin/camply/tree/main/camply/extensions/ontario_parks)).

---

## Quick start

Find a 30 A outlet site at Killbear for any weekend between now and
Labour Day, and keep checking forever, emailing you when one opens up:

=== "Bash / zsh"

    ```shell
    camply ontario-parks \
        --park Killbear \
        --start-date 2026-06-15 \
        --end-date 2026-09-15 \
        --require outlet \
        --notifications email \
        --search-forever
    ```

=== "PowerShell"

    ```powershell
    camply ontario-parks `
        --park Killbear `
        --start-date 2026-06-15 `
        --end-date 2026-09-15 `
        --require outlet `
        --notifications email `
        --search-forever
    ```

`--park` substring-matches case-insensitively against the curated
catalogue in
[`camply.extensions.ontario_parks.parks`](https://github.com/juftin/camply/tree/main/camply/extensions/ontario_parks/parks.py).
The flag is repeatable and expands to every match, so
`--park Algonquin` watches all 10 Algonquin frontcountry campgrounds
(Mew Lake, Pog Lake, Lake of Two Rivers, Canisbay, Achray, Brent,
Kiosk, Rock Lake, Tea Lake, Whitefish Lake) in one invocation:

```shell
camply ontario-parks \
    --park Algonquin \
    --start-date 2026-08-01 \
    --end-date 2026-08-04 \
    --nights 3 \
    --require outlet
```

To see every known park:

```shell
camply ontario-parks --list-parks
```

To see every filterable attribute Reserve Ontario exposes (Electrical
Service, Service Type, Privacy, Site Shade, Pull-through, etc.):

```shell
camply ontario-parks --park Killbear --list-filters
```

---

## What it adds on top of `canada-campsites`

| Flag                    | Behaviour                                                                |
|-------------------------|--------------------------------------------------------------------------|
| `--park NAME`           | Repeatable substring match against `ONTARIO_PARKS`. Matched parks are added to `--campground` automatically. |
| `--list-parks`          | Print the 93-entry park catalogue (`name → resourceLocationId`) and exit. |
| `--rec-area`            | **Hard-coded to 18.** Don't pass it — `ontario-parks` always targets the Ontario Parks tenant. |

Everything else (`--start-date`, `--end-date`, `--nights`, `--weekends`,
`--require`, `--exclude`, `--near-place`, `--radius-km`,
`--notifications`, `--search-forever`, `--yaml-config`, weekend
chunking, …) is delegated verbatim to `canada-campsites`. See
[Canadian Campsites](canada_campsites.md) for the full reference.

!!! tip "GPS coordinates are sparse"

    Reserve Ontario rarely populates `gpsCoordinates`, so the
    `--near-place / --radius-km` pre-filter usually keeps every
    park (because the default behaviour is to keep campgrounds with
    no coordinates rather than drop them). Pass `--strict-radius`
    to flip that behaviour.

---

## Generating an outlet report

The repo ships a sibling script of `canada_outlet_report.py` that
crawls all 93 Ontario Parks (plus the three Toronto-area conservation
authorities) and writes one big Markdown file listing every
outlet-equipped site available across every Fri-Sun weekend (plus
Civic Holiday and Labour Day long weekends) through the end of
September:

```shell
python -m scripts.ontario_outlet_report
```

Output lands at `ontario_outlet_weekends.md` in the repo root —
typically ~4–5 MB / ~16,000+ sites with clickable
`reservations.ontarioparks.ca` booking links.

---

## Full CLI reference

::: mkdocs-click
    :module: camply.extensions.ontario_parks.cli
    :command: ontario_parks
    :depth: 1
