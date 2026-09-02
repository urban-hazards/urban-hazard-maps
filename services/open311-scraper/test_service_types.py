"""Sanity tests for the scraper's service-code table and per-slug start clamp."""

import re
from datetime import date
from unittest.mock import MagicMock, patch

import fetch

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NEW = {
    "litter-debris": "155a5e9b-8c3a-4279-bbab-f6bba6ddb0d0",
    "park-litter-debris": "4278d986-8b62-4a2b-a43d-575e031b8f50",
    "improper-trash-storage": "acb41f11-e581-42bc-a0a5-877cb3a07747",
    "illegal-dumping": "60b145be-aef5-4a3c-8754-51472cf44088",
    "trash-out-early": "8a0698b8-9f00-4977-b907-aae2553aa2d3",
    "overflowing-trash": "c8e719d6-06ce-4375-813d-dccb3ca66402",
    "missed-waste": "994a8200-95d6-4720-826c-19bd142847b5",
    "ce-collection": "cb65b3ee-ab13-4c3c-8f3b-ffc743f99c94",
    "student-move-in": "715f7134-aac4-43f4-9e8b-b6fff5f47ad3",
}


def test_creatio_slugs_present_with_uuid_codes():
    for slug, code in NEW.items():
        assert fetch.SERVICE_TYPES[slug][0] == code
        assert UUID.match(code)


def test_slug_start_table():
    for slug in NEW:
        assert fetch.slug_start(slug) <= date(2026, 6, 1) or slug == "student-move-in"
    assert fetch.slug_start("park-litter-debris") == date(2026, 3, 1)  # Parks migrated in March 2026
    assert fetch.slug_start("student-move-in") == date(2026, 8, 1)
    assert fetch.slug_start("needles") == date.fromisoformat(fetch.START_DATE)


def test_fetch_type_clamps_start_to_slug_start():
    s3 = MagicMock()
    with patch("fetch.list_existing_days", return_value=set()) as listing:
        result = fetch.fetch_type(
            s3, "litter-debris", NEW["litter-debris"], "Litter & Debris", date(2023, 1, 1), date(2026, 6, 3), 0.0, True
        )
    assert listing.called
    assert result["slug"] == "litter-debris"
    assert result["days_needed"] == 3  # 2026-06-01..03 only; 2023-05 gap not scanned
