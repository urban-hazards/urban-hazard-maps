# Plan v3: encampment freshness chip vs. map (PR #154, bug 2)

Date: 2026-09-23. Supersedes v2 after round-2 review by codex, agy, DeepSeek V4 Pro, GLM-5.3,
DeepSeek 4.1 Flash. All five rejected v2's volume heuristic (P2) and its MIN_OK_VOLUME floor (P5).

## What round 2 agreed on
- No statistical "completeness" inference. It flaps in the first week of every month, misfires on
  seasonal layers, hides gaps after a recovery, and asserts "complete" without evidence.
- Coverage must come from a deterministic, source-level fact: the type-filtered feed stopped.
- Wording must not say "complete" or "data through" for a disrupted layer. Say "latest report" +
  "reporting disrupted", and put the qualifier next to the map count, not only in the banner.
- Keep the June points. Do not clip.
- Frontend must tolerate old health JSON (missing keys); gate on schema_version.
- Fix the year-window regression now; v1's split makes it worse.
- A frontend test for chip/map agreement is mandatory, not optional.

## v3 design

### H1. Sources: partition by provenance, not by mutable `type` (health.py, fetcher.py)
- `fetch_encampment_year` stamps each raw row with `_uhm_route: "type" | "queue"` at fetch time.
  Rows already cached without the stamp fall back to `type not in ENCAMPMENT_TYPES` → "queue".
- Sources: `ckan_legacy:Encampments` (route type) and `ckan_legacy:Encampments (queue)` (route
  queue). Assert `len(type_rows) + len(queue_rows) == len(rows)` per file; log if not.
- Each source gets a `coverage: bool` flag in SOURCES. Queue residual = False (it is a leak of
  encampment-tagged tickets through other categories, not a reporting channel). Type feed and
  Open311 successor = True.

### H2. Layer status and dates (health.py, schema_version 2)
- `layers[k].status` = `layer_status` over **coverage sources only**. Non-coverage sources cannot
  make a layer ok. No volume floor, no magic number.
- `layers[k].latest_report` = max `through` over **all** sources (Jun 22 for encampments).
- `layers[k].through` keeps its meaning = max `through` over coverage sources (May 27). Old
  frontends keep working.
- `layers[k].disrupted_since` = day after `through` when status != ok, else null.
- `through` for legacy sources computed from every `raw/<dataset>_*.json` year file present in the
  bucket (list_keys), not from the rolling-window `years` set. Window counts still use `years`.

### H3. Banner (DataFreshness.astro + new pure helper `lib/freshness.ts`)
- Move chip/notice derivation into `freshnessModel(health, frozen)` → `{chips, troubled}` so it is
  unit-testable with vitest. Handles `schema_version < 2` or missing keys: `latest_report ??
  through`, `disrupted_since ?? null`.
- Chip, layer ok: `Sharps: data through Sep 9, 2026` (unchanged).
- Chip, layer not ok: `Encampments: latest report Jun 22, 2026 · reporting disrupted since May 28`.
- Notice when any layer troubled: "Boston moved its 311 system to a new platform in 2026.
  Encampment reporting has been disrupted since May 28; reports that still arrive are shown, but low
  counts after that date reflect missing data, not fewer encampments." (Layer names and date
  generated from health; sentence template lives in the helper.)
- `frozen` fallback stays a last-resort constant keyed on coverage: `encampments: "2026-05-27"`
  (revert v1's change). Fallback renders the not-ok chip form with `latest_report = through`.

### H4. Map note (HeatMap.tsx)
- New compact prop `disruptions: Record<layer, { since: string; latest: string }>` built in
  index.astro from health. Not the whole health object.
- When the active layer has a disruption and the selected year-month >= month(since), the count
  reads `3 reports · reporting disrupted since May 28`. The month containing `since` (May) is
  included because May 28–31 are uncovered. Cleared automatically when coverage recovers.
- Timeline default (latest month) is unchanged; the note does the explaining.

### H5. Tests
Pipeline (`tests/test_health.py`):
- Provenance partition: type row 05-27, queue rows 06-05/06-17/06-22 with valid coordinates →
  type through 05-27, queue through 06-22, layer through 05-27, latest_report 06-22,
  disrupted_since 05-28, status stale.
- Trickle does not flip: add a queue row dated today-2 → queue source ok, layer still stale.
- Successor revives: 6 Open311 encampment rows in window → layer ok, disrupted_since null.
- Year window: today = 2028-01-30, only 2026 file present → type through still 05-27.
- Fallback for unstamped rows: rows without `_uhm_route`, type "Requests for Street Cleaning" →
  queue.
- Sharps/waste statuses unchanged by H2 (fixture from existing test).
Frontend (`frontend/src/lib/freshness.test.ts`, vitest):
- schema 2 disrupted layer → chip text and notice text exactly as H3.
- schema 1 (no new keys) → legacy chip, no crash.
- health null + frozen → not-ok chip with frozen date.
- Integration: given health + points fixture, the note condition in H4 fires for 2026-05, 2026-06
  and not for 2026-04.

### H6. Deploy order
Either order is safe: old health + new frontend renders legacy chip via fallbacks; new health + old
frontend renders `through` = May 27 as today. The symptom is gone only when both are live; say so
in the PR. Pipeline cron regenerates health at 07:00 UTC.

### Out of scope, filed as issues
- Encampments successor in Creatio: needs a new fetcher route + `ckan_creatio:Encampments*` source
  with coverage=True once the city's service name is known.
- Historical gap tracking (multiple disruption episodes) — v3 tracks only the current one.
- Fixing the flaky live-network test `test_merge_dedupe_and_source_tagging`.

## Round-2 auditor comparison (for Brian's Flash vs Pro question)
| voice | cost | distinctive catches |
|---|---|---|
| codex | $0 (sub) | "complete_through" is unfalsifiable; separate source activity from layer coverage; May itself partially uncovered; v1 health could already say Jun 22 |
| agy | $0 (sub) | recovery hides gaps; hardcode known feed-death dates; `_legacy_days` equality-only means P1 needs a refactor |
| DeepSeek V4 Pro | $0.017 | primary-source rule for coverage; open311-masks-dead-type test; schema_version gating; null-type edge |
| GLM-5.3 | $0.039 | first-week-of-month flap; partition on provenance not mutable `type`; ok-layer with split dates has no explanation; frontend tests mandatory |
| DeepSeek 4.1 Flash | $0.0016 | boundary is non-monotone and can move backward; assert type+queue == len; "you swapped one unproven claim for another"; scope MIN_OK per source |
