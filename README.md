# Boston 311 Needle Hotspot Map

Fully automated pipeline that pulls needle cleanup requests from Boston's 311 open data portal and publishes an interactive heatmap to GitHub Pages — no manual steps, no Tableau, no paid services.

**Live site:** https://coffeethencode.github.io/boston-needle-map/

![Pipeline](https://img.shields.io/badge/schedule-monthly-orange)
![Data](https://img.shields.io/badge/source-data.boston.gov-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## How it works

```
┌─────────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  data.boston.gov     │────▶│  pipeline.py  │────▶│  docs/index.html│
│  CKAN Datastore API │     │  Python 3.12  │     │  Leaflet.js map │
│  311 Service Reqs   │     │  No deps!     │     │  Static HTML    │
└─────────────────────┘     └──────────────┘     └────────┬────────┘
                                                          │
                            ┌──────────────┐              │
                            │ GitHub Pages │◀─────────────┘
                            │ Free hosting │  gh-pages branch
                            └──────────────┘
```

**Key details:**
- **Data source:** [Analyze Boston](https://data.boston.gov/dataset/311-service-requests) — 311 Service Requests dataset
- **Filter:** `TYPE = "Needle Pickup"` or `"Needle Clean-up"`
- **API:** Uses CKAN Datastore SQL API (fetches only needle rows, not the full 200MB+ CSV)
- **Output:** Self-contained HTML with embedded data, Leaflet.js heatmap, and CARTO dark tiles
- **Schedule:** GitHub Actions cron runs at 2 AM EST on the 1st of each month
- **Zero dependencies:** Python standard library only (no pip install needed)

---

## Setup (5 minutes)

### 1. Create the repo

```bash
# Clone or fork this repo
git clone https://github.com/<you>/boston-needle-map.git
cd boston-needle-map
```

### 2. Test locally

```bash
# Fetch last 3 years of data and generate the map
python pipeline.py

# Or specify exact years
python pipeline.py 2022 2023 2024 2025 2026

# Preview it
cd docs && python -m http.server 8000
# Open http://localhost:8000
```

### 3. Enable GitHub Pages

1. Push to GitHub: `git add . && git commit -m "init" && git push`
2. Go to **Settings → Pages**
3. Under "Source", select **GitHub Actions** (or `gh-pages` branch if using the deploy action)
4. The Actions workflow will run automatically on push

### 4. Done

Your map is live at `https://<username>.github.io/boston-needle-map/`

It auto-updates on the 1st of every month. You can also trigger it manually:
**Actions tab → "Update Needle Hotspot Map" → Run workflow**

---

## What's on the dashboard

| Tab | What it shows |
|---|---|
| **Heat Map** | Leaflet.js heatmap with dark CARTO tiles. Zoom in past level 15 to see individual markers with popups. |
| **Monthly Trend** | Bar chart of requests per month across all years |
| **Neighborhoods** | Table ranked by request count with % of total, top street, avg response time |
| **By Hour** | 24-hour distribution showing peak request times |

---

## Configuration

Edit the top of `pipeline.py` to adjust:

| Variable | What it does |
|---|---|
| `RESOURCE_IDS` | Map of year → CKAN resource ID. Add new years as Boston publishes them. |
| `NEEDLE_TYPES` | Set of TYPE values to filter on. |
| `BOSTON_BBOX` | Bounding box for coordinate validation. |

To find a new year's resource ID:
1. Go to https://data.boston.gov/dataset/311-service-requests
2. Click the year's CSV resource
3. The resource ID is in the URL: `/resource/<THIS-PART>/`

---

## Migrating from Tableau Public

If you were previously publishing to Tableau Public:

| | Tableau Public | This pipeline |
|---|---|---|
| **Automation** | ❌ Manual publish only | ✅ Fully automated (GitHub Actions cron) |
| **Cost** | Free | Free |
| **Hosting** | tableau.com | GitHub Pages (your domain) |
| **Customization** | Limited by Tableau | Full control (HTML/CSS/JS) |
| **Data freshness** | Whenever you remember | Monthly, automatic |
| **Embed** | iframe/Tableau API | Direct link or iframe |
| **Dependencies** | Tableau Desktop | Python 3 (standard library) |

---

## Files

```
boston-needle-map/
├── pipeline.py                        # The pipeline (fetch → process → generate HTML)
├── .github/workflows/update.yml       # GitHub Actions monthly cron + deploy
├── docs/                              # Output directory (served by GitHub Pages)
│   ├── index.html                     # The dashboard (generated)
│   └── needle_data.json               # Raw processed data (generated)
└── README.md
```

---

## Data source

All data comes from the City of Boston's [Analyze Boston](https://data.boston.gov/) open data portal under the [Open Data Commons PDDL license](http://www.opendefinition.org/licenses/odc-pddl).

The 311 dataset contains all service requests. This pipeline filters for needle-related request types, which represent reports to the city's Mobile Sharps Collection Team for picking up discarded needles found in public spaces.
