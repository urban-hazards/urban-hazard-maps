# Boston Urban Hazard Maps

Interactive heatmaps of public health and quality-of-life data from Boston's 311 open data portal. Currently visualizes two independently reported datasets: **sharps (needle) collection requests** and **encampment reports**.

These datasets are presented together because they are both publicly available through the same Boston 311 API — not because of any implied correlation or causation between them.

![Data](https://img.shields.io/badge/source-data.boston.gov-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## How it works

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  data.boston.gov     │────>│  FastAPI backend      │────>│  Astro frontend │
│  CKAN Datastore API │     │  Python 3.12 + uv     │     │  React + Leaflet│
│  311 Service Reqs   │     │  Pydantic + Typer     │     │  Railway deploy │
└─────────────────────┘     └──────────────────────┘     └─────────────────┘
```

**Key details:**
- **Data source:** [Analyze Boston](https://data.boston.gov/dataset/311-service-requests) — 311 Service Requests dataset
- **Sharps filter:** `TYPE` in `("Needle Pickup", "Needle Clean-up", "Needle Cleanup")` — available 2015–present
- **Encampment filter:** `TYPE = "Encampments"` — available 2025–present
- **API:** Uses CKAN Datastore SQL API (fetches only matching rows, not the full dataset)
- **Caching:** Redis in production, filesystem locally. Avoids re-fetching during development.
- **Deployment:** Railway (two services: backend + frontend)

---

## Setup

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [pnpm](https://pnpm.io/) (frontend package manager)
- [lefthook](https://github.com/evilmartians/lefthook) (git hooks)

### Install

```bash
# Clone the repo
git clone https://github.com/urban-hazards/urban-hazard-maps.git
cd urban-hazard-maps

# Backend
cd backend
uv sync

# Frontend
cd ../frontend
pnpm install

# Git hooks
lefthook install
```

---

## Usage

### Run locally

```bash
# Start the backend (port 8000)
cd backend
uv run boston-needle-map serve

# In another terminal, start the frontend (port 4321)
cd frontend
pnpm dev
```

### Other backend commands

```bash
# Fetch data and print summary
uv run boston-needle-map run

# Fetch specific years
uv run boston-needle-map run 2024 2025 2026

# Clear cached data
uv run boston-needle-map cache-clear

# Export data as JSON
uv run boston-needle-map dump-json
```

---

## Development

### Linting & Type Checking

**Backend** (from `backend/`):
```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
uv run pytest
```

**Frontend** (from `frontend/`):
```bash
pnpm check    # astro check + biome check
pnpm lint     # biome lint
pnpm format   # biome format
```

Git hooks (via lefthook) run ruff, mypy, and biome automatically on commit. All changes go through PRs with CI checks required to pass before merge.

---

## Project Structure

```
urban-hazard-maps/
├── backend/
│   ├── src/boston_needle_map/       # Python package
│   │   ├── api.py                  # FastAPI app (needle + encampment endpoints)
│   │   ├── cli.py                  # Typer CLI
│   │   ├── config.py               # Constants (CKAN URLs, resource IDs, type filters)
│   │   ├── models.py               # Pydantic models
│   │   ├── fetcher.py              # CKAN API data fetching
│   │   ├── cleaner.py              # Record normalization & validation
│   │   ├── analytics.py            # Stats computation
│   │   └── cache.py                # Cache adapter (Redis / filesystem)
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/                  # Astro pages
│   │   ├── components/             # Astro + React components
│   │   ├── lib/                    # TypeScript types, API client
│   │   └── styles/                 # Global CSS
│   ├── Dockerfile
│   └── package.json
├── CLAUDE.md                       # Project guide
└── lefthook.yml                    # Git hook config
```

---

## Data Sources

All data comes from the City of Boston's [Analyze Boston](https://data.boston.gov/) open data portal.

| Dataset | 311 Type | Available | Description |
|---|---|---|---|
| Sharps | `Needle Pickup`, `Needle Clean-up` | 2015–present | Reports to the city's Mobile Sharps Collection Team for safe retrieval of discarded sharps in public spaces |
| Encampments | `Encampments` | 2025–present | 311 reports filed under the "Quality of Life" category |

These are separate, independent datasets from the same 311 system. This project presents them on a shared map for geographic context — it does not assert or imply any relationship between them.

---

## License

MIT
