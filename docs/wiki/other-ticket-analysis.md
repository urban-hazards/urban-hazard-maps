# The "Other" Ticket Black Hole

> 142,946 General Request tickets exist only in the Open311 API, invisible in CKAN.
> Last updated: 2026-04-11

## Discovery

The CKAN bulk data export on data.boston.gov **completely excludes** tickets with
type "General Request" (`Mayor's 24 Hour Hotline:General Request:General Request`).
These are the catch-all "Other" bucket — when a citizen's issue doesn't fit a
predefined category, or when a category is selected but the ticket isn't
reclassified.

**142,946 tickets** from Jan 2023 to Apr 2026 exist only in the Open311 API.

## What's Hiding in "Other"

Sampling shows these tickets contain misrouted reports that were never
reclassified to their correct type:

| Hidden category | Est. count | Evidence |
|---|---|---|
| Encampment reports | ~9,200 | Description mentions tents, encampments |
| Waste/biohazard | ~2,400 | Description mentions feces, needles, biohazard |
| Rodent reports | ~700 | Structured form fields from app (Rat bites: No, etc.) |
| Noise complaints | Unknown | Not yet studied |
| Other misroutes | Unknown | Bulk of the 142k |

## Why They're Invisible

1. CKAN exports filter by specific `type` values — "General Request" isn't included
2. No one queries the Open311 API for this code because `/services.json` doesn't list it
3. The scraper fetches these under the `other` slug using the colon-delimited code

## The Rodent Routing Failure

~700 rodent reports are trapped in "Other" because the app's `input.Rodent Sighting`
button failed to reclassify them to `Rodent Activity`. These tickets still have
structured form fields (`Rat bites: [No] Rats in the house: [No]`) serialized
into the description — **proving they came through the app form** but the backend
routing failed.

This is a systemic bug: the app collected structured data, but the reclassification
step dropped it into the generic bucket.

## Implications for This Project

- **Needle/waste counts are undercounted** — some reports are trapped in "Other"
- **The scraper's `other` slug** fetches these tickets so we have the data
- **NLP classification** could recover misrouted tickets by scanning descriptions
- **Geographic analysis** of "Other" tickets could reveal neighborhood-level
  reporting gaps

## Future Work

- Run NLP classifier on "Other" descriptions to estimate true category breakdown
- Compare "Other" volume by neighborhood — are some areas worse at routing?
- Check if `?extensions=true` returns structured form fields for the ~700 rodent
  tickets (would definitively prove app routing failure)
- Track "Other" volume over time — is the routing improving or degrading?
