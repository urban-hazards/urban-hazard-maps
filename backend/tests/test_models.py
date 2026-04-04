"""Smoke tests for Pydantic models."""

from boston_needle_map.models import CleanedRecord


def test_cleaned_record_creation() -> None:
    record = CleanedRecord(
        lat=42.332,
        lng=-71.078,
        dt="2024-06-15T10:30:00",
        year=2024,
        month=6,
        hour=10,
        dow="Saturday",
        hood="South End",
        street="WASHINGTON ST",
        zipcode="02118",
        resp_hrs=4.5,
    )
    assert record.lat == 42.332
    assert record.hood == "South End"
    assert record.resp_hrs == 4.5


def test_cleaned_record_optional_resp_hrs() -> None:
    record = CleanedRecord(
        lat=42.332,
        lng=-71.078,
        dt="2024-06-15T10:30:00",
        year=2024,
        month=6,
        hour=10,
        dow="Saturday",
        hood="Roxbury",
        street="MASS AVE",
        zipcode="02119",
    )
    assert record.resp_hrs is None
