"""Load scraped Open311 data from S3 for bulk description enrichment."""

import logging
import re
from datetime import date
from typing import Any

from pipeline import storage
from pipeline.config import OPEN311_SCRAPER_PREFIX

logger = logging.getLogger(__name__)

# Pattern to extract date from S3 key like "open311/street-cleaning/2024-01-15.json"
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.json$")


def load_descriptions_from_s3(
    slugs: list[str],
    start_date: date,
    end_date: date,
) -> dict[str, dict[str, str | None]]:
    """Load scraped Open311 records from S3.

    Returns {service_request_id: {description, media_url, status_notes}}.
    """
    result: dict[str, dict[str, str | None]] = {}
    total_loaded = 0

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
                sr_id = record.get("service_request_id")
                if not sr_id:
                    continue

                result[str(sr_id)] = {
                    "description": record.get("description"),
                    "media_url": record.get("media_url"),
                    "status_notes": record.get("status_notes"),
                }
                total_loaded += 1

    logger.info("Loaded %d Open311 descriptions from S3 across %d slugs", total_loaded, len(slugs))
    return result


def normalize_open311_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert Open311 API fields to CKAN-like format for clean().

    Maps Open311 field names to the column names the pipeline expects from CKAN.
    Used for Phase 2 "Other" ticket ingestion where we have no CKAN equivalent.
    """
    return {
        "case_enquiry_id": record.get("service_request_id", ""),
        "open_dt": record.get("requested_datetime", ""),
        "closed_dt": record.get("updated_datetime", ""),
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
