"""Experiment runner — targeted enrichment and analysis."""

import json
import random
from pathlib import Path
from typing import Any

from data_experiments.classifier import ClassificationResult, WasteClassifier
from data_experiments.config import CACHE_DIR, OUTPUT_DIR
from data_experiments.enricher import enrich_records


def load_cached_records(cache_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load the most recent cached records."""
    cache = cache_dir or CACHE_DIR
    files = sorted(cache.glob("records_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("No cached records found")
    with open(files[0]) as f:
        return json.load(f)


def filter_by_neighborhoods(
    records: list[dict[str, Any]],
    neighborhoods: list[str],
) -> list[dict[str, Any]]:
    """Filter records to specific neighborhoods (case-insensitive partial match)."""
    result = []
    for r in records:
        n = (r.get("neighborhood") or "").lower()
        if any(target.lower() in n for target in neighborhoods):
            result.append(r)
    return result


def run_targeted_experiment(
    neighborhoods: list[str] | None = None,
    enrich_count: int = 300,
    enrich_delay: float = 0.15,
    seed: int = 42,
) -> dict[str, Any]:
    """Run a targeted experiment: filter, sample, enrich, classify, analyze."""
    print("=== Loading records ===")
    records = load_cached_records()
    print(f"  Loaded {len(records)} total records")

    if neighborhoods:
        records = filter_by_neighborhoods(records, neighborhoods)
        print(f"  Filtered to {len(records)} records in {neighborhoods}")

    # Pre-classify on closure_reason only to identify records with no signal
    print("\n=== Pre-classifying on closure_reason ===")
    classifier = WasteClassifier()
    pre_results = classifier.classify_batch(records)

    has_signal = []
    no_signal = []
    for rec, result in zip(records, pre_results):
        if result.score > 0.1:
            has_signal.append(rec)
        else:
            no_signal.append(rec)

    print(f"  Records with waste signal in closure_reason: {len(has_signal)}")
    print(f"  Records with NO signal: {len(no_signal)}")

    # Strategy: enrich ALL records that already have signal + a random sample of no-signal
    to_enrich = list(has_signal)  # Always enrich records with existing signal
    remaining_budget = enrich_count - len(to_enrich)

    if remaining_budget > 0 and no_signal:
        random.seed(seed)
        sample_size = min(remaining_budget, len(no_signal))
        sample = random.sample(no_signal, sample_size)
        to_enrich.extend(sample)
        print(f"  Enriching: {len(has_signal)} with signal + {sample_size} random sample = {len(to_enrich)} total")
    else:
        print(f"  Enriching: {len(to_enrich)} records")

    # Enrich with Open311 descriptions
    print("\n=== Enriching with Open311 descriptions ===")
    cache_name = "targeted"
    if neighborhoods:
        cache_name = "targeted_" + "_".join(n.lower().replace(" ", "_") for n in neighborhoods)
    enriched = enrich_records(to_enrich, delay=enrich_delay, max_records=len(to_enrich), cache_name=cache_name)

    # Re-classify with enriched data
    print("\n=== Re-classifying with enriched data ===")
    post_results = classifier.classify_batch(enriched)

    # Analyze: how many NEW detections did the description field give us?
    new_detections = []
    upgraded = []
    all_matches = []

    for rec, pre, post in zip(to_enrich, classifier.classify_batch(to_enrich), post_results):
        if post.score > 0.1:
            all_matches.append(post)
        if pre.score <= 0.1 and post.score > 0.1:
            new_detections.append(post)
        elif pre.confidence != post.confidence and post.score > pre.score:
            upgraded.append((pre, post))

    # Summary
    by_confidence = {}
    for r in post_results:
        by_confidence[r.confidence] = by_confidence.get(r.confidence, 0) + 1

    summary = {
        "total_enriched": len(enriched),
        "neighborhoods": neighborhoods,
        "classification_summary": by_confidence,
        "new_detections_from_description": len(new_detections),
        "upgraded_confidence": len(upgraded),
        "total_matches": len(all_matches),
    }

    print("\n=== RESULTS ===\n")
    print(f"  Total records enriched: {len(enriched)}")
    print(f"  High confidence:        {by_confidence.get('high', 0)}")
    print(f"  Medium confidence:      {by_confidence.get('medium', 0)}")
    print(f"  Low confidence:         {by_confidence.get('low', 0)}")
    print(f"  No match:               {by_confidence.get('none', 0)}")
    print(f"\n  NEW detections from Open311 description: {len(new_detections)}")
    print(f"  Upgraded confidence:                      {len(upgraded)}")

    if new_detections:
        print(f"\n  --- New detections ({len(new_detections)}) ---\n")
        new_detections.sort(key=lambda r: r.score, reverse=True)
        for r in new_detections[:20]:
            print(f"  [{r.confidence.upper():6}] score={r.score:.3f} case={r.case_id}")
            print(f"    terms={r.matched_terms} phrases={r.matched_phrases}")
            if r.context_boosters:
                print(f"    boosters={r.context_boosters}")
            if r.bpw_rejection:
                print("    ★ BPW rejection")
            for field_name, text in r.source_texts.items():
                preview = text[:200] + "..." if len(text) > 200 else text
                print(f"    {field_name}: {preview}")
            print()

    if all_matches:
        print(f"\n  --- All matches ({len(all_matches)}) ---\n")
        all_matches.sort(key=lambda r: r.score, reverse=True)
        for r in all_matches[:30]:
            print(f"  [{r.confidence.upper():6}] score={r.score:.3f} case={r.case_id}")
            print(f"    terms={r.matched_terms} phrases={r.matched_phrases}")
            if r.bpw_rejection:
                print("    ★ BPW rejection")
            for field_name, text in r.source_texts.items():
                preview = text[:150] + "..." if len(text) > 150 else text
                print(f"    {field_name}: {preview}")
            print()

    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results_file = OUTPUT_DIR / "experiment_results.json"
    results_data = {
        "summary": summary,
        "new_detections": [
            {
                "case_id": r.case_id,
                "score": r.score,
                "confidence": r.confidence,
                "matched_terms": r.matched_terms,
                "matched_phrases": r.matched_phrases,
                "context_boosters": r.context_boosters,
                "false_positive_flags": r.false_positive_flags,
                "bpw_rejection": r.bpw_rejection,
                "source_texts": r.source_texts,
            }
            for r in new_detections
        ],
        "all_matches": [
            {
                "case_id": r.case_id,
                "score": r.score,
                "confidence": r.confidence,
                "matched_terms": r.matched_terms,
                "matched_phrases": r.matched_phrases,
                "context_boosters": r.context_boosters,
                "false_positive_flags": r.false_positive_flags,
                "bpw_rejection": r.bpw_rejection,
                "source_texts": r.source_texts,
            }
            for r in all_matches
        ],
    }
    with open(results_file, "w") as f:
        json.dump(results_data, f, indent=2)
    print(f"\n  ✓ Saved results to {results_file}")

    return results_data
