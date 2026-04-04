"""Pipeline configuration and constants."""

from pathlib import Path

CKAN_BASE = "https://data.boston.gov/api/3/action"

# Resource IDs for each year's 311 dataset on data.boston.gov
RESOURCE_IDS: dict[int, str] = {
    2015: "c9509ab4-6f6d-4b97-979a-0cf2a10c922b",
    2016: "b7ea6b1b-3ca4-4c5b-9713-6dc1db52379a",
    2017: "30022137-709d-465e-baae-ca155b51927d",
    2018: "2be28d90-3a90-4af1-a3f6-f28c1e25880a",
    2019: "ea2e4696-4a2d-429c-9807-d02eb92e0222",
    2020: "6ff6a6fd-3141-4440-a880-6f60a37fe789",
    2021: "f53ebccd-bc61-49f9-83db-625f209c95f5",
    2022: "81a7b022-f8fc-4da5-80e4-b160058ca207",
    2023: "e6013a93-1321-4f2a-bf91-8d8a02f1e62f",
    2024: "dff4d804-5031-443a-8409-8344efd0e5c8",
    2025: "9d7c2214-4709-478a-a2e8-fb2020a5bb94",
    2026: "1a0b420d-99f1-4887-9851-990b2a5a6e17",
}

NEEDLE_TYPES: set[str] = {"Needle Pickup", "Needle Clean-up", "Needle Cleanup"}

BOSTON_BBOX = {
    "lat_min": 42.2279,
    "lat_max": 42.3969,
    "lon_min": -71.1912,
    "lon_max": -70.9235,
}

CACHE_DIR = Path("tmp")
UA = "Boston311NeedlePipeline/4.0 (fastapi-backend; public-health-research)"
