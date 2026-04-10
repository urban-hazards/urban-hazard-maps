"""Enrich 311 records with Open311 API description field.

Supports two enrichment paths:
  1. Bulk S3 — loads pre-scraped descriptions from open311/{slug}/ day-files
  2. API fallback — fetches individual descriptions for any records not in S3
"""

import contextlib
import json
import logging
import time
import urllib.request
from datetime import date
from typing import Any

from pipeline.config import OPEN311_BASE, UA

logger = logging.getLogger(__name__)


def fetch_open311_description(case_id: str) -> str | None:
    """Look up a single ticket's description from the Open311 API."""
    url = f"{OPEN311_BASE}/requests/{case_id}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and data:
                return data[0].get("description")  # type: ignore[no-any-return]
            elif isinstance(data, dict):
                return data.get("description")
    except Exception:
        pass
    return None


def enrich_records(
    records: list[dict[str, Any]],
    description_cache: dict[str, str | None],
    delay: float = 0.2,
    max_records: int | None = None,
    slugs: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
    """Enrich records with Open311 descriptions.

    Strategy:
      1. If slugs provided, bulk-load descriptions from scraped S3 data
      2. Apply any S3-sourced descriptions to records + update cache
      3. Fall back to individual API lookups for anything still unresolved

    Accepts a description_cache dict and returns (enriched_records, updated_cache).
    The caller is responsible for loading/saving the cache from S3.
    """
    to_process = records[:max_records] if max_records else records

    # --- Phase 1: Bulk S3 lookup ---
    s3_descriptions: dict[str, dict[str, str | None]] = {}
    if slugs:
        from pipeline.open311_loader import load_descriptions_from_s3

        # Determine date range from records
        dates: list[date] = []
        for rec in to_process:
            open_dt = rec.get("open_dt") or rec.get("OPEN_DT") or ""
            if open_dt:
                with contextlib.suppress(ValueError):
                    dates.append(date.fromisoformat(open_dt[:10]))

        if dates:
            start = min(dates)
            end = max(dates)
            s3_descriptions = load_descriptions_from_s3(slugs, start, end)
            logger.info("Loaded %d descriptions from S3 scrape", len(s3_descriptions))

    # --- Phase 2: Apply descriptions ---
    enriched = 0
    from_s3 = 0
    skipped = 0
    failed = 0

    for i, record in enumerate(to_process):
        case_id = record.get("case_enquiry_id") or ""
        if not case_id:
            continue

        case_id = str(case_id)

        # Check in-memory cache first
        if case_id in description_cache:
            record["open311_description"] = description_cache[case_id]
            skipped += 1
            continue

        # Check S3 bulk data
        if case_id in s3_descriptions:
            desc = s3_descriptions[case_id].get("description")
            description_cache[case_id] = desc
            record["open311_description"] = desc
            from_s3 += 1
            enriched += 1
            continue

        # Fall back to individual API lookup
        description = fetch_open311_description(case_id)
        description_cache[case_id] = description
        record["open311_description"] = description

        if description:
            enriched += 1
        else:
            failed += 1

        # Progress update every 50 records
        if (i + 1) % 50 == 0:
            logger.info(
                "  ... %d/%d (enriched: %d, s3: %d, cached: %d, failed: %d)",
                i + 1,
                len(to_process),
                enriched,
                from_s3,
                skipped,
                failed,
            )

        time.sleep(delay)

    logger.info(
        "Enrichment complete: %d new (%d from S3), %d cached, %d failed",
        enriched,
        from_s3,
        skipped,
        failed,
    )
    return to_process, description_cache
