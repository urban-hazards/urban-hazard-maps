# Open311 API Reference

> Last verified: 2026-04-11

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /v2/services.json` | List available service types (only 16 of 200+) |
| `GET /v2/services/{service_code}.json` | Service definition (404s for input.* and unlisted codes) |
| `GET /v2/requests.json` | Query tickets by service_code, date range, etc. |
| `GET /v2/requests/{id}.json` | Single ticket lookup by case_enquiry_id |
| `GET /v2/discovery.json` | API metadata and spec version |

**Base URL:** `https://boston2-production.spotmobile.net/open311`
**Test URL:** `https://boston2-test.spotmobile.net/open311/v2`

## Rate Limits

- 10 requests/minute (unauthenticated)
- 100 results per page max
- 90-day date range max per query
- 429 response includes `Retry-After` header
- API key request: `https://boston2-production.spotmobile.net/open311/app_requests/new`

## Extensions

Adding `?extensions=true` to any request returns additional fields:

- `extended_attributes.first_name`, `last_name`, `email` — **PII, do not store**
- `attributes[]` — structured form data from the app intake form
- `details{}` — key-value version of attributes

**Structured form fields discovered per type:**
- Needle Pickup: `needle_qty` (One, Few, Many), `needle_loc_type` (Public, Private)
- Rodent Activity: `Rat bites` (Yes/No), `Rats in the house` (Yes/No), `Rats outside of property` (Yes/No)
- Other types: not yet cataloged

These fields are stripped from CKAN. The API is the only source.

## Standard Fields (without extensions)

`service_request_id`, `status`, `status_notes`, `service_name`, `service_code`,
`description`, `requested_datetime`, `updated_datetime`, `address`, `lat`,
`long`, `media_url`, `token`

## What CKAN Strips

| Field | Open311 API | CKAN |
|---|---|---|
| Citizen description (free text) | 81-100% present | **Always empty** |
| Submitted photos (Cloudinary URLs) | 36-85% present | **Always empty** |
| Staff status notes | Present | Truncated to `closure_reason` |
| Structured form data (attributes) | Present via extensions | **Not available** |
| "Other" (General Request) tickets | Present | **Missing entirely** (142k+) |

## Three Service Code Formats

1. **Colon-delimited** (`Subject:Reason:Type`) — the real storage format, maps to CKAN columns
2. **`input.*` prefix** — BOS:311 app form buttons, tag zero stored records
3. **UUID** — rare (e.g. `11d12a6d-...` for Street Light Other)

See [Service Code Mapping](service-code-mapping.md) for the full table.
