"""CLI for data experiments."""

import json
from pathlib import Path
from typing import Optional

import typer

from data_experiments.config import (
    CACHE_DIR,
    OUTPUT_DIR,
    RESOURCE_IDS,
    SECONDARY_TYPES,
    STREET_CLEANING_TYPES,
)
from data_experiments.enricher import enrich_records
from data_experiments.fetcher import fetch_and_cache, get_record_count
from data_experiments.classifier import WasteClassifier

app = typer.Typer(help="Data experiments for Boston 311 human waste detection")


@app.command()
def counts(
    year: int = typer.Option(2025, help="Year to check"),
) -> None:
    """Show record counts for different types."""
    rid = RESOURCE_IDS.get(year)
    if not rid:
        typer.echo(f"No resource ID for {year}")
        raise typer.Exit(1)

    typer.echo(f"\n=== Record counts for {year} ===\n")
    all_types = STREET_CLEANING_TYPES | SECONDARY_TYPES
    for t in sorted(all_types):
        count = get_record_count(rid, {t})
        typer.echo(f"  {t}: {count or 'error'}")


@app.command()
def fetch(
    years: Optional[list[int]] = typer.Option(None, "--year", "-y", help="Years to fetch (default: 2025)"),
    include_secondary: bool = typer.Option(False, "--secondary", help="Include secondary types"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit records per year"),
) -> None:
    """Fetch street cleaning records from CKAN API."""
    if not years:
        years = [2025]

    types = STREET_CLEANING_TYPES
    if include_secondary:
        types = types | SECONDARY_TYPES

    typer.echo(f"\n=== Fetching records for {years} ===\n")
    records = fetch_and_cache(years, types=types, limit_per_year=limit)
    typer.echo(f"\n  Total: {len(records)} records")


@app.command()
def enrich(
    max_records: int = typer.Option(200, "--max", "-m", help="Max records to enrich via Open311"),
    delay: float = typer.Option(0.15, "--delay", "-d", help="Delay between API calls (seconds)"),
) -> None:
    """Enrich cached records with Open311 descriptions."""
    # Find the most recent cache file
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_files = sorted(CACHE_DIR.glob("records_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not cache_files:
        typer.echo("No cached records found. Run 'fetch' first.")
        raise typer.Exit(1)

    cache_file = cache_files[0]
    typer.echo(f"\n=== Enriching from {cache_file.name} ===\n")

    with open(cache_file) as f:
        records = json.load(f)

    typer.echo(f"  {len(records)} records loaded")
    enriched = enrich_records(records, delay=delay, max_records=max_records)

    # Save enriched records
    output_file = CACHE_DIR / f"enriched_{cache_file.name}"
    with open(output_file, "w") as f:
        json.dump(enriched, f, indent=2)
    typer.echo(f"\n  ✓ Saved enriched records to {output_file}")


@app.command()
def classify(
    min_confidence: str = typer.Option("low", help="Minimum confidence to show: high, medium, low"),
    use_enriched: bool = typer.Option(True, help="Use enriched records if available"),
    show_text: bool = typer.Option(False, "--show-text", help="Show full text for matches"),
    output_json: bool = typer.Option(True, "--json/--no-json", help="Save results as JSON"),
) -> None:
    """Run NLP classifier on cached records."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Try enriched first, fall back to raw
    records = None
    if use_enriched:
        enriched_files = sorted(CACHE_DIR.glob("enriched_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if enriched_files:
            with open(enriched_files[0]) as f:
                records = json.load(f)
            typer.echo(f"  ✓ Loaded {len(records)} enriched records from {enriched_files[0].name}")

    if records is None:
        cache_files = sorted(CACHE_DIR.glob("records_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not cache_files:
            typer.echo("No cached records found. Run 'fetch' first.")
            raise typer.Exit(1)
        with open(cache_files[0]) as f:
            records = json.load(f)
        typer.echo(f"  ✓ Loaded {len(records)} records from {cache_files[0].name}")

    typer.echo(f"\n=== Classifying {len(records)} records ===\n")

    classifier = WasteClassifier()
    results = classifier.classify_batch(records)

    # Filter by confidence
    confidence_levels = {"high": 3, "medium": 2, "low": 1, "none": 0}
    min_level = confidence_levels.get(min_confidence, 1)
    matches = [r for r in results if confidence_levels.get(r.confidence, 0) >= min_level]

    # Summary stats
    by_confidence = {}
    for r in results:
        by_confidence[r.confidence] = by_confidence.get(r.confidence, 0) + 1

    typer.echo("  Classification results:")
    typer.echo(f"    High confidence:   {by_confidence.get('high', 0)}")
    typer.echo(f"    Medium confidence: {by_confidence.get('medium', 0)}")
    typer.echo(f"    Low confidence:    {by_confidence.get('low', 0)}")
    typer.echo(f"    No match:          {by_confidence.get('none', 0)}")
    typer.echo(f"    Total:             {len(results)}")

    if matches:
        typer.echo(f"\n  --- Top matches (confidence >= {min_confidence}) ---\n")
        # Sort by score descending
        matches.sort(key=lambda r: r.score, reverse=True)
        for r in matches[:50]:  # Show top 50
            typer.echo(f"  [{r.confidence.upper():6}] score={r.score:.3f} case={r.case_id}")
            typer.echo(f"           terms={r.matched_terms} phrases={r.matched_phrases}")
            if r.context_boosters:
                typer.echo(f"           boosters={r.context_boosters}")
            if r.false_positive_flags:
                typer.echo(f"           ⚠ false_positive_flags={r.false_positive_flags}")
            if r.bpw_rejection:
                typer.echo("           ★ BPW rejection detected")
            if show_text:
                for field_name, text in r.source_texts.items():
                    preview = text[:200] + "..." if len(text) > 200 else text
                    typer.echo(f"           {field_name}: {preview}")
            typer.echo()

    # Save full results as JSON
    if output_json and matches:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_file = OUTPUT_DIR / "classification_results.json"
        results_data = []
        for r in matches:
            results_data.append({
                "case_id": r.case_id,
                "score": r.score,
                "confidence": r.confidence,
                "matched_terms": r.matched_terms,
                "matched_phrases": r.matched_phrases,
                "context_boosters": r.context_boosters,
                "false_positive_flags": r.false_positive_flags,
                "bpw_rejection": r.bpw_rejection,
                "source_texts": r.source_texts,
            })
        with open(output_file, "w") as f:
            json.dump(results_data, f, indent=2)
        typer.echo(f"\n  ✓ Saved {len(results_data)} results to {output_file}")


@app.command()
def scan_all(
    years: Optional[list[int]] = typer.Option(None, "--year", "-y", help="Years to scan"),
    enrich_max: int = typer.Option(500, "--enrich-max", help="Max records to enrich"),
    enrich_delay: float = typer.Option(0.15, "--enrich-delay", help="Delay between enrichment calls"),
) -> None:
    """Full pipeline: fetch, enrich, classify."""
    if not years:
        years = [2025]

    typer.echo("\n=== FULL PIPELINE ===\n")

    # Step 1: Fetch
    typer.echo("Step 1: Fetching records...")
    records = fetch_and_cache(years, types=STREET_CLEANING_TYPES)
    typer.echo(f"  Total: {len(records)} records\n")

    # Step 2: Enrich a sample
    typer.echo("Step 2: Enriching with Open311 descriptions...")
    enriched = enrich_records(records, delay=enrich_delay, max_records=enrich_max)
    typer.echo()

    # Step 3: Classify
    typer.echo("Step 3: Running NLP classifier...")
    classifier = WasteClassifier()
    results = classifier.classify_batch(enriched)

    # Summary
    by_confidence = {}
    for r in results:
        by_confidence[r.confidence] = by_confidence.get(r.confidence, 0) + 1

    typer.echo("\n=== RESULTS ===\n")
    typer.echo(f"  Total records scanned: {len(results)}")
    typer.echo(f"  High confidence:       {by_confidence.get('high', 0)}")
    typer.echo(f"  Medium confidence:     {by_confidence.get('medium', 0)}")
    typer.echo(f"  Low confidence:        {by_confidence.get('low', 0)}")
    typer.echo(f"  No match:              {by_confidence.get('none', 0)}")

    # Show high-confidence matches
    high_matches = [r for r in results if r.confidence == "high"]
    if high_matches:
        high_matches.sort(key=lambda r: r.score, reverse=True)
        typer.echo(f"\n  --- High confidence matches ({len(high_matches)}) ---\n")
        for r in high_matches[:30]:
            typer.echo(f"  score={r.score:.3f} case={r.case_id}")
            typer.echo(f"    terms={r.matched_terms} phrases={r.matched_phrases}")
            if r.bpw_rejection:
                typer.echo("    ★ BPW rejection")
            for field_name, text in r.source_texts.items():
                preview = text[:150] + "..." if len(text) > 150 else text
                typer.echo(f"    {field_name}: {preview}")
            typer.echo()

    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "classification_results.json"
    results_data = []
    for r in sorted(results, key=lambda r: r.score, reverse=True):
        if r.score > 0:
            results_data.append({
                "case_id": r.case_id,
                "score": r.score,
                "confidence": r.confidence,
                "matched_terms": r.matched_terms,
                "matched_phrases": r.matched_phrases,
                "context_boosters": r.context_boosters,
                "false_positive_flags": r.false_positive_flags,
                "bpw_rejection": r.bpw_rejection,
                "source_texts": r.source_texts,
            })
    with open(output_file, "w") as f:
        json.dump(results_data, f, indent=2)
    typer.echo(f"\n  ✓ Saved {len(results_data)} results to {output_file}")


@app.command()
def experiment(
    neighborhoods: Optional[list[str]] = typer.Option(
        None, "--neighborhood", "-n", help="Neighborhoods to target"
    ),
    enrich_count: int = typer.Option(300, "--enrich-count", help="Max records to enrich"),
    enrich_delay: float = typer.Option(0.15, "--enrich-delay", help="Delay between enrichment calls"),
) -> None:
    """Run targeted experiment: filter by neighborhood, enrich, classify."""
    from data_experiments.experiment import run_targeted_experiment

    if not neighborhoods:
        neighborhoods = ["South End", "Roxbury"]

    run_targeted_experiment(
        neighborhoods=neighborhoods,
        enrich_count=enrich_count,
        enrich_delay=enrich_delay,
    )


if __name__ == "__main__":
    app()
