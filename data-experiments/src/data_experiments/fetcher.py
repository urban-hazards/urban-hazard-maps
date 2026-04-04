"""Fetch 311 records from CKAN API."""

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from data_experiments.config import (
    CACHE_DIR,
    CKAN_BASE,
    RESOURCE_IDS,
    STREET_CLEANING_TYPES,
    UA,
)


def _api_get(url: str, timeout: int = 120) -> dict[str, Any] | None:
    """GET a CKAN API endpoint, return parsed JSON or None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ✗ API error: {e}")
        return None


def fetch_records_sql(
    resource_id: str,
    types: set[str],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Use CKAN datastore_search_sql to pull rows matching given types."""
    type_clauses = " OR ".join(f"\"type\" = '{t}'" for t in types)
    sql = f'SELECT * FROM "{resource_id}" WHERE ({type_clauses})'
    if limit:
        sql += f" LIMIT {limit}"
    url = f"{CKAN_BASE}/datastore_search_sql?sql={urllib.parse.quote(sql)}"
    data = _api_get(url)
    if data and data.get("success"):
        return data["result"]["records"]
    return []


def fetch_records_paged(
    resource_id: str,
    types: set[str],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Fallback: page through datastore_search with TYPE filter."""
    all_records: list[dict[str, Any]] = []
    for record_type in types:
        offset = 0
        page_size = 5000
        while True:
            filters = json.dumps({"type": record_type})
            url = (
                f"{CKAN_BASE}/datastore_search"
                f"?resource_id={resource_id}"
                f"&filters={urllib.parse.quote(filters)}"
                f"&limit={page_size}&offset={offset}"
            )
            data = _api_get(url)
            if not data or not data.get("success"):
                break
            records = data["result"]["records"]
            all_records.extend(records)
            if len(records) < page_size:
                break
            offset += page_size
            if limit and len(all_records) >= limit:
                break
    if limit:
        return all_records[:limit]
    return all_records


def fetch_year(
    year: int,
    types: set[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch records for a given year and set of types."""
    if types is None:
        types = STREET_CLEANING_TYPES

    rid = RESOURCE_IDS.get(year)
    if not rid:
        print(f"  ⚠ No resource ID for {year}, skipping")
        return []

    type_names = ", ".join(types)
    print(f"  → {year} [{type_names}]: trying SQL API...", end=" ", flush=True)
    records = fetch_records_sql(rid, types, limit=limit)
    if records:
        print(f"got {len(records)} records")
        return records

    print("retrying with paged search...", end=" ", flush=True)
    records = fetch_records_paged(rid, types, limit=limit)
    print(f"got {len(records)} records")
    return records


def fetch_and_cache(
    years: list[int],
    types: set[str] | None = None,
    limit_per_year: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch records for multiple years, cache to disk."""
    if types is None:
        types = STREET_CLEANING_TYPES

    type_key = "_".join(sorted(t.replace(" ", "_").replace("/", "_").lower() for t in types))
    cache_file = CACHE_DIR / f"records_{type_key}_{'_'.join(str(y) for y in years)}.json"

    if cache_file.exists():
        print(f"  ✓ Loading cached records from {cache_file}")
        with open(cache_file) as f:
            return json.load(f)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    all_records: list[dict[str, Any]] = []
    for year in years:
        records = fetch_year(year, types=types, limit=limit_per_year)
        all_records.extend(records)

    with open(cache_file, "w") as f:
        json.dump(all_records, f, indent=2)
    print(f"  ✓ Cached {len(all_records)} records to {cache_file}")

    return all_records


def get_record_count(resource_id: str, types: set[str]) -> int | None:
    """Get the count of records matching types without fetching all data."""
    type_clauses = " OR ".join(f"\"type\" = '{t}'" for t in types)
    sql = f'SELECT COUNT(*) as count FROM "{resource_id}" WHERE ({type_clauses})'
    url = f"{CKAN_BASE}/datastore_search_sql?sql={urllib.parse.quote(sql)}"
    data = _api_get(url)
    if data and data.get("success"):
        records = data["result"]["records"]
        if records:
            return int(records[0]["count"])
    return None
