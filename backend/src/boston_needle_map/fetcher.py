"""CKAN API data fetching for Boston 311 records."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from boston_needle_map.config import (
    CKAN_BASE,
    ENCAMPMENT_START_YEAR,
    ENCAMPMENT_TYPES,
    NEEDLE_TYPES,
    RESOURCE_IDS,
    UA,
)


def _api_get(url: str) -> dict[str, Any] | None:
    """GET a CKAN API endpoint, return parsed JSON or None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  ✗ API error: {e}")
        return None


def fetch_needle_records_sql(resource_id: str) -> list[dict[str, Any]]:
    """Use CKAN datastore_search_sql to pull only needle rows (fast)."""
    type_clauses = " OR ".join(f"\"type\" = '{t}'" for t in NEEDLE_TYPES)
    sql = f'SELECT * FROM "{resource_id}" WHERE ({type_clauses}) OR LOWER("type") LIKE \'%needle%\''
    url = f"{CKAN_BASE}/datastore_search_sql?sql={urllib.parse.quote(sql)}"
    data = _api_get(url)
    if data and data.get("success"):
        return data["result"]["records"]  # type: ignore[no-any-return]
    return []


def fetch_needle_records_paged(resource_id: str) -> list[dict[str, Any]]:
    """Fallback: page through datastore_search with a TYPE filter."""
    all_records: list[dict[str, Any]] = []
    for needle_type in NEEDLE_TYPES:
        offset = 0
        limit = 5000
        while True:
            filters = json.dumps({"type": needle_type})
            url = (
                f"{CKAN_BASE}/datastore_search"
                f"?resource_id={resource_id}"
                f"&filters={urllib.parse.quote(filters)}"
                f"&limit={limit}&offset={offset}"
            )
            data = _api_get(url)
            if not data or not data.get("success"):
                break
            records = data["result"]["records"]
            all_records.extend(records)
            if len(records) < limit:
                break
            offset += limit
    return all_records


def fetch_year(year: int) -> list[dict[str, Any]]:
    """Fetch needle records for a given year."""
    rid = RESOURCE_IDS.get(year)
    if not rid:
        print(f"  ⚠ No resource ID for {year}, skipping")
        return []

    print(f"  → {year}: trying SQL API...", end=" ", flush=True)
    records = fetch_needle_records_sql(rid)
    if records:
        print(f"got {len(records)} records")
        return records

    print("retrying with paged search...", end=" ", flush=True)
    records = fetch_needle_records_paged(rid)
    print(f"got {len(records)} records")
    return records


# --- Encampment fetching ---


def _fetch_type_records_sql(resource_id: str, types: set[str]) -> list[dict[str, Any]]:
    """Use CKAN datastore_search_sql to pull rows matching given types."""
    type_clauses = " OR ".join(f"\"type\" = '{t}'" for t in types)
    sql = f'SELECT * FROM "{resource_id}" WHERE ({type_clauses})'
    url = f"{CKAN_BASE}/datastore_search_sql?sql={urllib.parse.quote(sql)}"
    data = _api_get(url)
    if data and data.get("success"):
        return data["result"]["records"]  # type: ignore[no-any-return]
    return []


def _fetch_type_records_paged(resource_id: str, types: set[str]) -> list[dict[str, Any]]:
    """Fallback: page through datastore_search with a TYPE filter."""
    all_records: list[dict[str, Any]] = []
    for record_type in types:
        offset = 0
        limit = 5000
        while True:
            filters = json.dumps({"type": record_type})
            url = (
                f"{CKAN_BASE}/datastore_search"
                f"?resource_id={resource_id}"
                f"&filters={urllib.parse.quote(filters)}"
                f"&limit={limit}&offset={offset}"
            )
            data = _api_get(url)
            if not data or not data.get("success"):
                break
            records = data["result"]["records"]
            all_records.extend(records)
            if len(records) < limit:
                break
            offset += limit
    return all_records


def fetch_encampment_year(year: int) -> list[dict[str, Any]]:
    """Fetch encampment records for a given year."""
    if year < ENCAMPMENT_START_YEAR:
        return []

    rid = RESOURCE_IDS.get(year)
    if not rid:
        print(f"  ⚠ No resource ID for {year}, skipping")
        return []

    print(f"  → {year} encampments: trying SQL API...", end=" ", flush=True)
    records = _fetch_type_records_sql(rid, ENCAMPMENT_TYPES)
    if records:
        print(f"got {len(records)} records")
        return records

    print("retrying with paged search...", end=" ", flush=True)
    records = _fetch_type_records_paged(rid, ENCAMPMENT_TYPES)
    print(f"got {len(records)} records")
    return records
