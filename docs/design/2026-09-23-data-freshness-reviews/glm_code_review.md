## Merge blockers

**1. Plan-required integration test is missing — and it guards a live off-by-one risk.**
H5 mandates: "Integration: given health + points fixture, the note condition in H4 fires for 2026-05, 2026-06 and not for 2026-04." `freshness.test.ts` tests `isDisruptedMonth` in isolation (1-based months) but nothing wires `HeatMap`'s `selMonth` to it. `HeatMap.tsx:176-186` passes `selMonth` straight through; the `selMonth === 0` sentinel suggests 0 = "all months", but if the month `<select>` is 0-indexed (JS convention), the note fires one month early and `isDisruptedMonth`'s `month < 1` guard (freshness.ts:~192) silently suppresses January. This is exactly the bug class the missing test exists to catch. Block until the integration test is added or `selMonth`'s basis is proven 1-based in the diff.

**2. Double-read regression for needles/waste — the round-1 fix was applied only to encampments.**
`compute_source_health` (health.py:~205-212) calls `_legacy_window_days` (reads `raw/{dataset}_{year}.json` for window years) *and* `_legacy_through_days` (reads **every** `raw/{dataset}_*.json`, including those same window-year files). Each needles/waste window file is fetched twice per run, and `through` now pulls ~a decade of large year files daily via individual S3 GETs. The encampment branch got the one-pass treatment (`_encampment_partition`); do the same here: one read per year file, filter twice.

**3. Basemap change is unplanned, untested scope creep.**
The CARTO-key/Esri fallback (HeatMap.tsx:~348-375) is not in H1–H6, has zero tests, and `basemapKey={import.meta.env.CARTO_BASEMAP_KEY ?? process.env.CARTO_BASEMAP_KEY ?? ""}` (index.astro:~125) is fragile: Astro statically replaces `import.meta.env` at build; if the key is injected only at deploy/runtime the build silently bakes `""` and you get the Esri fallback with no telemetry. The key also lands in client HTML. Split into its own PR with a test, or drop it from this one.

**4. H3's frozen-constant revert is not in the diff.**
Plan: "frozen fallback stays a last-resort constant keyed on coverage: `encampments: '2026-05-27'` (revert v1's change)." No hunk touches the frozen constant or the `DataFreshness` call site in index.astro. If main still carries v1's value, the revert is missing. Also: if the caller passes no `frozen`, health-null renders zero chips and the banner vanishes entirely — that path is only tested at the lib level, never through `DataFreshness.astro`.

## Contract violations

**5. H1's assert is dead code.** `_row_route` (health.py:~120) is total — always "type" or "queue" — so `len(type_rows)+len(queue_rows) != len(rows)` in `_encampment_partition` (health.py:~140) can never be true. The plan says "Assert … log if not"; as written it's a log statement that provides false assurance. Make it a real assert or delete it.

**6. Notice subject contradicts the contract.** Contract: "`<Label>` reporting has been disrupted" with labels "Sharps, Encampments, Human Waste"; H3's example uses singular "Encampment". `NOTICE_SUBJECT` (freshness.ts:~24) picks singular. Contract and plan disagree; the test pins singular. Reconcile the contract text or the code — don't ship with the two documents contradicting each other.

**7. Legacy-notice fallback leaks into schema 2.** A schema-2 stale layer with empty `through` (never reported) is filtered out of `sentences` (freshness.ts:~155) and, if it's the only troubled layer, falls through to `LEGACY_NOTICE` — "We show those layers through their last complete date" — which the contract reserves for legacy schema. Chip also renders "latest report unknown". Edge case, but it's a schema-2 path emitting legacy copy.

## Races / ops

**8. List-then-read tear.** `_legacy_year_files` lists keys, then each file is read separately (health.py:~95-115, ~140). If the fetch step can run concurrently with health (or a retry overlaps the 07:00 cron) and `storage.write_json` isn't atomic temp-then-rename, health reads torn JSON. Sequential cron makes this low probability; confirm write atomicity or note the assumption.

**9. Unstamped-row misclassification is unbounded.** `_row_route`'s fallback classifies by the *mutable* `type` field — the exact thing H1 exists to escape. An unstamped type-route row whose `type` the city later scrubbed counts as queue, inflating queue `through`/`latest_report` and potentially regressing type `through` (which drives `disrupted_since`). Plan accepts the fallback, but there's no test for the mutated-`type` case and no log when fallback fires, so you can't measure how many rows are affected.

## Missing tests

- **No pipeline test for the degraded path.** The 2026-09-23 amendment (degraded → `disrupted_since: null`, volume-down copy) is tested only with a hand-built health object on the frontend. Nothing proves the pipeline can emit a degraded *layer* end-to-end (coverage source degraded, none ok). The amendment is one day old and completely untested against the producer.
- **Year-window regression tested for encampments only.** `test_encampment_through_ignores_rolling_year_window` covers the new `_legacy_through_days` path for one dataset; needles/waste `through` scanning all year files — new behavior with new parsing (`_legacy_year_files` stem splitting) — is untested, including non-year suffixes.
- **`disruptionsFromHealth` legacy/null paths untested**: schema-1 health (no `disrupted_since` key) and `health === null` both depend on `?? null` and return `{}`; the deploy-order safety H6 claims rests on this and it's unasserted.
- **`_legacy_year_files` parsing** (non-digit suffixes, `.json` filter) has no direct test.

## Nits

- `test_encampment_unstamped_rows_fall_back_to_type` name says "fall back to type" but asserts both directions.
- freshness.test.ts:127-131 mixes `isDisruptedMonth` guards with `freshnessModel` frozen-filter assertions; split the describe.
- `fmtShort` omits the year; a disruption spanning New Year renders "since Dec 31" ambiguously in 2027+. Contract specifies "Mon D", so conformant — but flag for the next contract revision.