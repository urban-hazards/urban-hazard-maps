"""Tests for the per-source health monitor."""

import json
from datetime import date, timedelta
from typing import Any
from unittest.mock import patch

from pipeline import storage
from pipeline.health import classify_status, compute_source_health, layer_status, write_source_health


def test_classify_status() -> None:
    assert classify_status(ratio=1.1, days_since=1, current=10) == "ok"
    assert classify_status(ratio=0.4, days_since=1, current=10) == "degraded"
    assert classify_status(ratio=None, days_since=1, current=10) == "ok"  # no baseline
    assert classify_status(ratio=1.0, days_since=15, current=10) == "stale"
    assert classify_status(ratio=0.0, days_since=3, current=0) == "stale"


def test_layer_status_rollup() -> None:
    assert layer_status(["stale", "ok"]) == "ok"
    assert layer_status(["stale", "degraded"]) == "degraded"
    assert layer_status(["stale", "stale"]) == "stale"


def test_compute_from_uncapped_sources(s3_bucket: tuple[Any, str]) -> None:
    storage.write_json("raw/needles_2026.json", [{"type": "Needle Pickup", "open_dt": "2026-08-20 10:00:00"}] * 12)
    storage.write_json("raw/needles_2025.json", [{"type": "Needle Pickup", "open_dt": "2025-08-20 10:00:00"}] * 10)
    storage.write_json("raw/encampments_v2_2026.json", [{"type": "Encampments", "open_dt": "2026-05-27 10:00:00"}])
    storage.write_json("raw/encampments_v2_2025.json", [{"type": "Encampments", "open_dt": "2025-08-20 10:00:00"}] * 5)
    storage.write_json(
        "raw/waste_2026.json", [{"type": "Requests for Street Cleaning", "open_dt": "2026-06-30 10:00:00"}]
    )
    storage.write_json(
        "raw/creatio.json",
        [{"creatio_service_name": "Litter & Debris", "open_dt": "2026-08-25 10:00:00+00"} for _ in range(7)],
    )
    storage.write_json("open311/needles/2026-08-30.json", [{"service_request_id": "1"}] * 3)
    storage.write_json("open311/encampments/2026-05-27.json", [{"service_request_id": "e"}])
    storage.write_json("open311/encampments/2026-09-01.json", [])  # persisted empty day
    storage.write_json("open311/litter-debris/2026-08-30.json", [{"service_request_id": "u"}] * 4)
    storage.write_json("metadata/creatio_service_names.json", ["Litter & Debris"])
    with patch("pipeline.health._creatio_service_names", return_value=["Litter & Debris", "Needle Cleanup"]):
        h = compute_source_health(today=date(2026, 9, 2))
    s = h["sources"]
    assert s["ckan_legacy:Needle Pickup"]["last_30d"] == 12 and s["ckan_legacy:Needle Pickup"]["ratio"] == 1.2
    assert s["ckan_legacy:Encampments"]["status"] == "stale"
    assert s["ckan_legacy:Encampments"]["through"] == "2026-05-27"
    assert s["ckan_legacy:Requests for Street Cleaning"]["status"] == "stale"
    assert s["ckan_creatio:Litter & Debris"]["ratio"] is None
    assert s["ckan_creatio:Litter & Debris"]["status"] == "ok"
    assert s["open311:litter-debris"]["last_30d"] == 4
    assert s["open311:encampments"]["through"] == "2026-05-27"  # empty-day files do not advance "through"
    assert h["layers"]["encampments"]["through"] == "2026-05-27"
    assert h["layers"]["encampments"]["status"] == "stale"
    assert h["layers"]["waste"]["status"] == "ok"
    assert h["layers"]["needles"]["status"] == "ok"
    assert h["layers"]["needles"]["disrupted_since"] is None
    assert h["new_service_names"] == ["Needle Cleanup"]
    assert h["schema_version"] == 2
    assert s["ckan_legacy:Needle Pickup"]["coverage"] is True
    write_source_health(h)
    client, bucket = s3_bucket
    saved = json.loads(client.get_object(Bucket=bucket, Key="metadata/source_health.json")["Body"].read())
    assert saved["schema_version"] == 2


def test_first_run_seeds_service_names_without_flagging_all_as_new(s3_bucket: tuple[Any, str]) -> None:
    with patch("pipeline.health._creatio_service_names", return_value=["A", "B"]):
        h = compute_source_health(today=date(2026, 9, 2))
    assert h["new_service_names"] == []
    assert storage.read_json("metadata/creatio_service_names.json") == ["A", "B"]


def _write_encampment_fixture(extra_queue_rows: list[dict[str, Any]] | None = None) -> None:
    """type row 2026-05-27 (route "type") + queue rows 06-05/06-17/06-22 (route "queue",
    type "Requests for Street Cleaning") — the canonical v3 provenance-partition fixture.
    """
    rows = [
        {"type": "Encampments", "queue": "INFO_Homeless Issue", "open_dt": "2026-05-27 10:00:00", "_uhm_route": "type"},
        {
            "type": "Requests for Street Cleaning",
            "queue": "INFO_Homeless Issue",
            "open_dt": "2026-06-05 09:00:00",
            "_uhm_route": "queue",
        },
        {
            "type": "Requests for Street Cleaning",
            "queue": "INFO_Homeless Issue",
            "open_dt": "2026-06-17 11:00:00",
            "_uhm_route": "queue",
        },
        {
            "type": "Requests for Street Cleaning",
            "queue": "INFO_Homeless Issue",
            "open_dt": "2026-06-22 12:39:43",
            "_uhm_route": "queue",
        },
    ]
    storage.write_json("raw/encampments_v2_2026.json", rows + (extra_queue_rows or []))


def test_encampment_provenance_partition(s3_bucket: tuple[Any, str]) -> None:
    """raw/encampments_v2_* rows are partitioned by provenance (`_uhm_route`), not by the
    mutable `type` field: the type-button feed and the queue-residual leak are separate
    sources. The queue residual is not coverage, so it cannot make the layer "ok", but it
    still counts toward `latest_report`.
    """
    _write_encampment_fixture()
    with patch("pipeline.health._creatio_service_names", return_value=[]):
        h = compute_source_health(today=date(2026, 9, 23))
    sources = h["sources"]
    assert sources["ckan_legacy:Encampments"]["through"] == "2026-05-27"
    assert sources["ckan_legacy:Encampments (queue)"]["through"] == "2026-06-22"
    assert sources["ckan_legacy:Encampments (queue)"]["coverage"] is False
    layer = h["layers"]["encampments"]
    assert layer["through"] == "2026-05-27"
    assert layer["latest_report"] == "2026-06-22"
    assert layer["disrupted_since"] == "2026-05-28"
    assert layer["status"] == "stale"


def test_encampment_queue_trickle_does_not_flip_layer(s3_bucket: tuple[Any, str]) -> None:
    """A couple of recent queue-residual rows make that (non-coverage) source look "ok" on
    recency, but must not revive the layer or move `disrupted_since` — only the type feed
    (or Open311) counts as coverage.
    """
    today = date(2026, 9, 23)
    trickle_day = (today - timedelta(days=2)).isoformat() + " 08:00:00"
    _write_encampment_fixture(
        extra_queue_rows=[
            {
                "type": "Requests for Street Cleaning",
                "queue": "INFO_Homeless Issue",
                "open_dt": trickle_day,
                "_uhm_route": "queue",
            }
        ]
    )
    with patch("pipeline.health._creatio_service_names", return_value=[]):
        h = compute_source_health(today=today)
    assert h["sources"]["ckan_legacy:Encampments (queue)"]["status"] == "ok"
    assert h["sources"]["ckan_legacy:Encampments (queue)"]["prior_year_30d"] == 0
    assert h["sources"]["ckan_legacy:Encampments (queue)"]["ratio"] is None
    layer = h["layers"]["encampments"]
    assert layer["status"] == "stale"
    assert layer["disrupted_since"] == "2026-05-28"


def test_encampment_open311_successor_revives_layer(s3_bucket: tuple[Any, str]) -> None:
    """A coverage source (Open311 successor) recovering flips the layer back to ok and
    clears disrupted_since, even though the legacy type feed and the queue residual are
    both still stale/non-coverage.
    """
    today = date(2026, 9, 23)
    yesterday = today - timedelta(days=1)
    _write_encampment_fixture()
    storage.write_json(
        f"open311/encampments/{yesterday.isoformat()}.json",
        [{"service_request_id": str(i)} for i in range(6)],
    )
    with patch("pipeline.health._creatio_service_names", return_value=[]):
        h = compute_source_health(today=today)
    layer = h["layers"]["encampments"]
    assert layer["status"] == "ok"
    assert layer["disrupted_since"] is None
    assert layer["latest_report"] == yesterday.isoformat()


def test_encampment_through_ignores_rolling_year_window(s3_bucket: tuple[Any, str]) -> None:
    """`through` for legacy sources must scan every raw/encampments_v2_*.json file present
    in the bucket, not just the rolling last_30d / prior_year_30d `years` set — otherwise
    "through" regresses to empty once the file's year falls out of that window.
    """
    _write_encampment_fixture()
    with patch("pipeline.health._creatio_service_names", return_value=[]):
        h = compute_source_health(today=date(2028, 1, 30))
    assert h["sources"]["ckan_legacy:Encampments"]["through"] == "2026-05-27"


def test_encampment_unstamped_rows_fall_back_to_type(s3_bucket: tuple[Any, str]) -> None:
    """Rows cached before the `_uhm_route` stamp existed fall back to
    `type not in ENCAMPMENT_TYPES` -> "queue"."""
    storage.write_json(
        "raw/encampments_v2_2026.json",
        [
            {"type": "Encampments", "open_dt": "2026-05-27 10:00:00"},
            {"type": "Requests for Street Cleaning", "open_dt": "2026-06-22 12:39:43"},
        ],
    )
    with patch("pipeline.health._creatio_service_names", return_value=[]):
        h = compute_source_health(today=date(2026, 9, 23))
    assert h["sources"]["ckan_legacy:Encampments"]["through"] == "2026-05-27"
    assert h["sources"]["ckan_legacy:Encampments (queue)"]["through"] == "2026-06-22"
