"""Download-only 2011–2014 needle records, in the legacy CKAN column shape."""

import csv
import io
import logging
import urllib.parse
import urllib.request
from typing import Any

from pipeline.config import CKAN_BASE, LEGACY_CSV_RESOURCES, NEEDLE_TYPES, UA
from pipeline.fetcher import _api_get

logger = logging.getLogger(__name__)

# Minimum schema needed to filter and clean a record. Preserve all other columns.
REQUIRED_FIELDS = {"case_enquiry_id", "open_dt", "type", "latitude", "longitude"}


def normalize_default_port(url: str) -> str:
    """Drop an explicit default port from a URL's host (…:443 for https, :80 for http).

    data.boston.gov redirects CSV downloads to a presigned S3 URL written as
    "https://s3.amazonaws.com:443/…". urllib keeps the port in the Host header,
    curl drops it, and AWS signed the request for the port-less host — so urllib
    gets SignatureDoesNotMatch (verified 2026-09-07). Normalizing fixes it.
    """
    parts = urllib.parse.urlsplit(url)
    default = {"https": 443, "http": 80}.get(parts.scheme)
    if parts.port is None or parts.port != default or not parts.hostname:
        return url
    host = parts.hostname
    if parts.username:
        cred = parts.username + (f":{parts.password}" if parts.password else "")
        host = f"{cred}@{host}"
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


class _PortNormalizingRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        return super().redirect_request(req, fp, code, msg, headers, normalize_default_port(newurl))


# Installed process-wide so urllib.request.urlopen (which tests patch) follows
# redirects with the default port stripped. Harmless for every other request.
urllib.request.install_opener(urllib.request.build_opener(_PortNormalizingRedirect))


def fetch_legacy_csv_year(year: int) -> list[dict[str, Any]]:
    """Stream the year's CSV and retain needle types / case-insensitive '%needle%'.

    GET follows the download's 302 redirect; HEAD is not supported by the host.
    Metadata, download and CSV errors propagate so failed reads are never cached
    as successful empty years. Memory holds only matching rows, not the full CSV.
    """
    if year not in LEGACY_CSV_RESOURCES:
        raise ValueError(f"No legacy CSV resource for {year}")
    resource_id = LEGACY_CSV_RESOURCES[year]
    metadata = _api_get(f"{CKAN_BASE}/package_show?id=311-service-requests")
    if not metadata or not metadata.get("success"):
        raise RuntimeError("Could not discover legacy CSV download URLs")
    resources = metadata.get("result", {}).get("resources", [])
    url = next((r.get("url") for r in resources if r.get("id") == resource_id), None)
    if not isinstance(url, str) or urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
        raise RuntimeError(f"Missing or invalid legacy CSV download URL for {year} ({resource_id})")

    request = urllib.request.Request(url, headers={"User-Agent": UA})
    rows: list[dict[str, Any]] = []
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        io.TextIOWrapper(response, encoding="utf-8-sig", newline="") as text,
    ):
        reader = csv.DictReader(text, strict=True)
        # BOM, capitalization and surrounding whitespace should not change
        # the CKAN-shaped keys returned to the cleaner.
        fields = [field.strip().lower() for field in (reader.fieldnames or [])]
        missing = REQUIRED_FIELDS - set(fields)
        if missing or len(fields) != len(set(fields)):
            raise RuntimeError(f"Invalid legacy CSV header for {year}: missing {sorted(missing)} or duplicate columns")
        reader.fieldnames = fields
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise RuntimeError(f"Malformed legacy CSV row for {year} at line {reader.line_num}")
            type_name = row["type"].strip()
            if type_name in NEEDLE_TYPES or "needle" in type_name.lower():
                rows.append(dict(row))
    logger.info("Legacy CSV %d: %d needle records", year, len(rows))
    return rows
