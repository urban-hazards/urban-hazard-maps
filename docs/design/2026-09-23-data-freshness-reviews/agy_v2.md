Here is an adversarial review of your revised plan v2.

### 1. Is the P2 completeness heuristic sound?
Absolutely not. It has catastrophic failure modes:
*   **The Gap Flaw (Missing recovery):** The algorithm walks backward from `latest` and stops at the *first* month that passes. If the feed dies in June, stays dead all summer, and is fixed in September, September's volume will pass the 25% check. `complete_through` will become September. The total blackout of June–August is silently hidden from the user, completely defeating the purpose of measuring completeness.
*   **Start-of-month flip-flopping:** On the 1st of a perfectly healthy month, the current month's volume will naturally be `< 25%` of the 6-month median. The heuristic will flag the current month as collapsed and violently drop `complete_through` back to the previous month. It will then unpredictably snap back to the current date mid-month once enough reports accumulate.
*   **Seasonality:** A valid seasonal dip `>75%` (e.g., winter) will erroneously trigger the collapse logic and permanently freeze the banner date for months.

### 2. Is MIN_OK_VOLUME = 5 defensible?
No. It is a magic number. While it masks the trickle bug for high-volume layers, it will permanently label legitimate, low-volume feeds as `stale` if they naturally average 2-4 reports a month. You should fix the trickle bug by enforcing a minimum `ratio` against the prior year's 30-day window, rather than hardcoding an absolute volume floor.

### 3. P3 Wording:
It is overly verbose and confusing. `complete through May 27 · last report Jun 22` forces the reader to mentally decipher the gap. The proposed notice text ("For those layers we mark the last month with normal volume...") reads like an internal PR description of your backend heuristic, not actionable information for a resident. Keep the UI simple and direct: "Data incomplete after May 27."

### 4. P4 Map plumbing:
Do not pass the entire `health.layers` object into the HeatMap island; it unnecessarily bloats the client payload. Furthermore, "reporting collapsed after May 27" is alarmist jargon. If a user selects an incomplete month, a simple "Data may be incomplete" string driven by a minimal date prop is sufficient.

### 5. P1 Partition and Creatio Reappearance:
Your P1 partition strictly splits `ckan_legacy`. If the type reappears in Creatio under a new name, it will flow into the `ckan_creatio` or `open311` fetchers. The P1 partition won't break, but the new data will be completely ignored until you manually update `LAYER_SOURCES["encampments"]` to explicitly include the new Creatio source. 

### 6. Ordering/Compat Risk:
If the frontend deploys first, the new UI will expect `latest` and `complete_through` keys. The old JSON won't have them. Your Astro components will render `undefined` or crash if you do not implement explicit fallbacks for missing keys.

### 7. What is still missing / Other flaws:
*   **Implementation gap in P1:** You propose a complementary predicate (`type != "Encampments"`) for the queue source, but `_legacy_days()` and the `SOURCES` mapping are strictly hardcoded for equality matching (`_days_from_rows(rows, "type", type_name)`). You cannot implement P1 without refactoring the pipeline's source selector schema to support exclusions, which is non-trivial and omitted from the plan.
*   **The fundamental approach:** You are building an unreliable statistical heuristic to detect a known, deterministic event (a system migration). The pipeline already knows the migration happened in mid-2026. Hardcode the end-of-life dates for dead legacy feeds (like `2026-05-27` for legacy encampments). Trying to auto-detect feed death using a 25% median heuristic will create an endless game of whack-a-mole with edge cases.
