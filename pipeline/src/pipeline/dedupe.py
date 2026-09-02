"""Deterministic cross-system fingerprint matching.

Legacy CKAN ids (numeric), Creatio CKAN ids (BCS-…) and Creatio Open311 ids (UUID)
share no namespace, so the same case in two systems can only be recognised by
fingerprint: same legacy-mapped type, same 4-dp coordinates (~11 m), open time
within a small window. Matches are reported as pairs, never silently discarded.
"""

from collections import defaultdict
from typing import Any

from pipeline.cleaner import _parse_datetime
from pipeline.config import CREATIO_SERVICE_MAP

Fingerprint = tuple[str, str, str, int]


def fingerprint(rec: dict[str, Any]) -> Fingerprint | None:
    """(legacy-mapped type, lat 4dp, lng 4dp, Boston-local minute index) or None."""
    try:
        lat = float(rec.get("latitude") or "")
        lng = float(rec.get("longitude") or "")
    except (TypeError, ValueError):
        return None
    dt = _parse_datetime(str(rec.get("open_dt") or ""))
    if dt is None:
        return None
    raw_type = str(rec.get("type") or "")
    return (CREATIO_SERVICE_MAP.get(raw_type, raw_type), f"{lat:.4f}", f"{lng:.4f}", int(dt.timestamp() // 60))


def match_cross_system(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    window_min: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (secondary rows with no primary match, QA pairs for the matched ones).

    Inputs are never mutated. Output order follows `secondary`.
    """
    index: dict[tuple[str, str, str], list[tuple[int, str]]] = defaultdict(list)
    for rec in primary:
        fp = fingerprint(rec)
        if fp is not None:
            index[fp[:3]].append((fp[3], str(rec.get("case_enquiry_id") or "")))
    unmatched: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for rec in secondary:
        fp = fingerprint(rec)
        hit: tuple[str, int] | None = None
        if fp is not None:
            for minute, pid in index.get(fp[:3], []):
                if abs(minute - fp[3]) <= window_min:
                    hit = (pid, abs(minute - fp[3]))
                    break
        if hit is None or fp is None:
            unmatched.append(rec)
        else:
            pairs.append(
                {
                    "primary_id": hit[0],
                    "secondary_id": str(rec.get("case_enquiry_id") or ""),
                    "type": fp[0],
                    "minutes_apart": hit[1],
                }
            )
    return unmatched, pairs
