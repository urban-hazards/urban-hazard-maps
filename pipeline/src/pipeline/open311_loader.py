"""Load scraped Open311 data from S3 for bulk description enrichment."""

import logging
import re
from collections.abc import Iterator
from datetime import date
from typing import Any

from pipeline import storage
from pipeline.config import OPEN311_SCRAPER_PREFIX

logger = logging.getLogger(__name__)

# Pattern to extract date from S3 key like "open311/street-cleaning/2024-01-15.json"
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.json$")


def _iter_day_records(
    slugs: list[str],
    start_date: date,
    end_date: date,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (slug, record) pairs from S3 day-files in the date range.

    Shared iteration logic for both description-only and full-record loaders.
    Skips records without a service_request_id.
    """
    for slug in slugs:
        prefix = f"{OPEN311_SCRAPER_PREFIX}/{slug}/"
        keys = storage.list_keys(prefix)

        day_keys: list[str] = []
        for key in keys:
            match = _DATE_RE.search(key)
            if not match:
                continue
            key_date = date.fromisoformat(match.group(1))
            if start_date <= key_date <= end_date:
                day_keys.append(key)

        logger.info("Loading %d day-files from s3 for slug=%s", len(day_keys), slug)

        for key in day_keys:
            records = storage.read_json(key)
            if not records or not isinstance(records, list):
                continue

            for record in records:
                if not record.get("service_request_id"):
                    continue
                yield slug, record


def load_descriptions_from_s3(
    slugs: list[str],
    start_date: date,
    end_date: date,
) -> dict[str, dict[str, str | None]]:
    """Load scraped Open311 records from S3.

    Returns {service_request_id: {description, media_url, status_notes}}.
    """
    result: dict[str, dict[str, str | None]] = {}

    for _slug, record in _iter_day_records(slugs, start_date, end_date):
        result[str(record["service_request_id"])] = {
            "description": record.get("description"),
            "media_url": record.get("media_url"),
            "status_notes": record.get("status_notes"),
        }

    logger.info("Loaded %d Open311 descriptions from S3 across %d slugs", len(result), len(slugs))
    return result


def load_records_from_s3(
    slugs: list[str],
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Return raw Open311 records across given slugs and inclusive date range.

    Iterates `open311/{slug}/YYYY-MM-DD.json`. Missing day files are logged
    and skipped. Malformed JSON raises (fail loud — silent corruption is worse
    than a gap). Each returned dict carries `_open311_slug` for traceability.
    """
    result: list[dict[str, Any]] = []

    for slug, record in _iter_day_records(slugs, start_date, end_date):
        result.append({**record, "_open311_slug": slug})

    logger.info("Loaded %d raw Open311 records from S3 across %d slugs", len(result), len(slugs))
    return result


def normalize_open311_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert Open311 API fields to CKAN-like format for clean().

    Maps Open311 field names to the column names the pipeline expects from CKAN.
    Used for "Other" ticket ingestion where we have no CKAN equivalent.

    `updated_datetime` is only mapped to `closed_dt` when `status == "closed"`.
    Open311's `updated_datetime` reflects any modification (reclassification,
    note edits), not just closure — copying it onto open records would create
    spurious closed_dt values and corrupt response-time stats.
    """
    # Gate closed_dt on actual closure status
    status = (record.get("status") or "").strip().lower()
    closed_dt = record.get("updated_datetime", "") if status == "closed" else ""

    return {
        "case_enquiry_id": record.get("service_request_id", ""),
        "open_dt": record.get("requested_datetime", ""),
        "closed_dt": closed_dt,
        "case_title": record.get("service_name", ""),
        "subject": record.get("service_name", ""),
        "type": record.get("service_name", ""),
        "queue": record.get("service_code", ""),
        "latitude": record.get("lat"),
        "longitude": record.get("long"),
        "neighborhood": record.get("address", ""),
        "location_street_name": record.get("address", ""),
        "location_zipcode": record.get("zipcode", ""),
        "closure_reason": record.get("status_notes", ""),
        "open311_description": record.get("description"),
    }
