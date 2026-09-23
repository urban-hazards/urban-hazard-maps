# Boston Urban Hazard Maps

Interactive heatmaps of publicly available data from Boston's [Analyze Boston](https://data.boston.gov/) open data portal (311 Service Requests).

We map whatever geolocated 311 data is available and interesting. Right now that's three datasets:

- **Sharps collection requests** — reports of discarded needles/syringes for safe pickup
- **Encampment reports** — 311 requests filed under the "Quality of Life" category (2023–present; the dedicated type ended May 27, 2026)
- **Human waste (beta)** — street-cleaning requests classified by text as human waste

**These are independent datasets.** They come from the same 311 system but are unrelated complaint types. We display them on the same map because it's useful to see where the city is responding to different kinds of issues — not because we're claiming any connection between them.

![Data](https://img.shields.io/badge/source-data.boston.gov-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## How it works

```
┌─────────────────────┐     ┌──────────────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  data.boston.gov     │────>│  pipeline/ (daily cron)   │────>│  S3 bucket (Tigris)  │────>│  frontend/ (Astro │
│  CKAN + Open311      │     │  Python 3.12 · uv · spaCy │     │  precomputed JSON    │     │  SSR + React map) │
└─────────────────────┘     └──────────────────────────┘     └─────────────────────┘     └──────────────────┘
```

**Key details:**
- **Data source:** [Analyze Boston](https://data.boston.gov/dataset/311-service-requests) 311 Service Requests (CKAN), plus the city's Open311 feed scraped by `services/open311-scraper/`
- **Sharps filter:** `TYPE` in `("Needle Pickup", "Needle Clean-up", "Needle Cleanup")`, 2015–present
- **Encampment filter:** `TYPE = "Encampments"` (2025+) plus tickets routed to the internal encampment queues (2023+); the dedicated type stopped appearing after May 27, 2026 (see `docs/wiki/encampment-intake-ended-2026.md`)
- **Human waste (beta):** `TYPE = "Requests for Street Cleaning"` classified with a spaCy model, 2024–present
- **Pipeline:** runs daily at 07:00 UTC on Railway, fetches the current year, computes stats, writes JSON to an S3-compatible bucket, and publishes a per-source health file (`docs/wiki/source-health-runbook.md`)
- **Frontend:** Astro SSR reads the bucket with a 5-minute cache; the client filters points by year/month in the browser
- **Deployment:** Railway (two services: pipeline cron + frontend). No GitHub Actions deploy.

---

## Setup

### Prerequisites
- Python 3.12 or 3.13 (spaCy has no 3.14 wheels yet; `pipeline/.python-version` pins 3.13)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [pnpm](https://pnpm.io/) (frontend package manager)
- [lefthook](https://github.com/evilmartians/lefthook) (git hooks)
- Docker (optional, for a local MinIO bucket)

### Install

```bash
git clone https://github.com/urban-hazards/urban-hazard-maps.git
cd urban-hazard-maps

# Pipeline
cd pipeline
uv sync
uv run python -m spacy download en_core_web_sm   # re-run after any `uv sync` that drops it
cp .env.example .env                              # points at local MinIO by default

# Frontend
cd ../frontend
pnpm install
cp .env.example .env

# Git hooks
cd ..
lefthook install
```

---

## Usage

### Run locally

```bash
# Local S3 (MinIO) — from the repo root; console at http://localhost:9001
docker compose up -d

# Run the pipeline once (from pipeline/)
uv run boston-pipeline                 # all datasets
uv run boston-pipeline -d needles      # one dataset
uv run boston-pipeline -d waste --force  # force re-fetch from CKAN
uv run boston-pipeline --verbose

# Start the frontend (from frontend/, port 4321)
pnpm dev
```

The frontend reads whatever the pipeline last wrote to the bucket. `CARTO_BASEMAP_KEY`
(optional) enables the CARTO basemap; without it the map falls back to Esri's keyless tiles.

---

## Development

### Linting, type checking, tests

**Pipeline** (from `pipeline/`):
```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
uv run pytest
```

**Frontend** (from `frontend/`):
```bash
pnpm check    # astro check + biome check
pnpm test     # vitest
pnpm lint     # biome lint
pnpm format   # biome format
```

Git hooks (via lefthook) run ruff, mypy, and biome on commit. All changes go through PRs;
`.github/workflows/pr.yml` must pass before merge.

---

## Project Structure

```
urban-hazard-maps/
├── pipeline/                       # Daily Python cron job (Railway)
│   ├── src/pipeline/
│   │   ├── run.py                  # Orchestrator: fetch → clean → classify → compute → write
│   │   ├── cli.py                  # Typer CLI (`boston-pipeline`)
│   │   ├── config.py               # CKAN resource IDs, type filters, S3 env vars
│   │   ├── fetcher.py              # CKAN fetching (type + queue strategies)
│   │   ├── cleaner.py              # Record normalization & validation
│   │   ├── classifier.py           # spaCy human-waste classifier
│   │   ├── analytics.py            # Heatmap bins, neighborhoods, hourly/monthly stats
│   │   ├── health.py               # Per-source freshness → metadata/source_health.json
│   │   └── storage.py              # S3 read/write
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/                       # Astro SSR site (Railway)
│   ├── src/
│   │   ├── pages/                  # Astro pages
│   │   ├── components/             # Astro components + React islands (HeatMap)
│   │   ├── lib/                    # bucket reader, types, freshness model
│   │   └── styles/
│   ├── Dockerfile
│   └── package.json
├── services/open311-scraper/       # Open311 day-file scraper (Railway)
├── docs/
│   ├── wiki/                       # What we know about Boston 311 (start at INDEX.md)
│   ├── design/                     # Design docs + review transcripts
│   └── architectural-decisions/
├── docker-compose.yml              # Local MinIO
├── CLAUDE.md                       # Project guide for AI assistants
└── lefthook.yml
```

---

## Data Sources

All data comes from the City of Boston's [Analyze Boston](https://data.boston.gov/) open data portal, published under the [Open Data Commons PDDL license](http://www.opendefinition.org/licenses/odc-pddl).

| Dataset | 311 Type | Available | Description |
|---|---|---|---|
| Sharps | `Needle Pickup`, `Needle Clean-up` | 2015–present | Reports to the city's Mobile Sharps Collection Team for safe retrieval of discarded sharps in public spaces |
| Encampments | `Encampments` + internal encampment queues | 2023–present (type stopped May 27, 2026) | 311 reports filed under the "Quality of Life" category |
| Human Waste (beta) | `Requests for Street Cleaning`, NLP-classified | 2024–present | Street-cleaning requests whose text describes human waste; see `/methodology` |

These are separate complaint types within the same 311 system. People call 311 for all kinds of reasons — potholes, noise, graffiti, needles, encampments, etc. We picked these two because they have good geolocation data and are relevant to public health. Showing them on the same map is a convenience, not a claim that they're related.

As more useful 311 categories become available, we may add them.

---

## License

MIT
