# Canadian Campsites 🇨🇦

The `camply canada-campsites` command is a wrapper around `camply campsites`
shipped in [`camply.extensions.canada_filters`](https://github.com/juftin/camply/tree/main/camply/extensions/canada_filters).
It defaults to the [`GoingToCamp`](providers.md#goingtocamp) provider — which
covers Parks Canada, BC Parks, Nova Scotia, Manitoba, New Brunswick,
Newfoundland & Labrador, Gatineau Park and several Ontario regions — and
post-filters results by radius from a chosen location and by amenity
toggles (electrical outlets, water, group sites, pets, etc.).

When only `--rec-area` is supplied it auto-expands into the full list of
campgrounds for that rec-area. If you also pass `--near` / `--near-place`
the expansion is pre-filtered by great-circle distance using each
campground's `gpsCoordinates` (where the provider exposes them).

!!! info "Pick the right rec-area"

    In camply's GoingToCamp config `--rec-area 1` is **Long Point
    Region** (a small Ontario conservation authority), not Parks
    Canada. Parks Canada is **`--rec-area 14`**. Run `camply
    recreation-areas --provider GoingToCamp` for the full list.

---

## Installation

This extension ships with `camply` itself. If you are installing from a
checkout (recommended while the feature is in flight):

```powershell
# From the repo root
pipx install --editable . --force --pip-args="--no-cache-dir"
```

The `--editable` flag means future `git pull`s show up immediately
without reinstalling. `--no-cache-dir` works around occasional Windows
permission errors in `%LOCALAPPDATA%\pip\cache`. On macOS / Linux drop
the `--pip-args` flag.

Verify the command is registered:

```shell
camply canada-campsites --help
```

---

## Quick start

Find every Parks Canada campsite within 200 km of Toronto that has an
electrical outlet, and keep checking forever, emailing you when one
opens up:

=== "Bash / zsh"

    ```shell
    camply canada-campsites \
        --rec-area 14 \
        --start-date 2026-06-15 \
        --end-date 2026-09-15 \
        --near-place Toronto \
        --radius-km 200 \
        --require outlet \
        --notifications email \
        --search-forever
    ```

=== "PowerShell"

    ```powershell
    camply canada-campsites `
        --rec-area 14 `
        --start-date 2026-06-15 `
        --end-date 2026-09-15 `
        --near-place Toronto `
        --radius-km 200 `
        --require outlet `
        --notifications email `
        --search-forever
    ```

You should see something like:

```text
INFO  Using Camply Provider: "GoingToCamp"
INFO  canada-campsites: applying 2 post-filter stage(s).
INFO  canada-campsites: expanded rec-area [14] into 14 campgrounds
      (114 total, 98 outside 200 km, 2 without coordinates).
INFO  92 booking nights selected for search, ranging from 2026-06-15 to 2026-09-14
```

!!! note "Sparse coordinates on GoingToCamp"

    GoingToCamp populates `gpsCoordinates` for only some campgrounds.
    By default unlocated campgrounds are **kept** in the radius
    pre-filter so the search still polls them; pass `--strict-radius`
    to drop campgrounds with no coordinates instead.

The first time it runs, `GoingToCamp` hits its `LIST_CAMPGROUNDS`
endpoint once to build the campground list — this is a one-shot cost
even with `--search-forever`.

---

## Filtering

The extension applies amenity-based filtering at the campsite level
after every poll cycle: `--require` / `--exclude` toggles, the
`--group-only` switch, and (for providers that populate campsite
location) a `--radius-km` distance check.

When `--rec-area` is supplied without `--campground` and a centre
(`--near` / `--near-place`) is set, the campground list is **also**
pre-filtered by each campground's `gpsCoordinates` so distant
campgrounds aren't polled at all. `--strict-radius` controls whether
campgrounds missing coordinates are dropped; the default is to keep
them (because GoingToCamp populates `gpsCoordinates` sparsely).

---

## Amenity toggles

`--require` and `--exclude` accept any of the registered toggles. The
table is defined in
[`attribute_filters.py`](https://github.com/juftin/camply/blob/main/camply/extensions/canada_filters/attribute_filters.py).
Common ones:

| Toggle                                  | Matches campsites with…           |
|-----------------------------------------|-----------------------------------|
| `outlet` / `electric` / `power` / `hydro` | Electrical hookup (EV / Tesla)    |
| `water`                                 | Potable water hookup              |
| `sewer`                                 | Sewer hookup                      |
| `group`                                 | Group sites                       |
| `pet_friendly` / `pets`                 | Pet-friendly listings             |
| `scenic` / `view`                       | "Nice view" attribute             |
| `shower`                                | Shower facilities                 |
| `fire_pit`                              | Fire pit / fire ring              |

Each flag is repeatable: `--require outlet --require water` keeps only
sites that have **both**.

---

## YAML configuration

For long-running searches it's easier to keep your options in a YAML
file and run them under `tmux` or `systemd`:

```yaml
--8<-- "docs/examples/canada_campsites.yaml"
```

Then:

```shell
camply canada-campsites --yaml-config ~/canada_campsites.yaml
```

The CLI flags override the YAML `filters:` block when both are set.

---

## Notifications

`camply canada-campsites` accepts every notifier `camply campsites`
supports (`email`, `slack`, `pushover`, `telegram`, `ntfy`, `webhook`,
`apprise`, …). For email, set the environment variables documented in
[How To Run Camply](how_to_run.md). To notify multiple people, set
`EMAIL_TO_ADDRESS` to a comma-separated list:

```text
EMAIL_TO_ADDRESS=me@example.com,partner@example.com
```

---

## Full CLI reference

::: mkdocs-click
    :module: camply.extensions.canada_filters.cli
    :command: canada_campsites
    :depth: 1
