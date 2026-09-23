## Bugs

**1. `_legacy_window_days` silently drops encampment rows for non-encampment datasets — but the encampment branch bypasses it. However, `_legacy_through_days` for non-encampment datasets now scans *all* year files, while `_legacy_window_days` still filters by `RESOURCE_IDS`. That's fine. The real bug: `_legacy_year_files` parses `stem.rsplit("_", 1)[-1]` — for `raw/encampments_v2_2026.json` the stem is `encampments_v2_2026`, so `rsplit("_",1)[-1]` = `"2026"`. OK. But for `raw/needles_2026.json` → `"2026"`. OK. For a hypothetical `raw/foo_bar_2026.json` → `"2026"`. OK. Not a bug.**

**2. `_encampment_partition` is called twice with overlapping year sets** (`health.py:compute_source_health`). `enc_type_window` uses `sorted(years)` (rolling window), `enc_type_full` uses `_legacy_year_files`. The window partition re-reads the same files. Wasteful but not wrong. **However**: `_legacy_year_files("encampments_v2")` lists keys with prefix `raw/encampments_v2_`. If a stale file like `raw/encampments_v2_2026_backup.json` exists, `stem.rsplit("_",1)[-1]` = `"backup"`, not a digit → skipped. Fine.

**3. `disrupted_since` computed from `through` (coverage max), not from the actual last coverage report day.** Contract says "day after `through` when status != ok". Matches. But `through` is `max` over coverage sources — if the type feed's last day is 2026-05-27 and Open311 encampments is also stale with last day 2026-04-01, `through` = 2026-05-27, `disrupted_since` = 2026-05-28. That's the contract. OK.

**4. `freshness.ts:notOkText` for schema-2 stale layer with empty `latest_report` and empty `through`** renders `"Encampments: latest report unknown"`. Contract says fall back to `through`; if both empty, "unknown" is arguably fine but the contract's frozen-fallback path expects a real date. Minor.

**5. `freshness.ts` degraded notice filter is wrong for legacy schema.** `troubled.filter((c) => c.disruptedSince || (hasModernSchema && c.status === "degraded"))`. For schema 1, `disruptedSince` is always `null` (set in the legacy branch), so the filter yields `[]` → falls to `LEGACY_NOTICE`. Correct. But for schema 2 with a **stale** layer whose `disrupted_since` is `null` (e.g. `through` empty), the filter drops it, and if it's the only troubled layer, `sentences.length === 0` → `LEGACY_NOTICE(troubled.map(c => c.label))`. That's the intended fallback. OK.

**6. `freshness.ts` frozen fallback ignores `hasModernSchema`.** When `health` is null, `layerEntries.length === 0`, so the frozen branch runs regardless. Contract: "health null → frozen fallback: render the not-ok form using frozen date as both through and latest_report, disrupted_since = frozen date + 1 day." Matches. But `addDay` uses local-time `Date` arithmetic; DST transitions could shift by an hour but `setDate(+1)` is calendar-safe. OK.

**7. `HeatMap.tsx` disruption note uses `selMonth === 0` as the "all months" sentinel.** Contract says "Selected 'all months'/'all years' → no note." If the UI uses `0` for "all months" and `"all"` for year, this works. But `isDisruptedMonth(d.since, Number(selYear), selMonth)` — if `selYear` is `"all"`, `Number("all")` = `NaN`, and `year !== sinceYear` → `NaN > sinceYear` is `false` → returns `false`. So the `selYear === "all"` guard is redundant but harmless. **However**: if `selMonth` is a 1-indexed month (Jan=1), then `isDisruptedMonth("2026-05-28", 2026, 5)` returns `true` (May), and the test asserts `isDisruptedMonth("2026-05-28", 2026, 4)` is `false` (April). So `selMonth` must be 1-indexed. But `selMonth === 0` is the "all" sentinel — consistent. OK.

**8. `HeatMap.tsx` "both" layer contract violation.** Contract: `"both" → show for whichever of needles/encampments is disrupted`. The code renders both `needlesDisruptionNote` and `encampmentsDisruptionNote` independently when `dataLayer === "both"`. That matches. But the contract also says the note is appended to "that layer's count line" — the code appends to each. OK.

**9. `HeatMap.tsx` waste note.** Contract's HeatMap prop section only mentions sharps/encampments/both. The code adds a waste note. Not a violation (waste is a layer key), but the contract's "both" clause doesn't cover waste. If `dataLayer === "waste"`, the note fires. Fine.

**10. `index.astro` passes `disruptionsFromHealth(sourceHealth)` but `sourceHealth` may be null.** `disruptionsFromHealth(null)` returns `{}`. OK.

**11. `basemapKey` prop is unrelated to the contract** — scope creep. Not a bug, but the diff bundles an unrelated CARTO→Esri fallback. The `maxNativeZoom: 16` with `maxZoom: 19` means Leaflet upscales; acceptable.

**12. `fetcher.py` stamps `_uhm_route` on the row dict, which is then persisted to `raw/encampments_v2_<year>.json`.** The cleaner/marker pipeline may not expect this key. If downstream code iterates row keys or serializes to a schema, `_uhm_route` leaks. Not shown in diff, but a contract risk.

**13. `health.py:_row_route` fallback uses `row.get("type") in ENCAMPMENT_TYPES`.** If `ENCAMPMENT_TYPES` is a set of strings and `type` is `None`, `None in set` is `False` → "queue". Correct per H1.

**14. `health.py` `_legacy_through_days` for non-encampment datasets scans all year files, but `_legacy_window_days` still filters `year not in RESOURCE_IDS`.** For needles/waste, `through` now comes from all files, `last_30d` from windowed files. Consistent with H2. But `RESOURCE_IDS` may not contain the current year if the dataset was renamed — then `last_30d` = 0 → status stale even though `through` is recent. Pre-existing behavior.

**15. `freshness.ts:fmt` returns `"unknown"` for empty string.** Contract's chip for ok layer with empty `through` would render `"Sharps: data through unknown"`. Edge case not covered by tests.

**16. `freshness.ts` notice for degraded layer uses `NOTICE_SUBJECT` = `"Sharps"` → `"Sharps reporting volume has dropped sharply..."`. Contract amendment says `"<Subject> reporting volume has dropped sharply since the switch"`. The test asserts exactly this. OK. But for `waste`, subject is `"Human waste"` → `"Human waste reporting volume..."`. Contract doesn't specify waste subject casing. Minor.

**17. `isDisruptedMonth` with malformed `since` (e.g. `""`)** → `Number("")` = 0, `sinceYear=0`, `sinceMonth=0` → returns `true` for any year/month. `disruptionsFromHealth` guards `if (!since) continue`, so `since` is non-empty. But `HeatMap` receives `disruptions` from `index.astro`; if a caller passes a malformed entry, the note fires spuriously. Defensive gap.

**18. `freshness.ts` `troubled` includes degraded layers, but the chip text for degraded is the ok-form + suffix.** The notice filter includes degraded only when `hasModernSchema`. For schema 1 with a degraded status (impossible from pipeline, but possible from hand-edited health), the filter drops it → legacy notice. Acceptable.

**19. `health.py` `disrupted_since` uses `date.fromisoformat(through)`.** If `through` is malformed (non-ISO), raises. `through` comes from `_local_day` which returns ISO or `""`. Guarded by `and through`. OK.

**20. `health.py` `latest_report = max((sources[k]["through"] for k in keys), default="")`** — includes non-coverage queue source. Contract: "max through over ALL sources". Matches. But if queue source has `through=""` and type has `"2026-05-27"`, `max` = `"2026-05-27"`. OK.

**21. `freshness.ts` `disruptionsFromHealth` includes layers with `status !== "ok"` and non-null `disrupted_since`.** Contract: "only for layers with status != 'ok' and non-null disrupted_since". Matches. But it also includes `degraded` layers if they somehow have `disrupted_since` set — pipeline never sets it for degraded, but a hand-edited health could. Minor.

**22. `HeatMap.tsx` `disruptionNoteFor` returns `fmtShort(d.since)` — the note text is `" · reporting disrupted since May 28"`.** Contract: `" · reporting disrupted since May 28"` (date "Mon D"). Matches.

**23. `HeatMap.tsx` note color `#8a6d1f` is hardcoded** — not a contract violation, but inconsistent with the chip styling.

**24. `freshness.test.ts` `baseSchema2Health` omits `waste` layer.** `freshnessModel` iterates `Object.entries(health.layers)` — only encampments and needles. The test for `disruptionsFromHealth` adds waste. OK.

**25. `freshness.test.ts` legacy test asserts `notice` equals the legacy text, but `freshnessModel` for schema 1 with a stale layer and `disruptedSince=null` → filter yields `[]` → `LEGACY_NOTICE`. Matches.**

**26. `health.py` `_encampment_partition` logs a warning if partition doesn't sum, but `_row_route` always returns "type" or "queue", so the sum always equals `len(rows)`.** The warning is dead code. Not a bug.

**27. `health.py` `_legacy_year_files` uses `storage.list_keys(f"raw/{prefix}_")`.** If `list_keys` returns keys with a leading slash or different prefix, parsing breaks. Assumed correct.

**28. `freshness.ts` `addDay` for `d=""`** → `new Date("T12:00:00")` = Invalid Date → `getFullYear()` = NaN → returns `"NaN-NaN-NaN"`. Frozen fallback with empty date would produce garbage. `frozen` is expected to have real dates, but no guard.

**29. `HeatMap.tsx` `disruptions` default `{}`** — if `index.astro` passes `undefined` (e.g. `sourceHealth` fetch fails and `disruptionsFromHealth` isn't called), default applies. OK.

**30. `health.py` `coverage` flag added to source dict, but `SourceHealthEntry` in `types.ts` marks it optional.** Frontend doesn't read it. OK.

**31. `freshness.ts` `notOkText` for schema-2 stale layer with `disruptedSince` set but `latestReport` empty** → `"Encampments: latest report unknown · reporting disrupted since May 28"`. Contract says fall back to `through` if `latest_report` empty; code does `layer.latest_report || through`. If both empty, "unknown". Edge case.

**32. `health.py` `disrupted_since` for a layer with `status="stale"` but `through=""`** → `None`. Contract: "day after `through` when status != 'ok', else null". If `through` empty, null is reasonable. But then the frontend chip renders `"latest report unknown"` with no disruption suffix. Contract's not-ok form says "if disrupted_since is null, omit the ' · reporting disrupted since …' part". Matches.

**33. `freshness.ts` `LEGACY_NOTICE` joins labels with `", "`** — for a single label, `"(Encampments)"`. Matches test.

**34. `health.py` `_legacy_window_days` for encampments is never called** (encampment branch bypasses it). Dead code for that dataset. Not a bug.

**35. `HeatMap.tsx` `selMonth === 0` guard** — if the UI uses `selMonth` as a string (e.g. `"all"`), `=== 0` fails and `isDisruptedMonth` gets `Number("all")` = NaN → returns false. Safe but fragile.

**36. `freshness.ts` `fmtShort` for `d="2026-05-28"`** → `new Date("2026-05-28T12:00:00")` → local noon → `"May 28"`. Matches.

**37. `health.py` `_open311_counts` unchanged** — `through` is newest non-empty day. For Open311 encampments successor, `through` = yesterday. Layer `through` = max over coverage sources = yesterday. `disrupted_since` = null (status ok). Matches test.

**38. `freshness.ts` `disruptionsFromHealth` uses `layer.latest_report || layer.through || ""`** — if both empty, `latest` = `""`. HeatMap doesn't use `latest`. OK.

**39. `health.py` `notes` for stale layer uses `through` (coverage max), not `latest_report`.** Contract doesn't specify notes format. OK.

**40. `freshness.ts` `troubled` is returned but `DataFreshness.astro` only uses `notice`.** `troubled` is dead in the component but exported for tests. OK.

## Contract violations

- **`freshness.ts` degraded chip text**: contract amendment says degraded keeps `data through` chip with suffix `" · reporting volume down"`. Code: `degradedText` = `okText + " · reporting volume down"`. Matches.
- **`freshness.ts` degraded notice**: contract says `"<Subject> reporting volume has dropped sharply since the switch; recent months may be incomplete."` Code matches.
- **`health.py` `disrupted_since` only for stale**: matches amendment.
- **`HeatMap.tsx` "both" layer**: contract says show for whichever of needles/encampments is disrupted. Code shows both independently. Matches.
- **`HeatMap.tsx` "all months"/"all years"**: `selYear === "all" || selMonth === 0` → no note. Matches.
- **`index.astro` builds `disruptions` from health**: matches.

## Edge cases not covered

- `health.layers` present but `schema_version` missing → `hasModernSchema = false` → legacy chip. Contract: "schema_version missing or < 2 (old health file): legacy form". Matches.
- `health.layers` empty but `health` non-null → frozen branch. Contract doesn't specify; reasonable.
- `frozen` empty and `health` null → `chips = []`, `notice = null`. `DataFreshness.astro` renders nothing. OK.
- `layer.status` missing → defaults to `"stale"`. Contract doesn't specify; reasonable.
- `layer.through` missing → `""` → `fmt("")` = `"unknown"`. Chip renders `"Sharps: data through unknown"`. Contract doesn't cover.

## Summary

The implementation largely satisfies the contract. The most concerning issues are: (a) `_uhm_route` leaking into persisted raw rows without downstream awareness (fetcher.py:204, 215); (b) `addDay`/`fmt` producing `"NaN-NaN-NaN"`/`"unknown"` for empty inputs without guards (freshness.ts:addDay, fmt); (c) `isDisruptedMonth` returning `true` for malformed `since` (freshness.ts:isDisruptedMonth); (d) the unrelated CARTO/Esri basemap change bundled into the diff (HeatMap.tsx:345-370); (e) `_encampment_partition` called twice with overlapping year sets, re-reading files (health.py:compute_source_health). None are contract violations per se, but (a) and (b) are latent bugs.