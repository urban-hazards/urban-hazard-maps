"""Tests for cross-system fingerprint matching."""

from typing import Any

from pipeline.creatio import normalize_creatio_record
from pipeline.dedupe import fingerprint, match_cross_system
from pipeline.open311_loader import normalize_open311_record

CREATIO_ROW: dict[str, Any] = {
    "case_id": "BCS-00256693",
    "open_date": "2026-07-16 16:10:24+00",
    "close_date": "",
    "case_topic": "Litter & Debris",
    "service_name": "Litter & Debris",
    "assigned_department": "PWD",
    "assigned_team": "PWD Highway (BEAM)",
    "case_status": "Closed",
    "closure_reason": "Resolved",
    "closure_comments": "None",
    "report_source": "BOS311",
    "full_address": "11-17 E Concord St, Boston, MA 02118",
    "street_name": "E Concord St",
    "zip_code": "02118",
    "neighborhood": "South End",
    "longitude": "-71.07473228",
    "latitude": "42.33768644",
}
OPEN311_SAME_CASE: dict[str, Any] = {
    "service_request_id": "6a2af5bf-cbba-4b18-8a2a-59eed542c8ef",
    "status": "closed",
    "service_name": "Litter & Debris",
    "service_code": "155a5e9b-8c3a-4279-bbab-f6bba6ddb0d0",
    "description": "Trash pile on the corner",
    "requested_datetime": "2026-07-16T16:11:00Z",
    "updated_datetime": "2026-07-17T08:06:36Z",
    "address": "11-17 E Concord St, South End, Ma, 02118",
    "lat": 42.337684,
    "long": -71.074731,
}


def test_fingerprint_applies_legacy_mapping_and_local_minutes() -> None:
    fa = fingerprint(normalize_creatio_record(CREATIO_ROW))
    fb = fingerprint(normalize_open311_record(OPEN311_SAME_CASE))
    assert fa is not None and fb is not None
    assert fa[:3] == fb[:3] == ("Requests for Street Cleaning", "42.3377", "-71.0747")
    assert fb[3] - fa[3] == 1


def test_fingerprint_none_without_coords_or_time() -> None:
    assert fingerprint({"type": "x", "open_dt": "", "latitude": "", "longitude": ""}) is None


def test_match_reports_pairs_and_keeps_unmatched() -> None:
    primary = [normalize_open311_record(OPEN311_SAME_CASE)]
    far = normalize_creatio_record({**CREATIO_ROW, "case_id": "BCS-2", "latitude": "42.3500", "longitude": "-71.0600"})
    late = normalize_creatio_record({**CREATIO_ROW, "case_id": "BCS-3", "open_date": "2026-07-16 16:25:00+00"})
    unmatched, pairs = match_cross_system(primary, [normalize_creatio_record(CREATIO_ROW), far, late], window_min=2)
    assert [r["case_enquiry_id"] for r in unmatched] == ["BCS-2", "BCS-3"]
    assert pairs == [
        {
            "primary_id": "6a2af5bf-cbba-4b18-8a2a-59eed542c8ef",
            "secondary_id": "BCS-00256693",
            "type": "Requests for Street Cleaning",
            "minutes_apart": 1,
        }
    ]


def test_match_is_pure() -> None:
    secondary = [normalize_creatio_record(CREATIO_ROW)]
    a = match_cross_system([], secondary)
    b = match_cross_system([], secondary)
    assert a == b and len(secondary) == 1
