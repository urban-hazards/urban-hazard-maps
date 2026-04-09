"""Fetch all 'Other' (General Request) tickets from Boston Open311 API.

Day-by-day batching to work around the 100-result-per-query cap.
Stores each day as a JSON object in S3 so you can stop and resume.

On first run, backfills from START_DATE to today.
On subsequent runs, only fetches days not already in S3.

Usage (local testing with env vars):
    BUCKET=... ACCESS_KEY_ID=... SECRET_ACCESS_KEY=... ENDPOINT=... python fetch.py

    python fetch.py --start 2025-01-01   # fetch from a specific date
    python fetch.py --dry-run            # show what would be fetched
"""

import argparse
import json
import logging
import os
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

S3_PREFIX = "open311/raw/"  # all raw day files go under this prefix

# --- Open311 API ---

OPEN311_BASE = "https://boston2-production.spotmobile.net/open311/v2"
SERVICE_CODE = "Mayor's 24 Hour Hotline:General Request:General Request"
START_DATE = "2023-01-01"
UA = "BostonHazardResearch/1.0 (public-health-research)"

# --- Rate limiting ---

DELAY = 0.5
MIN_DELAY = 0.3
MAX_DELAY = 60
BACKOFF_FACTOR = 2.0
COOLDOWN_FACTOR = 0.9

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


def list_existing_days(s3) -> set[str]:
    """List day files already in S3 to know what to skip."""
    existing = set()
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=S3_PREFIX):
            for obj in page.get("Contents", []):
                # key like "open311/raw/2023-01-15.json" -> "2023-01-15"
                key = obj["Key"]
                day_str = key.removeprefix(S3_PREFIX).removesuffix(".json")
                if len(day_str) == 10:  # YYYY-MM-DD
                    existing.add(day_str)
    except Exception as e:
        log.warning("Could not list existing S3 keys: %s", e)
    return existing


def save_day(s3, day: date, records: list[dict]) -> None:
    """Write a day's records to S3."""
    key = f"{S3_PREFIX}{day}.json"
    body = json.dumps(records, separators=(",", ":"))
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )


def update_manifest(s3, stats: dict) -> None:
    """Write a summary manifest so the pipeline knows what's available."""
    key = "open311/manifest.json"
    body = json.dumps(stats, indent=2, default=str)
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )


def fetch_day(day: date, current_delay: float) -> tuple[list[dict], float]:
    """Fetch all 'Other' tickets for a single day. Handles pagination and rate limits."""
    all_records = []
    page = 1
    delay = current_delay

    while True:
        start = f"{day}T00:00:00Z"
        end = f"{day}T23:59:59Z"
        params = urllib.parse.urlencode({
            "start_date": start,
            "end_date": end,
            "service_code": SERVICE_CODE,
            "page_size": 500,
            "page": page,
        })
        url = f"{OPEN311_BASE}/requests.json?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                for attempt in range(3):
                    delay = min(delay * BACKOFF_FACTOR, MAX_DELAY)
                    wait = delay * (attempt + 1)
                    log.info("  RATE LIMITED on %s (attempt %d), waiting %.0fs", day, attempt + 1, wait)
                    time.sleep(wait)
                    try:
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            data = json.loads(resp.read())
                        break
                    except urllib.error.HTTPError as retry_e:
                        if retry_e.code != 429:
                            log.error("  ERROR %s page %d: %s", day, page, retry_e)
                            return all_records or [], delay
                    except Exception:
                        pass
                else:
                    log.warning("  STILL LIMITED on %s after 3 retries, skipping", day)
                    return [], delay
            else:
                log.error("  ERROR %s page %d: %s", day, page, e)
                break
        except Exception as e:
            log.error("  ERROR %s page %d: %s", day, page, e)
            break

        if not data:
            break

        delay = max(delay * COOLDOWN_FACTOR, MIN_DELAY)
        all_records.extend(data)

        if len(data) >= 100:
            page += 1
            time.sleep(delay)
        else:
            break

    return all_records, delay


def main():
    parser = argparse.ArgumentParser(description="Fetch Open311 'Other' tickets to S3")
    parser.add_argument("--start", default=START_DATE, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (default: yesterday)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without fetching")
    parser.add_argument("--delay", type=float, default=DELAY, help="Initial delay between requests")
    args = parser.parse_args()

    if not BUCKET:
        log.error("BUCKET env var not set. Need S3/Tigris credentials.")
        sys.exit(1)

    s3 = get_s3_client()

    start = date.fromisoformat(args.start)
    # Default to yesterday so we don't fetch a partial day
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)

    # Check what's already in S3
    log.info("Checking S3 for existing data...")
    existing = list_existing_days(s3)
    log.info("Found %d days already in S3", len(existing))

    # Build list of days to fetch (newest first — recent data is most valuable)
    days_needed = []
    current = start
    while current <= end:
        if str(current) not in existing:
            days_needed.append(current)
        current += timedelta(days=1)
    days_needed.reverse()

    total_days = (end - start).days + 1
    log.info("Date range: %s to %s (%d days)", start, end, total_days)
    log.info("Already in S3: %d days", len(existing))
    log.info("Need to fetch: %d days", len(days_needed))

    if args.dry_run or not days_needed:
        if not days_needed:
            log.info("Nothing to fetch — all caught up!")
        return

    total_records = 0
    current_delay = args.delay

    for i, day in enumerate(days_needed):
        records, current_delay = fetch_day(day, current_delay)

        if records:
            save_day(s3, day, records)
            total_records += len(records)
            log.info("  %s: %d tickets (total: %d, delay: %.1fs)", day, len(records), total_records, current_delay)

        if i > 0 and i % 50 == 0 and not records:
            log.info("  ... %s (%d/%d days done)", day, i, len(days_needed))

        time.sleep(current_delay)

    # Write manifest so the pipeline knows what data is available
    all_days = existing | {str(d) for d in days_needed if True}
    manifest = {
        "last_run": datetime.utcnow().isoformat() + "Z",
        "total_days": len(all_days),
        "date_range": {"start": str(start), "end": str(end)},
        "records_fetched_this_run": total_records,
        "days_fetched_this_run": len(days_needed),
    }
    update_manifest(s3, manifest)

    log.info("Done. %d records fetched across %d days.", total_records, len(days_needed))


if __name__ == "__main__":
    main()
