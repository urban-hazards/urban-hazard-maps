# Shared contract between pipeline and frontend (v3) — both agents implement exactly this

## metadata/source_health.json, schema_version = 2
```
{
  "generated": "...", "schema_version": 2,
  "sources": {
    "<key>": { "through": "YYYY-MM-DD"|"", "last_30d": int, "prior_year_30d": int,
               "ratio": float|null, "status": "ok"|"degraded"|"stale", "coverage": bool }
  },
  "layers": {
    "<layer>": {
      "status": "ok"|"degraded"|"stale",      # computed over coverage sources ONLY
      "through": "YYYY-MM-DD"|"",            # max through over coverage sources (unchanged meaning)
      "latest_report": "YYYY-MM-DD"|"",      # max through over ALL sources
      "disrupted_since": "YYYY-MM-DD"|null,  # day after `through` when status != "ok", else null
      "sources": [...all source keys...],
      "coverage_sources": [...subset with coverage=true...]
    }
  },
  ... existing keys unchanged
}
```
Layer keys: "needles", "encampments", "waste". Frontend labels: Sharps, Encampments, Human Waste.

## Frontend rendering (DataFreshness chip)
- schema_version >= 2 and layer.status == "ok": `Sharps: data through Sep 9, 2026`
- schema_version >= 2 and layer.status != "ok":
  `Encampments: latest report Jun 22, 2026 · reporting disrupted since May 28`
  (if latest_report is empty, fall back to through; if disrupted_since is null, omit the
  " · reporting disrupted since …" part and render `latest report <date>`)
- schema_version missing or < 2 (old health file): legacy form `<Label>: data through <through>`
- health null → frozen fallback: render the not-ok form using frozen date as both through and
  latest_report, disrupted_since = frozen date + 1 day.
- Notice (when any layer not ok), one sentence per troubled layer, generated:
  "Boston moved its 311 system to a new platform in 2026. <Label> reporting has been disrupted
  since <disrupted_since>; reports that still arrive are shown, but low counts after that date
  reflect missing data, not fewer <plural noun>." plural nouns: needles→"sharps reports",
  encampments→"encampments", waste→"waste reports". Keep the existing "What changed" link.
  If disrupted_since is unknown (legacy schema), fall back to the existing notice text.
- Dates formatted "Mon D, YYYY" via the existing fmt() (local noon trick).

## HeatMap prop
`disruptions: Record<string, { since: string; latest: string }>` keyed by layer key, only for
layers with status != "ok" and non-null disrupted_since. Built in index.astro from health.
When the active data layer (sharps → "needles", encampments → "encampments", waste → "waste";
"both" → show for whichever of needles/encampments is disrupted) has an entry and the selected
year-month is >= the year-month of `since`, append to that layer's count line:
` · reporting disrupted since May 28` (date "Mon D"). Selected "all months"/"all years" → no note.

## Amendment 2026-09-23 (after live-data check)
`disrupted_since` is set only when the layer is **stale**. A **degraded** layer (reports still arrive at reduced volume) keeps the `data through` chip with the suffix " · reporting volume down" and gets the notice sentence "<Subject> reporting volume has dropped sharply since the switch; recent months may be incomplete."

## Reconciliation 2026-09-23 (GLM code review item 6)
The notice sentence subject is the singular form from `NOTICE_SUBJECT` (Sharps / Encampment / Human waste), not the chip `<Label>`. A schema-2 troubled layer with no `disrupted_since` (stale, nothing on record) gets "<Subject> reporting is disrupted; recent months may be incomplete." The legacy notice text is used only for schema < 2.
