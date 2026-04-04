"""Caching layer for fetched API data in tmp/."""

import json
import time
from pathlib import Path
from typing import Any

from boston_needle_map.config import CACHE_DIR

# Default max age: 24 hours
DEFAULT_MAX_AGE_SECONDS = 86400


def _ensure_cache_dir() -> None:
    """Create the cache directory if it doesn't exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_path(year: int) -> Path:
    """Return the cache file path for a given year."""
    return CACHE_DIR / f"year_{year}.json"


def load_cached(year: int, max_age: int = DEFAULT_MAX_AGE_SECONDS) -> list[dict[str, Any]] | None:
    """Load cached records for a year. Returns None if missing or stale."""
    path = get_cache_path(year)
    if not path.exists():
        return None

    age = time.time() - path.stat().st_mtime
    if age > max_age:
        print(f"  ⏳ Cache for {year} is stale ({age / 3600:.1f}h old), re-fetching")
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"  ✓ Loaded {len(data)} cached records for {year}")
        return data  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠ Cache read error for {year}: {e}")
        return None


def save_cache(year: int, records: list[dict[str, Any]]) -> None:
    """Save raw API records to cache."""
    _ensure_cache_dir()
    path = get_cache_path(year)
    path.write_text(json.dumps(records), encoding="utf-8")
    print(f"  💾 Cached {len(records)} records for {year}")


def clear_cache() -> None:
    """Remove all cached files."""
    if not CACHE_DIR.exists():
        print("  No cache directory found.")
        return

    count = 0
    for f in CACHE_DIR.glob("year_*.json"):
        f.unlink()
        count += 1
    print(f"  Cleared {count} cached file(s) from {CACHE_DIR}/")
