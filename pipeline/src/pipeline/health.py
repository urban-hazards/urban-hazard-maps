"""Daily per-source health snapshot: is each feed still delivering?

Counts come from uncapped inputs the pipeline already stores (raw CKAN year
caches, raw/creatio.json, Open311 day files) — never from the 3,000-row
markers.json. Writes metadata/source_health.json for the frontend.
"""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pipeline import storage
from pipeline.cleaner import _parse_datetime
from pipeline.config import CKAN_BASE, CREATIO_RESOURCE_ID, ENCAMPMENT_TYPES
from pipeline.fetcher import _api_get

logger = logging.getLogger(__name__)

WINDOW_DAYS = 30
STALE_DAYS = 14
DEGRADED_RATIO = 0.5
SCHEMA_VERSION = 2

# source key -> (kind, selector, coverage).
# kind: "ckan_legacy" (dataset, type) | "ckan_creatio" (service_name,) | "open311" (slug,)
# For kind "ckan_legacy" and dataset "encampments", selector[1] is a provenance route
# ("type" | "queue"), not a `type` value to match — see H1/_row_route below.
# coverage: whether this source can make its layer "ok" (see H1/H2 in plan_v3.md).
SOURCES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ckan_legacy:Needle Pickup": ("ckan_legacy", ("needles", "Needle Pickup"), True),
    "ckan_legacy:Encampments": ("ckan_legacy", ("encampments", "type"), True),
    "ckan_legacy:Encampments (queue)": ("ckan_legacy", ("encampments", "queue"), False),
    "ckan_legacy:Requests for Street Cleaning": ("ckan_legacy", ("waste", "Requests for Street Cleaning"), True),
    "ckan_creatio:Litter & Debris": ("ckan_creatio", ("Litter & Debris",), True),
    "ckan_creatio:Park Litter & Debris": ("ckan_creatio", ("Park Litter & Debris",), True),
    "open311:needles": ("open311", ("needles",), True),
    "open311:encampments": ("open311", ("encampments",), True),
    "open311:other": ("open311", ("other",), True),
    "open311:other-creatio": ("open311", ("other-creatio",), True),
    "open311:litter-debris": ("open311", ("litter-debris",), True),
    "open311:park-litter-debris": ("open311", ("park-litter-debris",), True),
}
LAYER_SOURCES: dict[str, list[str]] = {
    "needles": ["ckan_legacy:Needle Pickup", "open311:needles"],
    "encampments": ["ckan_legacy:Encampments", "ckan_legacy:Encampments (queue)", "open311:encampments"],
    "waste": [
        "ckan_legacy:Requests for Street Cleaning",
        "ckan_creatio:Litter & Debris",
        "ckan_creatio:Park Litter & Debris",
        "open311:other",
        "open311:other-creatio",
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


def _legacy_year_files(prefix: str) -> list[int]:
    """Years present in the bucket for a raw/<prefix>_*.json family (full history,
    independent of the rolling last_30d / prior_year_30d `years` window).
    """
    years: set[int] = set()
    for key in storage.list_keys(f"raw/{prefix}_"):
        if not key.endswith(".json"):
            continue
        stem = key.rsplit("/", 1)[-1][: -len(".json")]
        year_str = stem.rsplit("_", 1)[-1]
        if year_str.isdigit():
            years.add(int(year_str))
    return sorted(years)


def _legacy_days(dataset: str, type_name: str) -> list[str]:
    """Report days for a legacy CKAN source across every raw/<dataset>_*.json year file in
    the bucket (one read per file). `through` needs the full history — a file's year can fall
    out of the rolling `years` window — and the 30-day counts are date-filtered by _window, so
    the same list serves both.
    """
    days: list[str] = []
    for year in _legacy_year_files(dataset):
        days.extend(_days_from_rows(_rows(f"raw/{dataset}_{year}.json"), "type", type_name))
    return sorted(d for d in days if d)


def _row_route(row: dict[str, Any]) -> str:
    """Provenance route for an encampment row: "type" (fetched via the type-button
    strategy) or "queue" (fetched via the internal-routing-queue strategy). Rows fetched
    before the `_uhm_route` stamp existed fall back to the mutable `type` field.
    """
    route = row.get("_uhm_route")
    if route == "type" or route == "queue":
        return route
    return "type" if row.get("type") in ENCAMPMENT_TYPES else "queue"


def _encampment_partition(years: list[int]) -> tuple[list[str], list[str]]:
    """(type_days, queue_days) across the given raw/encampments_v2_<year>.json files,
    partitioned by provenance rather than by the mutable `type` field (H1).
    """
    type_days: list[str] = []
    queue_days: list[str] = []
    for year in sorted(set(years)):
        rows = _rows(f"raw/encampments_v2_{year}.json")
        if not rows:
            continue
        type_rows = [r for r in rows if _row_route(r) == "type"]
        queue_rows = [r for r in rows if _row_route(r) == "queue"]
        unstamped = sum(1 for r in rows if r.get("_uhm_route") not in ("type", "queue"))
        if unstamped:
            # Rows cached before the _uhm_route stamp existed are classified by the mutable
            # `type` field. Logged so the fallback's footprint is measurable; it disappears
            # after the next --force re-fetch of that year.
            logger.info(
                "raw/encampments_v2_%d.json: %d/%d rows unstamped, routed by type (%d type / %d queue)",
                year,
                unstamped,
                len(rows),
                len(type_rows),
                len(queue_rows),
            )
        type_days.extend(_local_day(str(r.get("open_dt") or "")) for r in type_rows)
        queue_days.extend(_local_day(str(r.get("open_dt") or "")) for r in queue_rows)
    return sorted(d for d in type_days if d), sorted(d for d in queue_days if d)


def _creatio_days(service_name: str) -> list[str]:
    days = _days_from_rows(_rows("raw/creatio.json"), "creatio_service_name", service_name)
    return [d for d in days if d]


def _open311_counts(slug: str, start: date, end: date) -> tuple[int, str]:
    """(records in [start, end], last day that actually has records).

    Empty days are persisted as [] files, so "through" must be the newest
    non-empty day, not the newest file.
    """
    keys = storage.list_keys(f"open311/{slug}/")
    days = sorted(k.rsplit("/", 1)[-1][:10] for k in keys if k.endswith(".json"))
    total = 0
    for d in days:
        if start.isoformat() <= d <= end.isoformat():
            total += len(_rows(f"open311/{slug}/{d}.json"))
    through = ""
    for d in reversed(days):
        if _rows(f"open311/{slug}/{d}.json"):
            through = d
            break
    return total, through


def _window(days: list[str], start: date, end: date) -> int:
    return sum(1 for d in days if start.isoformat() <= d <= end.isoformat())


def _creatio_service_names() -> list[str]:
    # `facets` is not enabled on data.boston.gov; `fields=…&distinct=true` is (verified 2026-09-02).
    url = f"{CKAN_BASE}/datastore_search?resource_id={CREATIO_RESOURCE_ID}&fields=service_name&distinct=true&limit=1000"
    data = _api_get(url)
    if not data or not data.get("success"):
        return []
    return sorted(str(r["service_name"]) for r in data["result"]["records"] if r.get("service_name"))


def compute_source_health(today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    start = today - timedelta(days=WINDOW_DAYS - 1)  # inclusive 30-day window
    py_start, py_end = start - timedelta(days=365), today - timedelta(days=365)

    # One pass over every encampment year file: `through` needs full history, and the
    # window counts are date-filtered by _window anyway, so a second windowed read is redundant.
    enc_type_full, enc_queue_full = _encampment_partition(_legacy_year_files("encampments_v2"))

    sources: dict[str, Any] = {}
    for key, (kind, sel, coverage) in SOURCES.items():
        if kind == "ckan_legacy" and sel[0] == "encampments":
            route = sel[1]  # "type" | "queue"
            full_days = enc_type_full if route == "type" else enc_queue_full
            cur = _window(full_days, start, today)
            prior = _window(full_days, py_start, py_end)
            through = full_days[-1] if full_days else ""
        elif kind == "ckan_legacy":
            dataset, type_name = sel
            full_days = _legacy_days(dataset, type_name)
            cur = _window(full_days, start, today)
            prior = _window(full_days, py_start, py_end)
            through = full_days[-1] if full_days else ""
        elif kind == "ckan_creatio":
            days = _creatio_days(sel[0])
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
            "coverage": coverage,
        }
    layers: dict[str, Any] = {}
    notes: list[str] = []
    for layer, keys in LAYER_SOURCES.items():
        coverage_keys = [k for k in keys if SOURCES[k][2]]
        statuses = [sources[k]["status"] for k in coverage_keys]
        status = layer_status(statuses)
        through = max((sources[k]["through"] for k in coverage_keys), default="")
        latest_report = max((sources[k]["through"] for k in keys), default="")
        # Only a *stale* layer (no coverage source reporting recently) is "disrupted since"
        # the day after its last coverage report. "degraded" means reports still arrive at
        # reduced volume, so no disruption date is claimed for it.
        disrupted_since = (
            (date.fromisoformat(through) + timedelta(days=1)).isoformat() if status == "stale" and through else None
        )
        layers[layer] = {
            "status": status,
            "through": through,
            "latest_report": latest_report,
            "disrupted_since": disrupted_since,
            "sources": keys,
            "coverage_sources": coverage_keys,
        }
        if status != "ok":
            notes.append(f"{layer}: {status} (through {through or 'never'})")
    names = _creatio_service_names()
    if not names:
        notes.append("Creatio service-name discovery returned nothing (CKAN distinct query failed)")
    known = storage.read_json("metadata/creatio_service_names.json")
    new_names = sorted(set(names) - set(known)) if isinstance(known, list) else []
    if names:
        storage.write_json("metadata/creatio_service_names.json", names)
    if new_names:
        notes.append(f"New Creatio service names: {', '.join(new_names)}")
    alerts: list[str] = []
    needle_names = [name for name in new_names if re.search(r"needle|syringe|sharp", name, re.IGNORECASE)]
    if needle_names:
        alert = f"Needle intake may have migrated: {', '.join(needle_names)} — add scraper slug + NEEDLE mapping"
        alerts.append(alert)
        notes.append(alert)
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
        "layers": layers,
        "creatio_service_names": names,
        "new_service_names": new_names,
        "alerts": alerts,
        "notes": notes,
    }


def write_source_health(health: dict[str, Any]) -> None:
    storage.write_json("metadata/source_health.json", health)
    logger.info("Source health: %s", {k: v["status"] for k, v in health["layers"].items()})
