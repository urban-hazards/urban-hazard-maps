#!/usr/bin/env python3
"""Mattress-complaint analysis for /mattress page.

Pulls two sources and writes frontend/src/data/mattress.json:
  1. CKAN 311 bulk export (data.boston.gov) — the `Mattress_Pickup` case type and
     the sanitation/enforcement case types a mattress complaint usually lands in.
  2. Open311 scraper corpora in S3 (open311/{other,illegal-trash,street-cleaning}/)
     — citizen descriptions (CKAN strips these) grepped for mattress mentions.

Run from pipeline/ so the S3 creds in pipeline/.env load:
    cd pipeline && uv run python ../scripts/mattress_analysis.py
"""

from __future__ import annotations

import collections
import concurrent.futures as cf
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
from pipeline.config import RESOURCE_IDS  # noqa: E402

OUT = ROOT / "frontend" / "src" / "data" / "mattress.json"
YEARS = range(2019, datetime.now(tz=UTC).year + 1)
# Case types a mattress complaint lands in when there is no mattress button.
CKAN_TYPES = [
    "Mattress_Pickup",
    "Schedule a Bulk Item Pickup",
    "Missed Trash/Recycling/Yard Waste/Bulk Item",
    "Improper Storage of Trash (Barrels)",
    "Requests for Street Cleaning",
    "Illegal Dumping",
    "CE Collection",
    "Poor Conditions of Property",
]
OPEN311_SLUGS = ["illegal-trash", "street-cleaning", "other"]
MATTRESS_RE = re.compile(r"mattress|matress|box ?spring", re.I)
BOSTON = ZoneInfo("America/New_York")


def local_month(ts: str) -> str:
    """Open311 requested_datetime is UTC ('...Z'); bucket by Boston local month."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts[:7]
    if dt.tzinfo is None:
        return ts[:7]
    return dt.astimezone(BOSTON).strftime("%Y-%m")


def ckan_sql(sql: str) -> list[dict]:
    # NOTE: data.boston.gov's WAF 403s on SUBSTR(); use LEFT(CAST(.. AS TEXT), n).
    url = "https://data.boston.gov/api/3/action/datastore_search_sql?sql=" + urllib.parse.quote(sql)
    with urllib.request.urlopen(url, timeout=120) as resp:
        return json.load(resp)["result"]["records"]


def ckan_monthly_by_type() -> tuple[dict[str, dict[str, int]], str]:
    clauses = " OR ".join(f"\"type\"='{t}'" for t in CKAN_TYPES)
    out: dict[str, dict[str, int]] = collections.defaultdict(dict)
    latest = ""
    for year in YEARS:
        rid = RESOURCE_IDS.get(year)
        if not rid:
            continue
        rows = ckan_sql(
            f'SELECT "type", LEFT(CAST("open_dt" AS TEXT),7) m, COUNT(*) c, '
            f'MAX(CAST("open_dt" AS TEXT)) mx FROM "{rid}" WHERE ({clauses}) GROUP BY 1,2 ORDER BY 1,2'
        )
        for r in rows:
            out[r["type"]][r["m"]] = r["c"]
            latest = max(latest, (r["mx"] or "")[:10])
        print(f"ckan {year}: {len(rows)} rows", file=sys.stderr)
    return dict(out), latest


def ckan_closure_mentions_monthly() -> dict[str, int]:
    """Closure notes mentioning a mattress on non-Mattress_Pickup cases."""
    out: dict[str, int] = collections.Counter()
    for year in YEARS:
        rid = RESOURCE_IDS.get(year)
        if not rid or year < 2022:
            continue
        rows = ckan_sql(
            f'SELECT LEFT(CAST("open_dt" AS TEXT),7) m, COUNT(*) c FROM "{rid}" '
            f"WHERE LOWER(\"closure_reason\") LIKE '%mattress%' AND \"type\"<>'Mattress_Pickup' GROUP BY 1 ORDER BY 1"
        )
        for r in rows:
            out[r["m"]] += r["c"]
    return dict(sorted(out.items()))


def ckan_source_by_type_year() -> dict[str, dict[str, dict[str, int]]]:
    """Intake channel (CKAN `source`: Constituent Call, Citizens Connect App, Self Service, ...)
    per case type per year, 2021 onward."""
    clauses = " OR ".join(f"\"type\"='{t}'" for t in CKAN_TYPES)
    out: dict[str, dict[str, dict[str, int]]] = collections.defaultdict(lambda: collections.defaultdict(dict))
    for year in YEARS:
        rid = RESOURCE_IDS.get(year)
        if not rid or year < 2021:
            continue
        rows = ckan_sql(
            f'SELECT "type", "source", COUNT(*) c FROM "{rid}" WHERE ({clauses}) GROUP BY 1,2 ORDER BY 1,3 DESC'
        )
        for r in rows:
            out[r["type"]][str(year)][r["source"] or "(blank)"] = r["c"]
    return {t: dict(v) for t, v in out.items()}


def mattress_pickup_facts() -> dict:
    facts: dict = {"by_source": collections.Counter(), "automation_closures": 0, "total": 0}
    for year in (2022, 2023, 2024):
        rid = RESOURCE_IDS[year]
        for r in ckan_sql(f'SELECT "source", COUNT(*) c FROM "{rid}" WHERE "type"=\'Mattress_Pickup\' GROUP BY 1'):
            facts["by_source"][r["source"]] += r["c"]
            facts["total"] += r["c"]
        facts["automation_closures"] += ckan_sql(
            f'SELECT COUNT(*) c FROM "{rid}" WHERE "type"=\'Mattress_Pickup\' '
            f"AND \"closure_reason\" LIKE '%Mattress Pickup Automation%'"
        )[0]["c"]
    facts["by_source"] = dict(facts["by_source"])
    return facts


def open311_mentions() -> tuple[dict, str]:
    load_dotenv(ROOT / "pipeline" / ".env")
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["ENDPOINT"],
        aws_access_key_id=os.environ["ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["SECRET_ACCESS_KEY"],
        region_name=os.environ.get("REGION", "auto"),
    )
    bucket = os.environ["BUCKET"]
    pag = s3.get_paginator("list_objects_v2")

    def load(key: str) -> list[dict]:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        try:
            data = json.loads(body)
        except ValueError:
            return []
        if isinstance(data, dict):
            data = data.get("records") or data.get("data") or []
        return data

    result: dict = {}
    latest = ""
    for slug in OPEN311_SLUGS:
        keys = [o["Key"] for p in pag.paginate(Bucket=bucket, Prefix=f"open311/{slug}/") for o in p.get("Contents", [])]
        latest = max(latest, keys[-1].rsplit("/", 1)[-1][:10]) if keys else latest
        total: dict[str, int] = collections.Counter()
        hits: dict[str, int] = collections.Counter()
        samples: list[str] = []
        with cf.ThreadPoolExecutor(16) as ex:
            for recs in ex.map(load, keys):
                for r in recs:
                    ym = local_month(r.get("requested_datetime") or "")
                    if not ym:
                        continue
                    total[ym] += 1
                    desc = r.get("description") or ""
                    if MATTRESS_RE.search(desc):
                        hits[ym] += 1
                        if len(samples) < 12 and 20 < len(desc) < 160 and ym >= "2025-01":
                            samples.append(desc.strip())
        result[slug] = {
            "total": dict(sorted(total.items())),
            "mattress": dict(sorted(hits.items())),
            "samples": samples,
        }
        print(f"open311 {slug}: {sum(total.values())} records, {sum(hits.values())} mattress", file=sys.stderr)
    return result, latest


def main() -> None:
    ckan_types, ckan_latest = ckan_monthly_by_type()
    closure = ckan_closure_mentions_monthly()
    sources = ckan_source_by_type_year()
    facts = mattress_pickup_facts()
    open311, open311_latest = open311_mentions()
    # Last month whose data is complete: drop the trailing month if the scrape ends before the 28th.
    last_full = open311_latest[:7] if int(open311_latest[8:10]) >= 28 else None
    if last_full is None:
        y, m = int(open311_latest[:4]), int(open311_latest[5:7])
        last_full = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
    mp = ckan_types.get("Mattress_Pickup", {})
    active = sorted(m for m, c in mp.items() if c >= 100)
    payload = {
        "generated": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "ckan_through": ckan_latest,
        "open311_through": open311_latest,
        "open311_last_full_month": last_full,
        "mattress_pickup": {
            "monthly": mp,
            "first_month": active[0] if active else None,
            "last_month": active[-1] if active else None,
            **facts,
        },
        "ckan_types_monthly": ckan_types,
        "ckan_source_yearly": sources,
        "closure_mentions_monthly": closure,
        "open311": open311,
    }
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
