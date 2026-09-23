"""Download-only needle years: mocked HTTP streams and moto historical caches."""

import csv
import io
import json
from typing import Any
from unittest.mock import patch

import pytest

from pipeline.cleaner import clean
from pipeline.config import LEGACY_CSV_RESOURCES, RESOURCE_IDS
from pipeline.legacy_csv import fetch_legacy_csv_year, normalize_default_port

HEADER = "case_enquiry_id,open_dt,type,latitude,longitude,closure_reason,source,location_zipcode\r\n"
CSV = (
    HEADER
    + '001,2011-07-15 12:00:00,Needle Pickup,42.34,-71.07,"Removed, at park\nnear gate",Citizens Connect App,02118\r\n'
    + "002,2011-07-16 12:00:00,Needle Clean-up,42.34,-71.07,,Phone,02118\r\n"
    + "003,2011-07-17 12:00:00,Needle Cleanup,42.34,-71.07,,Phone,02118\r\n"
    + "004,2011-07-18 12:00:00,DISCARDED NEEDLES,42.34,-71.07,,Phone,02118\r\n"
    + "005,2011-07-19 12:00:00,Requests for Street Cleaning,42.34,-71.07,"
    "needle mentioned only in closure,Phone,02118\r\n"
)


class StreamingCSV(io.BytesIO):
    """Catch attempts to read the entire download rather than bounded chunks."""

    reads = 0

    def read(self, size: int = -1) -> bytes:
        assert size >= 0, "CSV download must be streamed"
        self.reads += 1
        return super().read(size)

    def read1(self, size: int = -1) -> bytes:
        assert size >= 0, "CSV download must be streamed"
        self.reads += 1
        return super().read1(size)


def metadata_response(year: int) -> io.BytesIO:
    return io.BytesIO(
        json.dumps(
            {
                "success": True,
                "result": {
                    "resources": [
                        {"id": "unrelated", "url": "https://data.boston.gov/ignore.csv"},
                        {
                            "id": LEGACY_CSV_RESOURCES[year],
                            "url": f"https://data.boston.gov/download/revised-{year}.csv",
                        },
                    ]
                },
            }
        ).encode()
    )


@pytest.mark.parametrize("year", sorted(LEGACY_CSV_RESOURCES))
def test_streams_discovered_url_and_preserves_ckan_shape(year: int) -> None:
    # The real dumps share CKAN's columns; accept a BOM and header capitalization.
    text = CSV.replace(HEADER, HEADER.upper()).replace("2011-", f"{year}-")
    response = StreamingCSV(text.encode("utf-8-sig"))
    with patch("urllib.request.urlopen", side_effect=[metadata_response(year), response]) as get:
        rows = fetch_legacy_csv_year(year)
    assert get.call_args_list[0].args[0].full_url.endswith("/package_show?id=311-service-requests")
    request = get.call_args_list[1].args[0]
    assert request.full_url == f"https://data.boston.gov/download/revised-{year}.csv"
    assert request.get_method() == "GET"  # urllib follows 302 redirects; never use HEAD
    assert request.get_header("User-agent")
    assert response.reads > 0 and response.closed
    assert [r["case_enquiry_id"] for r in rows] == ["001", "002", "003", "004"]
    assert rows[0]["closure_reason"] == "Removed, at park\nnear gate"
    assert rows[0]["source"] == "Citizens Connect App"
    assert rows[0]["location_zipcode"] == "02118"
    assert set(rows[0]) == set(HEADER.strip().split(","))
    cleaned = clean(rows[0])
    assert cleaned is not None and cleaned.year == year


@pytest.mark.parametrize(
    "payload",
    [
        "<html>Temporary error</html>",
        HEADER + "001,2011-07-15,Needle Pickup\n",
        HEADER + '001,2011-07-15,Needle Pickup,42.34,-71.07,"unterminated',
    ],
)
def test_invalid_csv_fails_instead_of_caching_empty(payload: str) -> None:
    with (
        patch("urllib.request.urlopen", side_effect=[metadata_response(2011), io.BytesIO(payload.encode())]),
        pytest.raises((RuntimeError, csv.Error)),
    ):
        fetch_legacy_csv_year(2011)


@pytest.mark.parametrize(
    "metadata",
    [None, {"success": False}, {"success": True, "result": {"resources": []}}],
)
def test_missing_metadata_or_download_url_raises(metadata: dict[str, Any] | None) -> None:
    with patch("pipeline.legacy_csv._api_get", return_value=metadata), pytest.raises(RuntimeError):
        fetch_legacy_csv_year(2011)


def test_unsupported_year_does_not_fetch() -> None:
    with patch("urllib.request.urlopen") as get, pytest.raises(ValueError, match="2015"):
        fetch_legacy_csv_year(2015)
    get.assert_not_called()
    assert set(LEGACY_CSV_RESOURCES) == {2011, 2012, 2013, 2014}
    assert not LEGACY_CSV_RESOURCES.keys() & RESOURCE_IDS.keys()


def test_normalize_default_port_only_strips_scheme_default() -> None:
    assert (
        normalize_default_port("https://s3.amazonaws.com:443/bucket/key?X-Amz-Signature=abc")
        == "https://s3.amazonaws.com/bucket/key?X-Amz-Signature=abc"
    )
    assert normalize_default_port("https://host:8443/x") == "https://host:8443/x"
    assert normalize_default_port("http://host:80/x") == "http://host/x"
    assert normalize_default_port("https://host/x") == "https://host/x"
