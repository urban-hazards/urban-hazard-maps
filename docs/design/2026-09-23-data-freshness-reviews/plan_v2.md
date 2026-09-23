# Revised plan v2: encampment freshness chip vs. map (urban-hazard-maps PR #154, bug 2)

Date: 2026-09-23. Supersedes the v1 fix already committed on the PR branch (8a4c679),
which round-1 auditors (codex, agy) judged numerically correct but semantically wrong.

## The symptom
Live site chip: "Encampments: data through May 27, 2026". Same page, heatmap timeline
defaults to Jun 2026 and shows "3 encampments".

## Facts (verified against live S3 on 2026-09-23)
- `raw/encampments_v2_{year}.json` = union of two CKAN selectors, deduped by case id:
  (a) `type == "Encampments"` (button added 2025), (b) `queue == "INFO_Homeless Issue"`
  (2023+). Queue rows keep their original `type` ("Requests for Street Cleaning",
  "Improper Storage of Trash (Barrels)", ...).
- `encampments/points.json` (what the map draws) is built from ALL rows of those files
  that survive `cleaner.clean()` (drops rows with invalid coordinates).
- 2026 points by month: Jan 65, Feb 74, Mar 155, Apr 202, May 305, Jun 3. The 3 June rows
  are queue-matched, dated 06-05, 06-17, 06-22, all `case_status: Open`.
- `health.py` computes per-source `through` (last row date), `last_30d`, `prior_year_30d`,
  `ratio`, `status` in {ok, degraded, stale}; a layer's `through` = max over its sources;
  a layer is `ok` if ANY source is ok. Layer encampments has sources
  `ckan_legacy:Encampments` (type-filtered) and `open311:encampments`. Both `through`
  = 2026-05-27, last_30d = 0, status stale.
- Boston migrated 311 to Creatio mid-2026. The "Encampments" type stopped appearing in the
  legacy CKAN feed after 2026-05-27. Sharps and waste layers are `ok` (they have Open311 /
  Creatio successor sources); encampments has no working successor yet.
- Frontend `DataFreshness.astro` renders one chip per layer: `{label}: data through {date}`
  and, if any layer is not ok, a notice: "Boston moved its 311 system to a new platform in
  2026. Some categories stopped appearing in the city's data during the switch (X, Y). We
  show those layers through their last complete date rather than guess."
- Health is regenerated daily by the pipeline cron (07:00 UTC); frontend caches S3 reads
  5 min.

## Round-1 audit findings (codex + agy, both independent)
1. v1 redefined `ckan_legacy:Encampments` as the union, so the chip moved to Jun 22 while the
   banner still promises "last complete date". 3 rows vs 305 in May is not completeness;
   reader infers June is covered/quiet. Both auditors: misleading.
2. Trickle flips status: with union counting, one queue row inside 14 days makes
   `days_since < 14`, `last_30d > 0`; ratio vs prior year decides degraded vs ok; an `ok`
   source makes the whole layer ok and hides the notice while the type feed is dead.
   (Same weakness pre-exists for `open311:encampments`, prior_year_30d = 10.)
3. Redefining the source hides the type feed's specific failure from the sources diagnostics.
4. v1 test pins today to Sep 23 so June is safely stale; never exercises the flip.
5. Disagreement: agy wants points clipped to May 27; codex says clipping discards real open
   cases without proving May was complete — keep the reports, label the period incomplete.
6. Pre-existing: `years` = {window year, prior-year twin}. On 2028-01-30, 2026 leaves the
   set, legacy `through` goes empty, layer regresses to the Open311 date.
7. `frozen` fallback in index.astro is only used when health has no layers at all.

## Revised plan

### P1. Split the source; do not redefine it (health.py)
- `ckan_legacy:Encampments` stays type-filtered (`type == "Encampments"`) — this is the feed
  that died and its `through` = 2026-05-27 must remain visible in `sources`.
- Add `ckan_legacy:Encampments (queue)`: rows in `raw/encampments_v2_*` whose `type` is NOT
  "Encampments" (i.e. queue-matched). Same file, complementary predicate, so the two sources
  partition the file and their counts sum to the union.
- Layer `encampments.sources` = [type, queue, open311]. Layer `through` = max = 2026-06-22.
- Layer `status` rule unchanged for now (any-ok → ok). Known weakness; see P5.

### P2. Add a layer-level "latest vs. complete" pair instead of one date
Health `layers[k]` gains:
- `latest`: max `through` across sources (what v1 called `through`). = 2026-06-22.
- `complete_through`: the last month whose volume is not collapsed. Definition: walk months
  backward from `latest`; the first month M (inclusive) whose union count is >= 25% of the
  median monthly count of the preceding 6 months is the completeness boundary;
  `complete_through` = last day of M that has any row. For encampments: Jun (3) fails vs
  median(Dec..May ≈ 100+), May (305) passes → `complete_through` = 2026-05-27.
- Keep the existing `through` key populated = `complete_through` for one release so the
  current frontend keeps rendering May 27 if it deploys before the pipeline
  (schema_version → 2).
Sharps/waste: `latest` and `complete_through` coincide unless volume collapsed.

### P3. Frontend chip + notice wording (DataFreshness.astro)
- When `latest == complete_through` (healthy): `Sharps: data through Sep 9, 2026` (unchanged).
- When they differ: `Encampments: complete through May 27, 2026 · last report Jun 22, 2026`.
  Chip tooltip lists sources.
- Notice (only when some layer is not ok), replace the last sentence:
  "For those layers we mark the last month with normal volume as the complete-through date;
  a few later reports still arrive by other routes and are shown on the map, but recent
  months are incomplete, not quiet."
- `frozen` fallback stays keyed by `complete_through` semantics → revert to
  `encampments: "2026-05-27"`.

### P4. Map: keep the June points; label the incomplete period
- Do NOT clip points. The 3 June cases are real, open reports.
- In HeatMap, when the selected year-month is after the layer's `complete_through`, show a
  small inline note beside the count: "3 encampments · incomplete month (reporting collapsed
  after May 27)". Requires passing `sourceHealth.layers` (or just the two dates per layer)
  into the HeatMap island as a prop.

### P5. Status classification hardening (small, in this PR)
- A source counts toward layer `ok` only if its `last_30d >= MIN_OK_VOLUME` (proposed 5)
  in addition to the existing ratio/recency rules. Prevents 1–2 trickle rows from flipping a
  layer to ok. Does not change any layer's status today (encampments all 0; sharps/waste far
  above 5).

### P6. Tests (pipeline/tests/test_health.py)
- Type vs queue partition: a fixture with one type row (05-27) and one queue row (06-22)
  → type `through` 05-27, queue `through` 06-22, layer `latest` 06-22,
  `complete_through` 05-27, layer stale.
- Flip test: same fixture plus a queue row dated today-2 → queue source not `ok` because
  `last_30d` (1) < MIN_OK_VOLUME; layer stays not-ok.
- Completeness boundary: 6 months at ~100/mo then a month with 3 → boundary is the 100 month;
  a month with 40 (≥25%) → boundary moves forward.
- Coordinates: fixture rows carry valid lat/lon so a follow-on integration test can assert
  banner/map agreement via `compute_stats` (optional in this PR).
- Year-window regression (2028-01-30) is filed as a separate issue, not fixed here, unless
  the fix is one line (compute `through` from all available year files, not `years`).

### P7. Deploy order
1. Merge; pipeline cron regenerates `source_health.json` at 07:00 UTC (or run
   `uv run boston-pipeline --health-only` if such a flag exists; else full run).
2. Frontend picks it up within 5 min cache.
3. Until then the old health file + new frontend renders `through` (= May 27) unchanged.

## Alternatives rejected
- A. Clip points to `complete_through`: hides real open cases; implies May was complete.
- B. Frontend-only hide of months after `through`: same problem, plus map/stat mismatch.
- C. v1 (union `through`, wording unchanged): misleading per round 1.

## Questions for round-2 reviewers
1. Is the P2 completeness heuristic (25% of trailing 6-month median) sound? Better rule?
   Failure modes: seasonal layers (waste dips in winter), layers with < 6 months history,
   a legitimately quiet month.
2. Is `MIN_OK_VOLUME = 5` (P5) defensible? Any layer/source where a healthy month has < 5?
3. P3 wording: honest and readable to a non-technical resident? Shorter alternative?
4. P4: worth the prop plumbing, or is the chip + notice sufficient?
5. Anything in P1's partition that breaks when the "Encampments" type reappears in the
   Creatio feed under a new service name?
6. Ordering/compat risk in P2's schema bump (frontend deployed before pipeline, or vice versa)?
7. What is still missing?
