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
