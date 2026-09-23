## Answers to the round-2 questions

**1. Completeness heuristic (25% of trailing 6-month median).** Unsound as specified. Failure modes you list are real, not hypothetical:
- Seasonal layers: waste dips in winter; a normal January at 30% of the summer median would be flagged "incomplete" and the chip would regress to December. You then ship a *worse* chip in the healthy case.
- <6 months history: median of 1–2 months is noise; a single spike month sets an unreachable bar.
- Legitimately quiet month: indistinguishable from collapse by volume alone.
- The rule is also non-monotone: adding one row to June (3→4) doesn't move the boundary, but adding 30 does, and the boundary can *move backward* month-over-month as the trailing median shifts. A chip date that regresses is worse than a stale one.
- "Last day of M that has any row" is fragile: if May's last row were 05-20, the chip says 05-20 while the notice says "through May." Pick last-day-of-month or state the exact date consistently.

Better: don't infer completeness from volume at all. Use an explicit per-layer `expected_cadence` / `known_gap` config (you already know Boston migrated; you know the type feed died 05-27). Or gate on the *source* that died: `complete_through = max(through of sources whose status is ok)`. That's deterministic, explainable, and doesn't misfire on seasonality.

**2. MIN_OK_VOLUME = 5.** Defensible as a floor but arbitrary and untested against real per-source distributions. `open311:encampments` prior_year_30d = 10 — a healthy month there could plausibly be 3–4. You're changing classification semantics for *all* layers to fix one; scope it to sources flagged as "successor missing" or make it per-source config. Also: `classify_status` already returns stale when `current == 0`; the trickle case is `current ∈ [1,4]`, so the threshold is doing real work — justify 5 with data, not intuition.

**3. Wording.** "complete through May 27 · last report Jun 22" is two dates in one chip; residents will read the later one. The notice sentence is long and buries the point. Shorter: *"Encampments: reliable through May 27, 2026. A few later reports appear on the map but recent months are incomplete."* Drop "by other routes" — it's jargon.

**4. P4 prop plumbing.** Worth it *only if* the note is per-month and disappears when the user scrubs to May. Otherwise the chip + notice already carry the signal, and you're adding an island prop for a 3-row edge case. If you keep it, the note must not appear for healthy layers or for months ≤ complete_through.

**5. P1 partition vs. Creatio reappearance.** The partition is `type == "Encampments"` vs. everything else in the file. If Creatio reintroduces encampments under a new service name, `fetch_encampment_year` must add it to the union; if it lands with a *different* `type`, it silently becomes "queue" rows and the type source stays dead forever while the chip looks healthy. The partition is only correct as long as the fetcher's predicate and health's predicate stay in lockstep — nothing enforces that. Add an assertion in health: `type_count + queue_count == len(rows)`.

**6. Schema bump ordering.** P2 says keep `through = complete_through` for one release. But P3's frontend reads `latest`/`complete_through`; if the frontend deploys first, those keys are absent and the chip falls back to `through` (fine). If the pipeline deploys first, old frontend reads `through` = May 27 (fine). OK — but `frozen` in index.astro is reverted to `2026-05-27` in P3, which is only correct if `complete_through` semantics hold. If the heuristic misfires on a future month, `frozen` and live disagree. Make `frozen` a last-resort constant, not a semantic twin.

**7. Still missing.**
- No test that the *notice* renders when `latest != complete_through` but status is `ok` (P5 makes this possible: a source with 5+ trickle rows flips layer to ok, notice disappears, chip still shows two dates — contradictory).
- No test for the `years` window regression (P6 defers it; on 2028-01-30 the chip silently regresses to the Open311 date — that's the same class of bug you're fixing).
- No handling of `_local_day` timezone: the June rows are `+00` mislabeled per commit 28ec0fa; if `_parse_datetime` shifts them, `complete_through` could land on 05-31 or 06-01.
- P5 changes `layer_status` inputs globally; no test asserts sharps/waste statuses are unchanged.
- The rejected alternative A (clip) is dismissed on "May wasn't proven complete" — but your P2 heuristic *also* asserts May was complete. You've replaced one unproven claim with another, just moved it into a heuristic.