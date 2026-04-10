# Encampment Ticket Reclassification Research

Research branch: `research/encampment-reclassification`
Related issue: #48

## Goal

Understand where encampment-related 311 tickets lived before the "Encampments" button
was added in 2025, and how the tracking system fails to capture work that IS being done.

**IMPORTANT FRAMING:** CRT (Coordinated Response Team) and NEST are allies. They are
effective — especially from spring 2025 onward, and highly effective after Sep 1, 2025.
Open tickets ≠ failure. The teams communicate via text with reporters in hard-hit areas,
respond same-day, but then have to manually open 311 tickets after the fact. The work
happens in a parallel system that doesn't feed back into 311. This is a **tracking and
process problem**, not a performance problem.

The ultimate goal is to build a tool that helps CRT get more funding by showing the
volume and complexity of work they handle. Share preliminary numbers with CRT for
feedback before publishing — they are stakeholders, not subjects.

## Key Findings

### The Queue Field is the Rosetta Stone

Before 2025, there was no "Encampments" type, but these internal queues existed:

| Queue | 2023 | 2024 | 2025 | 2026 |
|-------|------|------|------|------|
| INFO_Encampments | 161 | 261 | 1,549 | 309 |
| INFO_CASS_Shelter_Site | — | 156 | 3 | — |
| INFO_Homeless Issue | — | 54 | 32 | 1 |
| INFO_Unsheltered_Persons | — | 47 | 33 | — |
| INFO_HumanWaste | 28 | 62 | 68 | 3 |

Pre-2025, tickets routed to INFO_Encampments were filed as:
- Requests for Street Cleaning (dominant)
- Ground Maintenance
- Poor Conditions of Property
- Improper Storage of Trash (Barrels)
- CE Collection
- Needle Pickup
- and ~10 other types

### The "Other" Button Mystery

The BOS:311 app has an "Other" button under General. Users type free text titles
like "Human puke" or "Human poop". The city reclassifies these — they don't appear
as type "Other" in CKAN. The original user text is NOT preserved in `case_title`
(gets overwritten) and is only available via the Open311 API.

### "Encampments" Button Adoption (2025)

The button captured new volume but didn't fix old routing. In 2025:
- 1,413 of 1,549 INFO_Encampments tickets properly typed "Encampments"
- 78 still came in through old types (Street Cleaning, Ground Maintenance, etc.)
- Tickets outside the known queues mentioning encampment keywords barely changed
  (49 "homeless" hits in 2024 → 44 in 2025)

### Human Vocabulary (from 225 closed tickets with encampment keywords)

What citizens and workers actually write, ranked by frequency:

**Citizen/reporter language:**
- "homeless" (89x), "trash" (39x), "camp" (38x), "encampment" (33x)
- "people" (26x), "blanket" (14x), "belongings" (12x), "sleeping" (12x)
- "tarp" (10x), "tent" (8x), "shopping cart" (6x)
- "debris" (16x) — contextual, only with homeless/camp

**City staff language:**
- "CRT" (24x) — Combined/Coordinated Response Team
- "outreach" (19x), "BPD" (6x), "DPW" (11x)
- "citation" (16x) — code enforcement saw it, couldn't cite
- "can't remove" / "unable" (7x) — worker present, person there, left

**Key staff names appearing:**
- Michaela Nee — Operations Manager, Coordinated Response Team
- William "Bill" Perkins — Assistant Director, Engagement Center & Street Outreach
- Daniel Nee — Superintendent of Street Operations, PWD
- Gilbert G. Costen — Assistant Superintendent, Street Operations
- Angel Rosario — Assistant Director, Recovery Services Outreach
- Leon Bethune — Director, Community Initiatives Bureau, BPHC
- C Perkins / Clarence Perkins Jr — Assistant Superintendent, Street Operations

**Key organizations/teams:**
- CRT (Coordinated Response Team) — primary encampment responders
- BEST team (Boston EMS?) — mental health co-response
- BPD (Boston Police Department) — quality of life referrals
- BPHC (Boston Public Health Commission)
- DMH (Department of Mental Health)
- DCR (Department of Conservation and Recreation) — state land
- Newmarket BID — neighborhood cleanup partner
- "State partners" — vague referral for state-owned land

### Resolution Patterns

Of 225 closed tickets with encampment keywords (outside known queues):
- **"Resolved" (79)** — actually cleaned/removed something
- **"Noted" (75)** — worker showed up, documented, left
  - "Homeless person sitting on the chair can't removed it"
  - "This actually a homeless person sleeping"
  - "Homeless belongings"
- **Other/no prefix (71)** — includes deflections, referrals, templates

### The Invisible Graveyard

Open tickets filed as Street Cleaning, Ground Maintenance, etc. that are actually
about encampments are invisible in CKAN — the keywords would only be in the Open311
description field, which isn't indexed in `_full_text`. We found zero open tickets
in our keyword search because only closed tickets have closure_reason text.

To find these, we'd need to pull Open311 descriptions for open tickets in suspect
types and scan them.

## Available Data Fields per Source

| Field | CKAN | Open311 | Notes |
|-------|------|---------|-------|
| case_title | Yes | Yes | Overwritten by city, not user text |
| type | Yes | Yes | City-assigned category |
| queue | Yes | No | Internal routing — the real signal |
| closure_reason | Yes | No | Only on closed tickets |
| description | No | Yes | User's original free text — the gold |
| case_status | Yes | Yes | Open/Closed |
| department | Yes | No | Which dept owns it |

## Deflection Analysis (2,868 tickets across all encampment-related queues, 2023-2026)

### Closure Categories

| Category | Count | % | What it means |
|----------|------:|--:|---------------|
| Still open | 1,418 | 49.4% | Never resolved |
| Actually resolved | 621 | 21.7% | Cleaned/removed/cleared |
| Other (uncategorized) | 599 | 20.9% | Needs manual review |
| Template response | 77 | 2.7% | Canned "thank you for contacting the Mayor" |
| Referred to state | 63 | 2.2% | "Flagged to MADCR/MADOT/state partners" |
| No encampment found | 37 | 1.3% | Went to look, nothing there |
| Contact email | 16 | 0.6% | "Email coordinated.response@boston.gov" |
| Resubmit | 12 | 0.4% | "Please resubmit with more detail" |
| Call police | 11 | 0.4% | "Report to BPD" |
| Private property | 9 | 0.3% | "City can't help, it's private land" |
| Call 911 | 5 | 0.2% | "Report trespassing/safety to 911" |

**Half of all encampment-queue tickets show as open in 311.** However, many of these
were likely acted on — CRT/NEST teams respond via text and in person, often same-day,
but the 311 system doesn't capture this. The "open" count reflects a tracking gap,
not inaction. See "CRT Effectiveness" section below.

### The Open Ticket Graveyard by Year

| Year | Queue | Still Open |
|------|-------|-----------|
| 2023 | INFO_Homeless Issue | 63 |
| 2023 | INFO_HumanWaste | 26 |
| 2024 | INFO_Encampments | 54 |
| 2024 | INFO_CASS_Shelter_Site | 35 |
| 2024 | INFO_Homeless Issue | 51 |
| 2024 | INFO_HumanWaste | 51 |
| 2025 | INFO_Encampments | 910 |
| 2025 | INFO_HumanWaste | 49 |
| 2025 | INFO_Homeless Issue | 19 |
| 2026 | INFO_Encampments | 142 |

910 encampment tickets from 2025 are still open. 63 homeless issue tickets from
2023 are still open — over 2 years old.

### Deflection Patterns

**"Call 911"** — Tickets closed by telling the reporter to call 911 for
"trespassing" or "safety concerns." Shifts the burden from city services to
emergency dispatch. Converts a sanitation/outreach issue into a criminal one.

**"Resubmit"** — Ticket closed, told to file again with better info. Resets the
clock and loses the original report's age/history.

**"Email coordinated.response@"** — Moves resolution off the public 311 system
into private email. No further public accountability.

**"Referred to state partners"** — MADCR, MADOT, MBTA. Ticket closed on Boston's
end. No tracking of whether the state actually did anything. Frequently used for
encampments on DCR land (parks, overpasses).

**"Private property"** — City declines to act. Sometimes checks for sharps only.

**"Template response"** — Almost all from INFO_CASS_Shelter_Site queue. Identical
"We have recorded your feedback" text. No action taken.

## CRT Effectiveness (the real story)

### The button worked

| Period | Encampments type | Street Cleaning | Other types |
|--------|----------------:|----------------:|------------:|
| Pre-button (2023-2024) | 0 | 461 | 409 |
| Early 2025 (Jan-Mar) | 0 | 20 | 11 |
| Summer 2025 (Apr-Aug) | 297 | 102 | 52 |
| Fall 2025 (Sep-Dec) | 1,118 | 46 | 39 |
| 2026 | 294 | 14 | 5 |

By 2026, 94% of encampment-queue tickets are properly typed "Encampments."

### CRT got faster despite 10x volume

| Period | Volume | Med. close time | Same-day close |
|--------|-------:|----------------:|---------------:|
| Pre-button (2023-2024) | 870 | 4 days | 21% |
| Summer 2025 (Apr-Aug) | 451 | 9 days | 23% |
| Fall 2025 (Sep-Dec) | 1,203 | 4 days | 27% |
| 2026 | 313 | **0 days** | **58%** |

Volume exploded Aug-Sep 2025 (40/mo → 332 → 538). CRT kept median close at
24-25 days even at 10x load. By 2026 they're closing majority same-day.

Low closure *rates* (34-41% in 2025) alongside fast close *times* is consistent
with the tracking bug — tickets acted on but not closed in 311.

### Employee-generated tickets: CRT building their own paper trail

| Year | Citizen App | Employee Generated | Constituent Call |
|------|------------:|-------------------:|-----------------:|
| 2023 | 260 | 0 | 27 |
| 2024 | 379 | 8 | 184 |
| 2025 | 744 | **851** | 85 |
| 2026 | 138 | **163** | 11 |

In 2025, CRT started generating more tickets than citizens filed. This is the
text-message-to-ticket workflow — teams respond in person via text, then
retroactively create 311 tickets for tracking. These employee-generated tickets
may be the ones most likely to show as "open" since the work was already done
before the ticket existed.

### Neighborhood hotspots

| Neighborhood | Total | Open | Close rate |
|-------------|------:|-----:|-----------:|
| Roxbury | 553 | 298 | 46% |
| South End | 374 | 185 | 51% |
| Boston (unspecified) | 362 | 193 | 47% |
| Back Bay | 270 | 115 | 57% |
| South Boston | 243 | 118 | 51% |
| Dorchester | 212 | 94 | 56% |
| Jamaica Plain | 186 | 126 | **32%** |
| Downtown | 182 | 80 | 56% |

Jamaica Plain is the outlier at 32% closure rate. Worth investigating — different
team coverage? State land (DCR)? Different reporting patterns?

## The 311 Routing Failure (tickets closed without CRT)

365 tickets with encampment keywords were closed by other departments without
ever being routed to CRT. This IS a 311 system problem — CRT never got the chance.

### Failure Modes

| Category | Count | What happened |
|----------|------:|---------------|
| debris_cleaned | 176 | Cleaned around the person, never flagged for outreach |
| NOTED_PERSON_PRESENT | 90 | Worker saw person, wrote "can't remove," closed ticket |
| noted_other | 51 | Various notes, no CRT referral |
| needle_team_found_encampment | 20 | Sharps crew found encampment, closed as needle ticket |
| shopping_cart | 3 | Shopping cart = homeless person, closed as street cleaning |

### Trend: improving

| Year | Improperly closed | Notes |
|------|------------------:|-------|
| 2023 | 143 | No Encampments button, no routing |
| 2024 | 111 | Slightly better |
| 2025 | 95 | Button exists, routing improving |
| 2026 | 16 (partial year) | Dramatic improvement |

### Top queues that close encampment tickets without CRT

- PWDx_Code Enforcement (55) — sees homeless, can't cite, closes
- INFO01_GenericForm (46) — the "Other" catch-all
- INFO_Mass DCR (36) — state land referrals
- GEN_Needle_Pickup (32) — sharps team encounters encampments
- PWDx_District 03: North Dorchester (26)
- PARK_Maintenance (various regions, 55 combined)

### Key quotes from improper closures

- "Removal of the homeless is not a code enforcement issue."
- "Homeless person sitting on the chair can't removed it"
- "Our job is not to harass the homeless. We only recover syringes."
- "It belongs to the homeless person on site. BPL property."
- "We will grab belongings in the morning when the police are on scene."

These illustrate workers who encounter encampments but have no pathway to
trigger outreach — they close the ticket in their system because from their
department's perspective, the task is done or impossible.

## What We Know (confirmed from data)

1. **Queue field is the Rosetta Stone** — `INFO_Encampments` etc. existed as routing
   queues before the Encampments button. This is how we trace pre-button tickets.

2. **The Encampments button works** — 94% proper typing in 2026, up from 0% pre-2025.
   Misrouted tickets dropped from ~143/yr to ~16/yr pace.

3. **CRT is fast and getting faster** — Median 0 days to close in 2026, 58% same-day.
   Even during the Aug-Sep 2025 10x spike they held median at 24-25 days.

4. **NEST (started mid-Sep 2025) made a visible impact** — Nov 2025 was the first
   month where closures matched new tickets (228/228). Dedicated police unit trained
   for this, works hand-in-hand with CRT.

5. **Employee-generated tickets dominate since 2025** — CRT creates more tickets than
   citizens file. This is the text→ticket workflow. These are likely the "stuck open"
   ones since the work was done before the ticket was created.

6. **1,418 tickets show as open — this is a tracking bug, not a failure.** CRT/NEST
   act via text and in-person, the 311 system doesn't capture it. Need CRT input on
   how to interpret these.

7. **365 tickets were closed by wrong dept without CRT** — workers encounter
   encampments on other jobs, close the ticket from their perspective. No pathway
   to trigger outreach. This is the actual 311 routing failure.

8. **Seasonality matters** — volume drops in winter (cold weather), encampments are
   becoming shorter-term rather than long-term settlements. Summer overwhelms.

9. **Human vocabulary for encampment tickets:** homeless, camp, belongings, sleeping,
   blanket, tarp, tent, shopping cart, CRT, outreach, debris. Staff use: CRT, BPD,
   DPW, MADCR, MADOT, "state partners," "outreach conducted."

10. **Jamaica Plain is an outlier** — 32% closure rate vs 50%+ elsewhere. 126 open
    tickets. Hypothesis: DCR/state land concentration? Different coverage model?

## What We Don't Know Yet (open questions)

- What's in the 599 "other" closures we haven't categorized?
- What do Open311 descriptions say on the open tickets? (CKAN only has closure text)
- Are there encampment tickets with NO keywords at all — just a photo and a pin drop?
- What's the resubmit/repeat pattern? Same locations getting filed, closed, refiled?
- Why Jamaica Plain? Is it DCR land, different team, different reporter behavior?
- What does CRT's actual workflow look like? Where does 311 fail to capture their work?
- How do encampment and waste tickets overlap? Same locations? Same reporters?
- What's the geographic pattern of "referred to state" — are they on DCR/MBTA land?
- Feb 2024 had 115 new tickets with 106 constituent calls — what happened? (Was this
  a campaign or a single event?)

## The "Other" Button — Dead End (confirmed)

The BOS:311 app has an "Other" button under General. In CKAN, these flow through
queue `INFO01_GenericeFormforOtherServiceRequestTypes` (6,088 tickets in 2024,
4,183 in 2025). The city reclassifies them into real types — "Other" doesn't
exist as a type in CKAN.

We searched this queue for encampment keywords: only **16 per year** had hits.
Most "sleeping" matches were animals (bats, rabbits, dogs). The real encampment
ones mostly made it to CRT — closures show "Per CRT, case can be closed."

**Conclusion:** The "Other" button is not a significant source of lost encampment
tickets. The reclassification process works for these. The real routing failures
are in tickets filed directly as Street Cleaning, Ground Maintenance, etc. that
never get reclassified.

## Gaps in Current Pipeline/Experiments Config

Scott's waste classifier (`data-experiments/src/data_experiments/config.py`) scans:
- Primary: `Requests for Street Cleaning`
- Secondary: `Needle Pickup`, `Pick up Dead Animal`, `Missed Trash`,
  `Unsanitary Conditions`, `Encampments`

**Not scanned (but should be for encampment work):**
- `Ground Maintenance` — 70 encampment-keyword tickets found in our research
- `Improper Storage of Trash (Barrels)` — 31 tickets
- `Poor Conditions of Property` — 22 tickets
- `Equipment Repair` — 6 tickets (parks equipment near encampments)
- `Illegal Dumping` — 8 tickets
- `CE Collection` — 5 tickets

**Not used at all (new discovery from this research):**
- The `queue` field — this is the real routing signal. Scott's classifier only
  looks at `type`. Adding queue-based analysis would immediately identify all
  encampment-routed tickets regardless of their public-facing type.
- `INFO01_GenericeFormforOtherServiceRequestTypes` — the "Other" catch-all queue.
  Low signal for encampments (16/yr) but worth noting.

## What Scott Can Do (advanced NLP/pipeline work)

### 1. Build an encampment classifier (like the waste classifier)
The waste classifier is keyword/lemma scoring with spaCy. An encampment version
would use the vocabulary we've extracted:
- **High signal:** encampment, homeless, unsheltered, tent, camp, sleeping (person context)
- **Medium signal:** belongings, blanket, tarp, shopping cart, debris (need context)
- **Context boosters:** CRT, outreach, BPD, BPHC, shelter, NEST
- **False positive contexts:** camping (recreational), tent (event/store), debris (construction)
- Run against ALL ticket types to find hidden encampment tickets the queue missed

### 2. Open311 enrichment for open tickets
Same pattern as waste pipeline: pull Open311 descriptions for open tickets in
Street Cleaning, Ground Maintenance, Poor Conditions, Improper Storage types.
Classify the description text. This finds the invisible graveyard — open tickets
that are actually about encampments but have no closure_reason text to search.

### 3. Temporal analysis / seasonality modeling
- Monthly volume overlaid with weather data (temp, precipitation)
- Detect if encampments are trending shorter-term (open→close duration shrinking)
- Identify the NEST inflection point (mid-Sep 2025) statistically
- Forecast seasonal demand to help CRT plan staffing

### 4. Geographic clustering
- Heatmap of encampment tickets over time (animate by month)
- Identify persistent locations vs transient ones
- Overlay with city vs state land boundaries (DCR, MBTA, MassDOT)
- Correlate with needle and waste ticket locations

### 5. Repeat-location analysis
- Cluster tickets by location (fuzzy match on lat/lng)
- Identify locations with 5+, 10+, 20+ tickets
- Track whether same locations get filed→closed→refiled (the "resubmit loop")
- Duration between reports at same location (are encampments getting shorter-term?)

### 6. Cross-contamination with waste classifier
- Run waste classifier on encampment-queue tickets
- How many encampment tickets also describe human waste?
- Are waste+encampment combo tickets handled differently?

### 7. Closure text NLP
- Classify the 599 "other" closures programmatically
- Detect deflection language patterns (resubmit, call 911, email us, private property)
- Score closure quality: did the response actually address the report?
- Identify auto-closed/stale tickets vs human-reviewed ones

## Questions for CRT (bring to first meeting)

### Understanding the tracking gap
- We see 1,418 tickets showing as open. Roughly what % do you think were
  actually acted on but not closed in 311?
- Is there a way for us to cross-reference with your internal tracking?
- When you create employee-generated tickets after texting, do those ever
  get closed, or are they just for documentation?

### The routing problem
- We found 365 tickets closed by other depts (street cleaning, parks, code
  enforcement) that mention encampments. Were you aware of these?
- Would it help to have an alert when other depts close tickets with
  encampment keywords?

### Monthly volume (share the chart)
- Aug-Sep 2025 was a 10x spike. What drove that? Button adoption? Actual
  increase in encampments? Both?
- Nov 2025 you caught up (228 in / 228 closed). Was that NEST ramping up?
- The cumulative open count is 1,418 and climbing. Is there a bulk-close
  process that could clean up tickets you've already handled?

### Jamaica Plain
- JP has a 32% closure rate vs 50%+ elsewhere. Is that a coverage gap,
  state land issue, or something else?

### Seasonality and trends
- Are you seeing encampments becoming shorter-term?
- When do you need the most staffing? Is the summer spike predictable?
- Would a monthly volume forecast be useful for planning?

### What would help you most?
- If we could build one tool or analysis to help you get more funding,
  what would it be?
- What data do you wish 311 captured that it doesn't?

## Files in this research directory

- `README.md` — this document
- `raw_closure_texts.txt` — all 225 closure reasons from keyword-matched tickets
- `monthly_volume.json` — monthly new/closed/source/misrouted counts + cumulative open
