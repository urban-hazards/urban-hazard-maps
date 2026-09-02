# Mattress Data in Boston 311

> How mattress pickups and mattress complaints show up (and stop showing up) in Boston's 311 data.
> Source of truth for the `/mattress` page. Regenerate numbers with
> `cd pipeline && uv run python ../scripts/mattress_analysis.py` (writes `frontend/src/data/mattress.json`).

## Timeline

| Date | Event | Evidence |
|---|---|---|
| 2022-11-01 | MassDEP bans mattresses/box springs (and textiles) from trash disposal statewide | mass.gov waste-ban guide; boston.com 2022-10-31 |
| 2023-01 | 311 starts logging `Mattress_Pickup` cases (Subject: Public Works, Reason: Sanitation). One stray case 2022-10-26. | CKAN 2023 resource |
| 2023-01 → 2024-05 | 36,548 `Mattress_Pickup` cases. 98% source `Constituent Call` (phone), 2% `Employee Generated`, **zero** app/web sources. 87% closed with note `Mattress Pickup Automation Mattress Scheduled Pickup Automation`. Peak 3,417 (Aug 2023). | CKAN 2023/2024 |
| 2024-05-10 | Last `Mattress_Pickup` case. May 2024 = 801 cases. | CKAN 2024 |
| 2024-06-04 | Public Works launches self-service scheduling at boston.gov/mattress ("On Tuesday, the Public Works Department went live with an online system…" — Dorchester Reporter, 2024-06-06). Pickups no longer create 311 cases. | dotnews.com/columns/2024/boston-goes-mattresses |
| 2024-12 | `Schedule a Bulk Item Pickup` logs its last case (same pattern: scheduling moved off 311). | CKAN 2024/2025 |

The queue `Z_DO_NOT_USE_PWDx_WM_Mattress_Pickup` survives as a retired queue; every May–September a few hundred
unrelated Street Cleaning / Code Enforcement cases still get parked in it.

## Where mattress complaints live now

No case type for a dumped mattress exists. Residents file under the closest thing; the text is only visible in the
Open311 API `description` field (CKAN strips it). Regex `mattress|matress|box ?spring`, Boston-local month bucketing:

| Queue (scraper slug → CKAN type) | 2023 | 2024 | 2025 |
|---|---|---|---|
| illegal-trash → Improper Storage of Trash (Barrels) | 2,078 | 2,141 | 2,108 |
| street-cleaning → Requests for Street Cleaning | 1,639 | 1,367 | 1,127 |
| other → General Request ("Other") | 918 | 742 | 596 |
| **Total** | **4,635** | **4,250** | **3,831** |
| Share of all reports in those queues | 5.1% | 4.7% | 4.7% |

Seasonality: every year peaks in late Aug–Sep (Sept 1 move-out); 2024 and 2025 peak in August. The Aug 2025 peak was the largest.

**Answer to "did complaints go down after the self-service scheduler?"** — a little, not a lot. 12 months before
vs 12 months after June 2024: ~403/mo → ~334/mo (−17%), on a background drift of roughly −8%/yr. Share of queue
volume is flat. Pickup requests (people who own a mattress) and dumped-mattress complaints (people who found one)
are different populations; the scheduler changed where the first group is recorded, not the second group's behavior.

## Traps

- `closure_reason LIKE '%mattress%'` on non-Mattress_Pickup types jumps 265 (2022) → 3,177 (2023). That is staff
  closure templates pointing residents at the pickup program, not resident behavior. Don't present it as demand.
- CKAN `datastore_search_sql` is behind Cloudflare: `SUBSTR()` in the SQL returns 403. Use `LEFT(CAST(col AS TEXT), n)`.
  2026's `open_dt` is a timestamp column (ISO `T`), earlier years are text — `CAST` handles both.
- Open311 `requested_datetime` is UTC (`...Z`). Bucket by America/New_York or month-boundary evenings shift.
- Open311 scraper file dates run past the last complete month; use `open311_last_full_month` from the JSON, not the
  file date, when labeling "through".
- The Open311 API exposes 2023 onward only. There is no description-level baseline before the mattress program.

## Asks for the city (if they want this tracked)

1. Export of boston.gov/mattress appointments since 2024-06 (date, neighborhood/zip) — restores the pickup series.
2. Pre-2023 311 export **with** `description` — the public CKAN drops it; the API doesn't go back that far.
3. A "dumped mattress" case type or sub-type so ~4,000 free-text reports a year become countable.
