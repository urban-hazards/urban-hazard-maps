# SHARPS Team Analysis

> Derived from 10,737 Needle Pickup closure notes in 2024.
> Last updated: 2026-04-11

## Workers Identified

Six SHARPS workers identified by initials in closure notes:

| Worker | Closures | Schedule | Peak Hours (ET) | Syringes Parsed |
|--------|----------|----------|-----------------|-----------------|
| JT | 2,480 | Mon-Fri, light weekends | 11PM-1AM | — (text format) |
| CD | 1,900 | Mon-Fri only (3 Sat, 19 Sun) | 5-6AM, 11AM | — (text format) |
| DW | 1,877 | Tue-Thu heavy | 11PM-3AM | 4,418 (avg 2.4) |
| JG | 1,401 | Heavy Sunday, light Friday | 5-6AM, 10AM | 1,525 (avg 2.2) |
| DF | 1,391 | Sat-Sun-Mon heavy | 11PM-1AM | — (text format) |
| DT | 750 | — | — | 5,913 (avg 7.9!) |

## Two Shift Patterns

- **Overnight shift** (JT, DW, DF): 11PM-3AM closures
- **Early morning shift** (CD, JG): 5-6AM, 10-11AM closures
- DT handles heavy pickups at ~4x the average count per ticket

## Closure Note Formats

Workers each have their own shorthand:

| Format | Example | Worker |
|---|---|---|
| Count + initials | `6dw`, `13dt` | DW, DT, DP |
| Text + terminal initials | `Needle recovered. JT.` | JT, CD |
| "recovered by" + initials | `1 syringe recovered by jg` | JG |
| Just initials | `Df.` | DF |
| Initials pair | `Recovered. CD RA` | Teams |

## NLP Opportunity: Syringe Count Parsing

Closure notes contain real syringe pickup counts. Parseable formats:
- `[N]dw`, `[N]dt`, `[N]jg` — count + worker initials
- `[N] syringe(s) recovered by [initials]`
- `[N] syringes [N2]dt recovered by [initials]` — mixed paraphernalia

From parsed counts alone (2024): **13,058 syringes** from 3,523 tickets with
parseable counts. True total is higher — JT and CD close the most tickets but
use text format without explicit counts.

## Workflow

1. **Citizens report via app** (80%) or phone (19%) — real-time
2. **SHARPS crew responds** — overnight or early morning shift
3. **Crew logs closure** with syringe count + worker initials
4. SHARPS does NOT create tickets — they only close citizen-created ones
   (only 5 "Employee Generated" tickets in all of 2024)

## High-Count Tickets (20+ syringes)

- 10 tickets in 2024 with 20+ syringes (max: 100)
- 6/10 on Mondays — weekend accumulation
- Locations: Mass Ave, Shawmut, Worcester St (South End), Albany St (BMC area)
- Source: 8/10 Citizens Connect App, 2/10 phone calls
