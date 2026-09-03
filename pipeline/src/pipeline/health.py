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

# source key -> (kind, selector).
# kind: "ckan_legacy" (dataset, type) | "ckan_creatio" (service_name,) | "open311" (slug,)
SOURCES: dict[str, tuple[str, tuple[str, ...]]] = {
    "ckan_legacy:Needle Pickup": ("ckan_legacy", ("needles", "Needle Pickup")),
    "ckan_legacy:Encampments": ("ckan_legacy", ("encampments", "Encampments")),
    "ckan_legacy:Requests for Street Cleaning": ("ckan_legacy", ("waste", "Requests for Street Cleaning")),
    "ckan_creatio:Litter & Debris": ("ckan_creatio", ("Litter & Debris",)),
    "ckan_creatio:Park Litter & Debris": ("ckan_creatio", ("Park Litter & Debris",)),
    "open311:needles": ("open311", ("needles",)),
    "open311:encampments": ("open311", ("encampments",)),
    "open311:other": ("open311", ("other",)),
    "open311:other-creatio": ("open311", ("other-creatio",)),
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
            total += len(_rows(f"open311/{slug}/{d}.json"))
    return total, (days[-1] if days else "")


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
