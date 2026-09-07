"""Seeded manual precision audit of stored waste classifications; no model calls."""

import csv
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

import typer

from pipeline import storage
from pipeline.cleaner import _parse_datetime
from pipeline.config import HIGH_SIGNAL_LEMMAS, HIGH_SIGNAL_PHRASES, MEDIUM_SIGNAL_LEMMAS
from pipeline.open311_loader import load_records_from_s3

START = date(2026, 7, 1)
END = date(2026, 8, 31)
SLUGS = ["litter-debris", "park-litter-debris"]
COLUMNS = ["case_id", "opened", "slug", "confidence", "score", "description", "closure_reason", "label", "notes"]
app = typer.Typer()


def keyword_hits(result: dict[str, Any]) -> list[str]:
    """Report the signals saved by the classifier, without reclassifying text."""
    terms = set(result.get("matched_terms", []))
    hits = [f"HIGH term: {term}" for term in sorted(terms & HIGH_SIGNAL_LEMMAS)]
    hits += [
        f"HIGH phrase: {phrase}" for phrase in sorted(set(result.get("matched_phrases", [])) & set(HIGH_SIGNAL_PHRASES))
    ]
    hits += [f"MEDIUM term: {term}" for term in sorted(terms & MEDIUM_SIGNAL_LEMMAS)]
    if result.get("bpw_rejection"):
        hits.append("HIGH BPW rejection")
    return hits


def write_precision_sample(
    n: int,
    seed: int = 42,
    classified_key: str = "waste/classified.json",
    output_dir: Path = Path("../research"),
    sample_date: date | None = None,
) -> Path:
    """Sample equally across nonempty (slug, Boston month, confidence) strata.

    Small strata are exhausted and unused slots redistributed. Prints population
    and sample sizes for weighted precision. Reads S3 only; writes a local CSV.
    """
    if n < 1:
        raise ValueError("n must be positive")
    classified = storage.read_json(classified_key)
    if not isinstance(classified, list):
        raise ValueError(f"Missing or invalid classifications: {classified_key}")
    positives = {
        str(r["case_id"]): r for r in classified if r.get("case_id") and r.get("confidence") in ("high", "medium")
    }
    # Day files follow UTC; September 1 UTC can still be August 31 in Boston.
    records = load_records_from_s3(SLUGS, START, END + timedelta(days=1))
    strata: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for rec in sorted(records, key=lambda r: (str(r["service_request_id"]), r["_open311_slug"])):
        cid = str(rec["service_request_id"])
        opened = _parse_datetime(str(rec.get("requested_datetime") or ""))
        if cid not in positives or cid in seen or opened is None or not START <= opened.date() <= END:
            continue
        seen.add(cid)
        result = positives[cid]
        texts = result.get("source_texts") or {}
        row = {
            "case_id": cid,
            "opened": opened.isoformat(),
            "slug": rec["_open311_slug"],
            "confidence": result["confidence"],
            "score": result["score"],
            "description": texts.get("open311_description", rec.get("description")) or "",
            "closure_reason": texts.get("closure_reason", rec.get("status_notes")) or "",
            "label": "",
            "notes": "",
        }
        strata[(row["slug"], opened.strftime("%Y-%m"), row["confidence"])].append(row)

    population = sum(len(rows) for rows in strata.values())
    if n > population:
        raise ValueError(f"Requested {n} cases, but only {population} eligible positives have Open311 records")
    if n < len(strata):
        raise ValueError(f"n must be at least {len(strata)} to represent every nonempty stratum")

    rng = random.Random(seed)
    keys = sorted(strata)
    allocation = dict.fromkeys(keys, 0)
    for _ in range(n):
        available = [key for key in keys if allocation[key] < len(strata[key])]
        key = min(available, key=lambda key: allocation[key])
        allocation[key] += 1
    sample = []
    typer.echo(f"Eligible positives: {population}; sampled: {n}; seed: {seed}")
    typer.echo("Strata (slug / Boston month / confidence): population, sampled")
    for key in keys:
        typer.echo(f"{' / '.join(key)}: {len(strata[key])}, {allocation[key]}")
        sample.extend(rng.sample(strata[key], allocation[key]))
    rng.shuffle(sample)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"precision_sample_{sample_date or date.today()}.csv"
    # Refuse to overwrite a file that may already contain human labels.
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sample)

    counts: Counter[str] = Counter()
    typer.echo("Keyword hits per sampled case (saved classification):")
    for row in sample:
        hits = keyword_hits(positives[row["case_id"]])
        counts.update(hits)
        typer.echo(f"{row['case_id']}: {'; '.join(hits) or '(no saved HIGH/MEDIUM signals)'}")
    typer.echo("Keyword-hit breakdown (cases per signal; signals can overlap):")
    for hit, count in sorted(counts.items()):
        typer.echo(f"{hit}: {count}")
    typer.echo(f"Wrote {path}")
    return path


@app.command()
def main(
    n: Annotated[int, typer.Option(min=1)] = 100,
    seed: int = 42,
    classified_key: str = "waste/classified.json",
    output_dir: Path = Path("../research"),
) -> None:
    """Export July–August 2026 litter positives for human labeling (read-only S3)."""
    try:
        write_precision_sample(n, seed, classified_key, output_dir)
    except (ValueError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc)) from exc


if __name__ == "__main__":
    app()
