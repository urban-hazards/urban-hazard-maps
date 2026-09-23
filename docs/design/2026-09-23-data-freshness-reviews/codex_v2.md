P2 still claims completeness without evidence. I would remove that claim before implementing v2.

1. **P2’s heuristic is not a completeness rule.** A month missing 75% of expected reports can pass. After six collapsed months, the median collapses too; with a zero median, any later trickle passes. One recovered month also moves the boundary past earlier gaps, incorrectly implying continuous coverage. Current partial months, seasonality, insufficient history, duplicates, and backfills add further failure modes.

   “Last day with a row” cannot establish the last covered day: an empty day might be fully observed. May’s 305 reports do not prove coverage through May 27.

   Use `latest_report` plus explicit coverage state—disrupted, unknown, or verified restored—with supporting evidence. Volume anomalies can inform that state, but should not produce a field named `complete_through`.

2. **P5’s five-report floor does not solve the status problem.** With the supplied Open311 prior-year count of 10, five recent reports yield ratio 0.5 and therefore `ok`. A source with no baseline also becomes `ok` at five. The same misleading notice disappearance remains, just at a higher threshold.

   The supplied information cannot establish whether healthy sources sometimes have fewer than five reports; that requires examining their histories. More fundamentally, any-ok aggregation assumes each source independently provides adequate coverage. A healthy complementary queue cannot establish that the missing type feed has been replaced. Separate source activity from layer coverage, and gate the coverage notice on the latter.

3. **P3’s wording repeats the unsupported promise.** “Complete through” and “normal volume” overstate what a 25% threshold establishes. Equality of dates also does not mean healthy: both dates can be old, missing, or derived from incomplete inputs.

   Suggested chip: **“Encampments: latest report Jun 22, 2026 · reporting disrupted.”**

   Suggested notice: **“Encampment reporting is disrupted. Available reports are shown, but low counts may reflect missing data.”**

   Keep the dedicated type’s May 27 last-report date in source details. Do not attribute every future stale source to the migration without evidence.

4. **P4’s local warning is necessary.** Users interpreting “3 encampments” need the qualification beside that number; a distant chip is insufficient. Prefer **“3 reports · reporting incomplete.”**

   Pass coverage state and affected periods, not merely two dates. Define month overlap explicitly: if coverage ends May 27, May itself contains potentially uncovered days. A month-only comparison that starts warnings in June misses this. Recovery can leave historical gaps, so one moving cutoff is insufficient.

5. **P1 partitions the cached population, not the acquisition routes.** `type != "Encampments"` identifies queue-only residual rows under the stated fetcher invariant. Rows matching both selectors go into the type partition, so the “queue” source does not measure the entire queue feed. Its counts could disappear because classifications changed, without queue acquisition failing.

   A renamed Creatio service is outside this legacy-file partition. Recovery requires explicit ingestion, classification, map inclusion, and health mapping for the successor. Neither the complementary predicate nor name discovery establishes that automatically.

6. **P2/P7 do not specify safe compatibility.** Adding fields while changing `through` from latest observed date to inferred completeness changes its meaning. Define explicit handling for both schemas, missing layers, null dates, and unavailable health; missing completeness must remain unknown.

   P7’s claim that old health necessarily contains May 27 is unsafe: the committed v1 can generate June 22. A new frontend must not reinterpret that v1 `through` as a completeness boundary. Test both deployment orders using both old-health variants. Also specify frontend deployment and how independently published/cached points and health remain consistent.

7. **P6 cannot validate the proposed behavior as written.** The two-row fixture provides no six-month baseline. Treating absent months as zeros makes June pass against a zero median; treating them as unknown leaves no justified May boundary. P5 changes layer eligibility, while its test expects the source itself to become non-ok—resolve that inconsistency.

   Add cases for five-row recovery, zero/missing baselines, prolonged collapse, partial months, historical gaps, invalid coordinates, and duplicate cases across sources. Define whether layer dates describe raw reports or rendered points; summing source counts is not a deduplicated union.

   The year-window issue becomes part of P2: on January 30, 2027, a June 2026 baseline needs December 2025, already excluded. Historical coverage cannot depend on the current rolling-window file set.

