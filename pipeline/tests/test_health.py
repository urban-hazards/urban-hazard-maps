"""Tests for the per-source health monitor."""

import json
from datetime import date
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
    assert h["layers"]["encampments"]["status"] == "stale"
    assert h["layers"]["waste"]["status"] == "ok"
    assert h["new_service_names"] == ["Needle Cleanup"]
    write_source_health(h)
    client, bucket = s3_bucket
    saved = json.loads(client.get_object(Bucket=bucket, Key="metadata/source_health.json")["Body"].read())
    assert saved["schema_version"] == 1


def test_first_run_seeds_service_names_without_flagging_all_as_new(s3_bucket: tuple[Any, str]) -> None:
    with patch("pipeline.health._creatio_service_names", return_value=["A", "B"]):
        h = compute_source_health(today=date(2026, 9, 2))
    assert h["new_service_names"] == []
    assert storage.read_json("metadata/creatio_service_names.json") == ["A", "B"]
