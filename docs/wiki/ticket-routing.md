# Ticket Routing: How 311 Categories Actually Work

> Last updated: 2026-04-11

## Litter: There Is No "Litter" Category

The word "litter" in 311 jargon almost exclusively means **litter baskets**
(public trash cans), not litter on the ground.

- "Empty Litter Basket" (2,560/yr) = "this city trash can is full"
- "Litter Basket Maintenance" (80/yr) = "this trash can is damaged"
- "Request for Litter Basket Installation" (105/yr) = "we need a trash can here"

**Ground litter has no dedicated category.** It scatters across:

| Type | 2024 Count | What it really is |
|---|---|---|
| Requests for Street Cleaning | 22,539 | Catch-all: "the street is dirty" |
| Improper Storage of Trash | 20,432 | Residential code violations |
| Ground Maintenance | 3,902 | Parks dept — litter in green spaces |
| Illegal Dumping | 2,997 | Bulk/deliberate, 96% phone calls, no app button |
| Empty Litter Basket | 2,560 | Overflowing public trash cans |

The app's "Litter" button (`input.Litter`) probably routes to "Requests for
Street Cleaning." If true, app-submitted litter reports are indistinguishable
from all other street cleaning requests without reading the description text.

**Future work:** NLP classifier on descriptions to separate real litter reports
from other street cleaning complaints, similar to the human waste classifier.

## Overflowing Trash Can: Still a Mystery

`input.Overflowing Trash Can` maps to... unclear. Candidates:
- `Empty Litter Basket` (2,560/yr) — most likely, same concept
- `Overflowing or Un-kept Dumpster` (95/yr) — low volume, Inspectional Services
- `Requests for Street Cleaning` — possible catch-all

## Graffiti: Two Departments

- `Property Management:Graffiti:Graffiti Removal` — 2,501/yr
- `Public Works Department:Highway Maintenance:PWD Graffiti` — 1,305/yr

Both scraped under separate slugs (`graffiti`, `graffiti-pwd`). Need to study
whether they serve different areas, have different response times, or handle
different types of graffiti.

## Structured Form Data in Reclassified Tickets

When a citizen submits through an `input.*` app form, the backend serializes
the form responses into the `description` field of the reclassified ticket.
For example, Rodent Activity descriptions contain: `"Rat bites: [No] Rats in
the house: [No] Rats outside of property: [Yes]"`.

This means:
1. Reclassification preserves the original form data
2. Structured fields are parseable from descriptions
3. Presence of structured form data = ticket came through the app

## The Street Cleaning Catch-All

"Requests for Street Cleaning" (22,539/yr) absorbs everything. Queue routing:

| Queue | Count | What it suggests |
|---|---|---|
| PWDx district queues (12) | ~18,000+ | Standard street cleaning |
| PWDx_Missed Trash\Recycling | 648 | Missed collection re-routed here |
| INFO_Reallocation From Dept | 432 | Bounced from other depts |
| INFO_Mass DCR | 326 | State land — referred out |
| INFO_Encampments | 163 | Encampment reports mistyped |
| INFO_MBTA | 242 | Transit property |
| INFO_HumanWaste | 45 | Waste reports mistyped |
| GEN_Needle_Pickup | 31 | Needle reports mistyped |
