# Encampment intake ended in May 2026

> Source of truth for the site's encampment migration caveat. Findings checked
> September 2–6, 2026 against legacy CKAN, Open311, and the Creatio service list.
> These are intake/coverage findings, not a count of people or encampments.

## Evidence

The dedicated legacy `Encampments` type ends May 27, 2026; the last Open311
request is also May 27. Monthly legacy type counts in 2026 were:

| Month | Requests |
|---|---:|
| January | 59 |
| February | 73 |
| March | 146 |
| April | 196 |
| May | 296 |

These counts concern the named type, not the broader historical INFO queue
series that the pipeline also ingests. Earlier migration notes described the
cutoff loosely as June / no cases after June; May 27 is the precise last-request
date established by the follow-up checks.

We checked the following paths:

- Legacy yearly CKAN records, filtering `type = Encampments`, including the
  2026 resource in `pipeline.config.RESOURCE_IDS`.
- The legacy encampment Open311 feed on both `311.boston.gov` and
  `boston2-production.spotmobile.net`: no requests since June 1, 2026.
  The scraper uses `Mayor's 24 Hour Hotline:Quality of Life:Encampments`.
  The migration audit also checked the encampment UUID code beginning
  `8638e79a-`; a UUID by itself does not prove a code belongs to Creatio.
- The Creatio CKAN resource `254adca6-64ab-4c5c-9fc0-a6da622be185` and
  new-system Open311 UUID service codes in the
  [observed code table](creatio-open311-codes.json): no dedicated encampment topic.
  `/services.json` alone is insufficient because it omits new-system codes.
- An August 2026 description sample across **all new-system codes**: approximately
  7 encampment-language reports among 1,500 sampled requests. This is a sampled
  text finding, not an exhaustive monthly count or a validated classifier.
- Other and Litter & Debris resident-text scans: the Other corpus had roughly
  30 encampment mentions per month until June; Litter & Debris had roughly
  30 per month since July. These mentions show scattered reporting through
  other categories, not continuity with the dedicated intake series.

Sources and reproduction context: the [migration plan](../plans/2026-09-02-creatio-migration-plan.md),
[data-quality issue 13](data-quality-issues.md#13-system-transition-data-fracture-oct-2025),
[Open311 API reference](open311-api-reference.md), and scraper `SERVICE_TYPES`
in `services/open311-scraper/fetch.py`. Public entry points are
[Boston's 311 dataset](https://data.boston.gov/dataset/311-service-requests)
and [Open311 requests](https://311.boston.gov/open311/v2/requests.json).
The approximate text-scan findings above are the September follow-up audit
observations; the repository does not contain a complete labeled census.

## What this means for the site

Treat the dedicated encampment intake as removed until a replacement is verified.
Keep the historical layer frozen at its last complete coverage date, with a
visible caveat. A flat or empty series after the cutoff must not be presented
as a decline in encampments or homelessness.

Do not splice keyword mentions from Other or Litter & Debris into the historical
type/queue series. The input population and reporting route changed, and the
scattered mentions are not a validated successor. Reopening the layer requires
an identified intake route, verified coverage and a documented method break.
Continue monitoring new service names using the source-health monitor.
