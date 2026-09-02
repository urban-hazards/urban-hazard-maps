"""Tests for the Creatio CKAN reader, normalizer and monthly counts."""

from datetime import date
from typing import Any
from unittest.mock import patch

from pipeline.cleaner import clean
from pipeline.config import CREATIO_SERVICE_MAP
from pipeline.creatio import fetch_creatio_records, monthly_counts, normalize_creatio_record

ROW: dict[str, Any] = {
    "case_id": "BCS-00256693",
    "open_date": "2026-07-31 23:30:00+00",  # 7:30 PM Boston, still July
    "close_date": "2026-08-01 12:06:36+00",
    "case_topic": "Litter & Debris",
    "service_name": "Litter & Debris",
    "assigned_department": "Public Works Department (PWD)",
    "assigned_team": "PWD Highway (BEAM)",
    "case_status": "Closed",
    "closure_reason": "Resolved",
    "closure_comments": "Trash removed",
    "report_source": "BOS311",
    "full_address": "11-17 E Concord St, Boston, MA 02118",
    "street_name": "E Concord St",
    "zip_code": "02118",
    "neighborhood": "South End",
    "longitude": "-71.07473228",
    "latitude": "42.33768644",
}


def test_normalize_maps_to_ckan_shape_and_keeps_staff_text_separate() -> None:
    n = normalize_creatio_record(ROW)
    assert n["case_enquiry_id"] == "BCS-00256693"
    assert n["type"] == "Requests for Street Cleaning"
    assert n["creatio_service_name"] == "Litter & Debris"
    assert n["queue"] == "PWD Highway (BEAM)"
    assert n["source"] == "BOS311"
    assert n["closure_reason"] == "Resolved"
    assert n["creatio_closure_comments"] == "Trash removed"
    assert n["latitude"] == "42.33768644" and n["longitude"] == "-71.07473228"
    assert n["neighborhood"] == "South End" and n["location_street_name"] == "E Concord St"
    assert n["location_zipcode"] == "02118"
    assert n["source_system"] == "creatio"
    assert "open311_description" not in n


def test_none_comments_become_empty() -> None:
    assert normalize_creatio_record({**ROW, "closure_comments": "None"})["creatio_closure_comments"] == ""


def test_normalized_row_cleans_in_boston_local_time() -> None:
    rec = clean(normalize_creatio_record(ROW))
    assert rec is not None
    assert (rec.year, rec.month, rec.hour) == (2026, 7, 19)
    assert rec.resp_hrs == 12.6


def test_unmapped_service_name_passes_through() -> None:
    assert normalize_creatio_record({**ROW, "service_name": "Pothole"})["type"] == "Pothole"


def test_service_map_covers_spec_table() -> None:
    assert CREATIO_SERVICE_MAP["Litter & Debris"] == "Requests for Street Cleaning"
    assert CREATIO_SERVICE_MAP["Park Litter & Debris"] == "Requests for Street Cleaning"
    assert CREATIO_SERVICE_MAP["Improper Trash Storage"] == "Improper Storage of Trash (Barrels)"
    assert CREATIO_SERVICE_MAP["Illegal Dumping or Disposal"] == "Illegal Dumping"
    assert CREATIO_SERVICE_MAP["Missed Waste Pick-up"] == "Missed Trash/Recycling/Yard Waste/Bulk Item"
    assert CREATIO_SERVICE_MAP["Code Enforcement Collection"] == "CE Collection"


def test_monthly_counts_bucket_in_boston_time_by_legacy_type() -> None:
    rows = [
        normalize_creatio_record(ROW),  # July (Boston)
        normalize_creatio_record({**ROW, "case_id": "BCS-2", "open_date": "2026-08-01 03:59:00+00"}),  # Jul 31 Boston
        normalize_creatio_record({**ROW, "case_id": "BCS-3", "service_name": "Illegal Dumping or Disposal"}),
    ]
    assert monthly_counts(rows) == {
        "Requests for Street Cleaning": {"2026-07": 2},
        "Illegal Dumping": {"2026-07": 1},
    }


def _page(total: int, ids: list[str]) -> dict[str, Any]:
    recs = [{**ROW, "case_id": i} for i in ids]
    return {"success": True, "result": {"total": total, "records": recs}}


def test_fetch_pages_filters_since_and_asserts_total() -> None:
    pages = [_page(3, ["a", "b"]), _page(3, ["c"])]
    with patch("pipeline.creatio._api_get", side_effect=pages) as get:
        out = fetch_creatio_records({"Litter & Debris"}, since=date(2026, 6, 1), page_size=2)
    assert [r["case_id"] for r in out] == ["a", "b", "c"]
    assert get.call_count == 2
    assert "254adca6-64ab-4c5c-9fc0-a6da622be185" in get.call_args_list[0].args[0]
    assert "offset=2" in get.call_args_list[1].args[0]


def test_fetch_raises_on_short_read_and_schema_drift() -> None:
    with patch("pipeline.creatio._api_get", side_effect=[_page(5, ["a"])]):
        try:
            fetch_creatio_records({"Litter & Debris"}, since=date(2026, 6, 1), page_size=2)
        except RuntimeError as e:
            assert "expected 5" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
    bad = {
        "success": True,
        "result": {"total": 1, "records": [{"case_id": "x", "open_date": "2026-07-01 00:00:00+00"}]},
    }
    with patch("pipeline.creatio._api_get", side_effect=[bad]):
        try:
            fetch_creatio_records({"Litter & Debris"}, since=date(2026, 6, 1), page_size=2)
        except RuntimeError as e:
            assert "schema drift" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
