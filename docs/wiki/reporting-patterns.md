# Reporting Patterns: When and How Citizens Report

> Analysis of 10,737 Needle Pickup tickets from 2024.
> Last updated: 2026-04-11

## Peak Hour: 12 AM is Real

The peak reporting hour for needle tickets is **12 AM Eastern**. This is
verified real — not a data artifact.

- Zero records have fake `T00:00:00` timestamps across all years (2015-2024)
- CKAN timestamps are real UTC times; pipeline correctly converts to Eastern
- Distribution shows smooth overnight curve: 9PM→12AM→3AM, not a spike

## Reporting Time vs Activity Time

**Ticket timestamps measure when people REPORT, not when the activity occurs.**

The 12 AM peak means many Bostonians are out at midnight and see needles.
Actual needle use likely peaks earlier (afternoon-evening), but reporting lags.
Someone walks past needles on their morning commute and files at 8 AM for
something left at 2 AM.

The site should make clear that hourly charts show *reporting patterns*, not
*activity patterns*.

## Source Breakdown

| Source | Count | % |
|---|---|---|
| Citizens Connect App | 8,667 | 80% |
| Constituent Call | 2,064 | 19% |
| Employee Generated | 5 | 0.05% |
| City Worker App | 1 | 0.01% |

## Midnight Cluster Analysis

137 days in 2024 had 5+ tickets filed within 30 minutes. Initial hypothesis:
professional sweep crews logging via the app.

**Disproved by geographic analysis:** Most clusters span 2-5 miles across
multiple neighborhoods (requiring 5-22 mph). These are **multiple independent
citizens** reporting around the same time, not one person walking a route.

| Cluster type | Count | Evidence |
|---|---|---|
| Multi-person (spread > 1.5 mi) | 18 of top 25 | Physically impossible for one walker |
| Ambiguous (0.3-1.4 mi) | 7 of top 25 | Could be one person, could be several |
| Tight sweep (< 0.3 mi) | 0 of top 25 | None found in top clusters |

**The "Citizens Connect App" source label is reliable for needle tickets.**
The midnight peak is genuine independent citizen reporting.

## Submitter Data (PII — do not store)

The Open311 API with `?extensions=true` exposes `first_name`, `last_name`,
`email` in `extended_attributes`. This could definitively confirm cluster
independence but is PII we must not store or publish. Available for one-time
analysis only.

## Future Investigation

- Constituent Call hour patterns — do phone reports follow business hours?
- "Employee Generated" tickets (n=5) — what are these?
- Per-type reporting patterns — do encampment reports have different hour curves?
- Repeat reporters — does the `token` field allow anonymous tracking?
