# Open311 Scraper

Standalone service that fetches **all 16 service types** from Boston's Open311 API and stores raw daily JSON files in S3/Tigris.

## Why not just use CKAN?

The city publishes 311 data in bulk on data.boston.gov, but that export **strips critical fields**:

| Field | Open311 API | CKAN Bulk |
|-------|-------------|-----------|
| Citizen description (free text) | Present (94% of tickets) | **Removed** |
| Photos (Cloudinary URLs) | Present (85% of needle tickets) | **Always empty** |
| Staff status notes | Present | Truncated to `closure_reason` only |
| "Other" tickets (General Request) | Present (142k+) | **Missing entirely** |

This scraper preserves the complete records that CKAN strips down.

## Service types

All 16 types exposed by the BOS:311 app are scraped:

- `other` — General Request (invisible in CKAN)
- `needles` — Needle Cleanup
- `encampments` — Encampments
- `potholes` — Pothole Repair
- `sidewalks` — Broken Sidewalk
- `dead-animals` — Dead Animal Pickup
- `graffiti` — Illegal Graffiti
- `litter` — Litter
- `rodents` — Rodent Sighting
- `trash-cans` — Overflowing Trash Can
- `abandoned-vehicles` — Abandoned Vehicle
- `parking` — Illegal Parking
- `traffic-signals` — Traffic Signal
- `signs` — Damaged Sign
- `abandoned-bikes` — Abandoned Bicycle
- `illegal-trash` — Residential Trash out Illegally

## S3 layout

```
open311/
  other/2023-01-01.json
  needles/2023-01-01.json
  potholes/2023-01-01.json
  ...
  manifest.json
```

## Railway deployment

Deploy as a **cron service** in the same Railway project. Shares the same Tigris bucket.

Env vars: `BUCKET`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`, `ENDPOINT`, `REGION`

Root directory: `services/open311-scraper`

Cron schedule: `0 6 * * *` (daily at 6 AM UTC)

## First run

Backfills from 2023-01-01 across all 16 types. Full backfill takes ~36 hours at the API rate limit. Each type is independently resumable — if the service restarts, it skips days already in S3.

## Usage

```bash
python fetch.py                    # fetch all types, backfill from 2023
python fetch.py --type other       # fetch only "Other" tickets
python fetch.py --type needles     # fetch only needle tickets
python fetch.py --start 2025-01-01 # start from a specific date
python fetch.py --dry-run          # show plan without fetching
```

## Sweep mode

`--sweep` fetches a day's tickets with **no `service_code`** filter, so a
single request returns every service type at once — one day = one query
(paginated), instead of one query per (day, type). This is how the
2023-01-01→present backfill runs: per-type mode would need 30 requests per
day; sweep mode needs one plus pagination.

```bash
python fetch.py --sweep --start 2023-01-01 --delay 10
```

Use `--delay 10` (vs. the per-type default of 7) for backfill sweeps — it
leaves headroom under the shared 10 req/min API budget so the daily per-type
job never gets rate-limited waiting behind a backfill.

**Staging layout** — sweep mode never writes the canonical `open311/{slug}/`
paths. Everything lands under a separate prefix:

```
open311/_sweep/
  {slug}/YYYY-MM-DD.json       # one file per slug that had records that day
  _unmapped/YYYY-MM-DD.json    # flat list of records whose service_code
                                # isn't in SERVICE_TYPES
  _done/YYYY-MM-DD.json        # completion marker: {pages, records, slugs,
                                # unmapped, fetched_at} — this is the resume
                                # index for sweep mode, not the slug files
  manifest.json                # aggregated unmapped_codes + slug_counts
```

A day is buffered entirely in memory and written only after its terminal
(< 100 record) page. If any part of a day fails — the fetch, a `save_day`
exception (S3 rate limit, connection drop, etc.), a post-write verification
mismatch, or even the final `_done/` marker write itself — every object
written for that day is rolled back and no `_done/` marker is written, so
the next run retries the whole day from scratch. This means a page-3
failure, or an S3 error partway through the per-slug writes, can never leave
a day half-written across slug files.

**Crash recovery / orphan cleanup.** If the process is killed mid-write
(not just a clean exception), the rollback above never runs and slug files
from that attempt can be left in S3 with no `_done/` marker. Resume treats
a day with no marker as not-done and retries it — but before writing
anything fresh, `sweep_day` first batch-deletes every possible slug/unmapped
key for that day (built from the static `SERVICE_TYPES` list, not an S3
listing, so it's one API call regardless of slug count; deleting a key that
doesn't exist is a no-op). So a retried day is always overwritten cleanly,
never stacked on top of a crash-orphaned file.

**Pause coordination.** Because both the daily per-type job and a backfill
sweep draw from the same unauthenticated rate limit, the daily job can
signal the sweep to yield: pass `--coordinate-sweep` and it writes
`open311/_sweep/_pause` before it starts and deletes it when it's done (in a
`finally`). **This flag is off by default** — a normal per-type run makes no
S3 calls against the pause key at all. Railway's daily cron should add
`--coordinate-sweep` once the backfill sweep starts running; until then,
leaving it off means the daily job never grows a new S3 failure path.

The pause object body is JSON: `{"set_at": "<ISO UTC timestamp>",
"ttl_seconds": 7200}` (2 hours). The sweep checks for that key before every
day and blocks (polling every 60s) while it's present *and fresh*. A pause
older than `set_at + ttl_seconds` — or, for a non-JSON/unparsable body,
older than 2 hours by the object's S3 `LastModified` — is treated as stale:
logged, deleted, and ignored. As a second backstop, a single sweep-loop
call to the pause check will wait at most 3 hours total before proceeding
regardless. Together these mean a daily-job crash that skips its `finally`
(SIGKILL, OOM) can no longer deadlock the backfill forever.

`wait_if_paused` is only checked once per day, before `sweep_day` starts —
not before every page request inside it — so there is a race window: if the
daily job starts while the sweep is mid-day (fetching a paginated day can
take several minutes), both jobs can issue requests concurrently until the
sweep finishes that day and checks the pause object again. The sweep's
`--delay 10` (vs. the daily job's own delay) leaves enough headroom under
the shared 10 req/min budget that this overlap is statistically unlikely to
cause 429s; a shared token bucket would close the window fully but is out of
scope here.

**Manifest aggregation.** `manifest.json` (`slug_counts`, `unmapped_codes`,
`days_done`, `date_range`, `last_run`) is maintained as a rolling fold, not
a full rescan: each run reads the existing manifest once at the start,
folds in the slug/unmapped counts from each day it completes, and writes
the result back at the end (and every 50 days as a mid-run checkpoint, so a
long backfill doesn't lose everything to a crash near the finish). This
avoids a `GET` per `_done/` marker on every run, which would otherwise add
minutes of blocking I/O once years of history are swept. Pass
`--rebuild-manifest` (with `--sweep`) to force the old full-scan behavior
on demand — it reads every `_done/` marker and rebuilds `manifest.json`
from scratch, without running the sweep itself:

```bash
python fetch.py --sweep --rebuild-manifest
```

**Promotion is not implemented yet.** Sweep mode only stages data; nothing
currently copies `_sweep/{slug}/...` into the canonical `open311/{slug}/...`
paths that the frontend reads. That reconciliation step (diff staged vs.
canonical by `service_request_id`, promote only non-regressing days) is
future work — see `~/projects/mbta_311_referrals/SCRAPER_FIX_PLAN_v3.md`.
Unmapped codes accumulate in the sweep manifest's `unmapped_codes` field;
promoting a newly-recognized type means adding it to `SERVICE_TYPES` and then
pulling its records out of `_sweep/_unmapped/` (no re-fetch needed).
