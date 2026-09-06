"""Precision audit uses stored positives and moto day files, never an NLP model."""

import csv
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from pipeline import storage
from pipeline.tools.precision_sample import COLUMNS, app, write_precision_sample


def test_seeded_strata_and_keyword_breakdown(
    s3_bucket: tuple[Any, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    classified = []
    for slug in ("litter-debris", "park-litter-debris"):
        for month in (7, 8):
            records = []
            for confidence in ("high", "medium"):
                for i in range(3):
                    cid = f"{slug}-{month}-{confidence}-{i}"
                    classified.append(
                        {
                            "case_id": cid,
                            "confidence": confidence,
                            "score": 0.8 if confidence == "high" else 0.4,
                            "matched_terms": ["feces", "urine"],
                            "matched_phrases": ["human waste"],
                            "source_texts": {"closure_reason": "Scored closure"},
                        }
                    )
                    records.append(
                        {
                            "service_request_id": cid,
                            "requested_datetime": f"2026-{month:02d}-15T12:00:00Z",
                            "description": 'Human waste, urine\nby "park"',
                            "status_notes": "New closure",
                        }
                    )
            storage.write_json(f"open311/{slug}/2026-{month:02d}-15.json", records + records[:1])
    # Exclude wrong slugs, low/none confidence, missing IDs, and dates outside Boston's window.
    for cid, slug, opened, confidence in [
        ("other", "other", "2026-07-10T12:00:00Z", "high"),
        ("low", "litter-debris", "2026-07-10T12:00:00Z", "low"),
        ("none", "litter-debris", "2026-07-10T12:00:00Z", "none"),
        ("june", "litter-debris", "2026-07-01T02:00:00Z", "high"),
        ("september", "litter-debris", "2026-09-01T05:00:00Z", "high"),
    ]:
        classified.append({"case_id": cid, "confidence": confidence, "score": 0.8})
        key = f"open311/{slug}/{opened[:10]}.json"
        storage.write_json(
            key, (storage.read_json(key) or []) + [{"service_request_id": cid, "requested_datetime": opened}]
        )
    classified.append({"case_id": "no-day-file", "confidence": "high", "score": 0.8})
    storage.write_json("waste/classified.json", classified)
    path = write_precision_sample(8, 17, output_dir=tmp_path, sample_date=date(2026, 9, 6))
    assert path.name == "precision_sample_2026-09-06.csv"
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == COLUMNS
    assert len({r["case_id"] for r in rows}) == 8
    assert len({(r["slug"], r["opened"][:7], r["confidence"]) for r in rows}) == 8
    assert all(r["label"] == r["notes"] == "" for r in rows)
    assert all(r["description"] == 'Human waste, urine\nby "park"' for r in rows)
    assert all(r["closure_reason"] == "Scored closure" for r in rows)
    output = capsys.readouterr().out
    assert "Eligible positives: 24; sampled: 8; seed: 17" in output
    assert "HIGH term: feces: 8" in output
    assert "HIGH phrase: human waste: 8" in output
    assert "MEDIUM term: urine: 8" in output
    storage.write_json("waste/classified.json", list(reversed(classified)))
    repeat = write_precision_sample(8, 17, output_dir=tmp_path / "repeat", sample_date=date(2026, 9, 6))
    assert path.read_bytes() == repeat.read_bytes()
    with pytest.raises(FileExistsError):
        write_precision_sample(8, 17, output_dir=tmp_path, sample_date=date(2026, 9, 6))
    with pytest.raises(ValueError, match="at least 8"):
        write_precision_sample(7, output_dir=tmp_path)
    with pytest.raises(ValueError, match="only 24"):
        write_precision_sample(25, output_dir=tmp_path)


def test_boston_end_boundary_and_cli(s3_bucket: tuple[Any, str], tmp_path: Path) -> None:
    storage.write_json("waste/classified.json", [{"case_id": "last", "confidence": "high", "score": 0.9}])
    storage.write_json(
        "open311/litter-debris/2026-09-01.json",
        [
            {
                "service_request_id": "last",
                "requested_datetime": "2026-09-01T03:59:59Z",
            }
        ],
    )
    result = CliRunner().invoke(app, ["--n", "1", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    with next(tmp_path.glob("*.csv")).open() as handle:
        row = next(csv.DictReader(handle))
    assert row["opened"] == "2026-08-31T23:59:59-04:00"
    assert row["description"] == row["closure_reason"] == ""


def test_missing_classifications_fail(s3_bucket: tuple[Any, str], tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Missing or invalid"):
        write_precision_sample(1, output_dir=tmp_path)
    with pytest.raises(ValueError, match="positive"):
        write_precision_sample(0, output_dir=tmp_path)
