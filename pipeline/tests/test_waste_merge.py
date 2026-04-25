"""Test waste pipeline ingestion of CKAN + Open311 Other corpus.

Verifies:
- CKAN records are kept and tagged as confirmed/detected
- Open311 duplicates (same service_request_id as CKAN case_enquiry_id) are dropped
- Unique Open311 waste-positive records are ingested and tagged as detected
- Non-waste Open311 records are excluded by the classifier
- No output record has missing source field
"""

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

from pipeline.open311_loader import load_records_from_s3, normalize_open311_record

# --- Fixtures: four records per §57 spec ---

CKAN_CONFIRMED: dict[str, Any] = {
    "case_enquiry_id": "101005000001",
    "open_dt": "2024-06-15T10:00:00",
    "closed_dt": "2024-06-16T08:00:00",
    "case_title": "Requests for Street Cleaning",
    "subject": "Requests for Street Cleaning",
    "type": "Requests for Street Cleaning",
    "queue": "INFO_HumanWaste",
    "latitude": 42.3350,
    "longitude": -71.0750,
    "neighborhood": "South End",
    "location_street_name": "100 Mass Ave",
    "location_zipcode": "02118",
    "closure_reason": "Outside contractor dispatched for human waste cleanup",
}

OPEN311_DUPLICATE: dict[str, Any] = {
    "service_request_id": "101005000001",
    "status": "closed",
    "service_name": "Other",
    "service_code": "Mayor's 24 Hour Hotline:General Request:General Request",
    "description": "Human waste on sidewalk | Case (SR) Type: [Human Waste]",
    "requested_datetime": "2024-06-15T10:00:00Z",
    "updated_datetime": "2024-06-16T08:00:00Z",
    "address": "100 Mass Ave, South End, Ma, 02118",
    "lat": 42.3350,
    "long": -71.0750,
}

OPEN311_WASTE_POSITIVE: dict[str, Any] = {
    "service_request_id": "101004900099",
    "status": "open",
    "service_name": "Other",
    "service_code": "Mayor's 24 Hour Hotline:General Request:General Request",
    "description": "Human feces on the sidewalk near the bus stop",
    "requested_datetime": "2023-03-20T14:30:00Z",
    "updated_datetime": "2025-08-10T09:00:00Z",
    "address": "150 Southampton St, Roxbury, Ma, 02118",
    "lat": 42.3325,
    "long": -71.0666,
    "status_notes": "Referred to BPHC",
}

OPEN311_NOT_WASTE: dict[str, Any] = {
    "service_request_id": "101004900100",
    "status": "open",
    "service_name": "Other",
    "service_code": "Mayor's 24 Hour Hotline:General Request:General Request",
    "description": "Broken street light on corner",
    "requested_datetime": "2023-04-01T08:00:00Z",
    "updated_datetime": "2023-04-02T10:00:00Z",
    "address": "200 Beacon St, Boston, Ma, 02116",
    "lat": 42.3540,
    "long": -71.0700,
}


class TestNormalizeOpen311Record:
    def test_gates_closed_dt_on_status_closed(self) -> None:
        result = normalize_open311_record(OPEN311_DUPLICATE)
        assert result["closed_dt"] == "2024-06-16T08:00:00Z"

    def test_gates_closed_dt_on_status_open(self) -> None:
        """Open records must not get a spurious closed_dt from updated_datetime."""
        result = normalize_open311_record(OPEN311_WASTE_POSITIVE)
        assert result["closed_dt"] == ""

    def test_maps_core_fields(self) -> None:
        result = normalize_open311_record(OPEN311_WASTE_POSITIVE)
        assert result["case_enquiry_id"] == "101004900099"
        assert result["open_dt"] == "2023-03-20T14:30:00Z"
        assert result["latitude"] == 42.3325
        assert result["longitude"] == -71.0666
        assert result["open311_description"] == "Human feces on the sidewalk near the bus stop"
        assert result["closure_reason"] == "Referred to BPHC"


class TestLoadRecordsFromS3:
    def test_loads_and_tags_slug(self, s3_bucket: Any) -> None:
        client, bucket = s3_bucket
        key = "open311/other/2024-01-15.json"
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps([OPEN311_WASTE_POSITIVE, OPEN311_NOT_WASTE]),
        )

        from datetime import date

        results = load_records_from_s3(["other"], date(2024, 1, 1), date(2024, 12, 31))
        assert len(results) == 2
        assert all(r["_open311_slug"] == "other" for r in results)

    def test_skips_out_of_range_dates(self, s3_bucket: Any) -> None:
        client, bucket = s3_bucket
        client.put_object(
            Bucket=bucket,
            Key="open311/other/2022-12-31.json",
            Body=json.dumps([OPEN311_WASTE_POSITIVE]),
        )

        from datetime import date

        results = load_records_from_s3(["other"], date(2023, 1, 1), date(2024, 12, 31))
        assert len(results) == 0


class TestWasteMergeDedupe:
    """Test the dedupe logic that will run in _process_waste.

    Rather than calling the full pipeline (which needs spaCy, district data,
    etc.), we test the dedupe + normalize logic directly.
    """

    def test_duplicate_dropped_by_id(self) -> None:
        ckan_ids = {str(CKAN_CONFIRMED["case_enquiry_id"])}
        open311_records = [OPEN311_DUPLICATE, OPEN311_WASTE_POSITIVE, OPEN311_NOT_WASTE]

        unique = [r for r in open311_records if str(r.get("service_request_id", "")) not in ckan_ids]
        assert len(unique) == 2
        assert OPEN311_DUPLICATE not in unique

    def test_normalized_records_have_required_fields(self) -> None:
        normalized = normalize_open311_record(OPEN311_WASTE_POSITIVE)
        required = ["case_enquiry_id", "open_dt", "latitude", "longitude", "closure_reason"]
        for f in required:
            assert f in normalized, f"Missing field: {f}"


@dataclass
class _FakeResult:
    """Minimal ClassificationResult stand-in."""

    case_id: str = ""
    score: float = 0.0
    confidence: str = "none"
    matched_terms: list[str] = field(default_factory=list)
    matched_phrases: list[str] = field(default_factory=list)
    context_boosters: list[str] = field(default_factory=list)
    false_positive_flags: list[str] = field(default_factory=list)
    bpw_rejection: bool = False
    source_texts: dict[str, str] = field(default_factory=dict)


def _make_fake_classifier(waste_ids: set[str]) -> MagicMock:
    """Return a mock WasteClassifier whose classify_batch returns high for waste_ids."""

    def classify_batch(records: list[dict[str, Any]]) -> list[_FakeResult]:
        results = []
        for r in records:
            cid = str(r.get("case_enquiry_id", ""))
            queue = r.get("queue", "")
            if cid in waste_ids or "HumanWaste" in queue:
                results.append(_FakeResult(case_id=cid, score=0.9, confidence="high"))
            else:
                results.append(_FakeResult(case_id=cid, score=0.0, confidence="none"))
        return results

    mock = MagicMock()
    mock.classify_batch = classify_batch
    return mock


class TestProcessWasteIntegration:
    """Integration test for _process_waste dedupe + merge path.

    Mocks spaCy classifier, enricher, and districts to isolate the
    merge/dedupe contract without external dependencies.
    """

    def test_merge_dedupe_and_source_tagging(self, s3_bucket: Any) -> None:
        client, bucket = s3_bucket

        # Seed Other corpus in S3
        client.put_object(
            Bucket=bucket,
            Key="open311/other/2024-06-15.json",
            Body=json.dumps([OPEN311_DUPLICATE, OPEN311_WASTE_POSITIVE, OPEN311_NOT_WASTE]),
        )

        # IDs the classifier should mark as waste
        waste_ids = {
            CKAN_CONFIRMED["case_enquiry_id"],
            OPEN311_WASTE_POSITIVE["service_request_id"],
        }
        fake_classifier = _make_fake_classifier(waste_ids)

        with (
            patch("pipeline.run.WasteClassifier", return_value=fake_classifier),
            patch("pipeline.run.enrich_records", side_effect=lambda recs, cache, **kw: (recs, cache)),
            patch("pipeline.run._enrich_districts"),
            patch("pipeline.run.compute_stats") as mock_stats,
            patch("pipeline.run.storage") as mock_storage,
        ):
            # compute_stats needs to return something with the right shape
            mock_stats_result = MagicMock()
            mock_stats_result.total = 0
            mock_stats_result.markers = []
            mock_stats_result.points = []
            mock_stats_result.heat_keys = {"all": []}
            mock_stats.return_value = mock_stats_result

            # storage.read_json for description cache
            mock_storage.read_json.return_value = {}
            mock_storage.list_keys.return_value = ["open311/other/2024-06-15.json"]

            # Re-read the actual S3 data for the Other corpus load
            from pipeline import storage as real_storage

            mock_storage.read_json.side_effect = lambda key: real_storage.read_json(key)
            mock_storage.list_keys.side_effect = lambda prefix: real_storage.list_keys(prefix)

            from pipeline.run import _process_waste

            _process_waste([CKAN_CONFIRMED], force=False)

        # Verify compute_stats received the right records
        call_args = mock_stats.call_args
        cleaned_records = call_args[0][0]

        # Should have 2 records: CKAN confirmed + Open311 waste-positive
        # Duplicate (same ID as CKAN) dropped, non-waste excluded by classifier
        assert len(cleaned_records) == 2

        sources = {r.source for r in cleaned_records}
        assert "confirmed" in sources
        assert "detected" in sources

        # No record should be missing source
        assert all(r.source is not None for r in cleaned_records)
