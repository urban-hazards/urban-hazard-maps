# Service Code Mapping

> Maps scraper slugs to Open311 service codes. This is the source of truth —
> `services/open311-scraper/fetch.py` should match this table.
>
> Last updated: 2026-04-11

## The input.* Discovery

The `/services.json` endpoint lists 16 services. Four use `input.*` prefix
codes that are **BOS:311 app form button identifiers** — they define what the
app presents to users but tag zero stored records. When a citizen taps one,
the backend reclassifies to a colon-delimited code before saving.

| App button (input.*) | Routes to (colon-delimited) | CKAN type | 2024 vol |
|---|---|---|---|
| `input.Illegal Graffiti` | `Property Management:Graffiti:Graffiti Removal` | Graffiti Removal | 2,501 |
| `input.Litter` | Probably `Requests for Street Cleaning` | — | 22,539 |
| `input.Rodent Sighting` | `Inspectional Services:Environmental Services:Rodent Activity` | Rodent Activity | 5,015 |
| `input.Overflowing Trash Can` | Probably `Empty Litter Basket` | — | TBD |

## Scraper Service Code Table

| Slug | Service Code | Human Name | Status |
|---|---|---|---|
| other | `Mayor's 24 Hour Hotline:General Request:General Request` | Other (General Request) | Verified |
| needles | `Mayor's 24 Hour Hotline:Needle Program:Needle Pickup` | Needle Cleanup | Verified |
| encampments | `Mayor's 24 Hour Hotline:Quality of Life:Encampments` | Encampments | Verified |
| potholes | `Public Works Department:Highway Maintenance:Request for Pothole Repair` | Pothole Repair | Verified |
| sidewalks | `Public Works Department:Highway Maintenance:Sidewalk Repair (Make Safe)` | Broken Sidewalk | Verified |
| dead-animals | `Public Works Department:Street Cleaning:Pick up Dead Animal` | Dead Animal Pickup | Verified |
| graffiti | `Property Management:Graffiti:Graffiti Removal` | Graffiti Removal | Fixed 2026-04-11 |
| graffiti-pwd | `Public Works Department:Highway Maintenance:PWD Graffiti` | PWD Graffiti | Added 2026-04-11 |
| litter-baskets | `Public Works Department:Highway Maintenance:Empty Litter Basket` | Empty Litter Basket | Fixed 2026-04-11 |
| rodents | `Inspectional Services:Environmental Services:Rodent Activity` | Rodent Activity | Fixed 2026-04-11 |
| trash-cans | `Inspectional Services:Environmental Services:Overflowing or Un-kept Dumpster` | Overflowing or Un-kept Dumpster | Fixed 2026-04-11 |
| abandoned-vehicles | `Transportation - Traffic Division:Enforcement & Abandoned Vehicles:Abandoned Vehicles` | Abandoned Vehicle | Verified |
| parking | `Transportation - Traffic Division:Enforcement & Abandoned Vehicles:Parking Enforcement` | Illegal Parking | Verified |
| traffic-signals | `Transportation - Traffic Division:Signs & Signals:Traffic Signal Inspection` | Traffic Signal | Verified |
| signs | `Transportation - Traffic Division:Signs & Signals:Sign Repair` | Damaged Sign | Verified |
| abandoned-bikes | `Mayor's 24 Hour Hotline:Abandoned Bicycle:Abandoned Bicycle` | Abandoned Bicycle | Verified |
| illegal-trash | `Public Works Department:Code Enforcement:Improper Storage of Trash (Barrels)` | Residential Trash out Illegally | Verified |
| street-cleaning | `Public Works Department:Street Cleaning:Requests for Street Cleaning` | Requests for Street Cleaning | Verified |

## /services.json Is Incomplete

The endpoint lists only 16 services. CKAN has **200+ distinct type values**.
The unlisted codes are fully queryable — just not discoverable through Open311
service discovery. To find all valid codes, query CKAN for distinct
`subject:reason:type` combinations.


## Creatio (new system) codes — 2026

The new 311 system's cases are served by the same Open311 endpoint but under **UUID** service codes
that `/services.json` never lists. Filtering works (`?service_code=<uuid>&start_date=…`). Discovered by
sweeping `requests.json` June–Sept 2026; full table with observed volumes and description rates in
[creatio-open311-codes.json](creatio-open311-codes.json). Scraper slugs (fetch.py `SERVICE_TYPES`):

| slug | UUID | service_name | legacy type (CREATIO_SERVICE_MAP) |
|---|---|---|---|
| litter-debris | `155a5e9b-8c3a-4279-bbab-f6bba6ddb0d0` | Litter & Debris | Requests for Street Cleaning |
| park-litter-debris | `4278d986-8b62-4a2b-a43d-575e031b8f50` | Park Litter & Debris | Requests for Street Cleaning |
| improper-trash-storage | `acb41f11-e581-42bc-a0a5-877cb3a07747` | Improper Trash Storage | Improper Storage of Trash (Barrels) |
| trash-out-early | `8a0698b8-9f00-4977-b907-aae2553aa2d3` | Trash Placed Out Early | Improper Storage of Trash (Barrels) |
| overflowing-trash | `c8e719d6-06ce-4375-813d-dccb3ca66402` | Overflowing Trash | Improper Storage of Trash (Barrels) |
| illegal-dumping | `60b145be-aef5-4a3c-8754-51472cf44088` | Illegal Dumping or Disposal | Illegal Dumping |
| missed-waste | `994a8200-95d6-4720-826c-19bd142847b5` | Missed Waste Pick-up | Missed Trash/Recycling/Yard Waste/Bulk Item |
| ce-collection | `cb65b3ee-ab13-4c3c-8f3b-ffc743f99c94` | Code Enforcement Collection | CE Collection |
| student-move-in | `715f7134-aac4-43f4-9e8b-b6fff5f47ad3` | Student Move-In (Trash Collection) | — |

These slugs start at 2026-06-01 (`SLUG_START`); nothing exists before. No needle or encampment code
exists in the new system as of Sept 2026 — watch `metadata/source_health.json` `new_service_names`.
