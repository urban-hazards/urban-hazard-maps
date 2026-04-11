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
