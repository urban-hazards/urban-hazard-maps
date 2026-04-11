# Open311 Service Code Reference

> Maintained as we discover how Boston's 311 system actually works vs how it appears.
> Last verified: 2026-04-11 against live API + CKAN bulk data.

## The Two Code Systems

Boston's Open311 API (`boston2-production.spotmobile.net/open311/v2`) uses two
different formats for service codes. Understanding the difference is critical
because **querying with the wrong format returns zero records**.

### 1. `input.*` codes (app form identifiers)

The `/services.json` endpoint lists 16 services. Four of them use an `input.*`
prefix. These are **submission form identifiers** for the BOS:311 mobile app —
they define what buttons the app presents to users. When a citizen taps one,
the backend reclassifies the ticket into a colon-delimited code before saving.

**These codes tag zero stored records.** Querying `/requests.json` with an
`input.*` code always returns an empty array.

| input.* code | App button label | Group |
|---|---|---|
| `input.Illegal Graffiti` | Illegal Graffiti | Graffiti |
| `input.Litter` | Litter | Litter and Trash |
| `input.Rodent Sighting` | Rodent Sighting | Health Hazards |
| `input.Overflowing Trash Can` | Overflowing Trash Can | Litter and Trash |

**Where they actually route to:**

| App button (input.*) | Stored as (colon-delimited) | CKAN type name | 2024 volume |
|---|---|---|---|
| input.Illegal Graffiti | `Property Management:Graffiti:Graffiti Removal` | Graffiti Removal | 2,501 |
| input.Litter | `Public Works Department:Street Cleaning:Requests for Street Cleaning` (probable) | Requests for Street Cleaning | 22,539 |
| input.Rodent Sighting | `Inspectional Services:Environmental Services:Rodent Activity` | Rodent Activity | 5,015 |
| input.Overflowing Trash Can | Unknown — possibly Empty Litter Basket or Street Cleaning | TBD | TBD |

### 2. Colon-delimited codes (`Subject:Reason:Type`)

The actual storage format. Maps directly to CKAN's `subject`, `reason`, and
`type` columns. These are the codes that return real data from the API.

Examples:
- `Mayor's 24 Hour Hotline:General Request:General Request`
- `Public Works Department:Street Cleaning:Pick up Dead Animal`
- `Inspectional Services:Environmental Services:Rodent Activity`

### 3. UUID codes (rare)

At least one service uses a UUID: `11d12a6d-6ca7-426a-8905-0e1929527419`
(Street Light Other). Origin unknown — possibly from a different intake system.

## /services.json Is Incomplete

The endpoint lists only 16 services, but **CKAN has 200+ distinct type values**
and the API stores records under many more colon-delimited codes than
/services.json advertises. The unlisted codes are fully queryable — they just
aren't discoverable through the standard Open311 service discovery.

To find all valid codes, cross-reference CKAN's distinct `type` values and
construct the colon-delimited code from `subject:reason:type`.

## Service Code Mapping (scraper)

Current mapping used by `services/open311-scraper/fetch.py`:

| Slug | Service Code | Status |
|---|---|---|
| other | `Mayor's 24 Hour Hotline:General Request:General Request` | Verified |
| needles | `Mayor's 24 Hour Hotline:Needle Program:Needle Pickup` | Verified |
| encampments | `Mayor's 24 Hour Hotline:Quality of Life:Encampments` | Verified |
| potholes | `Public Works Department:Highway Maintenance:Request for Pothole Repair` | Verified |
| sidewalks | `Public Works Department:Highway Maintenance:Sidewalk Repair (Make Safe)` | Verified |
| dead-animals | `Public Works Department:Street Cleaning:Pick up Dead Animal` | Verified |
| graffiti | `Property Management:Graffiti:Graffiti Removal` | Fixed 2026-04-11 (was input.Illegal Graffiti) |
| graffiti-pwd | `Public Works Department:Highway Maintenance:PWD Graffiti` | Added 2026-04-11 (second graffiti dept) |
| litter-baskets | `Public Works Department:Highway Maintenance:Empty Litter Basket` | Fixed 2026-04-11 (was input.Litter) |
| rodents | `Inspectional Services:Environmental Services:Rodent Activity` | Fixed 2026-04-11 (was input.Rodent Sighting) |
| trash-cans | `Inspectional Services:Environmental Services:Overflowing or Un-kept Dumpster` | Fixed 2026-04-11 (was input.Overflowing Trash Can) |
| abandoned-vehicles | `Transportation - Traffic Division:Enforcement & Abandoned Vehicles:Abandoned Vehicles` | Verified |
| parking | `Transportation - Traffic Division:Enforcement & Abandoned Vehicles:Parking Enforcement` | Verified |
| traffic-signals | `Transportation - Traffic Division:Signs & Signals:Traffic Signal Inspection` | Verified |
| signs | `Transportation - Traffic Division:Signs & Signals:Sign Repair` | Verified |
| abandoned-bikes | `Mayor's 24 Hour Hotline:Abandoned Bicycle:Abandoned Bicycle` | Verified |
| illegal-trash | `Public Works Department:Code Enforcement:Improper Storage of Trash (Barrels)` | Verified |
| street-cleaning | `Public Works Department:Street Cleaning:Requests for Street Cleaning` | Verified |

## Open Questions

### Where does "input.Litter" actually route?

The app has a "Litter" button, but there is **no stored type called "Litter"**
in CKAN or the API. The most likely destination is "Requests for Street
Cleaning" (22,539/year) — the catch-all for dirty streets. But we haven't
confirmed the routing. If true, it means app-submitted litter reports are
indistinguishable from all other street cleaning requests without reading the
description text.

"Litter" in 311 jargon almost exclusively refers to **litter baskets** (public
trash cans), not litter on the ground:
- "Empty Litter Basket" = "this city trash can is full, please empty it"
- "Litter Basket Maintenance" = "this trash can is damaged/missing"
- "Request for Litter Basket Installation" = "we need a trash can here"

Ground litter has no dedicated category. It scatters across:
- Requests for Street Cleaning (22,539/year) — main catch-all
- Illegal Dumping (2,997/year) — bulk/deliberate, 96% phone calls
- Ground Maintenance (3,902/year) — parks dept handles these
- Improper Storage of Trash (20,432/year) — residential code violations

### Where does "input.Overflowing Trash Can" route?

Still unconfirmed. Candidates:
- `Empty Litter Basket` (2,560/year) — most likely, same concept
- `Overflowing or Un-kept Dumpster` (95/year) — low volume, Inspectional Services
- `Requests for Street Cleaning` — possible catch-all

### Do input.* tickets carry structured form data?

Rodent Activity tickets from the API contain structured form fields in the
description: `"Rat bites: [No] Rats in the house: [No] Rats outside of
property: [Yes]"`. This structured data is **not written by citizens** — it's
generated by the app's intake form. This means the app IS collecting structured
data through the input.* forms, it's just being serialized into the description
field of the reclassified ticket.

This is important because it means:
1. The reclassification preserves the original form responses
2. We can parse structured fields out of descriptions for any type that uses app forms
3. The presence of structured form data in a ticket tells us it came through the app

### Are ~700 rodent reports trapped in "Other"?

Research on "Other" (General Request) tickets found ~700 mentioning rats/rodents
that were never reclassified. Need to study:
- Do they have the structured form fields? (If yes, the app submitted them as
  rodent reports but routing failed)
- Are they eventually acted on through a different path?
- What patterns distinguish trapped-in-Other from properly-routed?

### Peak hour analysis: Is 12 AM real or a batch artifact?

For needle/sharps data, the peak hour is **12 AM Eastern** — verified real
timestamps, not a data artifact. Zero records have fake `T00:00:00` across all
years (2015-2024). CKAN timestamps are real UTC times; the pipeline correctly
converts to Eastern.

**Critical caveat: ticket timestamps measure when people REPORT, not when the
activity occurs.** Needle use likely peaks afternoon through evening, but
reporting lags by hours. Someone walks past needles on their morning commute
and files at 8 AM for something left at 2 AM. A city worker starts their shift
and logs what accumulated overnight. The 12 AM peak may reflect:
- Late-night pedestrians (bar/nightlife crowd) reporting what they see in real-time
- Employee batch-entry of overnight accumulation
- Some mix of both

**Investigated (2024 data, 10,737 Needle Pickup tickets):**

Source breakdown: Citizens Connect App 80%, Constituent Call 19%, Employee
Generated 0.05% (5 tickets). The midnight peak is overwhelmingly real-time
citizen app reports, not batch entry. BPHC/SHARPS team does NOT create tickets
in bulk — they respond to citizen-created ones and log closures with syringe
counts and worker initials (e.g. "78 syringes recovered 13dt", "recovered by
jg"). Only 5 employee-generated tickets all year.

High-count tickets (20+ syringes, n=10): 6/10 on Mondays (weekend
accumulation), all at expected hotspots (Mass Ave, South End, BMC area). No
round-minute clustering, confirming real-time reporting not batch entry.

### SHARPS team worker identification (from closure notes)

Analysis of 10,737 Needle Pickup closures in 2024 revealed 6 identifiable
SHARPS workers by their initials in closure notes. The closure format varies
by worker but follows patterns like `[count][initials]` (e.g. "6dw") or
`[text]. [INITIALS].` (e.g. "Needle recovered. JT.").

| Worker | Closures | Schedule | Peak Close Hours (ET) | Syringe Count |
|--------|----------|----------|----------------------|---------------|
| JT | 2,480 | Mon-Fri, light wknd | 11PM-1AM | no parsed counts |
| CD | 1,900 | Mon-Fri only | 5-6AM, 11AM | no parsed counts |
| DW | 1,877 | Tue-Thu heavy | 11PM-3AM | 4,418 (avg 2.4) |
| JG | 1,401 | Heavy Sun, light Fri | 5-6AM, 10AM | 1,525 (avg 2.2) |
| DF | 1,391 | Sat-Sun-Mon | 11PM-1AM | no parsed counts |
| DT | 750 | — | — | 5,913 (avg 7.9!) |

Two shift patterns: overnight (JT, DW, DF: 11PM-3AM) and early morning
(CD, JG: 5-6AM, 10-11AM). DT handles the heavy pickups at nearly 4x the
average count per ticket.

**NLP opportunity:** Parse syringe counts from all closure notes to build
a real needle collection dataset. The count formats are: `[N]dw`, `[N]dt`,
`[N] syringe(s) recovered by [initials]`, and freetext. Would give us actual
pickup volumes, not just ticket counts.

**Citizen vs employee on ticket creation (REVISED):** Open311 descriptions
show real citizen language on many tickets (free text, photos, auto-translated
messages). However, **132 days in 2024 show clear sweep-route patterns**: 5-10
tickets filed within 10-30 min across 4-10 unique locations spanning multiple
neighborhoods. These are unmistakably a crew driving/walking a route and logging
via the app — not citizens. Estimated ~924 tickets (~11% of app submissions)
come from professional sweeps logged as "Citizens Connect App."

Geographic analysis of these clusters disproved the sweep theory: most clusters
span 2-5 miles across multiple neighborhoods, requiring 5-22 mph — physically
impossible for one person walking. These are multiple citizens independently
filing around the same time (midnight bar-closing, people walking home). Only a
few tight-radius clusters (< 0.3 mi) remain ambiguous.

**The "Citizens Connect App" source label appears reliable for needle tickets.**
The midnight peak is real: many Bostonians are out at midnight and independently
report needles. This is consistent with the Open311 description text (specific
local context, auto-translated messages, photos).

**Submitter data exists** in the Open311 API via `?extensions=true` — includes
`first_name`, `last_name`, `email` in `extended_attributes`. This is PII we
must NOT store or publish, but can be used for one-time analysis to confirm
whether cluster tickets come from different people. Also exposed: structured
form fields (`needle_qty`, `needle_loc_type`) which CKAN strips.

**Structured form data available per ticket type:**
- Needle Pickup: `needle_qty` (One, Few, Many), `needle_loc_type` (Public, Private)
- These are in the `attributes` array and `details` dict on the API response
- Other types likely have their own structured form fields — worth cataloging

**Still worth investigating:** Constituent-call hour patterns (19% of tickets):
- "Citizens Connect App" at midnight → real-time reports from people who are out
- "Employee Generated" at midnight → batch entry, timestamp is logging time not observation time
- "Constituent Call" at midnight → unlikely, call center hours matter
- Look for recurring daily spikes at shift-change times (7 AM, 3 PM) which would indicate crew logging patterns
- Check if "Employee Generated" tickets cluster at round hours (:00, :30) which would suggest manual batch entry vs real-time

**For the public:** The site should make clear that hourly charts show
*reporting patterns*, not *activity patterns*. Eventually: drill-down from any
stat to the raw records that produced it, showing CKAN row IDs and Open311
request IDs so users can verify methodology.

### Graffiti: Two departments, one problem

Graffiti Removal (Property Management, 2,501/year) and PWD Graffiti (Public
Works, 1,305/year) appear to be the same service split across departments.
Need to study whether they serve different areas, have different response
times, or handle different types of graffiti.

## API Reference

- **Services list:** `GET /v2/services.json`
- **Service definition:** `GET /v2/services/{service_code}.json` (404s for input.* and unlisted codes)
- **Requests:** `GET /v2/requests.json?service_code=...&start_date=...&end_date=...`
- **Discovery:** `GET /v2/discovery.json`
- **Base URL:** `https://boston2-production.spotmobile.net/open311`
- **Test URL:** `https://boston2-test.spotmobile.net/open311/v2`
- **Rate limit:** 10 req/min unauthenticated, 100 results/page, 90-day date range max
- **API key request:** `https://boston2-production.spotmobile.net/open311/app_requests/new`
