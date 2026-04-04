"""Typer CLI for the Boston 311 Needle Hotspot Pipeline."""

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from boston_needle_map.cache import clear_cache, load_cached, save_cache
from boston_needle_map.cleaner import clean
from boston_needle_map.config import RESOURCE_IDS
from boston_needle_map.fetcher import fetch_year
from boston_needle_map.models import CleanedRecord

app = typer.Typer(
    name="boston-needle-map",
    help="Boston 311 Needle Hotspot Pipeline — Backend CLI",
)


@app.command()
def run(
    years: Annotated[list[int] | None, typer.Argument(help="Years to fetch (defaults to last 3 + current)")] = None,
    use_cache: Annotated[bool, typer.Option("--cache/--no-cache", help="Use tmp/ cache for fetched data")] = True,
) -> None:
    """Fetch needle records and compute stats (prints summary)."""
    from boston_needle_map.analytics import compute_stats

    if years is None:
        now = datetime.now().year
        years = [y for y in range(now - 2, now + 1) if y in RESOURCE_IDS]

    typer.echo(f"\u2554{'=' * 46}\u2557")
    typer.echo("\u2551  Boston 311 Needle Hotspot Pipeline          \u2551")
    typer.echo(f"\u2551  Years: {', '.join(str(y) for y in years):<37s} \u2551")
    typer.echo(f"\u255a{'=' * 46}\u255d")

    all_records: list[CleanedRecord] = []
    for year in years:
        raw: list[dict[str, object]]
        if use_cache:
            cached = load_cached(year)
            if cached is not None:
                raw = cached
            else:
                raw = fetch_year(year)
                if raw:
                    save_cache(year, raw)
        else:
            raw = fetch_year(year)

        cleaned = [r for r in (clean(row) for row in raw) if r is not None]
        typer.echo(f"  \u2713 {year}: {len(raw)} raw \u2192 {len(cleaned)} valid")
        all_records.extend(cleaned)

    if not all_records:
        typer.echo("\n\u26a0 No records retrieved.")
        return

    typer.echo(f"\n  Total valid records: {len(all_records):,}")
    typer.echo("  Computing stats...")

    stats = compute_stats(all_records)
    typer.echo(f"  Peak neighborhood: {stats.peak_hood}")
    typer.echo(f"  Peak hour: {stats.peak_hour}")
    typer.echo(f"  Avg monthly: {stats.avg_monthly}")
    typer.echo(f"  Generated: {stats.generated}")


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", "-h", help="Host to bind to")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", "-p", help="Port to serve on")] = 8000,
) -> None:
    """Start the FastAPI server."""
    import uvicorn

    typer.echo(f"Starting FastAPI server on {host}:{port}")
    uvicorn.run("boston_needle_map.api:app", host=host, port=port, reload=False)


@app.command(name="cache-clear")
def cache_clear_cmd() -> None:
    """Clear all cached data in tmp/."""
    clear_cache()
    typer.echo("Cache cleared.")


@app.command()
def dump_json(
    years: Annotated[list[int] | None, typer.Argument(help="Years to fetch")] = None,
    output: Annotated[str, typer.Option("--output", "-o", help="Output file path")] = "data.json",
) -> None:
    """Dump pipeline data as JSON file."""
    from boston_needle_map.analytics import compute_stats

    if years is None:
        now = datetime.now().year
        years = [y for y in range(now - 2, now + 1) if y in RESOURCE_IDS]

    all_records: list[CleanedRecord] = []
    for year in years:
        cached = load_cached(year)
        if cached is not None:
            raw = cached
        else:
            raw = fetch_year(year)
            if raw:
                save_cache(year, raw)
        cleaned = [r for r in (clean(row) for row in raw) if r is not None]
        all_records.extend(cleaned)

    stats = compute_stats(all_records)
    out_path = Path(output)
    out_path.write_text(
        json.dumps(
            {
                "generated": stats.generated,
                "total": stats.total,
                "years": stats.years,
                "records": [r.model_dump() for r in all_records],
            }
        ),
        encoding="utf-8",
    )
    typer.echo(f"Wrote {out_path} ({len(all_records)} records)")


if __name__ == "__main__":
    app()
