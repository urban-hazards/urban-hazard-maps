# Data Quality Issues

> 14 systemic problems with Boston's 311 open data feed on data.boston.gov.
> Audited against 2024-2025 data (267K records in 2025).
> Last updated: 2026-04-11

## 1. Description Field Stripped

The Open311 API returns the citizen's free-text complaint (`description`). CKAN
strips it entirely — both legacy and new Creatio system. This is the single
biggest data quality issue. The public sees what the city wrote when closing,
not what residents reported.

- Open311 API: 81-100% of tickets have descriptions
- CKAN: 0% — field doesn't exist in any export year (2011-2026)
- CSV downloads identical to CKAN — no description anywhere

## 2. Human Waste Routing Black Hole

`INFO_HumanWaste` queue receives only ~65 tickets/year citywide. Zero phone-call
tickets reach it — only app-submitted ones. Call center operators route to
`PWDx_District` queues (regular trash crew), who then bounce with "BPW does not
service human waste on public streets." 181 confirmed misroutes in 2024-2026.

See: `research/human_waste_examples.json` (326 labeled examples).

## 3. Routing Chaos

"Requests for Street Cleaning" routes to **92 different queues** across 2025.
168 distinct queues, 17 departments, 162 ticket types. Same ticket type can go
to completely different teams depending on which operator handles it.

Top types by queue destinations: Street Cleaning (92), General Comments (84),
Sidewalk Repair (75), Pothole Repair (64).

## 4. Silent Closures

Thousands of tickets closed with boilerplate text and no real resolution:
- "Case Closed Case Invalid" (199x occurrences)
- "Case Closed Case Noted" (173x)
- "Case Closed Case Resolved" (156x)
- 4,304 tickets closed as "Invalid" in 2025
- 403 "Referred to External Agency" with no tracking after referral

## 5. SLA Gaming

85,042 tickets marked OVERDUE out of 267,187 total (31.8%). 1,139 marked
"ONTIME" but closed as "Invalid" or "Noted" — hitting SLA targets by closing
without doing anything. 47,203 cases from before Sept 2025 still sitting Open.

## 6. Photo Field Broken

`submitted_photo` returns 0 results in aggregate CKAN queries despite individual
Open311 API records containing Cloudinary URLs. Only 31.3% of records have
`closed_photo`. Photo URLs point to `spot-boston-res.cloudinary.com` — could
disappear if the city changes vendors.

## 7. Location Data Gaps

- 2,236 records: no lat/long
- 2,574 records: no street address
- 56,280 records (21.1%): no zip code
- "1 City Hall Plz" is most-used address (449 tickets) — likely a fallback default

## 8. Neighborhood Naming Inconsistency

Duplicate/overlapping names make geographic analysis unreliable:
- "Allston" vs "Allston / Brighton"
- "South Boston" vs "South Boston / South Boston Waterfront"
- "Mattapan" vs "Greater Mattapan"
- A blank space `' '` is a distinct neighborhood value

## 9. Duplicate Tickets

3,716 tickets closed as "duplicate" in 2025. No dedup field or linked-case-id
to track which case is the original. Same address + same type + same day shows
clusters of 3+ tickets.

## 10. Missing Data Silos

Several agencies maintain records outside the 311 feed:
- **New Market Business District** — own data, not in 311
- **BPHC** — separate records for biohazard/health; `INFO_BPHC` queue is a
  referral target but cases leave the 311 dataset
- **Encampment Response Team (CRT)** — outcomes not tracked back to 311
- **SHARPS team** — closures reference work done but no SHARPS-specific dataset

## 11. Source Field Opacity

"Employee Generated" is 47% of all tickets (125,493) — the largest source.
No way to distinguish: did an employee see the issue, re-enter a phone call,
or auto-generate from an internal system? "City Worker App" (26,769) vs
"Employee Generated" (125,493) — difference unclear.

## 12. No Audit Trail

When a ticket is re-routed between queues, only the final queue is recorded.
No timestamp for routing changes, no "original queue" field. Impossible to
measure how many times a ticket bounced before resolution.

## 13. System Transition Data Fracture (Oct 2025)

Legacy Lagan system being replaced by Creatio. Cases split across two CKAN
datasets with **no direct field mapping**. Key fields lost: `subject`, `reason`,
`type` replaced by `service_name`, `case_topic`. Categories "renamed,
consolidated, split, or retired entirely." Must query both datasets during
transition (expected complete mid-2026).

- [Data Transition Guide (Google Doc)](https://docs.google.com/document/d/e/2PACX-1vQ9ExKIGyrLJeyVUO92qNw0Cbj5m6Sz2IAATdBgYiAGW69Wuv7dk10PHUPR7UdawGt_e89q9VhxH-I0/pub)

## 14. Description Still Missing from New System

The new Creatio system has 29 fields. Still no `description`. The Open311 API
continues serving it live — it's deliberately excluded from the open data export.

## Research Scripts

All audit scripts live in `research/` in the repo:
- `data_quality_audit.py` — full audit
- `data_quality_patch.py` — supplemental queries
- `human_waste_explore.py`, `human_waste_extract.py`, `human_waste_deep_dive.py`
