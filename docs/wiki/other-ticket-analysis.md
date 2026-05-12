# The "Other" Ticket Black Hole

> 142,946 General Request tickets exist only in the Open311 API, invisible in CKAN.
> Last updated: 2026-04-25

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

## Reclassification Behavior (verified 2026-04-25)

When staff reclassify an "Other" ticket to a specific type (e.g., Human Waste),
the ticket **stays in the Other corpus** with `service_name: "Other"` unchanged.
The reclassification is visible only in the `description` field as staff-appended
text like `| Case (SR) Type: [Human Waste]  Referred To: [HUMAN WASTE]`.

Key findings from checking 10 known reclassified waste IDs (issue #57 §4b):

1. **`service_name` / `service_code` never change** — they remain "Other" / "General Request"
2. **Records don't drop out** — each appears in exactly 1 day-file (the day filed)
3. **Reclassified tickets never appear in CKAN** — checked 5 IDs via direct CKAN
   API query, zero results. They are permanently invisible to the bulk export.
4. **ID namespace matches** — Open311 `service_request_id` uses the same 12-digit
   `10100x` format as CKAN `case_enquiry_id`. Dedupe by ID is safe.

This means for pipeline ingestion:
- The Other corpus is the **only source** for these tickets
- CKAN-based dedupe is a safety net, not functionally necessary
- The `[Human Waste]` tag in descriptions provides an additional classification
  signal beyond the NLP classifier

## Future Work

- ~~Run NLP classifier on "Other" descriptions to estimate true category breakdown~~ **Done for waste** (issue #57, 2,433 waste reports recovered)
- Compare "Other" volume by neighborhood — are some areas worse at routing?
- Check if `?extensions=true` returns structured form fields for the ~700 rodent
  tickets (would definitively prove app routing failure)
- Track "Other" volume over time — is the routing improving or degrading?
- Ingest encampment reclassifications from Other (6,533 tickets — issue #84 subtask 3)
