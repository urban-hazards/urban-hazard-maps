# Round-2 review of revised plan

## Answers to your questions

**1. P2 completeness heuristic (25% of trailing 6-month median)**

Not sound as specified. Failure modes you list are real, but the bigger issue is that the heuristic is unprincipled and untested against known seasonal data. Waste volume in Boston drops substantially in winter; a legitimate February at 40% of summer median would be flagged "incomplete." The 6-month trailing window is arbitrary—why not 3 or 12? And "median of preceding 6 months" is undefined for layers with < 6 months history (you acknowledge but don't resolve). For encampments specifically, the signal you actually need is "the type-filtered feed stopped producing rows," which is a source-level fact, not a volume heuristic. A cleaner rule: `complete_through` = max date where the *primary* source for that layer (the type-filtered CKAN feed) has a row, falling back to the max across all sources if the primary source is still active. For encampments, primary = `ckan_legacy:Encampments`, which gives May 27 directly. For layers with multiple active sources, use max across sources. This avoids inventing a statistical boundary that will misfire on seasonality and short history.

**2. MIN_OK_VOLUME = 5**

Defensible as a floor, but it's a band-aid on the wrong layer of the problem. The real issue is that `layer_status` uses any-ok, so one healthy source masks a dead one. If you're going to harden status, fix the aggregation: a layer should be `ok` only if its *primary* source is ok, or if all sources are ok. MIN_OK_VOLUME alone doesn't prevent the open311 source from flipping the layer ok when it gets 5+ rows in a window while the type feed is dead. Your own facts say `open311:encampments` has `prior_year_30d = 10`; if it gets 5+ rows in a future window, the layer flips ok under your P5 rule even though the type feed is still dead. That's the exact failure you're trying to prevent.

**3. P3 wording**

Readable but verbose. "Complete through May 27, 2026 · last report Jun 22, 2026" is good. The notice paragraph is too long for a chip area. Consider: "Recent months for Encampments are incomplete due to the 311 system change. We mark the last month with normal reporting volume." Drop the clause about "a few later reports still arrive by other routes"—that's detail for a data-quality page, not a chip.

**4. P4 prop plumbing**

Worth it, but only if the note is small and doesn't require the full `sourceHealth.layers` object. Pass a compact map: `{ encampments: { completeThrough: "2026-05-27", latest: "2026-06-22" } }`. Don't couple HeatMap to the entire health schema. The inline note is necessary; otherwise the map shows June with 3 points and the chip says May 27, and a careful reader will think the map is broken.

**5. P1 partition when type reappears under Creatio**

Your partition is `type == "Encampments"` vs `type != "Encampments"` within `raw/encampments_v2_*`. If Creatio starts emitting rows with a new type name (e.g., "Encampment Report" or a service name like "Encampments" but in `raw/creatio.json`), those rows won't be in `raw/encampments_v2_*` at all unless the fetcher is updated. The partition itself doesn't break, but the layer will silently miss the new source. You need a separate Creatio source for encampments (like `ckan_creatio:Encampments`), and the fetcher needs to route those rows into the encampment raw file or a new raw file. P1 as written doesn't address this.

**6. Schema bump ordering**

You say "keep `through` = `complete_through` for one release" but don't specify how the frontend knows whether `latest` exists. If the frontend deploys before the pipeline regenerates, it reads old health JSON with `through` but no `latest`/`complete_through`. Your P3 code must handle `latest == null` gracefully (fall back to `through`). If the pipeline deploys first, the frontend still reads `through` and ignores the new fields—fine. But you haven't specified a schema_version check in the frontend. Add one: if `health.schema_version < 2`, use `through` only; else use `latest`/`complete_through`.

**7. What's still missing**

- **P6 year-window regression**: You defer the 2028-01-30 bug but it's directly relevant. Your P1 split means `ckan_legacy:Encampments` `through` will go empty when 2026 leaves the `years` set, and the layer will regress to open311's date. You should fix this now: compute `through` from all available year files, not just the window years. It's not one line, but it's small and prevents a known future regression.
- **Test for the open311 source masking the dead type feed**: Your P6 flip test only covers queue rows. Add a test where `open311:encampments` has 6 rows in the window and the type feed is dead; assert the layer is still not `ok` under your intended semantics.
- **P2 boundary test with seasonal data**: You don't have one. If you keep the heuristic, test it against a synthetic seasonal pattern to show it doesn't false-positive.
- **`complete_through` definition ambiguity**: "last day of M that has any row" is unclear when M is the boundary month. If May has rows on the 27th, is `complete_through` May 27 or May 31? You say May 27, so you mean "last day with a row," not "last day of M." Clarify.
- **P5 interaction with `layer_status`**: You say "status rule unchanged for now," but P5 changes source status. If a source has 4 rows in the window, it's not ok under P5, but `layer_status` still returns ok if any *other* source is ok. The layer can still be ok while the type feed is dead. This is the core bug; deferring it means the notice still won't show in the scenario you're worried about.

## Other problems

- **P1 partition counts**: You say the two sources "partition the file." True only if every row has `type` either exactly "Encampments" or not. What about rows with missing or null `type`? They fall into the queue bucket. Is that correct? A row with no type and no queue match shouldn't be in the file at all (fetcher guarantees queue match), but if `type` is null, you're labeling it queue-matched. Fine, but be explicit.
- **P2 "keep `through` populated = `complete_through`"**: This means the chip shows May 27, but `latest` is June 22. If the frontend hasn't been updated to read `latest`, the user sees May 27 and the map shows June points—the exact symptom you're fixing. Your deploy order says old health + new frontend renders `through` unchanged, but old frontend + new health also renders `through` = May 27. So the symptom persists until both deploy. That's acceptable for a staged rollout, but you should say so explicitly and not claim the chip is fixed until both are live.
- **P4 note text**: "reporting collapsed after May 27" is jargon. "Reporting dropped sharply after May 27" or "May 27 was the last complete month" is clearer.