# Creatio Migration Build — Implementation Plan (rev 2, post-audit)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-feed the pipeline and site through Boston 311's Lagan→Creatio migration so no layer goes silently dark, and correct the /mattress page for the split.

**Architecture:** The Open311 endpoint already serves Creatio cases under UUID service codes with resident descriptions, so the scraper gains new slugs and the waste classifier gains Litter & Debris resident text as input. The pipeline gains a Creatio CKAN reader (counts only, staff text never classified), a deterministic fingerprint module used for coverage QA, and a per-source daily health file; the frontend shows per-layer freshness, a migration notice, and a static freeze for encampments. Nothing in the daily path calls an LLM.

**Tech Stack:** Python 3.12 / uv / pydantic v2 / boto3 / pytest+moto (pipeline); Python stdlib + boto3 (scraper); Astro 6 + React 19 + TypeScript + Biome (frontend).

**Spec:** `docs/plans/2026-09-02-creatio-migration-plan.md` and GitHub issues #134–#142. Paths below are monorepo paths.

## Global Constraints

- Implementers: run `uv run ruff format src/ tests/` after pasting any snippet; the plan's code is wrapped for readability, not guaranteed ≤120 chars.
- Pipeline: `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, `uv run mypy src/` (strict), `uv run pytest` must pass. Line length 120 — wrap long literals.
- Frontend: tabs, no semicolons, double quotes; `pnpm check` must pass; run `pnpm exec biome format --write src/` before commit.
- Any new key the frontend reads from S3 JSON gets a defensive default; `EMPTY_PAGE_STATS` in `frontend/src/lib/bucket.ts` stays in sync with `PageStats`.
- Timestamps: bucket by `America/New_York` via `pipeline.cleaner._parse_datetime` (handles naive-UTC legacy strings and `+00` Creatio strings; verified).
- No shared ID namespace between legacy (`101…`), Creatio CKAN (`BCS-…`) and Creatio Open311 (UUID). Never dedupe across systems by ID.
- Creatio `closure_comments` is staff text. It is stored under its own key and is never given to the waste classifier or counted as a resident description.
- Only Open311 rows (resident text) enter the classifier. Creatio CKAN rows are for counts and coverage QA only.
- PRs, not pushes to main; pipeline PRs tag scottfrasso. Scraper, pipeline and frontend are separate Railway services → separate PRs.
- Running the pipeline or scraper locally with `pipeline/.env` writes to the PROD bucket. Only run the scraper for the new slugs (additive keys); never `--force` the pipeline locally.

## Verified facts the code relies on

- Creatio Open311 UUID codes (`docs/wiki/creatio-open311-codes.json`): Litter & Debris `155a5e9b-8c3a-4279-bbab-f6bba6ddb0d0`; Park Litter & Debris `4278d986-8b62-4a2b-a43d-575e031b8f50`; Improper Trash Storage `acb41f11-e581-42bc-a0a5-877cb3a07747`; Illegal Dumping or Disposal `60b145be-aef5-4a3c-8754-51472cf44088`; Trash Placed Out Early `8a0698b8-9f00-4977-b907-aae2553aa2d3`; Overflowing Trash `c8e719d6-06ce-4375-813d-dccb3ca66402`; Missed Waste Pick-up `994a8200-95d6-4720-826c-19bd142847b5`; Code Enforcement Collection `cb65b3ee-ab13-4c3c-8f3b-ffc743f99c94`; Student Move-In (Trash Collection) `715f7134-aac4-43f4-9e8b-b6fff5f47ad3`. `?service_code=<uuid>&start_date=…` works; none return rows before 2026-06.
- Creatio CKAN resource `254adca6-64ab-4c5c-9fc0-a6da622be185`; `datastore_search` with `filters={"service_name": …}` + `limit/offset` works and returns `total`. Do not use `datastore_search_sql` (WAF).
- `analytics.compute_stats` caps `markers` at the 3,000 most recent (analytics.py:160) — never count from `markers.json`. Uncapped raw rows are cached by `run._fetch_dataset_years` at `raw/{dataset}_{year}.json` (encampments: `raw/encampments_v2_{year}.json`).
- `open311_loader.normalize_open311_record` sets `type` = Open311 `service_name` (loader:126), so Creatio-fed rows carry names like `Litter & Debris`, not legacy types.
- `run._process_waste` writes `page_stats: dict[str, Any]` (run.py ~397) to `waste/stats.json` (~426). `tests/test_waste_merge.py` has `_make_fake_classifier(waste_ids)` and patches `pipeline.run.WasteClassifier`.
- Scraper `fetch_type(s3, slug, service_code, name, start, end, delay, dry_run)` scans `days_needed` newest→oldest (fetch.py:300) with a 90-consecutive-empty-day bailout; `main()` loops `for slug, (service_code, name) in types_to_fetch.items()` (fetch.py:606) and verify mode calls `_verify_type` (~527). `START_DATE = "2023-01-01"`; `from datetime import date, datetime, timedelta` present.
- Legacy encampment feed last request 2026-05-27; no Creatio encampment topic; legacy Street Cleaning Open311 returns 0 since 2026-07-01.

## File map

| File | Responsibility |
|---|---|
| `services/open311-scraper/fetch.py` | Creatio UUID slugs, per-slug start clamp in `fetch_type` and verify |
| `services/open311-scraper/test_service_types.py` | (new) slug table + clamp tests |
| `pipeline/src/pipeline/config.py` | Creatio resource id, service map, waste-input slugs |
| `pipeline/src/pipeline/creatio.py` | (new) `fetch_creatio_records`, `normalize_creatio_record`, `monthly_counts` |
| `pipeline/src/pipeline/dedupe.py` | (new) `fingerprint`, `match_cross_system` (coverage QA) |
| `pipeline/src/pipeline/health.py` | (new) per-source counts → `metadata/source_health.json` |
| `pipeline/src/pipeline/run.py` | waste inputs, Creatio counts + coverage QA, health call, `schema_version` |
| `pipeline/tests/test_creatio.py`, `test_dedupe.py`, `test_health.py`, `test_waste_merge.py` | tests |
| `frontend/src/lib/types.ts`, `bucket.ts` | `SourceHealth`, `fetchSourceHealth` |
| `frontend/src/components/DataFreshness.astro` | (new) chips, notice, static freeze |
| `frontend/src/pages/index.astro`, `mattress.astro` | render / caveat |
| `scripts/mattress_analysis.py` | Creatio slugs + Creatio CKAN monthly via paged reads |

Execution order: Task 6 (public caveat, no data dependency) → Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 7 → Task 8.

---

### Task 1: Scraper — Creatio UUID slugs with per-slug start clamp (#136)

**Files:**
- Modify: `services/open311-scraper/fetch.py`
- Create: `services/open311-scraper/test_service_types.py`

**Interfaces:**
- Produces: `SERVICE_TYPES` gains 9 slugs; `CREATIO_START = date(2026, 6, 1)`; `SLUG_START: dict[str, date]`; `slug_start(slug: str) -> date`. `fetch_type` and verify mode clamp `start = max(start, slug_start(slug))`.

- [ ] **Step 1: Write the failing tests**

```python
# services/open311-scraper/test_service_types.py
import re
from datetime import date
from unittest.mock import MagicMock, patch

import fetch

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NEW = {
    "litter-debris": "155a5e9b-8c3a-4279-bbab-f6bba6ddb0d0",
    "park-litter-debris": "4278d986-8b62-4a2b-a43d-575e031b8f50",
    "improper-trash-storage": "acb41f11-e581-42bc-a0a5-877cb3a07747",
    "illegal-dumping": "60b145be-aef5-4a3c-8754-51472cf44088",
    "trash-out-early": "8a0698b8-9f00-4977-b907-aae2553aa2d3",
    "overflowing-trash": "c8e719d6-06ce-4375-813d-dccb3ca66402",
    "missed-waste": "994a8200-95d6-4720-826c-19bd142847b5",
    "ce-collection": "cb65b3ee-ab13-4c3c-8f3b-ffc743f99c94",
    "student-move-in": "715f7134-aac4-43f4-9e8b-b6fff5f47ad3",
}


def test_creatio_slugs_present_with_uuid_codes():
    for slug, code in NEW.items():
        assert fetch.SERVICE_TYPES[slug][0] == code
        assert UUID.match(code)


def test_slug_start_table():
    for slug in NEW:
        assert fetch.slug_start(slug) == date(2026, 6, 1)
    assert fetch.slug_start("needles") == date.fromisoformat(fetch.START_DATE)


def test_fetch_type_clamps_start_to_slug_start():
    s3 = MagicMock()
    with patch("fetch.list_existing_days", return_value=set()) as listing:
        result = fetch.fetch_type(s3, "litter-debris", NEW["litter-debris"], "Litter & Debris",
                                  date(2023, 1, 1), date(2026, 6, 3), 0.0, True)
    assert listing.called
    assert result["slug"] == "litter-debris"
    # dry_run reports the plan: only days from 2026-06-01 onward are in scope
    assert result.get("days_needed", result.get("skipped", 0) + result.get("fetched", 0)) <= 3
```

- [ ] **Step 2: Run to verify failure**

Run: `cd services/open311-scraper && python3 -m pytest test_service_types.py -q`
Expected: FAIL (`KeyError: 'litter-debris'`, `AttributeError: slug_start`)

- [ ] **Step 3: Implement**

In `fetch.py`, append to `SERVICE_TYPES` (before its closing brace):

```python
    # --- Creatio (new 311 system). The Open311 endpoint accepts these UUIDs
    # as service_code but does not list them in /services.json. Discovered by
    # sweeping requests.json — see docs/wiki/creatio-open311-codes.json.
    "litter-debris": ("155a5e9b-8c3a-4279-bbab-f6bba6ddb0d0", "Litter & Debris"),
    "park-litter-debris": ("4278d986-8b62-4a2b-a43d-575e031b8f50", "Park Litter & Debris"),
    "improper-trash-storage": ("acb41f11-e581-42bc-a0a5-877cb3a07747", "Improper Trash Storage"),
    "illegal-dumping": ("60b145be-aef5-4a3c-8754-51472cf44088", "Illegal Dumping or Disposal"),
    "trash-out-early": ("8a0698b8-9f00-4977-b907-aae2553aa2d3", "Trash Placed Out Early"),
    "overflowing-trash": ("c8e719d6-06ce-4375-813d-dccb3ca66402", "Overflowing Trash"),
    "missed-waste": ("994a8200-95d6-4720-826c-19bd142847b5", "Missed Waste Pick-up"),
    "ce-collection": ("cb65b3ee-ab13-4c3c-8f3b-ffc743f99c94", "Code Enforcement Collection"),
    "student-move-in": ("715f7134-aac4-43f4-9e8b-b6fff5f47ad3", "Student Move-In (Trash Collection)"),
}

# Creatio codes have no cases before June 2026. The scanner walks newest→oldest
# and bails after 90 empty days, so without a clamp every run would burn ~90
# requests per slug re-discovering the pre-migration gap (and `--verify` would
# walk back to 2023). Clamp the scan window per slug instead.
CREATIO_START = date(2026, 6, 1)
SLUG_START: dict[str, date] = {
    slug: CREATIO_START
    for slug in (
        "litter-debris", "park-litter-debris", "improper-trash-storage", "illegal-dumping",
        "trash-out-early", "overflowing-trash", "missed-waste", "ce-collection", "student-move-in",
    )
}


def slug_start(slug: str) -> date:
    """Earliest date worth scanning for a slug (default: global START_DATE)."""
    return SLUG_START.get(slug, date.fromisoformat(START_DATE))
```

At the top of `fetch_type` body (first statement) and at the top of `_verify_type` body add:

```python
    start = max(start, slug_start(slug))
```

- [ ] **Step 4: Run tests**

Run: `cd services/open311-scraper && python3 -m pytest test_service_types.py -q`
Expected: 3 passed. (If `fetch_type`'s dry-run return lacks `days_needed`, adjust the third assertion to whatever key it returns for the planned count — read the function; do not change its behavior.)

- [ ] **Step 5: Live-run the new slugs (additive prod keys)**

```bash
cd services/open311-scraper && set -a && source ../../pipeline/.env && set +a
python3 fetch.py --type litter-debris --dry-run
for t in litter-debris park-litter-debris improper-trash-storage illegal-dumping; do python3 fetch.py --type $t; done
```
Expected: `open311/<slug>/2026-06-01.json` … yesterday. June–Aug Litter & Debris record total within ±5% of CKAN Creatio (Jun 519, Jul 2,418, Aug 3,062).

- [ ] **Step 6: Commit**

```bash
git add services/open311-scraper/fetch.py services/open311-scraper/test_service_types.py
git commit -m "feat(scraper): Creatio UUID service codes with per-slug start clamp (#136)"
```

---

### Task 2: Pipeline — Creatio CKAN reader, normalizer, monthly counts (#137, #139)

**Files:**
- Modify: `pipeline/src/pipeline/config.py`
- Create: `pipeline/src/pipeline/creatio.py`
- Create: `pipeline/tests/test_creatio.py`

**Interfaces:**
- Produces in config: `CREATIO_RESOURCE_ID`, `CREATIO_SERVICE_MAP: dict[str, str]`, `CREATIO_WASTE_SERVICE_NAMES: set[str]`, `CREATIO_START_DATE = date(2025, 8, 1)`; `SCRAPER_SLUGS_FOR_WASTE_INPUT = ["other", "litter-debris", "park-litter-debris"]`.
- Produces in creatio.py: `fetch_creatio_records(service_names: set[str], since: date, page_size: int = 5000) -> list[dict[str, Any]]`; `normalize_creatio_record(row) -> dict[str, Any]` (CKAN-shaped; `closure_reason` = reason only; `creatio_closure_comments` separate; `source_system="creatio"`); `monthly_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]` = `{legacy_type: {"YYYY-MM": n}}` bucketed in Boston time.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_creatio.py
from datetime import date
from typing import Any
from unittest.mock import patch

from pipeline.cleaner import clean
from pipeline.config import CREATIO_SERVICE_MAP
from pipeline.creatio import fetch_creatio_records, monthly_counts, normalize_creatio_record

ROW: dict[str, Any] = {
    "case_id": "BCS-00256693",
    "open_date": "2026-07-31 23:30:00+00",  # 7:30 PM Boston, still July
    "close_date": "2026-08-01 12:06:36+00",
    "case_topic": "Litter & Debris",
    "service_name": "Litter & Debris",
    "assigned_department": "Public Works Department (PWD)",
    "assigned_team": "PWD Highway (BEAM)",
    "case_status": "Closed",
    "closure_reason": "Resolved",
    "closure_comments": "Trash removed",
    "report_source": "BOS311",
    "full_address": "11-17 E Concord St, Boston, MA 02118",
    "street_name": "E Concord St",
    "zip_code": "02118",
    "neighborhood": "South End",
    "longitude": "-71.07473228",
    "latitude": "42.33768644",
}


def test_normalize_maps_to_ckan_shape_and_keeps_staff_text_separate():
    n = normalize_creatio_record(ROW)
    assert n["case_enquiry_id"] == "BCS-00256693"
    assert n["type"] == "Requests for Street Cleaning"
    assert n["creatio_service_name"] == "Litter & Debris"
    assert n["queue"] == "PWD Highway (BEAM)"
    assert n["source"] == "BOS311"
    assert n["closure_reason"] == "Resolved"
    assert n["creatio_closure_comments"] == "Trash removed"
    assert n["latitude"] == "42.33768644" and n["longitude"] == "-71.07473228"
    assert n["neighborhood"] == "South End" and n["location_street_name"] == "E Concord St"
    assert n["location_zipcode"] == "02118"
    assert n["source_system"] == "creatio"
    assert "open311_description" not in n


def test_none_comments_become_empty():
    assert normalize_creatio_record({**ROW, "closure_comments": "None"})["creatio_closure_comments"] == ""


def test_normalized_row_cleans_in_boston_local_time():
    rec = clean(normalize_creatio_record(ROW))
    assert rec is not None
    assert (rec.year, rec.month, rec.hour) == (2026, 7, 19)
    assert rec.resp_hrs == 12.6


def test_unmapped_service_name_passes_through():
    assert normalize_creatio_record({**ROW, "service_name": "Pothole"})["type"] == "Pothole"


def test_service_map_covers_spec_table():
    assert CREATIO_SERVICE_MAP["Litter & Debris"] == "Requests for Street Cleaning"
    assert CREATIO_SERVICE_MAP["Park Litter & Debris"] == "Requests for Street Cleaning"
    assert CREATIO_SERVICE_MAP["Improper Trash Storage"] == "Improper Storage of Trash (Barrels)"
    assert CREATIO_SERVICE_MAP["Illegal Dumping or Disposal"] == "Illegal Dumping"
    assert CREATIO_SERVICE_MAP["Missed Waste Pick-up"] == "Missed Trash/Recycling/Yard Waste/Bulk Item"
    assert CREATIO_SERVICE_MAP["Code Enforcement Collection"] == "CE Collection"


def test_monthly_counts_bucket_in_boston_time_by_legacy_type():
    rows = [
        normalize_creatio_record(ROW),  # July (Boston)
        normalize_creatio_record({**ROW, "case_id": "BCS-2", "open_date": "2026-08-01 03:59:00+00"}),  # still Jul 31 Boston
        normalize_creatio_record({**ROW, "case_id": "BCS-3", "service_name": "Illegal Dumping or Disposal"}),
    ]
    assert monthly_counts(rows) == {
        "Requests for Street Cleaning": {"2026-07": 2},
        "Illegal Dumping": {"2026-07": 1},
    }


def _page(total: int, ids: list[str]) -> dict[str, Any]:
    recs = [{**ROW, "case_id": i} for i in ids]
    return {"success": True, "result": {"total": total, "records": recs}}


def test_fetch_pages_filters_since_and_asserts_total():
    pages = [_page(3, ["a", "b"]), _page(3, ["c"])]
    with patch("pipeline.creatio._api_get", side_effect=pages) as get:
        out = fetch_creatio_records({"Litter & Debris"}, since=date(2026, 6, 1), page_size=2)
    assert [r["case_id"] for r in out] == ["a", "b", "c"]
    assert get.call_count == 2
    assert "254adca6-64ab-4c5c-9fc0-a6da622be185" in get.call_args_list[0].args[0]
    assert "offset=2" in get.call_args_list[1].args[0]


def test_fetch_raises_on_short_read_and_schema_drift():
    with patch("pipeline.creatio._api_get", side_effect=[_page(5, ["a"])]):
        try:
            fetch_creatio_records({"Litter & Debris"}, since=date(2026, 6, 1), page_size=2)
        except RuntimeError as e:
            assert "expected 5" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
    bad = {
        "success": True,
        "result": {"total": 1, "records": [{"case_id": "x", "open_date": "2026-07-01 00:00:00+00"}]},
    }
    with patch("pipeline.creatio._api_get", side_effect=[bad]):
        try:
            fetch_creatio_records({"Litter & Debris"}, since=date(2026, 6, 1), page_size=2)
        except RuntimeError as e:
            assert "schema drift" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd pipeline && uv run pytest tests/test_creatio.py -q`
Expected: FAIL with `ModuleNotFoundError: pipeline.creatio`

- [ ] **Step 3: Config**

Append to `pipeline/src/pipeline/config.py` after `RESOURCE_IDS`:

```python
# --- Creatio ("311 Service Requests - NEW SYSTEM") ---
# Boston is migrating 311 from Lagan to Creatio in department waves (2025-08 →).
# Migrated case types stop appearing in the legacy yearly resources (e.g. Requests
# for Street Cleaning / Illegal Dumping / Encampments end June 2026).
# See docs/plans/2026-09-02-creatio-migration-plan.md.
CREATIO_RESOURCE_ID = "254adca6-64ab-4c5c-9fc0-a6da622be185"
CREATIO_START_DATE: date = date(2025, 8, 1)

# Creatio service_name -> legacy CKAN type (deterministic mapping table).
CREATIO_SERVICE_MAP: dict[str, str] = {
    "Litter & Debris": "Requests for Street Cleaning",
    "Park Litter & Debris": "Requests for Street Cleaning",
    "Improper Trash Storage": "Improper Storage of Trash (Barrels)",
    "Trash Placed Out Early": "Improper Storage of Trash (Barrels)",
    "Overflowing Trash": "Improper Storage of Trash (Barrels)",
    "Illegal Dumping or Disposal": "Illegal Dumping",
    "Missed Waste Pick-up": "Missed Trash/Recycling/Yard Waste/Bulk Item",
    "Code Enforcement Collection": "CE Collection",
}

# Successor of "Requests for Street Cleaning". Resident text for these comes only
# from the Open311 scraper slugs below; Creatio CKAN rows carry staff comments.
CREATIO_WASTE_SERVICE_NAMES: set[str] = {"Litter & Debris", "Park Litter & Debris"}
```

Replace the existing `SCRAPER_SLUGS_FOR_WASTE_INPUT` line with:

```python
SCRAPER_SLUGS_FOR_WASTE_INPUT: list[str] = ["other", "litter-debris", "park-litter-debris"]
```

- [ ] **Step 4: Implement `pipeline/src/pipeline/creatio.py`**

```python
"""Creatio (new Boston 311 system) CKAN reader, normalizer and monthly counts."""

import json
import logging
import urllib.parse
from collections import defaultdict
from datetime import date
from typing import Any

from pipeline.cleaner import _parse_datetime
from pipeline.config import CKAN_BASE, CREATIO_RESOURCE_ID, CREATIO_SERVICE_MAP
from pipeline.fetcher import _api_get

logger = logging.getLogger(__name__)

# Fields we read. A missing one means the CKAN schema drifted — fail loudly.
REQUIRED_FIELDS = {
    "case_id",
    "open_date",
    "close_date",
    "service_name",
    "assigned_team",
    "closure_reason",
    "closure_comments",
    "report_source",
    "street_name",
    "zip_code",
    "neighborhood",
    "longitude",
    "latitude",
}


def fetch_creatio_records(service_names: set[str], since: date, page_size: int = 5000) -> list[dict[str, Any]]:
    """Page through datastore_search per service_name; keep rows opened on/after `since`.

    Uses datastore_search (not _sql): the SQL endpoint sits behind a WAF and paged
    reads return a `total` we can assert against. Raises RuntimeError on a short
    read or on schema drift.
    """
    out: list[dict[str, Any]] = []
    for name in sorted(service_names):
        offset = 0
        total: int | None = None
        got = 0
        while True:
            filters = urllib.parse.quote(json.dumps({"service_name": name}))
            url = (
                f"{CKAN_BASE}/datastore_search?resource_id={CREATIO_RESOURCE_ID}"
                f"&filters={filters}&limit={page_size}&offset={offset}"
            )
            data = _api_get(url)
            if not data or not data.get("success"):
                raise RuntimeError(f"Creatio fetch failed for {name!r} at offset {offset}")
            result = data["result"]
            if total is None:
                total = int(result.get("total", 0))
            records: list[dict[str, Any]] = result["records"]
            if offset == 0 and records:
                missing = REQUIRED_FIELDS - set(records[0].keys())
                if missing:
                    raise RuntimeError(f"Creatio schema drift: missing {sorted(missing)}")
            out.extend(r for r in records if str(r.get("open_date") or "")[:10] >= since.isoformat())
            got += len(records)
            if len(records) < page_size:
                break
            offset += page_size
        if total is not None and got != total:
            raise RuntimeError(f"Creatio {name!r}: read {got} rows, expected {total}")
        logger.info("Creatio %s: %d rows, %d since %s", name, got, len(out), since)
    return out


def normalize_creatio_record(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a Creatio CKAN row into the legacy CKAN shape cleaner.clean() expects.

    `type` is the mapped legacy type (unmapped names pass through). Staff text lives
    only in `creatio_closure_comments`; `open311_description` is never set here.
    """
    service_name = str(row.get("service_name") or "").strip()
    comments = str(row.get("closure_comments") or "").strip()
    if comments.lower() == "none":
        comments = ""
    return {
        "case_enquiry_id": str(row.get("case_id") or ""),
        "open_dt": str(row.get("open_date") or ""),
        "closed_dt": str(row.get("close_date") or ""),
        "case_title": service_name,
        "subject": str(row.get("assigned_department") or ""),
        "reason": str(row.get("case_topic") or ""),
        "type": CREATIO_SERVICE_MAP.get(service_name, service_name),
        "creatio_service_name": service_name,
        "queue": str(row.get("assigned_team") or ""),
        "closure_reason": str(row.get("closure_reason") or "").strip(),
        "creatio_closure_comments": comments,
        "source": str(row.get("report_source") or ""),
        "latitude": str(row.get("latitude") or ""),
        "longitude": str(row.get("longitude") or ""),
        "neighborhood": str(row.get("neighborhood") or ""),
        "location_street_name": str(row.get("street_name") or ""),
        "location_zipcode": str(row.get("zip_code") or "")[:5],
        "source_system": "creatio",
    }


def _month_dict() -> dict[str, int]:
    return defaultdict(int)


def monthly_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """{legacy_type: {"YYYY-MM": n}} with months in Boston local time."""
    out: dict[str, dict[str, int]] = defaultdict(_month_dict)
    for r in rows:
        dt = _parse_datetime(str(r.get("open_dt") or ""))
        if dt is None:
            continue
        out[str(r.get("type") or "")][dt.strftime("%Y-%m")] += 1
    return {t: dict(m) for t, m in out.items()}
```

- [ ] **Step 5: Run tests, lint, types**

Run: `cd pipeline && uv run pytest tests/test_creatio.py -q && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/`
Expected: 8 passed, clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/src/pipeline/config.py pipeline/src/pipeline/creatio.py pipeline/tests/test_creatio.py
git commit -m "feat(pipeline): Creatio CKAN reader, service map, normalizer, monthly counts (#137 #139)"
```

---

### Task 3: Pipeline — fingerprint matching for cross-system coverage QA (#138)

**Files:**
- Create: `pipeline/src/pipeline/dedupe.py`
- Create: `pipeline/tests/test_dedupe.py`

**Interfaces:**
- Produces: `fingerprint(rec) -> tuple[str, str, str, int] | None` = (legacy-mapped type, lat 4dp, lng 4dp, Boston-local minute); `match_cross_system(primary, secondary, window_min=2) -> tuple[list[dict], list[dict]]` = (secondary rows with no primary match, QA pairs `{"primary_id", "secondary_id", "type", "minutes_apart"}`). The mapping `CREATIO_SERVICE_MAP` is applied inside `fingerprint`, so Open311 rows typed `Litter & Debris` and Creatio rows typed `Requests for Street Cleaning` compare equal.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_dedupe.py
from typing import Any

from pipeline.creatio import normalize_creatio_record
from pipeline.dedupe import fingerprint, match_cross_system
from pipeline.open311_loader import normalize_open311_record

CREATIO_ROW: dict[str, Any] = {
    "case_id": "BCS-00256693", "open_date": "2026-07-16 16:10:24+00", "close_date": "", "case_topic": "Litter & Debris",
    "service_name": "Litter & Debris", "assigned_department": "PWD", "assigned_team": "PWD Highway (BEAM)",
    "case_status": "Closed", "closure_reason": "Resolved", "closure_comments": "None", "report_source": "BOS311",
    "full_address": "11-17 E Concord St, Boston, MA 02118", "street_name": "E Concord St", "zip_code": "02118",
    "neighborhood": "South End", "longitude": "-71.07473228", "latitude": "42.33768644",
}
OPEN311_SAME_CASE: dict[str, Any] = {
    "service_request_id": "6a2af5bf-cbba-4b18-8a2a-59eed542c8ef", "status": "closed", "service_name": "Litter & Debris",
    "service_code": "155a5e9b-8c3a-4279-bbab-f6bba6ddb0d0", "description": "Trash pile on the corner",
    "requested_datetime": "2026-07-16T16:11:00Z", "updated_datetime": "2026-07-17T08:06:36Z",
    "address": "11-17 E Concord St, South End, Ma, 02118", "lat": 42.337684, "long": -71.074731,
}


def test_fingerprint_applies_legacy_mapping_and_local_minutes():
    fa = fingerprint(normalize_creatio_record(CREATIO_ROW))
    fb = fingerprint(normalize_open311_record(OPEN311_SAME_CASE))
    assert fa is not None and fb is not None
    assert fa[:3] == fb[:3] == ("Requests for Street Cleaning", "42.3377", "-71.0747")
    assert fb[3] - fa[3] == 1


def test_fingerprint_none_without_coords_or_time():
    assert fingerprint({"type": "x", "open_dt": "", "latitude": "", "longitude": ""}) is None


def test_match_reports_pairs_and_keeps_unmatched():
    primary = [normalize_open311_record(OPEN311_SAME_CASE)]
    far = normalize_creatio_record({**CREATIO_ROW, "case_id": "BCS-2", "latitude": "42.3500", "longitude": "-71.0600"})
    late = normalize_creatio_record({**CREATIO_ROW, "case_id": "BCS-3", "open_date": "2026-07-16 16:25:00+00"})
    unmatched, pairs = match_cross_system(primary, [normalize_creatio_record(CREATIO_ROW), far, late], window_min=2)
    assert [r["case_enquiry_id"] for r in unmatched] == ["BCS-2", "BCS-3"]
    assert pairs == [{
        "primary_id": "6a2af5bf-cbba-4b18-8a2a-59eed542c8ef", "secondary_id": "BCS-00256693",
        "type": "Requests for Street Cleaning", "minutes_apart": 1,
    }]


def test_match_is_pure():
    secondary = [normalize_creatio_record(CREATIO_ROW)]
    a = match_cross_system([], secondary)
    b = match_cross_system([], secondary)
    assert a == b and len(secondary) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `cd pipeline && uv run pytest tests/test_dedupe.py -q`
Expected: FAIL `ModuleNotFoundError: pipeline.dedupe`

- [ ] **Step 3: Implement**

```python
"""Deterministic cross-system fingerprint matching.

Legacy CKAN ids (numeric), Creatio CKAN ids (BCS-…) and Creatio Open311 ids (UUID)
share no namespace, so the same case in two systems can only be recognised by
fingerprint: same legacy-mapped type, same 4-dp coordinates (~11 m), open time
within a small window. Matches are reported as pairs, never silently discarded.
"""

from collections import defaultdict
from typing import Any

from pipeline.cleaner import _parse_datetime
from pipeline.config import CREATIO_SERVICE_MAP

Fingerprint = tuple[str, str, str, int]


def fingerprint(rec: dict[str, Any]) -> Fingerprint | None:
    """(legacy-mapped type, lat 4dp, lng 4dp, Boston-local minute index) or None."""
    try:
        lat = float(rec.get("latitude") or "")
        lng = float(rec.get("longitude") or "")
    except (TypeError, ValueError):
        return None
    dt = _parse_datetime(str(rec.get("open_dt") or ""))
    if dt is None:
        return None
    raw_type = str(rec.get("type") or "")
    return (CREATIO_SERVICE_MAP.get(raw_type, raw_type), f"{lat:.4f}", f"{lng:.4f}", int(dt.timestamp() // 60))


def match_cross_system(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    window_min: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (secondary rows with no primary match, QA pairs for the matched ones).

    Inputs are never mutated. Output order follows `secondary`.
    """
    index: dict[tuple[str, str, str], list[tuple[int, str]]] = defaultdict(list)
    for rec in primary:
        fp = fingerprint(rec)
        if fp is not None:
            index[fp[:3]].append((fp[3], str(rec.get("case_enquiry_id") or "")))
    unmatched: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for rec in secondary:
        fp = fingerprint(rec)
        hit = None
        if fp is not None:
            for minute, pid in index.get(fp[:3], []):
                if abs(minute - fp[3]) <= window_min:
                    hit = (pid, abs(minute - fp[3]))
                    break
        if hit is None:
            unmatched.append(rec)
        else:
            pairs.append({
                "primary_id": hit[0],
                "secondary_id": str(rec.get("case_enquiry_id") or ""),
                "type": fp[0] if fp else "",
                "minutes_apart": hit[1],
            })
    return unmatched, pairs
```

- [ ] **Step 4: Run tests, lint, types**

Run: `cd pipeline && uv run pytest tests/test_dedupe.py -q && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/`
Expected: 4 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/pipeline/dedupe.py pipeline/tests/test_dedupe.py
git commit -m "feat(pipeline): cross-system fingerprint matching for coverage QA (#138)"
```

---

### Task 4: Pipeline — waste inputs, Creatio counts, coverage QA, schema_version (#139/#140)

**Files:**
- Modify: `pipeline/src/pipeline/run.py`
- Modify: `pipeline/tests/test_waste_merge.py` (append one test)

**Interfaces:**
- Consumes: `fetch_creatio_records`, `normalize_creatio_record`, `monthly_counts`, `match_cross_system`, `CREATIO_SERVICE_MAP`, `CREATIO_WASTE_SERVICE_NAMES`, `CREATIO_START_DATE`, `SCRAPER_SLUGS_FOR_WASTE_INPUT`.
- Produces: `waste/stats.json` gains `"schema_version": 2` and `"sources": {"ckan_legacy", "open311_other", "open311_litter_debris", "creatio_ckan_rows", "creatio_open311_matched", "creatio_open311_unmatched"}`; new S3 files `raw/creatio.json` (all mapped services since `CREATIO_START_DATE`, normalized), `metadata/creatio_monthly.json` (`monthly_counts` output), `waste/qa_creatio_coverage.json` (`{"pairs": [...], "unmatched_creatio_ids": [...]}`).
- Classifier input = legacy CKAN street cleaning + Open311 rows (other, litter-debris, park-litter-debris). Creatio CKAN rows never enter the classifier.

- [ ] **Step 1: Write the failing test** (append to `tests/test_waste_merge.py`)

```python
CREATIO_ROW: dict[str, Any] = {
    "case_id": "BCS-00256693", "open_date": "2026-07-16 16:10:24+00", "close_date": "2026-07-17 08:06:36+00",
    "case_topic": "Litter & Debris", "service_name": "Litter & Debris", "assigned_department": "PWD",
    "assigned_team": "PWD Highway (BEAM)", "case_status": "Closed", "closure_reason": "Resolved",
    "closure_comments": "Human feces removed", "report_source": "BOS311",
    "full_address": "11-17 E Concord St, Boston, MA 02118", "street_name": "E Concord St", "zip_code": "02118",
    "neighborhood": "South End", "longitude": "-71.07473228", "latitude": "42.33768644",
}
OPEN311_LITTER_SAME_CASE: dict[str, Any] = {
    "service_request_id": "6a2af5bf-cbba-4b18-8a2a-59eed542c8ef", "status": "closed",
    "service_name": "Litter & Debris", "service_code": "155a5e9b-8c3a-4279-bbab-f6bba6ddb0d0",
    "description": "Human feces on the sidewalk by the bus stop", "requested_datetime": "2026-07-16T16:10:30Z",
    "updated_datetime": "2026-07-17T08:06:36Z", "address": "11-17 E Concord St, South End, Ma, 02118",
    "lat": 42.33768644, "long": -71.07473228,
}


def test_waste_uses_litter_debris_text_and_reports_creatio_coverage(s3_bucket):
    from pipeline import run

    def fake_load(slugs: list[str], start: Any, end: Any) -> list[dict[str, Any]]:
        return [OPEN311_LITTER_SAME_CASE] if "litter-debris" in slugs else []

    fake_classifier = _make_fake_classifier({"101005000001", "6a2af5bf-cbba-4b18-8a2a-59eed542c8ef"})
    with (
        patch("pipeline.run.fetch_creatio_records", return_value=[CREATIO_ROW]),
        patch("pipeline.run.load_records_from_s3", side_effect=fake_load),
        patch("pipeline.run.WasteClassifier", return_value=fake_classifier),
        patch("pipeline.run.enrich_records", side_effect=lambda recs, cache, **kw: (recs, cache)),
        patch("pipeline.run._enrich_districts"),
    ):
        count = run._process_waste([CKAN_CONFIRMED], force=False)

    client, bucket = s3_bucket
    stats = json.loads(client.get_object(Bucket=bucket, Key="waste/stats.json")["Body"].read())
    assert stats["schema_version"] == 2
    assert stats["sources"] == {
        "ckan_legacy": 1, "open311_other": 0, "open311_litter_debris": 1,
        "creatio_ckan_rows": 1, "creatio_open311_matched": 1, "creatio_open311_unmatched": 0,
    }
    assert count == 2  # legacy confirmed + the Litter & Debris resident report; Creatio CKAN row not classified
    qa = json.loads(client.get_object(Bucket=bucket, Key="waste/qa_creatio_coverage.json")["Body"].read())
    assert qa["pairs"][0]["secondary_id"] == "BCS-00256693"
    monthly = json.loads(client.get_object(Bucket=bucket, Key="metadata/creatio_monthly.json")["Body"].read())
    assert monthly["Requests for Street Cleaning"]["2026-07"] == 1
```

(`_make_fake_classifier` already returns a `classify_batch` mock keyed on `case_enquiry_id`; if its match key differs, read it and pass the right ids.)

- [ ] **Step 2: Run to verify failure**

Run: `cd pipeline && uv run pytest tests/test_waste_merge.py -q -k creatio_coverage`
Expected: FAIL (`AttributeError: … has no attribute 'fetch_creatio_records'`)

- [ ] **Step 3: Implement in `run.py`**

Imports (extend the existing `from pipeline.config import (…)` block and add lines):

```python
from pipeline.config import CREATIO_SERVICE_MAP, CREATIO_START_DATE  # add to the existing block
from pipeline.creatio import fetch_creatio_records, monthly_counts, normalize_creatio_record
from pipeline.dedupe import match_cross_system
```

Inside `_process_waste`, replace the block from `# Load Other corpus from Open311 scraper` through the `logger.info("Waste input: …")` call with:

```python
    today = datetime.now(UTC).date()

    # Resident-text corpora from the Open311 scraper: "other" (Lagan, numeric ids)
    # and the Creatio successors of Street Cleaning (UUID ids, litter-debris slugs).
    open311_raw = load_records_from_s3(SCRAPER_SLUGS_FOR_WASTE_INPUT, OPEN311_WASTE_START_DATE, today)

    # Same-namespace exact-id dedupe (Other vs legacy CKAN share numeric ids).
    dupes_dropped = 0
    open311_unique: list[dict[str, Any]] = []
    for rec in open311_raw:
        if str(rec.get("service_request_id", "")) in ckan_ids:
            dupes_dropped += 1
        else:
            open311_unique.append(rec)
    open311_normalized = [normalize_open311_record(r) for r in open311_unique]
    n_litter = sum(1 for r in open311_unique if str(r.get("service_name", "")) in CREATIO_WASTE_SERVICE_NAMES)

    # Creatio CKAN rows: counts + coverage QA only. They carry staff text, so they
    # are NOT classified and NOT merged into the candidate corpus.
    creatio_raw = fetch_creatio_records(set(CREATIO_SERVICE_MAP), CREATIO_START_DATE)
    creatio_rows = [normalize_creatio_record(r) for r in creatio_raw]
    storage.write_json("raw/creatio.json", creatio_rows)
    storage.write_json("metadata/creatio_monthly.json", monthly_counts(creatio_rows))
    creatio_waste = [r for r in creatio_rows if r.get("creatio_service_name") in CREATIO_WASTE_SERVICE_NAMES]
    litter_rows = [r for r in open311_normalized if r.get("type") in CREATIO_WASTE_SERVICE_NAMES]
    unmatched, pairs = match_cross_system(litter_rows, creatio_waste)
    storage.write_json(
        "waste/qa_creatio_coverage.json",
        {"pairs": pairs, "unmatched_creatio_ids": [r["case_enquiry_id"] for r in unmatched]},
    )

    all_raw = raw_records + open311_normalized
    source_counts = {
        "ckan_legacy": len(raw_records),
        "open311_other": len(open311_unique) - n_litter,
        "open311_litter_debris": n_litter,
        "creatio_ckan_rows": len(creatio_rows),
        "creatio_open311_matched": len(pairs),
        "creatio_open311_unmatched": len(unmatched),
    }
    logger.info(
        "Waste input: %s (exact-id dupes dropped=%d) total_candidates=%d", source_counts, dupes_dropped, len(all_raw)
    )
```

Where `page_stats: dict[str, Any] = {…}` is built (run.py ~397), add two entries to the literal:

```python
        "schema_version": 2,
        "sources": source_counts,
```

Also add `"schema_version": 2,` to the `page_stats` literal in `_process_dataset` so all three layers carry it. Ensure `CREATIO_WASTE_SERVICE_NAMES` is in the config import block.

- [ ] **Step 4: Run the suite, lint, types**

Run: `cd pipeline && uv run pytest -q && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/pipeline/run.py pipeline/tests/test_waste_merge.py
git commit -m "feat(pipeline): waste classifies Litter & Debris resident text; Creatio counts + coverage QA; schema_version (#139 #140)"
```

---

### Task 5: Pipeline — per-source health monitor (#135)

**Files:**
- Create: `pipeline/src/pipeline/health.py`
- Create: `pipeline/tests/test_health.py`
- Modify: `pipeline/src/pipeline/run.py` (`run_pipeline`)

**Interfaces:**
- Produces `compute_source_health(today: date | None = None) -> dict[str, Any]`, `write_source_health(health) -> None` → `metadata/source_health.json`:

```json
{
  "generated": "…", "schema_version": 1,
  "sources": {
    "ckan_legacy:Needle Pickup":          {"through": "2026-09-01", "last_30d": 1180, "prior_year_30d": 1100, "ratio": 1.07, "status": "ok"},
    "ckan_legacy:Encampments":            {"through": "2026-05-27", "last_30d": 0,    "prior_year_30d": 210,  "ratio": 0.0,  "status": "stale"},
    "ckan_legacy:Requests for Street Cleaning": {"through": "2026-06-30", "last_30d": 0, "prior_year_30d": 1951, "ratio": 0.0, "status": "stale"},
    "ckan_creatio:Litter & Debris":       {"through": "2026-09-01", "last_30d": 3062, "prior_year_30d": 0,    "ratio": null, "status": "ok"},
    "open311:other":                      {"through": "2026-09-01", "last_30d": 1400, "prior_year_30d": 1500, "ratio": 0.93, "status": "ok"},
    "open311:litter-debris":              {"through": "2026-09-01", "last_30d": 2900, "prior_year_30d": 0,    "ratio": null, "status": "ok"},
    "open311:needles":                    {"…": "…"}, "open311:encampments": {"…": "…"}
  },
  "layers": {
    "needles":     {"status": "ok",    "through": "2026-09-01", "sources": ["ckan_legacy:Needle Pickup", "open311:needles"]},
    "encampments": {"status": "stale", "through": "2026-05-27", "sources": ["ckan_legacy:Encampments", "open311:encampments"]},
    "waste":       {"status": "ok",    "through": "2026-09-01", "sources": ["ckan_legacy:Requests for Street Cleaning", "ckan_creatio:Litter & Debris", "open311:other", "open311:litter-debris"]}
  },
  "creatio_service_names": ["…"], "new_service_names": [], "notes": ["…"]
}
```
Rules: `ratio = None` when `prior_year_30d == 0`. `status`: `stale` if `through` older than 14 days or `last_30d == 0`; `degraded` if ratio is not None and < 0.5; else `ok`. Layer status = `ok` if any source is `ok`, else `degraded` if any `degraded`, else `stale`; layer `through` = max over sources. Counts come from uncapped inputs: legacy from `raw/{dataset}_{year}.json` (encampments `raw/encampments_v2_{year}.json`) filtered by `type`; Creatio from `raw/creatio.json` filtered by `creatio_service_name`; Open311 from `open311/{slug}/YYYY-MM-DD.json` record counts (file listing + reads within the two windows). Prior-year window = same 30 days shifted by `timedelta(days=365)`.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_health.py
import json
from datetime import date
from unittest.mock import patch

from pipeline import storage
from pipeline.health import classify_status, compute_source_health, layer_status, write_source_health


def test_classify_status():
    assert classify_status(ratio=1.1, days_since=1, current=10) == "ok"
    assert classify_status(ratio=0.4, days_since=1, current=10) == "degraded"
    assert classify_status(ratio=None, days_since=1, current=10) == "ok"  # no baseline
    assert classify_status(ratio=1.0, days_since=15, current=10) == "stale"
    assert classify_status(ratio=0.0, days_since=3, current=0) == "stale"


def test_layer_status_rollup():
    assert layer_status(["stale", "ok"]) == "ok"
    assert layer_status(["stale", "degraded"]) == "degraded"
    assert layer_status(["stale", "stale"]) == "stale"


def test_compute_from_uncapped_sources(s3_bucket):
    # legacy raw caches (uncapped)
    storage.write_json("raw/needles_2026.json", [{"type": "Needle Pickup", "open_dt": "2026-08-20 10:00:00"}] * 12)
    storage.write_json("raw/needles_2025.json", [{"type": "Needle Pickup", "open_dt": "2025-08-20 10:00:00"}] * 10)
    storage.write_json("raw/encampments_v2_2026.json", [{"type": "Encampments", "open_dt": "2026-05-27 10:00:00"}])
    storage.write_json("raw/encampments_v2_2025.json", [{"type": "Encampments", "open_dt": "2025-08-20 10:00:00"}] * 5)
    storage.write_json("raw/waste_2026.json", [{"type": "Requests for Street Cleaning", "open_dt": "2026-06-30 10:00:00"}])
    storage.write_json("raw/creatio.json", [
        {"creatio_service_name": "Litter & Debris", "open_dt": "2026-08-25 10:00:00+00"} for _ in range(7)
    ])
    storage.write_json("open311/needles/2026-08-30.json", [{"service_request_id": "1"}] * 3)
    storage.write_json("open311/litter-debris/2026-08-30.json", [{"service_request_id": "u"}] * 4)
    storage.write_json("metadata/creatio_service_names.json", ["Litter & Debris"])
    with patch("pipeline.health._creatio_service_names", return_value=["Litter & Debris", "Needle Cleanup"]):
        h = compute_source_health(today=date(2026, 9, 2))
    s = h["sources"]
    assert s["ckan_legacy:Needle Pickup"]["last_30d"] == 12 and s["ckan_legacy:Needle Pickup"]["ratio"] == 1.2
    assert s["ckan_legacy:Encampments"]["status"] == "stale" and s["ckan_legacy:Encampments"]["through"] == "2026-05-27"
    assert s["ckan_legacy:Requests for Street Cleaning"]["status"] == "stale"
    assert s["ckan_creatio:Litter & Debris"]["ratio"] is None and s["ckan_creatio:Litter & Debris"]["status"] == "ok"
    assert s["open311:litter-debris"]["last_30d"] == 4
    assert h["layers"]["encampments"]["status"] == "stale"
    assert h["layers"]["waste"]["status"] == "ok"
    assert h["new_service_names"] == ["Needle Cleanup"]
    write_source_health(h)
    client, bucket = s3_bucket
    saved = json.loads(client.get_object(Bucket=bucket, Key="metadata/source_health.json")["Body"].read())
    assert saved["schema_version"] == 1


def test_first_run_seeds_service_names_without_flagging_all_as_new(s3_bucket):
    with patch("pipeline.health._creatio_service_names", return_value=["A", "B"]):
        h = compute_source_health(today=date(2026, 9, 2))
    assert h["new_service_names"] == []
    assert storage.read_json("metadata/creatio_service_names.json") == ["A", "B"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd pipeline && uv run pytest tests/test_health.py -q`
Expected: FAIL `ModuleNotFoundError: pipeline.health`

- [ ] **Step 3: Implement**

```python
"""Daily per-source health snapshot: is each feed still delivering?

Counts come from uncapped inputs the pipeline already stores (raw CKAN year
caches, raw/creatio.json, Open311 day files) — never from the 3,000-row
markers.json. Writes metadata/source_health.json for the frontend.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pipeline import storage
from pipeline.cleaner import _parse_datetime
from pipeline.config import CKAN_BASE, CREATIO_RESOURCE_ID, RESOURCE_IDS
from pipeline.fetcher import _api_get

logger = logging.getLogger(__name__)

WINDOW_DAYS = 30
STALE_DAYS = 14
DEGRADED_RATIO = 0.5
SCHEMA_VERSION = 1

# source key -> (kind, selector). kind: "ckan_legacy" (dataset, type) | "ckan_creatio" (service_name) | "open311" (slug)
SOURCES: dict[str, tuple[str, tuple[str, ...]]] = {
    "ckan_legacy:Needle Pickup": ("ckan_legacy", ("needles", "Needle Pickup")),
    "ckan_legacy:Encampments": ("ckan_legacy", ("encampments", "Encampments")),
    "ckan_legacy:Requests for Street Cleaning": ("ckan_legacy", ("waste", "Requests for Street Cleaning")),
    "ckan_creatio:Litter & Debris": ("ckan_creatio", ("Litter & Debris",)),
    "ckan_creatio:Park Litter & Debris": ("ckan_creatio", ("Park Litter & Debris",)),
    "open311:needles": ("open311", ("needles",)),
    "open311:encampments": ("open311", ("encampments",)),
    "open311:other": ("open311", ("other",)),
    "open311:litter-debris": ("open311", ("litter-debris",)),
    "open311:park-litter-debris": ("open311", ("park-litter-debris",)),
}
LAYER_SOURCES: dict[str, list[str]] = {
    "needles": ["ckan_legacy:Needle Pickup", "open311:needles"],
    "encampments": ["ckan_legacy:Encampments", "open311:encampments"],
    "waste": [
        "ckan_legacy:Requests for Street Cleaning",
        "ckan_creatio:Litter & Debris",
        "ckan_creatio:Park Litter & Debris",
        "open311:other",
        "open311:litter-debris",
        "open311:park-litter-debris",
    ],
}


def classify_status(ratio: float | None, days_since: int, current: int) -> str:
    if days_since > STALE_DAYS or current == 0:
        return "stale"
    if ratio is not None and ratio < DEGRADED_RATIO:
        return "degraded"
    return "ok"


def layer_status(statuses: list[str]) -> str:
    if "ok" in statuses:
        return "ok"
    if "degraded" in statuses:
        return "degraded"
    return "stale"


def _local_day(value: str) -> str:
    dt = _parse_datetime(value)
    return dt.date().isoformat() if dt else ""


def _days_from_rows(rows: list[dict[str, Any]], key: str, want: str, field: str = "open_dt") -> list[str]:
    return sorted(_local_day(str(r.get(field) or "")) for r in rows if str(r.get(key) or "") == want)


def _rows(key: str) -> list[dict[str, Any]]:
    data = storage.read_json(key)
    return data if isinstance(data, list) else []


def _legacy_days(dataset: str, type_name: str, years: set[int]) -> list[str]:
    days: list[str] = []
    for year in sorted(years):
        if year not in RESOURCE_IDS:
            continue
        key = f"raw/encampments_v2_{year}.json" if dataset == "encampments" else f"raw/{dataset}_{year}.json"
        days.extend(_days_from_rows(_rows(key), "type", type_name))
    return sorted(d for d in days if d)


def _creatio_days(service_name: str) -> list[str]:
    days = _days_from_rows(_rows("raw/creatio.json"), "creatio_service_name", service_name)
    return [d for d in days if d]


def _open311_counts(slug: str, start: date, end: date) -> tuple[int, str]:
    keys = storage.list_keys(f"open311/{slug}/")
    days = sorted(k.rsplit("/", 1)[-1][:10] for k in keys if k.endswith(".json"))
    total = 0
    for d in days:
        if start.isoformat() <= d <= end.isoformat():
            total += len(storage.read_json(f"open311/{slug}/{d}.json") or [])
    return total, (days[-1] if days else "")


def _window(days: list[str], start: date, end: date) -> int:
    return sum(1 for d in days if start.isoformat() <= d <= end.isoformat())


def _creatio_service_names() -> list[str]:
    # `facets` is not enabled on data.boston.gov; `fields=…&distinct=true` is (verified 2026-09-02, 58 names).
    url = f"{CKAN_BASE}/datastore_search?resource_id={CREATIO_RESOURCE_ID}&fields=service_name&distinct=true&limit=1000"
    data = _api_get(url)
    if not data or not data.get("success"):
        return []
    return sorted(str(r["service_name"]) for r in data["result"]["records"] if r.get("service_name"))


def compute_source_health(today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    start = today - timedelta(days=WINDOW_DAYS)
    py_start, py_end = start - timedelta(days=365), today - timedelta(days=365)
    years = {start.year, today.year, py_start.year, py_end.year}
    sources: dict[str, Any] = {}
    for key, (kind, sel) in SOURCES.items():
        if kind in ("ckan_legacy", "ckan_creatio"):
            days = _legacy_days(sel[0], sel[1], years) if kind == "ckan_legacy" else _creatio_days(sel[0])
            cur = _window(days, start, today)
            prior = _window(days, py_start, py_end)
            through = days[-1] if days else ""
        else:
            cur, through = _open311_counts(sel[0], start, today)
            prior, _ = _open311_counts(sel[0], py_start, py_end)
        ratio = round(cur / prior, 2) if prior else None
        days_since = (today - date.fromisoformat(through)).days if through else 10_000
        sources[key] = {
            "through": through,
            "last_30d": cur,
            "prior_year_30d": prior,
            "ratio": ratio,
            "status": classify_status(ratio, days_since, cur),
        }
    layers: dict[str, Any] = {}
    notes: list[str] = []
    for layer, keys in LAYER_SOURCES.items():
        statuses = [sources[k]["status"] for k in keys]
        through = max((sources[k]["through"] for k in keys), default="")
        layers[layer] = {"status": layer_status(statuses), "through": through, "sources": keys}
        if layers[layer]["status"] != "ok":
            notes.append(f"{layer}: {layers[layer]['status']} (through {through or 'never'})")
    names = _creatio_service_names()
    if not names:
        notes.append("Creatio service-name discovery returned nothing (CKAN distinct query failed)")
    known = storage.read_json("metadata/creatio_service_names.json")
    new_names = sorted(set(names) - set(known)) if isinstance(known, list) else []
    if names:
        storage.write_json("metadata/creatio_service_names.json", names)
    if new_names:
        notes.append(f"New Creatio service names: {', '.join(new_names)}")
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
        "layers": layers,
        "creatio_service_names": names,
        "new_service_names": new_names,
        "notes": notes,
    }


def write_source_health(health: dict[str, Any]) -> None:
    storage.write_json("metadata/source_health.json", health)
    logger.info("Source health: %s", {k: v["status"] for k, v in health["layers"].items()})
```

In `run_pipeline`, before `# Write metadata`:

```python
    try:
        write_source_health(compute_source_health())
    except Exception:  # the monitor must never break the data run
        logger.exception("source health failed")
```
with `from pipeline.health import compute_source_health, write_source_health` in imports.

- [ ] **Step 4: Run suite, lint, types**

Run: `cd pipeline && uv run pytest -q && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/pipeline/health.py pipeline/tests/test_health.py pipeline/src/pipeline/run.py
git commit -m "feat(pipeline): per-source health monitor -> metadata/source_health.json (#135)"
```

---

### Task 6: Frontend — freeze notice, freshness chips, schema check (#134/#141)

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/bucket.ts`
- Create: `frontend/src/components/DataFreshness.astro`
- Modify: `frontend/src/pages/index.astro`, `frontend/src/pages/mattress.astro`

**Interfaces:**
- `fetchSourceHealth(): Promise<SourceHealth | null>`; `<DataFreshness health={SourceHealth | null} frozen={Record<string, string>} />`. `PageStats.schema_version?: number`.

- [ ] **Step 1: Types**

Append to `types.ts`:

```ts
export type SourceStatus = "ok" | "degraded" | "stale"

export interface SourceHealthEntry {
	through: string
	last_30d: number
	prior_year_30d: number
	ratio: number | null
	status: SourceStatus
}

export interface LayerHealth {
	status: SourceStatus
	through: string
	sources: string[]
}

export interface SourceHealth {
	generated: string
	schema_version?: number
	sources?: Record<string, SourceHealthEntry>
	layers: Record<string, LayerHealth>
	creatio_service_names?: string[]
	new_service_names?: string[]
	notes?: string[]
}
```
Add `schema_version?: number` to `PageStats`.

- [ ] **Step 2: Fetcher**

In `bucket.ts` import `SourceHealth` and append:

```ts
export async function fetchSourceHealth(): Promise<SourceHealth | null> {
	if (!USE_S3) return null
	try {
		const h = await readJson<SourceHealth>("metadata/source_health.json")
		return h && typeof h === "object" && h.layers ? h : null
	} catch {
		return null
	}
}
```

- [ ] **Step 3: Component**

```astro
---
// frontend/src/components/DataFreshness.astro
import type { SourceHealth } from "../lib/types"

interface Props {
	health: SourceHealth | null
	/** Static per-layer freeze dates shown even when no health file exists. */
	frozen?: Record<string, string>
}
const { health, frozen = {} } = Astro.props

const LABELS: Record<string, string> = { needles: "Sharps", encampments: "Encampments", waste: "Human Waste" }
const fmt = (d: string) =>
	d ? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "unknown"

const layers = Object.entries(health?.layers ?? {})
const chips = layers.length
	? layers.map(([k, l]) => ({ key: k, label: LABELS[k] ?? k, through: l.through ?? "", status: l.status ?? "stale", sources: l.sources ?? [] }))
	: Object.entries(frozen).map(([k, d]) => ({ key: k, label: LABELS[k] ?? k, through: d, status: "stale" as const, sources: [] }))
const troubled = chips.filter((c) => c.status !== "ok")
---

{chips.length > 0 && (
	<section class="freshness" aria-label="Data freshness">
		<div class="container freshness-inner">
			<div class="chips">
				{chips.map((c) => (
					<span class={`chip chip-${c.status}`} title={c.sources.join(", ")}>
						{c.label}: data through {fmt(c.through)}
					</span>
				))}
			</div>
			{troubled.length > 0 && (
				<p class="notice">
					Boston moved its 311 system to a new platform in 2026. Some categories stopped appearing in the
					city's data during the switch ({troubled.map((c) => c.label).join(", ")}). We show those layers
					through their last complete date rather than guess.
					<a href="/data-quality#migration">What changed</a>
				</p>
			)}
		</div>
	</section>
)}

<style>
	.freshness { background: #fbf7ea; border-bottom: 1px solid #ecdfb5; font-size: 0.85rem; }
	.freshness-inner { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; padding: 8px 0; }
	.chips { display: flex; flex-wrap: wrap; gap: 6px; }
	.chip { border-radius: 999px; padding: 2px 10px; background: #e8f1e5; color: #244d1f; }
	.chip-degraded { background: #fde9cc; color: #6b3f00; }
	.chip-stale { background: #f8d9d6; color: #7a1f16; }
	.notice { margin: 0; color: #4a4a46; line-height: 1.4; }
	.notice a { color: inherit; margin-left: 4px; }
</style>
```

- [ ] **Step 4: Wire into `index.astro`**

Add `fetchSourceHealth` to the `../lib/bucket` import; append `fetchSourceHealth()` to the `Promise.all` array and `sourceHealth` to the destructuring; import `DataFreshness`; render after the header:

```astro
	<Header generated={stats.generated} />
	<DataFreshness
		health={sourceHealth}
		frozen={{ encampments: "2026-05-27", waste: "2026-06-30" }}
	/>
```

Add an anchor section to `frontend/src/pages/data-quality.astro` (`<section id="migration" class="section">`) with two paragraphs: what changed (Lagan→Creatio, June 2026 cutoffs for Street Cleaning / Illegal Dumping / Encampments, no encampment category in the new system) and what we do (freeze until re-fed; Litter & Debris resident text now feeds the waste layer).

In `mattress.astro` Method list add:

```astro
					<li>
						2026 counts for Requests for Street Cleaning, Illegal Dumping and Improper Storage are
						low from June 2026: Boston moved those categories to a new 311 system whose export is
						separate. Both systems are shown side by side in the table above.
					</li>
```

- [ ] **Step 5: Verify**

Run: `cd frontend && pnpm exec biome format --write src/ && pnpm check && pnpm dev`
Open `http://localhost:4321/` with agent-browser: with no health file the static freeze chips for Encampments and Human Waste render with the notice; page otherwise unchanged; no console errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): migration notice, freshness chips, static freeze for encampments/waste (#134 #141)"
```

---

### Task 7: Mattress page — 2026 across both systems (#142)

**Files:**
- Modify: `scripts/mattress_analysis.py`, `frontend/src/pages/mattress.astro`

**Interfaces:**
- `mattress.json` gains Open311 slugs `litter-debris`, `improper-trash-storage`, `illegal-dumping` (same shape; empty if not yet scraped) and `creatio_types_monthly: {legacy_type: {ym: n}}` computed with `pipeline.creatio.fetch_creatio_records` + `monthly_counts` (paged reads, Boston-local months; no CKAN SQL).

- [ ] **Step 1: Script**

```python
from pipeline.config import CREATIO_SERVICE_MAP, CREATIO_START_DATE  # after the existing sys.path insert
from pipeline.creatio import fetch_creatio_records, monthly_counts, normalize_creatio_record

OPEN311_SLUGS = ["illegal-trash", "street-cleaning", "other", "litter-debris", "improper-trash-storage", "illegal-dumping"]


def creatio_monthly_by_type() -> dict[str, dict[str, int]]:
    rows = [normalize_creatio_record(r) for r in fetch_creatio_records(set(CREATIO_SERVICE_MAP), CREATIO_START_DATE)]
    return monthly_counts(rows)
```
In `main()` add `"creatio_types_monthly": creatio_monthly_by_type(),` to the payload. In `open311_mentions`, when `keys` is empty for a slug, store `{"total": {}, "mattress": {}, "samples": []}` and log it.

- [ ] **Step 2: Page**

In section 4's table, after the `ckanRows` rows, render one row per key of `mattress.creatio_types_monthly` (yearly sums via the existing `yearOf`) labelled `"<legacy type> (new system)†"`, and a footnote `† New 311 system (Creatio); 2026 only; shown separately from the legacy rows above, not summed.` Section 2's mention table gains three rows for the new-system resident-text slugs (`litter-debris` → "Litter & Debris (new system)", `improper-trash-storage`, `illegal-dumping`) placed after the legacy rows and before Total, and Total sums all six; guard reads with `?.mattress ?? {}` so an unscraped slug renders 0.

- [ ] **Step 3: Regenerate and verify**

Run: `cd pipeline && uv run python ../scripts/mattress_analysis.py && cd ../frontend && pnpm check && pnpm dev` → `/mattress` shows the Creatio rows and footnote; no console errors.

- [ ] **Step 4: Commit**

```bash
git add scripts/mattress_analysis.py frontend/src/data/mattress.json frontend/src/pages/mattress.astro
git commit -m "feat(mattress): 2026 counts across legacy + Creatio, labeled separately (#142)"
```

---

### Task 8: Docs and PRs

- [ ] `docs/wiki/data-quality-issues.md` §13: June 2026 cutoffs, UUID-code fact, encampment intake end 2026-05-27. `docs/wiki/service-code-mapping.md`: Creatio table → `creatio-open311-codes.json`. `docs/wiki/dev-setup.md`: pnpm-10 build-script trap.
- [ ] PRs in this order: (1) frontend Task 6 (closes #134, part of #141); (2) scraper Task 1 (#136); (3) pipeline Tasks 2–5 (tag scottfrasso; closes #135 #137 #138 #139 #140; note the pipeline Railway service must redeploy — check `imageDigest`); (4) mattress Task 7 + docs (#142).
- [ ] After (3) merges and the cron runs: `metadata/source_health.json` exists, home page chips switch from static freeze to live values.
