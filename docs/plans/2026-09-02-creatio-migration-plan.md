# Plan: UHM data through the Lagan → Creatio migration

Date: 2026-09-02. Drafted by Claude, audited by Codex and Antigravity (their corrections folded in).
Owners: Brian = frontend, Scott = pipeline. Tracked as GitHub issues (see bottom).

## What is true (verified 2026-09-02)

1. Boston is migrating 311 from Lagan to Creatio in department waves through mid/late 2026. CKAN has two
   datasets: legacy yearly files (2011–2026) and "311 Service Requests - NEW SYSTEM"
   (`254adca6-64ab-4c5c-9fc0-a6da622be185`, 48,646 rows, 2025-08 → now, ramping to ~15k/month).
2. Legacy file cutoffs: Requests for Street Cleaning, Illegal Dumping, Encampments have no cases after
   June 2026; Improper Storage of Trash drops ~75% from July. Needle Pickup and General Request ("Other")
   are still legacy.
3. **The Open311 endpoint already serves Creatio cases.** `311.boston.gov` and
   `boston2-production.spotmobile.net` are the same service. Creatio cases carry UUID request IDs and
   UUID `service_code`s (not listed in `services.json`), with `description` and `media_url`. Litter &
   Debris: 360 of 392 recent requests have descriptions. Filtering by UUID code works
   (`?service_code=155a5e9b-…`). 45 codes discovered so far: `docs/wiki/creatio-open311-codes.json`.
   Our scraper returns 0 for migrated types only because it asks for the legacy colon-codes.
4. Encampments: 0 requests since 2026-06-01 on both hosts for `8638e79a-…`; legacy type ends June;
   Creatio has no encampment topic. Treat as a removed intake until proven otherwise.
5. Human-waste classifier: its Street Cleaning input stopped in July, but `Other` still flows (partial,
   not zero — audit correction). Litter & Debris descriptions are the natural successor input.
6. IDs: legacy `case_enquiry_id` (numeric) and Creatio `case_id` (`BCS-…`) / Open311 UUID share no
   namespace. The transition guide says the columns *correspond*, not that values match (audit correction).
7. Creatio CKAN `open_date` is timestamptz (UTC). Bucket in America/New_York. Creatio ships
   `neighborhood` and districts as text; keep deriving political districts from GIS as today (audit
   correction: CKAN text districts are known-bad).
8. Creatio `closure_comments` is staff text; never mix it into resident-description series.
9. CSV dumps 2011–2014 are download-only (datastore empty), same schema, no description. Deferred.
10. Frontend had not deployed since May 3 (pnpm 10 build-script approvals). Fixed in #131.

## Order of work

1. Public caveat + freeze (Brian, S). Site-wide note; waste and encampment layers show "data through
   2026-06" until re-fed. Update `types.ts` / `EMPTY_PAGE_STATS` with any new keys in the same PR.
2. Source health + migration monitor (Scott, M). Daily: last record date and 30-day counts per layer for
   legacy CKAN, Creatio CKAN, Open311 (legacy codes and UUID codes); diff `service_name` set to catch the
   next wave; write `source_health.json` to S3; frontend chips read it.
3. Scraper: add UUID codes (Scott, S). Litter & Debris, Improper Trash Storage, Illegal Dumping or
   Disposal, Trash Placed Out Early, Overflowing Trash, Missed Waste Pick-up, Park Litter & Debris,
   Student Move-In. Keep legacy codes. Backfill from 2026-06-01.
4. Creatio CKAN fetcher (Scott, M). Paged fetch with count assertions and schema snapshot; tz-aware
   parsing; fail loudly on drift.
5. Mapping + dedup (Scott, M). Deterministic table (below). Canonical key `source_system:id`. Exact-ID
   merges within a system only; cross-system collapse only when mapped layer + normalized address (or
   rounded lat/lng) + local open time ±2 min + bucket all match, else emit QA candidates. No LLM in the
   daily path.
6. Integrate countable series (Scott, L). Trash / dumping / missed-bulk counts = legacy + Creatio.
7. Classified layers policy (Brian+Scott, M). Waste: run the classifier on Litter & Debris descriptions
   from Open311 (same resident-text signal); validate on a sample before publishing; label the method
   break. Encampments: stay frozen; publish the finding that the intake disappeared.
8. Frontend data contract (Brian, M). Schema version in S3 JSON; visible missing-data states; health chips.
9. Mattress page correction (Brian, S). 2026 columns: resident-description counts from Open311 (legacy +
   UUID codes), Creatio CKAN counts labeled separately; never staff comments in the complaint row.
10. Docs (fold into each issue). Wiki: data-quality-issues #13 cutoffs; service-code-mapping Creatio
    table; dev-setup pnpm trap.

Cut: 2011–2014 backfill (no description gain; revisit only if a pre-2015 series is wanted).

## Mapping table (deterministic)

| Layer / bucket | Legacy `type` | Creatio `service_name` (CKAN) / Open311 UUID |
|---|---|---|
| waste_candidates (classifier input) | Requests for Street Cleaning | Litter & Debris `155a5e9b…`, Park Litter & Debris |
| illegal_trash | Improper Storage of Trash (Barrels) | Improper Trash Storage `acb41f11…`, Trash Placed Out Early `8a0698b8…`, Overflowing Trash `c8e719d6…` |
| illegal_dumping | Illegal Dumping | Illegal Dumping or Disposal `60b145be…` |
| missed_bulk | Missed Trash/Recycling/Yard Waste/Bulk Item, CE Collection | Missed Waste Pick-up `994a8200…`, Code Enforcement Collection |
| needles | Needle Pickup / Clean-up / Cleanup | none yet (still legacy); monitor for Needle/Syringe/Sharps |
| encampments | Encampments + INFO queues | none (intake gone since June 2026) |

Full UUID list with observed volumes: `docs/wiki/creatio-open311-codes.json`.

## Acceptance

- Monitor writes daily; a synthetic 60% drop trips the banner; a new `service_name` appears in the diff.
- Scraper backfill: Litter & Debris June–Aug 2026 counts match CKAN Creatio within ±5%.
- 2026 monthly Improper Storage = legacy + Creatio within ±5%; zero duplicate canonical keys.
- No silent series anywhere: each layer shows data or a dated note.
