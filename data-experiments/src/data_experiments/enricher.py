"""Enrich 311 records with Open311 API description field."""

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from data_experiments.config import CACHE_DIR, OPEN311_BASE, UA


def fetch_open311_description(case_id: str) -> str | None:
    """Look up a single ticket's description from the Open311 API."""
    url = f"{OPEN311_BASE}/requests/{case_id}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and data:
                return data[0].get("description")
            elif isinstance(data, dict):
                return data.get("description")
    except Exception:
        pass
    return None


def enrich_records(
    records: list[dict[str, Any]],
    delay: float = 0.2,
    max_records: int | None = None,
    cache_name: str = "enriched",
) -> list[dict[str, Any]]:
    """Enrich records with Open311 descriptions. Caches results incrementally."""
    cache_file = CACHE_DIR / f"{cache_name}_descriptions.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing cache
    description_cache: dict[str, str | None] = {}
    if cache_file.exists():
        with open(cache_file) as f:
            description_cache = json.load(f)
        print(f"  ✓ Loaded {len(description_cache)} cached descriptions")

    to_process = records[:max_records] if max_records else records
    enriched = 0
    skipped = 0
    failed = 0

    for i, record in enumerate(to_process):
        case_id = record.get("case_enquiry_id") or record.get("case_enquiry_id", "")
        if not case_id:
            continue

        case_id = str(case_id)

        if case_id in description_cache:
            record["open311_description"] = description_cache[case_id]
            skipped += 1
            continue

        description = fetch_open311_description(case_id)
        description_cache[case_id] = description
        record["open311_description"] = description

        if description:
            enriched += 1
        else:
            failed += 1

        # Progress update every 50 records
        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1}/{len(to_process)} (enriched: {enriched}, cached: {skipped}, failed: {failed})")
            # Save cache incrementally
            with open(cache_file, "w") as f:
                json.dump(description_cache, f, indent=2)

        time.sleep(delay)

    # Final cache save
    with open(cache_file, "w") as f:
        json.dump(description_cache, f, indent=2)

    print(f"  ✓ Enrichment complete: {enriched} new, {skipped} cached, {failed} failed")
    return to_process
