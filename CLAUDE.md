# Boston Needle Map - Project Guide

## Quick Reference
- **Architecture:** Monorepo — Astro SSR frontend + FastAPI backend
- **Backend:** Python 3.12+, uv, FastAPI, Pydantic v2, Typer CLI
- **Frontend:** Astro (hybrid SSR), React islands, TypeScript (no semicolons), pnpm
- **Linting (backend):** ruff + mypy (strict mode)
- **Linting (frontend):** Biome (no semicolons, tabs)
- **Git hooks:** lefthook (runs ruff + mypy + biome on pre-commit)
- **Deployment:** Railway (two services: backend + frontend)

## Backend Commands (run from `backend/`)
- `uv run boston-needle-map run` -- fetch data and print summary
- `uv run boston-needle-map serve` -- start FastAPI server on :8000
- `uv run boston-needle-map cache-clear` -- clear tmp/ cache
- `uv run boston-needle-map dump-json` -- export data as JSON
- `uv run ruff check src/ tests/` -- lint
- `uv run ruff format src/ tests/` -- format
- `uv run mypy src/` -- type check
- `uv run pytest` -- run tests

## Frontend Commands (run from `frontend/`)
- `pnpm dev` -- start dev server on :4321
- `pnpm build` -- build for production
- `pnpm preview` -- preview production build
- `pnpm check` -- astro check + biome check
- `pnpm lint` -- biome lint
- `pnpm format` -- biome format

## Architecture
- `backend/` -- FastAPI Python service
  - `src/boston_needle_map/`
    - `api.py` -- FastAPI app with REST endpoints
    - `cli.py` -- Typer CLI entrypoint
    - `config.py` -- constants (CKAN URLs, resource IDs, bounding box)
    - `models.py` -- Pydantic models (CleanedRecord, DashboardStats, etc.)
    - `fetcher.py` -- CKAN API data fetching
    - `cleaner.py` -- raw record normalization and validation
    - `analytics.py` -- stats computation (heatmap bins, neighborhoods, hourly)
    - `cache.py` -- tmp/ directory caching for fetched data
  - `Dockerfile` -- backend container
- `frontend/` -- Astro SSR service
  - `src/pages/` -- Astro pages (index, neighborhood detail)
  - `src/components/` -- Astro server components + React client islands
  - `src/lib/` -- TypeScript types, API client, helpers
  - `src/styles/` -- global CSS
  - `Dockerfile` -- frontend container

## API Endpoints
- `GET /api/health` -- health check
- `GET /api/stats` -- full DashboardStats payload
- `GET /api/stats/summary` -- lightweight summary
- `GET /api/neighborhoods` -- neighborhood list
- `GET /api/neighborhoods/{slug}` -- single neighborhood
- `GET /api/heatmap?year=all&month=0` -- heatmap data
- `GET /api/hourly` -- hourly distribution
- `GET /api/monthly` -- year-monthly breakdown
- `GET /api/zips` -- top zip codes
- `GET /api/markers?limit=3000` -- map markers

## Conventions
- All data flows through Pydantic models (CleanedRecord, DashboardStats)
- Never commit secrets or API keys
- Cache files go to tmp/; this directory is gitignored
- Use `python-dateutil` for datetime parsing
- TypeScript: no semicolons, use Biome, tabs for indentation
- Frontend uses pnpm, backend uses uv
