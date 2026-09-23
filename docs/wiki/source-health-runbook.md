# Source-health runbook

`pipeline/src/pipeline/health.py` computes `metadata/source_health.json` during
the daily pipeline. The frontend reads it for freshness chips and notices.
This measures delivery of reports, not the prevalence of hazards or classifier
precision. Inspect an existing snapshot with read-only bucket access; do not
run the pipeline just to diagnose health. `compute_source_health()` itself
writes the service-name baseline, so it is not a read-only inspection command.
Never load the production `pipeline/.env` for local investigation or tests.

## Reading the snapshot

- `generated`: UTC time the snapshot was computed. Check this first against the
  expected daily schedule and `metadata/last_run.json`. An old snapshot can still
  say `ok`. Monitor exceptions are logged and do not abort the pipeline, so a
  successful pipeline run does not guarantee a fresh health file.
- `schema_version`: currently 1.
- `sources`: per-source `through`, `last_30d`, `prior_year_30d`, `ratio`, `status`.
- `layers`: `needles`, `encampments`, `waste`, each with `status`, `through` and
  the exact source keys contributing to it.
- `creatio_service_names`: all names returned by the CKAN distinct query.
- `new_service_names`: sorted additions relative to
  `metadata/creatio_service_names.json`. The first successful run seeds that
  baseline without reporting every name as new. Successful discovery replaces
  the baseline; additions normally appear for one snapshot only. Save evidence
  when investigating. Removed names are not reported.
- `notes`: non-OK layers, failed/empty service-name discovery, and new names.
  An empty discovery result preserves the previous baseline; an empty
  `new_service_names` list alone does not prove discovery succeeded.
- `alerts`: strings shown in the frontend notice, even when all layers are OK.
  New names matching `needle|syringe|sharp` (case insensitive) produce
  `Needle intake may have migrated: <names> — add scraper slug + NEEDLE mapping`
  in both `alerts` and `notes`. Follow the new-name response below. These alerts
  share the one-snapshot lifetime of the additions; older snapshots may omit
  the `alerts` field, and no matching additions produce `[]`.

The current window is the inclusive 30 days ending on `today` (UTC date by
default). The comparison window is shifted back exactly 365 days, not the
previous 30 days. `ratio` is current/prior rounded to two decimals, or `null`
when the prior count is zero. Status uses that rounded ratio:

| Status | Rule, in precedence order |
|---|---|
| `stale` | No reports in the current window, or newest report day is more than 14 days old. Missing history also becomes stale. |
| `degraded` | Otherwise, non-null ratio is below 0.50 (more than a 50% drop). |
| `ok` | Otherwise; this includes active feeds with no prior-year baseline. |

Layer status is `ok` if **any** contributing source is OK; otherwise degraded
if any is degraded; otherwise stale. Layer `through` is the latest source date.
Always inspect individual sources: one live Other feed can keep waste OK even
when Litter & Debris is missing. Neither a recent date nor an OK chip establishes
complete coverage, permits unfreezing encampments, or validates waste precision.

## Per-source keys and inputs

| Source key | Stored input and selector |
|---|---|
| `ckan_legacy:Needle Pickup` | `raw/needles_<year>.json`, exact `type = Needle Pickup` (not all needle aliases) |
| `ckan_legacy:Encampments` | `raw/encampments_v2_<year>.json`, exact `type = Encampments` (not the full INFO queue series) |
| `ckan_legacy:Requests for Street Cleaning` | `raw/waste_<year>.json`, exact legacy type |
| `ckan_creatio:Litter & Debris` | `raw/creatio.json`, `creatio_service_name = Litter & Debris` |
| `ckan_creatio:Park Litter & Debris` | `raw/creatio.json`, `creatio_service_name = Park Litter & Debris` |
| `open311:needles`, `open311:encampments` | `open311/<slug>/YYYY-MM-DD.json` |
| `open311:other`, `open311:other-creatio` | Same day-file layout; legacy and Creatio General Request respectively |
| `open311:litter-debris`, `open311:park-litter-debris` | Same day-file layout; new-system resident text |

CKAN counts use uncapped raw records and Boston-local opening dates. Creatio
rows must already have passed through `creatio_timestamp()` to repair the
misleading `+00` timezone label. Legacy health reads only the years needed by
the two windows; its `through` is the latest matching date in those caches.
It is not an all-history search. Never compare against capped `markers.json`.

Open311 counts use the UTC dates of scraper day files and their row counts.
Their `through` is the newest **nonempty** day file, not the newest key or
upload time; persisted `[]` days do not advance it. Empty days mean a successful
zero-result fetch. Missing days can mean a scraper failure or dates before a
slug's configured start. Storage read/list failures can look like missing data;
check logs before concluding the city stopped accepting reports.

## Responding to failures

### Legacy stale

Check the source's raw cache, pipeline fetch logs and current-year resource ID
in `config.RESOURCE_IDS`. Compare a small public CKAN query for that exact type
with the stored last date. If CKAN is current but the cache is stale, investigate
fetch errors, credentials and the scheduled job. If both stop together, compare
Creatio names and Open311 codes for a migration. Street Cleaning and dedicated
Encampments have known cutoffs; do not invent zero-valued successor series.
See the [encampment finding](encampment-intake-ended-2026.md). A new needle cutoff
needs investigation because needles were still legacy in the September audit.

### Creatio missing or stale

Inspect `raw/creatio.json` and fetch logs. `_load_creatio_rows()` falls back only
to nonempty caches whose latest opening date is at most seven days old; otherwise
it raises. A count mismatch or missing required fields also fails the fetch.
Check public `datastore_search` for `config.CREATIO_RESOURCE_ID`, the exact
`service_name`, and `creatio.REQUIRED_FIELDS`. Check both schema and timestamp
normalization before updating a mapping. An empty distinct-name result is a
separate discovery failure, even if cached Creatio counts remain healthy.

### Open311 degraded or stale

Inspect recent day keys and empty versus missing files, then the scraper job's
logs for HTTP failures or rate limits. Confirm the slug's `SERVICE_TYPES` code
and `SLUG_START` in `services/open311-scraper/fetch.py`. Query a small public
Open311 date window for that code and compare IDs/counts to stored days. The
public `/services.json` list omits new UUID codes: also consult the
[observed UUID table](creatio-open311-codes.json). For Litter & Debris, compare
the uncapped inputs and `waste/qa_creatio_coverage.json`; account for UTC versus
Boston date boundaries and incompatible CKAN/Open311 IDs. Correct the code or
failed fetch first; arrange any required backfill through the normal operational
deployment process, not a local production scraper run.

### New service names

Save the snapshot and inspect each addition's CKAN rows, topic, first date and
Open311 UUID service code. Decide whether it is a successor to a tracked type.
For a verified successor, update deterministic `CREATIO_SERVICE_MAP`, scraper
`SERVICE_TYPES`/`SLUG_START`, relevant input slugs and health source mappings,
with tests and a documented method break. Keep resident descriptions separate
from Creatio staff closure comments. Do not use an LLM or guess a mapping from
the name alone. Resolve coverage and, for waste, the
[precision audit](data-quality-issues.md#16-validating-the-waste-classifier-on-new-system-text)
before treating the new feed as a comparable series.

Verify code fixes with the pipeline's Ruff, mypy and moto pytest checks, the
scraper tests when codes change, and frontend checks when notices change. After
the normal deployment, inspect the next scheduled snapshot and original inputs
to confirm recovery; a newer `generated` timestamp alone is insufficient.
