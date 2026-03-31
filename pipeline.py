#!/usr/bin/env python3
"""
Boston 311 Needle Hotspot Pipeline
====================================
Fetches needle-related 311 requests from Boston's open data portal,
processes them, and generates a self-contained static HTML dashboard
with a Leaflet.js heatmap.

Output: docs/index.html (served by GitHub Pages)

Run manually:   python pipeline.py
Run multi-year: python pipeline.py 2023 2024 2025 2026
Automated:      GitHub Actions cron (see .github/workflows/update.yml)
"""

import csv
import io
import json
import math
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from string import Template

# ── Config ──────────────────────────────────────────────────────────────────

CKAN_BASE = "https://data.boston.gov/api/3/action"

# Resource IDs for each year's 311 dataset on data.boston.gov
RESOURCE_IDS = {
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

NEEDLE_TYPES = {"Needle Pickup", "Needle Clean-up", "Needle Cleanup"}

BOSTON_BBOX = {
    "lat_min": 42.2279, "lat_max": 42.3969,
    "lon_min": -71.1912, "lon_max": -70.9235,
}

OUTPUT_DIR = Path("docs")
UA = "Boston311NeedlePipeline/2.0 (github-actions; public-health-research)"

# ── Data fetching ───────────────────────────────────────────────────────────

def _api_get(url: str) -> dict | None:
    """GET a CKAN API endpoint, return parsed JSON or None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  ✗ API error: {e}")
        return None


def fetch_needle_records_sql(resource_id: str) -> list[dict]:
    """Use CKAN datastore_search_sql to pull only needle rows (fast)."""
    type_clauses = " OR ".join(f"\"type\" = '{t}'" for t in NEEDLE_TYPES)
    sql = (
        f'SELECT * FROM "{resource_id}" '
        f'WHERE ({type_clauses}) '
        f'OR LOWER("type") LIKE \'%needle%\''
    )
    url = f"{CKAN_BASE}/datastore_search_sql?sql={urllib.parse.quote(sql)}"
    data = _api_get(url)
    if data and data.get("success"):
        return data["result"]["records"]
    return []


def fetch_needle_records_paged(resource_id: str) -> list[dict]:
    """Fallback: page through datastore_search with a TYPE filter."""
    all_records = []
    for needle_type in NEEDLE_TYPES:
        offset = 0
        limit = 5000
        while True:
            filters = json.dumps({"type": needle_type})
            url = (
                f"{CKAN_BASE}/datastore_search"
                f"?resource_id={resource_id}"
                f"&filters={urllib.parse.quote(filters)}"
                f"&limit={limit}&offset={offset}"
            )
            data = _api_get(url)
            if not data or not data.get("success"):
                break
            records = data["result"]["records"]
            all_records.extend(records)
            if len(records) < limit:
                break
            offset += limit
    return all_records


def fetch_year(year: int) -> list[dict]:
    """Fetch needle records for a given year."""
    rid = RESOURCE_IDS.get(year)
    if not rid:
        print(f"  ⚠ No resource ID for {year}, skipping")
        return []

    print(f"  → {year}: trying SQL API...", end=" ", flush=True)
    records = fetch_needle_records_sql(rid)
    if records:
        print(f"got {len(records)} records")
        return records

    print(f"retrying with paged search...", end=" ", flush=True)
    records = fetch_needle_records_paged(rid)
    print(f"got {len(records)} records")
    return records


# ── Cleaning ────────────────────────────────────────────────────────────────

def clean(row: dict) -> dict | None:
    """Normalize a raw API record. Returns None if invalid."""
    try:
        lat = float(row.get("latitude") or row.get("LATITUDE") or 0)
        lon = float(row.get("longitude") or row.get("LONGITUDE") or 0)
    except (ValueError, TypeError):
        return None

    if not (BOSTON_BBOX["lat_min"] <= lat <= BOSTON_BBOX["lat_max"]):
        return None
    if not (BOSTON_BBOX["lon_min"] <= lon <= BOSTON_BBOX["lon_max"]):
        return None

    dt_str = row.get("open_dt") or row.get("OPEN_DT") or ""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(dt_str[:19], fmt)
            break
        except ValueError:
            continue
    else:
        return None

    closed_str = row.get("closed_dt") or row.get("CLOSED_DT") or ""
    closed = None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            closed = datetime.strptime(closed_str[:19], fmt)
            break
        except ValueError:
            continue

    hood = (
        row.get("neighborhood")
        or row.get("NEIGHBORHOOD")
        or row.get("neighborhood_services_district")
        or ""
    ).strip()

    street = (
        row.get("location_street_name")
        or row.get("LOCATION_STREET_NAME")
        or ""
    ).strip()

    return {
        "lat": lat,
        "lng": lon,
        "dt": dt.isoformat(),
        "year": dt.year,
        "month": dt.month,
        "hour": dt.hour,
        "dow": dt.strftime("%A"),
        "hood": hood,
        "street": street,
        "zipcode": (row.get("location_zipcode") or row.get("LOCATION_ZIPCODE") or "").strip()[:5],
        "resp_hrs": (
            round((closed - dt).total_seconds() / 3600, 1) if closed else None
        ),
    }


# ── Analytics ───────────────────────────────────────────────────────────────

def compute_stats(records: list[dict]) -> dict:
    """Compute all the stats the HTML template needs."""

    years = sorted(set(r["year"] for r in records))

    # Compact point array for client-side filtering: [lat, lng, year, month]
    points = [[r["lat"], r["lng"], r["year"], r["month"]] for r in records]

    # Neighborhood breakdown
    by_hood = defaultdict(list)
    for r in records:
        by_hood[r["hood"] or "Unknown"].append(r)

    hood_stats = []
    for name, recs in sorted(by_hood.items(), key=lambda x: -len(x[1])):
        streets = Counter(r["street"] for r in recs if r["street"])
        resp = [r["resp_hrs"] for r in recs if r["resp_hrs"] is not None]
        hood_stats.append({
            "name": name,
            "count": len(recs),
            "pct": round(len(recs) / len(records) * 100, 1),
            "top_street": streets.most_common(1)[0][0] if streets else "—",
            "avg_resp": round(sum(resp) / max(len(resp), 1), 1),
        })

    # Hourly distribution
    hourly = Counter(r["hour"] for r in records)
    hourly_data = [hourly.get(h, 0) for h in range(24)]

    # Monthly counts by year for Chart.js trend line
    year_monthly = {
        str(y): [sum(1 for r in records if r["year"] == y and r["month"] == m)
                 for m in range(1, 13)]
        for y in years
    }

    # Top zip codes
    zip_counts = Counter(r["zipcode"] for r in records if r["zipcode"])
    zip_stats = [{"zip": z, "count": c} for z, c in zip_counts.most_common(10)]

    # Individual markers for zoom-in layer (cap at 3000 most recent)
    recent = sorted(records, key=lambda r: r["dt"], reverse=True)[:3000]
    markers = [
        {"lat": r["lat"], "lng": r["lng"], "dt": r["dt"][:10],
         "hood": r["hood"], "street": r["street"], "zip": r["zipcode"]}
        for r in recent
    ]

    dow = Counter(r["dow"] for r in records)

    return {
        "total": len(records),
        "years": years,
        "points": points,
        "hoods": hood_stats[:15],
        "hourly": hourly_data,
        "year_monthly": year_monthly,
        "zip_stats": zip_stats,
        "markers": markers,
        "generated": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        "peak_hood": hood_stats[0]["name"] if hood_stats else "—",
        "peak_hour": max(range(24), key=lambda h: hourly.get(h, 0)),
        "peak_dow": dow.most_common(1)[0][0] if dow else "—",
        "avg_monthly": round(len(records) / max(len(set(
            f"{r['year']}-{r['month']}" for r in records)), 1), 1),
    }


# ── HTML Generation ─────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Boston 311 Needle Requests</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body { height:100%; overflow:hidden; }
  body { background:#f0f0f0; color:#1a1a1a;
    font-family:'Source Sans 3','Segoe UI',system-ui,sans-serif;
    display:flex; flex-direction:column; }

  /* ── Header ── */
  .hdr {
    background:#fff; border-bottom:1px solid #d0d0d0;
    padding:10px 16px; display:flex; align-items:center;
    justify-content:space-between; flex-shrink:0; gap:12px;
    box-shadow:0 1px 3px rgba(0,0,0,.1);
  }
  .hdr-left { display:flex; align-items:baseline; gap:10px; }
  .hdr-title { font-size:18px; font-weight:700; color:#1a1a1a; }
  .hdr-sub { font-size:12px; color:#666; }
  .hdr-right { font-size:11px; color:#888; }

  /* ── Main layout ── */
  .main { flex:1; display:flex; overflow:hidden; }

  /* ── Map area ── */
  #map-wrap { flex:1; position:relative; }
  #map { position:absolute; inset:0; }

  /* Filter overlay — floats over the map, top-right */
  #filter-box {
    position:absolute; top:10px; right:10px; z-index:500;
    background:rgba(255,255,255,0.96); border:1px solid #ccc;
    border-radius:6px; padding:12px 14px; min-width:160px;
    box-shadow:0 2px 10px rgba(0,0,0,.15);
    font-size:13px; line-height:1.4;
  }
  .filter-section { margin-bottom:10px; }
  .filter-section:last-child { margin-bottom:0; }
  .filter-label { font-weight:700; font-size:11px; color:#444;
    text-transform:uppercase; letter-spacing:.05em; margin-bottom:5px; }
  .radio-row { display:flex; align-items:center; gap:5px;
    padding:1px 0; cursor:pointer; color:#333; }
  .radio-row input { cursor:pointer; accent-color:#e85a1b; }
  .radio-row:hover { color:#e85a1b; }

  /* Showing count box */
  #count-box {
    position:absolute; bottom:28px; left:10px; z-index:500;
    background:rgba(255,255,255,0.93); border:1px solid #ccc;
    border-radius:4px; padding:6px 10px; font-size:12px; color:#333;
    box-shadow:0 1px 5px rgba(0,0,0,.12);
  }

  /* ── Right charts panel ── */
  #charts-panel {
    width:300px; flex-shrink:0; background:#fff;
    border-left:1px solid #d0d0d0; overflow-y:auto;
    display:flex; flex-direction:column;
  }
  .chart-section { padding:14px 14px 10px; border-bottom:1px solid #e8e8e8; }
  .chart-title { font-size:13px; font-weight:700; color:#222;
    margin-bottom:10px; }
  .chart-sub { font-size:11px; color:#888; margin-top:4px; }

  /* Legend strip */
  .legend-strip { display:flex; align-items:center; gap:6px;
    font-size:11px; color:#666; margin-top:6px; }
  .legend-grad { height:8px; flex:1; border-radius:4px;
    background:linear-gradient(90deg,
      transparent 0%, #00aa44 20%, #ffff00 50%, #ff8800 75%, #cc0000 100%); }

  /* Neighborhood table */
  .hood-table { width:100%; border-collapse:collapse; font-size:12px; }
  .hood-table td { padding:4px 2px; }
  .hood-table .hname { color:#222; width:45%; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis; max-width:110px; }
  .hood-table .hbar-cell { width:40%; }
  .hbar { height:6px; border-radius:3px; background:#4e79a7; }
  .hood-table .hcount { color:#e85a1b; font-weight:600;
    text-align:right; width:15%; }

  /* Zip table */
  .zip-row { display:flex; align-items:center; gap:6px;
    font-size:12px; padding:3px 0; }
  .zip-label { width:55px; color:#555; font-weight:600; }
  .zip-bar-wrap { flex:1; }
  .zip-bar { height:6px; border-radius:3px; background:#76b7b2; }
  .zip-count { width:45px; text-align:right; color:#333; }

  /* Leaflet popup */
  .info-popup { font-size:12px; line-height:1.6; color:#222; }
  .info-popup b { font-size:13px; color:#e85a1b; display:block; }

  @media(max-width:900px) {
    #charts-panel { display:none; }
  }
  @media(max-width:640px) {
    .main { flex-direction:column; }
    #map-wrap { flex:none; height:55vh; }
    #map { position:relative; height:100%; }
    #filter-box { font-size:11px; padding:8px 10px; }
  }
</style>
</head>
<body>

<!-- ── Header ── -->
<div class="hdr">
  <div class="hdr-left">
    <span class="hdr-title">Boston 311 Needle Requests</span>
    <span class="hdr-sub">Needle Pickup &amp; Needle Clean-up · $YEARS</span>
  </div>
  <div class="hdr-right">
    Data: <a href="https://data.boston.gov/dataset/311-service-requests"
      target="_blank" style="color:#4e79a7">data.boston.gov</a>
    &nbsp;·&nbsp; Updated $GENERATED
    &nbsp;·&nbsp; <a href="https://github.com/coffeethencode/boston-needle-map"
      target="_blank" style="color:#4e79a7">Source</a>
  </div>
</div>

<!-- ── Main ── -->
<div class="main">

  <!-- Map -->
  <div id="map-wrap">
    <div id="map"></div>

    <!-- Filter overlay -->
    <div id="filter-box">
      <div class="filter-section">
        <div class="filter-label">Year</div>
        <label class="radio-row">
          <input type="radio" name="yr" value="all" checked> All Years
        </label>
        <!-- year radios injected by JS -->
      </div>
      <div class="filter-section">
        <div class="filter-label">Month</div>
        <label class="radio-row">
          <input type="radio" name="mo" value="0" checked> All Months
        </label>
        <label class="radio-row"><input type="radio" name="mo" value="1"> January</label>
        <label class="radio-row"><input type="radio" name="mo" value="2"> February</label>
        <label class="radio-row"><input type="radio" name="mo" value="3"> March</label>
        <label class="radio-row"><input type="radio" name="mo" value="4"> April</label>
        <label class="radio-row"><input type="radio" name="mo" value="5"> May</label>
        <label class="radio-row"><input type="radio" name="mo" value="6"> June</label>
        <label class="radio-row"><input type="radio" name="mo" value="7"> July</label>
        <label class="radio-row"><input type="radio" name="mo" value="8"> August</label>
        <label class="radio-row"><input type="radio" name="mo" value="9"> September</label>
        <label class="radio-row"><input type="radio" name="mo" value="10"> October</label>
        <label class="radio-row"><input type="radio" name="mo" value="11"> November</label>
        <label class="radio-row"><input type="radio" name="mo" value="12"> December</label>
      </div>
    </div>

    <!-- Count readout -->
    <div id="count-box">Showing <strong id="count-val">$TOTAL</strong> requests</div>
  </div>

  <!-- Charts panel -->
  <div id="charts-panel">

    <div class="chart-section">
      <div class="chart-title">Requests by Year</div>
      <canvas id="trend-chart" height="160"></canvas>
      <div class="legend-strip">
        <span>Low</span>
        <div class="legend-grad"></div>
        <span>High</span>
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-title">Top Neighborhoods</div>
      <table class="hood-table" id="hood-table"></table>
    </div>

    <div class="chart-section">
      <div class="chart-title">Requests by Hour</div>
      <canvas id="hour-chart" height="100"></canvas>
    </div>

    <div class="chart-section">
      <div class="chart-title">Top Zip Codes</div>
      <div id="zip-list"></div>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script>
// ── Data ──────────────────────────────────────────────────────────────
// POINTS: [lat, lng, year, month] — compact, filtered client-side
const POINTS      = $POINTS_JSON;
const MARKERS     = $MARKERS_JSON;
const HOODS       = $HOODS_JSON;
const HOURLY      = $HOURLY_JSON;
const YEAR_MONTHLY= $YEAR_MONTHLY_JSON;
const ZIP_STATS   = $ZIP_STATS_JSON;
const ALL_YEARS   = $YEARS_JSON;

// ── Heat gradient: green → yellow → orange → red (matches Tableau) ───
const GRADIENT = {
  0.00: 'rgba(0,0,0,0)',
  0.12: 'rgba(0,170,68,0.5)',
  0.30: 'rgba(0,204,0,0.75)',
  0.50: 'rgba(255,255,0,0.88)',
  0.70: 'rgba(255,136,0,0.94)',
  0.88: 'rgba(220,30,0,0.97)',
  1.00: 'rgba(150,0,0,1)',
};

// ── State ──────────────────────────────────────────────────────────────
let selYear = 'all', selMonth = 0;

// ── Map ────────────────────────────────────────────────────────────────
const map = L.map('map', { center:[42.332,-71.078], zoom:13 });

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; <a href="https://carto.com/">CARTO</a> &middot; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
  subdomains: 'abcd', maxZoom: 19,
}).addTo(map);

// ── Heatmap ────────────────────────────────────────────────────────────
const BIN = 0.0008;

function buildHeat(yr, mo) {
  const grid = new Map();
  let n = 0;
  for (const [lat, lng, y, m] of POINTS) {
    if (yr !== 'all' && y !== yr) continue;
    if (mo !== 0 && m !== mo) continue;
    const key = `${Math.round(lat/BIN)*BIN},${Math.round(lng/BIN)*BIN}`;
    grid.set(key, (grid.get(key) || 0) + 1);
    n++;
  }
  document.getElementById('count-val').textContent = n.toLocaleString();
  const pts = [];
  grid.forEach((count, key) => {
    const [la, lo] = key.split(',').map(Number);
    pts.push([la, lo, count]);
  });
  const sorted = pts.map(p => p[2]).sort((a,b)=>a-b);
  const p95 = sorted[Math.floor(sorted.length * 0.95)] || 1;
  return L.heatLayer(pts, {
    radius: 38, blur: 28, maxZoom: 16,
    max: p95, minOpacity: 0.4, gradient: GRADIENT,
  });
}

let heatLayer = buildHeat('all', 0);
heatLayer.addTo(map);

function updateHeat() {
  map.removeLayer(heatLayer);
  heatLayer = buildHeat(selYear, selMonth);
  heatLayer.addTo(map);
}

// ── Filters ────────────────────────────────────────────────────────────
// Year radios
const yrSection = document.querySelector('[name=yr]').closest('.filter-section');
ALL_YEARS.forEach(yr => {
  const lbl = document.createElement('label');
  lbl.className = 'radio-row';
  lbl.innerHTML = `<input type="radio" name="yr" value="${yr}"> ${yr}`;
  yrSection.appendChild(lbl);
});

document.querySelectorAll('[name=yr]').forEach(r => {
  r.addEventListener('change', () => { selYear = r.value === 'all' ? 'all' : +r.value; updateHeat(); updateTrendChart(); });
});
document.querySelectorAll('[name=mo]').forEach(r => {
  r.addEventListener('change', () => { selMonth = +r.value; updateHeat(); });
});

// ── Marker layer (zoom 15+) ────────────────────────────────────────────
const markerGroup = L.layerGroup();
MARKERS.forEach(m => {
  L.circleMarker([m.lat, m.lng], {
    radius:5, fillColor:'#e85a1b', fillOpacity:0.85,
    color:'#fff', weight:1, opacity:0.6,
  }).bindPopup(
    `<div class="info-popup"><b>${m.hood||'Unknown'}</b>${m.street||''}<br>${m.dt}${m.zip?' &middot; '+m.zip:''}</div>`
  ).addTo(markerGroup);
});
map.on('zoomend', () => {
  if (map.getZoom() >= 15) map.addLayer(markerGroup);
  else map.removeLayer(markerGroup);
});

// ── Trend chart (Chart.js) ─────────────────────────────────────────────
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const YEAR_COLORS  = ['#4e79a7','#f28e2b','#e15759','#76b7b2','#59a14f'];

function buildTrendDatasets(filterYear) {
  return Object.entries(YEAR_MONTHLY)
    .filter(([yr]) => filterYear === 'all' || +yr === filterYear)
    .map(([yr, vals], i) => ({
      label: yr,
      data: vals,
      borderColor: YEAR_COLORS[i % YEAR_COLORS.length],
      backgroundColor: YEAR_COLORS[i % YEAR_COLORS.length] + '22',
      borderWidth: 2,
      pointRadius: 3,
      tension: 0.3,
      fill: false,
    }));
}

const trendCtx = document.getElementById('trend-chart').getContext('2d');
const trendChart = new Chart(trendCtx, {
  type: 'line',
  data: { labels: MONTHS_SHORT, datasets: buildTrendDatasets('all') },
  options: {
    responsive: true,
    plugins: { legend:{ labels:{ font:{size:10}, boxWidth:12 } } },
    scales: {
      x: { ticks:{ font:{size:10} }, grid:{ color:'#eee' } },
      y: { ticks:{ font:{size:10} }, grid:{ color:'#eee' },
           title:{ display:true, text:'Cases', font:{size:10} } },
    },
    animation: { duration: 400 },
  },
});

function updateTrendChart() {
  trendChart.data.datasets = buildTrendDatasets(selYear);
  trendChart.update();
}

// ── Neighborhood table ──────────────────────────────────────────────────
(function() {
  const el = document.getElementById('hood-table');
  const max = HOODS[0] ? HOODS[0].count : 1;
  HOODS.forEach(h => {
    const w = Math.max(2, Math.round((h.count / max) * 100));
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="hname" title="${h.name}">${h.name}</td>
      <td class="hbar-cell"><div class="hbar" style="width:${w}%"></div></td>
      <td class="hcount">${h.count.toLocaleString()}</td>`;
    el.appendChild(tr);
  });
})();

// ── Hour chart ─────────────────────────────────────────────────────────
new Chart(document.getElementById('hour-chart').getContext('2d'), {
  type: 'bar',
  data: {
    labels: Array.from({length:24}, (_,i) => i===0?'12a':i<12?i+'a':i===12?'12p':(i-12)+'p'),
    datasets: [{
      data: HOURLY,
      backgroundColor: HOURLY.map(v => {
        const t = v / Math.max(...HOURLY);
        return t > 0.7 ? '#cc0000' : t > 0.4 ? '#ff8800' : '#4e79a7';
      }),
      borderWidth: 0,
    }],
  },
  options: {
    responsive: true,
    plugins: { legend:{ display:false } },
    scales: {
      x: { ticks:{ font:{size:8}, maxRotation:0 }, grid:{ display:false } },
      y: { ticks:{ font:{size:9} }, grid:{ color:'#eee' } },
    },
  },
});

// ── Zip code list ───────────────────────────────────────────────────────
(function() {
  const el = document.getElementById('zip-list');
  const max = ZIP_STATS[0] ? ZIP_STATS[0].count : 1;
  ZIP_STATS.forEach(z => {
    const w = Math.max(2, Math.round((z.count / max) * 100));
    const div = document.createElement('div');
    div.className = 'zip-row';
    div.innerHTML = `
      <span class="zip-label">${z.zip}</span>
      <div class="zip-bar-wrap"><div class="zip-bar" style="width:${w}%"></div></div>
      <span class="zip-count">${z.count.toLocaleString()}</span>`;
    el.appendChild(div);
  });
})();
</script>
</body>
</html>"""


def generate_html(stats: dict) -> str:
    """Inject computed stats into the HTML template."""
    html = HTML_TEMPLATE
    html = html.replace("$GENERATED", stats["generated"])
    html = html.replace("$TOTAL", f"{stats['total']:,}")
    html = html.replace("$PEAK_HOOD", stats["peak_hood"])
    html = html.replace("${PEAK_HOUR}", str(stats["peak_hour"]))
    html = html.replace("$PEAK_DOW", stats["peak_dow"])
    html = html.replace("$AVG_MONTHLY", str(stats["avg_monthly"]))
    html = html.replace("$YEARS", ", ".join(str(y) for y in stats["years"]))
    html = html.replace("$POINTS_JSON", json.dumps(stats["points"]))
    html = html.replace("$YEARS_JSON", json.dumps(stats["years"]))
    html = html.replace("$MARKERS_JSON", json.dumps(stats["markers"]))
    html = html.replace("$HOODS_JSON", json.dumps(stats["hoods"]))
    html = html.replace("$HOURLY_JSON", json.dumps(stats["hourly"]))
    html = html.replace("$YEAR_MONTHLY_JSON", json.dumps(stats["year_monthly"]))
    html = html.replace("$ZIP_STATS_JSON", json.dumps(stats["zip_stats"]))
    return html


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        years = sorted(int(y) for y in sys.argv[1:])
    else:
        # Default: last 3 years + current
        now = datetime.now().year
        years = [y for y in range(now - 2, now + 1) if y in RESOURCE_IDS]

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  Boston 311 Needle Hotspot Pipeline          ║")
    print(f"║  Years: {', '.join(str(y) for y in years):<37s} ║")
    print(f"╚══════════════════════════════════════════════╝")

    all_records = []
    for year in years:
        raw = fetch_year(year)
        cleaned = [r for r in (clean(row) for row in raw) if r is not None]
        print(f"  ✓ {year}: {len(raw)} raw → {len(cleaned)} valid")
        all_records.extend(cleaned)

    if not all_records:
        print("\n⚠ No records retrieved. Writing placeholder page.")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "index.html").write_text(
            "<html><body><h1>No data available</h1>"
            "<p>The pipeline could not retrieve data from data.boston.gov. "
            "Check the CKAN API or resource IDs.</p></body></html>"
        )
        return

    print(f"\n  Total valid records: {len(all_records):,}")
    print(f"  Computing stats...")

    stats = compute_stats(all_records)
    html = generate_html(stats)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  ✓ Wrote {out_path} ({len(html):,} bytes)")

    # Also dump raw data as JSON for anyone who wants it
    data_path = OUTPUT_DIR / "needle_data.json"
    data_path.write_text(json.dumps({
        "generated": stats["generated"],
        "total": stats["total"],
        "years": stats["years"],
        "records": all_records,
    }), encoding="utf-8")
    print(f"  ✓ Wrote {data_path}")

    print(f"\n  Done. Serve with: cd docs && python -m http.server 8000")


if __name__ == "__main__":
    main()
