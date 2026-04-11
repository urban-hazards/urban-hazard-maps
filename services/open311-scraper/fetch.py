"""Fetch all Boston Open311 tickets and store raw JSON in S3.

Pulls ALL 16 service types exposed by the BOS:311 app. Each type gets its
own S3 prefix (open311/{slug}/YYYY-MM-DD.json) so data is organized and
independently resumable.

Why we pull from the API when CKAN bulk data exists:
  1. "Other" (General Request) tickets are MISSING from CKAN entirely — 142k+ invisible tickets
  2. CKAN strips citizen descriptions from ALL types — the free-text field is gone
  3. CKAN strips ALL photos — the submitted_photo column is universally empty
  4. CKAN strips staff status notes — only a truncated closure_reason survives

The API is the only source of the actual human-written reports and photo evidence.

API constraints (from https://boston2-production.spotmobile.net/open311/docs):
  - 10 requests per minute (unauthenticated)
  - 100 results per page max
  - 429 response includes Retry-After header
  - 90-day max date range (we use single days, so N/A)

Usage:
    python fetch.py                        # fetch all types, all days
    python fetch.py --type other           # fetch only "Other" tickets
    python fetch.py --type needles         # fetch only needle tickets
    python fetch.py --start 2025-01-01     # fetch from a specific date
    python fetch.py --dry-run              # show plan without fetching
"""

import argparse
import json
import logging
import math
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import boto3

# --- Config from env (same env vars as the main pipeline) ---

BUCKET = os.environ.get("BUCKET", "")
S3_ACCESS_KEY = os.environ.get("ACCESS_KEY_ID", "")
S3_SECRET_KEY = os.environ.get("SECRET_ACCESS_KEY", "")
S3_ENDPOINT = os.environ.get("ENDPOINT", "")
S3_REGION = os.environ.get("REGION", "us-east-1")

# --- Open311 API ---

OPEN311_BASE = "https://boston2-production.spotmobile.net/open311/v2"
START_DATE = "2023-01-01"
UA = "BostonHazardResearch/1.0 (public-health-research)"

# Service types to scrape from the Open311 API.
#
# NOTE: The /services.json endpoint lists 16 types, but 4 use "input.*" prefix
# codes (e.g. "input.Litter") that are BOS:311 app form identifiers — they tag
# zero stored records. Real records use colon-delimited Subject:Reason:Type
# codes. The correct codes below were verified against CKAN and live API queries.
# See docs/open311-service-codes.md for the full mapping.
#
# slug -> (service_code, human_name)
SERVICE_TYPES: dict[str, tuple[str, str]] = {
    "other": (
        "Mayor's 24 Hour Hotline:General Request:General Request",
        "Other (General Request)",
    ),
    "needles": (
        "Mayor's 24 Hour Hotline:Needle Program:Needle Pickup",
        "Needle Cleanup",
    ),
    "encampments": (
        "Mayor's 24 Hour Hotline:Quality of Life:Encampments",
        "Encampments",
    ),
    "potholes": (
        "Public Works Department:Highway Maintenance:Request for Pothole Repair",
        "Pothole Repair",
    ),
    "sidewalks": (
        "Public Works Department:Highway Maintenance:Sidewalk Repair (Make Safe)",
        "Broken Sidewalk",
    ),
    "dead-animals": (
        "Public Works Department:Street Cleaning:Pick up Dead Animal",
        "Dead Animal Pickup",
    ),
    "graffiti": (
        "Property Management:Graffiti:Graffiti Removal",
        "Graffiti Removal",
    ),
    "graffiti-pwd": (
        "Public Works Department:Highway Maintenance:PWD Graffiti",
        "PWD Graffiti",
    ),
    "litter-baskets": (
        "Public Works Department:Highway Maintenance:Empty Litter Basket",
        "Empty Litter Basket",
    ),
    "rodents": (
        "Inspectional Services:Environmental Services:Rodent Activity",
        "Rodent Activity",
    ),
    "trash-cans": (
        "Inspectional Services:Environmental Services:Overflowing or Un-kept Dumpster",
        "Overflowing or Un-kept Dumpster",
    ),
    "abandoned-vehicles": (
        "Transportation - Traffic Division:Enforcement & Abandoned Vehicles:Abandoned Vehicles",
        "Abandoned Vehicle",
    ),
    "parking": (
        "Transportation - Traffic Division:Enforcement & Abandoned Vehicles:Parking Enforcement",
        "Illegal Parking",
    ),
    "traffic-signals": (
        "Transportation - Traffic Division:Signs & Signals:Traffic Signal Inspection",
        "Traffic Signal",
    ),
    "signs": (
        "Transportation - Traffic Division:Signs & Signals:Sign Repair",
        "Damaged Sign",
    ),
    "abandoned-bikes": (
        "Mayor's 24 Hour Hotline:Abandoned Bicycle:Abandoned Bicycle",
        "Abandoned Bicycle",
    ),
    "illegal-trash": (
        "Public Works Department:Code Enforcement:Improper Storage of Trash (Barrels)",
        "Residential Trash out Illegally",
    ),
    "street-cleaning": (
        "Public Works Department:Street Cleaning:Requests for Street Cleaning",
        "Requests for Street Cleaning",
    ),
}

# --- Rate limiting (API allows 10 req/min = 1 every 6s) ---

DELAY = 7.0
MAX_DELAY = 120
MAX_RETRIES = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def get_s3_client():
    kwargs = {
        "service_name": "s3",
        "region_name": S3_REGION,
    }
    if S3_ACCESS_KEY:
        kwargs["aws_access_key_id"] = S3_ACCESS_KEY
    if S3_SECRET_KEY:
        kwargs["aws_secret_access_key"] = S3_SECRET_KEY
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
    return boto3.client(**kwargs)


def list_existing_days(s3, prefix: str) -> set[str]:
    """List day files already in S3 under a given prefix."""
    existing = set()
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                day_str = key.removeprefix(prefix).removesuffix(".json")
                if len(day_str) == 10:
                    existing.add(day_str)
    except Exception as e:
        log.warning("Could not list S3 keys at %s: %s", prefix, e)
    return existing


def save_day(s3, prefix: str, day: date, records: list[dict]) -> None:
    """Write a day's records to S3 with record count in metadata."""
    key = f"{prefix}{day}.json"
    body = json.dumps(records, separators=(",", ":"))
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
        Metadata={"record-count": str(len(records))},
    )


def verify_day(s3, prefix: str, day: date, expected_count: int) -> bool:
    """Verify a saved day file has the right record count."""
    key = f"{prefix}{day}.json"
    try:
        resp = s3.head_object(Bucket=BUCKET, Key=key)
        stored_count = resp.get("Metadata", {}).get("record-count")
        if stored_count and int(stored_count) != expected_count:
            log.warning("  MISMATCH %s: expected %d, got %s", day, expected_count, stored_count)
            return False
        return True
    except Exception:
        return False


def _do_request(url: str) -> tuple[list[dict] | None, int | None]:
    """Make a single HTTP request. Returns (data, retry_after_seconds)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()), None
    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry_after = e.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else 60
            return None, wait
        raise


def fetch_day(day: date, service_code: str, delay: float) -> tuple[list[dict], float]:
    """Fetch all tickets for a single day and service type with pagination."""
    all_records = []
    page = 1

    while True:
        params = urllib.parse.urlencode({
            "start_date": f"{day}T00:00:00Z",
            "end_date": f"{day}T23:59:59Z",
            "service_code": service_code,
            "per_page": 100,
            "page": page,
        })
        url = f"{OPEN311_BASE}/requests.json?{params}"

        data = None
        for attempt in range(MAX_RETRIES):
            try:
                data, retry_after = _do_request(url)
            except Exception as e:
                log.error("  ERROR %s page %d: %s (discarding %d partial records)",
                          day, page, e, len(all_records))
                return [], delay

            if data is not None:
                break

            wait = min(retry_after or 60, MAX_DELAY)
            log.info("  RATE LIMITED on %s page %d (attempt %d/%d), Retry-After: %ds",
                     day, page, attempt + 1, MAX_RETRIES, wait)
            time.sleep(wait)
        else:
            log.warning("  GIVING UP on %s after %d retries (will retry next run)", day, MAX_RETRIES)
            return [], delay

        if not data:
            break

        all_records.extend(data)

        if len(data) >= 100:
            page += 1
            time.sleep(delay)
        else:
            break

    return all_records, delay


def fetch_type(
    s3, slug: str, service_code: str, name: str,
    start: date, end: date, delay: float, dry_run: bool,
) -> dict:
    """Fetch all days for a single service type. Returns run stats."""
    prefix = f"open311/{slug}/"

    existing = list_existing_days(s3, prefix)
    days_needed = []
    current = start
    while current <= end:
        if str(current) not in existing:
            days_needed.append(current)
        current += timedelta(days=1)
    days_needed.reverse()

    total_days = (end - start).days + 1
    est_minutes = len(days_needed) * delay / 60

    log.info("[%s] %s — %d/%d days needed (est. %.0f min)",
             slug, name, len(days_needed), total_days, est_minutes)

    if dry_run or not days_needed:
        return {"slug": slug, "name": name, "fetched": 0, "skipped": 0, "existing": len(existing)}

    total_records = 0
    skipped = 0
    consecutive_empty = 0
    EMPTY_BAILOUT = 90  # skip type after 90 consecutive empty days (~3 months)

    for i, day in enumerate(days_needed):
        records, delay = fetch_day(day, service_code, delay)

        if records:
            save_day(s3, prefix, day, records)
            if not verify_day(s3, prefix, day, len(records)):
                s3.delete_object(Bucket=BUCKET, Key=f"{prefix}{day}.json")
                skipped += 1
            else:
                total_records += len(records)
                consecutive_empty = 0
                if len(records) > 0:
                    log.info("  [%s] %s: %d tickets (total: %d, %d/%d)",
                             slug, day, len(records), total_records, i + 1, len(days_needed))
        else:
            skipped += 1
            consecutive_empty += 1

        if consecutive_empty >= EMPTY_BAILOUT and total_records == 0:
            log.error("  [%s] BAILOUT: %d consecutive empty days with 0 total records — "
                      "service_code '%s' likely wrong. Skipping remaining %d days.",
                      slug, consecutive_empty, service_code, len(days_needed) - i - 1)
            break

        if i > 0 and i % 100 == 0:
            log.info("  [%s] PROGRESS: %d/%d days, %d records, %d skipped",
                     slug, i, len(days_needed), total_records, skipped)

        time.sleep(delay)

    return {
        "slug": slug,
        "name": name,
        "fetched": total_records,
        "days_attempted": len(days_needed),
        "skipped": skipped,
        "existing": len(existing),
    }


def _fetch_api_count(day: date, service_code: str, delay: float) -> tuple[int, float]:
    """Fetch the actual record count for a day from the API.

    Fetches all records and counts them (no shortcut for count-only).
    Returns (count, updated_delay).
    """
    records, delay = fetch_day(day, service_code, delay)
    return len(records), delay


def _verify_type(
    s3,
    slug: str,
    service_code: str,
    name: str,
    start: date,
    end: date,
    delay: float,
    sample_rate: float,
) -> dict:
    """Run verification checks on existing scraped data for one type.

    Checks:
      1. Gap detection — find missing days, re-fetch them
      2. Record count verification — compare stored vs API counts
      3. Cross-day consistency — flag days far below neighbors' average
    """
    prefix = f"open311/{slug}/"
    existing = list_existing_days(s3, prefix)

    # Build full date range
    all_days: list[date] = []
    current = start
    while current <= end:
        all_days.append(current)
        current += timedelta(days=1)

    stats = {
        "slug": slug,
        "name": name,
        "total_days_in_range": len(all_days),
        "existing_days": len(existing),
        "gaps_found": 0,
        "gaps_filled": 0,
        "suspicious_zeros": 0,
        "partial_detected": 0,
        "count_verified_ok": 0,
        "count_mismatch": 0,
        "consistency_flagged": 0,
    }

    # --- Check 1: Gap detection (missing days) ---
    missing_days = [d for d in all_days if str(d) not in existing]
    stats["gaps_found"] = len(missing_days)
    log.info("[%s] Gap detection: %d missing days out of %d", slug, len(missing_days), len(all_days))

    for day in missing_days:
        records, delay = fetch_day(day, service_code, delay)
        if records:
            save_day(s3, prefix, day, records)
            stats["gaps_filled"] += 1
            log.info("  [%s] Gap filled: %s (%d records)", slug, day, len(records))
        else:
            stats["suspicious_zeros"] += 1
            log.warning("  [%s] Suspicious zero: %s (no records from API)", slug, day)
        time.sleep(delay)

    # Refresh existing days after gap filling
    existing = list_existing_days(s3, prefix)

    # --- Check 2: Record count verification ---
    existing_sorted = sorted(existing)
    if sample_rate < 1.0:
        sample_size = max(1, int(len(existing_sorted) * sample_rate))
        days_to_check = random.sample(existing_sorted, sample_size)
        log.info("[%s] Record count check: sampling %d/%d days (%.0f%%)",
                 slug, len(days_to_check), len(existing_sorted), sample_rate * 100)
    else:
        days_to_check = existing_sorted
        log.info("[%s] Record count check: full scan of %d days", slug, len(days_to_check))

    for day_str in days_to_check:
        day = date.fromisoformat(day_str)
        key = f"{prefix}{day}.json"

        # Get stored count from metadata
        try:
            resp = s3.head_object(Bucket=BUCKET, Key=key)
            stored_count_str = resp.get("Metadata", {}).get("record-count")
            if stored_count_str is None:
                continue
            stored_count = int(stored_count_str)
        except Exception:
            continue

        # Fetch actual count from API
        api_count, delay = _fetch_api_count(day, service_code, delay)
        time.sleep(delay)

        if api_count == 0:
            # API returned nothing — can't verify, skip
            continue

        if stored_count < api_count:
            # Partial data — delete so next regular run re-fetches
            s3.delete_object(Bucket=BUCKET, Key=key)
            stats["partial_detected"] += 1
            log.warning("  [%s] PARTIAL %s: stored %d < API %d — deleted for re-fetch",
                        slug, day, stored_count, api_count)
        elif stored_count > api_count:
            log.info("  [%s] OVER-COUNT %s: stored %d > API %d (API may have deduped)",
                     slug, day, stored_count, api_count)
            stats["count_verified_ok"] += 1
        else:
            stats["count_verified_ok"] += 1

    # --- Check 3: Cross-day consistency ---
    # Load record counts for all existing days to compute rolling averages
    day_counts: dict[str, int] = {}
    for day_str in existing_sorted:
        key = f"{prefix}{day_str}.json"
        try:
            resp = s3.head_object(Bucket=BUCKET, Key=key)
            count_str = resp.get("Metadata", {}).get("record-count")
            if count_str is not None:
                day_counts[day_str] = int(count_str)
        except Exception:
            continue

    if len(day_counts) >= 7:
        sorted_days = sorted(day_counts.keys())
        counts_list = [day_counts[d] for d in sorted_days]

        for i, day_str in enumerate(sorted_days):
            # Use a 7-day window centered on this day
            window_start = max(0, i - 3)
            window_end = min(len(counts_list), i + 4)
            neighbors = counts_list[window_start:i] + counts_list[i + 1:window_end]

            if not neighbors:
                continue

            avg = sum(neighbors) / len(neighbors)
            if avg > 0 and day_counts[day_str] <= avg * 0.5:
                stats["consistency_flagged"] += 1
                log.warning("  [%s] CONSISTENCY %s: %d records vs %.0f neighbor avg (%.0f%%)",
                            slug, day_str, day_counts[day_str], avg,
                            day_counts[day_str] / avg * 100 if avg > 0 else 0)

    return stats


def run_verify(
    s3,
    types_to_verify: dict[str, tuple[str, str]],
    start: date,
    end: date,
    delay: float,
    sample_rate: float,
) -> None:
    """Run verify mode across all requested types and write report."""
    all_stats = []
    for slug, (service_code, name) in types_to_verify.items():
        log.info("=== Verifying [%s] %s ===", slug, name)
        stats = _verify_type(s3, slug, service_code, name, start, end, delay, sample_rate)
        all_stats.append(stats)

        log.info("[%s] Summary: %d gaps found, %d filled, %d suspicious zeros, "
                 "%d partial deleted, %d verified OK, %d consistency flagged",
                 slug, stats["gaps_found"], stats["gaps_filled"],
                 stats["suspicious_zeros"], stats["partial_detected"],
                 stats["count_verified_ok"], stats["consistency_flagged"])

    # Write report
    report = {
        "run_time": datetime.utcnow().isoformat() + "Z",
        "date_range": {"start": str(start), "end": str(end)},
        "sample_rate": sample_rate,
        "types": all_stats,
        "totals": {
            "gaps_found": sum(s["gaps_found"] for s in all_stats),
            "gaps_filled": sum(s["gaps_filled"] for s in all_stats),
            "suspicious_zeros": sum(s["suspicious_zeros"] for s in all_stats),
            "partial_detected": sum(s["partial_detected"] for s in all_stats),
            "count_verified_ok": sum(s["count_verified_ok"] for s in all_stats),
            "consistency_flagged": sum(s["consistency_flagged"] for s in all_stats),
        },
    }

    key = "open311/verify_report.json"
    body = json.dumps(report, indent=2, default=str)
    s3.put_object(Bucket=BUCKET, Key=key, Body=body.encode("utf-8"), ContentType="application/json")
    log.info("Verify report written to s3://%s/%s", BUCKET, key)


def main():
    parser = argparse.ArgumentParser(description="Fetch Boston Open311 tickets to S3")
    parser.add_argument("--start", default=START_DATE, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (default: yesterday)")
    parser.add_argument("--type", default=None, help="Slug of a single type to fetch (e.g. 'needles', 'other')")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without fetching")
    parser.add_argument("--delay", type=float, default=DELAY, help="Delay between requests in seconds")
    parser.add_argument("--verify", action="store_true", help="Verify existing scraped data integrity")
    parser.add_argument("--sample", type=float, default=None,
                        help="Sample rate for verify mode (0.0-1.0, e.g. 0.1 for 10%%)")
    parser.add_argument("--full", action="store_true", help="Full verify (check every day)")
    args = parser.parse_args()

    if not BUCKET:
        log.error("BUCKET env var not set. Need S3/Tigris credentials.")
        sys.exit(1)

    s3 = get_s3_client()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)

    # Determine which types to fetch
    if args.type:
        if args.type not in SERVICE_TYPES:
            log.error("Unknown type: %s (available: %s)", args.type, ", ".join(SERVICE_TYPES.keys()))
            sys.exit(1)
        types_to_fetch = {args.type: SERVICE_TYPES[args.type]}
    else:
        types_to_fetch = SERVICE_TYPES

    log.info("Date range: %s to %s", start, end)
    log.info("Types: %s", ", ".join(types_to_fetch.keys()))

    # --- Verify mode ---
    if args.verify:
        if args.sample is not None:
            sample_rate = max(0.0, min(1.0, args.sample))
        elif args.full:
            sample_rate = 1.0
        else:
            sample_rate = 1.0  # default to full on first run
        run_verify(s3, types_to_fetch, start, end, args.delay, sample_rate)
        return

    # --- Normal fetch mode ---
    all_stats = []
    for slug, (service_code, name) in types_to_fetch.items():
        stats = fetch_type(s3, slug, service_code, name, start, end, args.delay, args.dry_run)
        all_stats.append(stats)

    # Write manifest
    manifest = {
        "last_run": datetime.utcnow().isoformat() + "Z",
        "date_range": {"start": str(start), "end": str(end)},
        "types": all_stats,
    }
    key = "open311/manifest.json"
    body = json.dumps(manifest, indent=2, default=str)
    s3.put_object(Bucket=BUCKET, Key=key, Body=body.encode("utf-8"), ContentType="application/json")

    total_fetched = sum(s["fetched"] for s in all_stats)
    total_skipped = sum(s.get("skipped", 0) for s in all_stats)
    log.info("Done. %d records fetched across %d types, %d days skipped.",
             total_fetched, len(all_stats), total_skipped)


if __name__ == "__main__":
    main()
