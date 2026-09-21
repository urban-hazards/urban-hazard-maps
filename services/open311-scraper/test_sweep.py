"""Tests for sweep mode: fetch_day_all, group_by_slug, sweep_day, run_sweep."""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import fetch

OTHER_CODE = fetch.SERVICE_TYPES["other"][0]
NEEDLES_CODE = fetch.SERVICE_TYPES["needles"][0]
ENCAMPMENTS_CODE = fetch.SERVICE_TYPES["encampments"][0]
UNKNOWN_CODE = "Some Dept:Unknown Reason:Mystery Type"
UNKNOWN_NAME = "Mystery Type"


def _records(code: str, n: int, name: str = "x") -> list[dict]:
    return [{"service_code": code, "service_name": name, "id": f"{code}-{i}"} for i in range(n)]


class NotFound(Exception):
    """Mimics enough of a boto3 ClientError shape for fetch._is_not_found."""

    response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}


class FakeS3:
    """Minimal S3 stand-in that tracks put_object bodies so verify_day/head_object
    can be answered consistently, and records call order for assertions."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.put_object = MagicMock(side_effect=self._put_object)
        self.head_object = MagicMock(side_effect=self._head_object)
        self.delete_object = MagicMock(side_effect=self._delete_object)
        self.delete_objects = MagicMock(side_effect=self._delete_objects)
        self.get_object = MagicMock(side_effect=self._get_object)

    def _put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[Key] = {
            "Body": Body,
            "Metadata": kwargs.get("Metadata", {}),
            "LastModified": kwargs.get("LastModified", datetime.now(timezone.utc)),
        }

    def _head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise NotFound("404 Not Found")
        return {"Metadata": self.objects[Key]["Metadata"]}

    def _get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise NotFound("404 Not Found")
        obj = self.objects[Key]
        body = obj["Body"]

        class _Body:
            def read(_self):
                return body

        return {"Body": _Body(), "LastModified": obj.get("LastModified")}

    def _delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def _delete_objects(self, Bucket, Delete, **kwargs):
        deleted = []
        for obj in Delete.get("Objects", []):
            key = obj["Key"]
            self.objects.pop(key, None)
            deleted.append({"Key": key})
        return {"Deleted": deleted}


def test_three_page_day_writes_slug_files_unmapped_and_marker_last():
    day = date(2026, 1, 27)
    page1 = _records(OTHER_CODE, 40) + _records(NEEDLES_CODE, 40) + _records(UNKNOWN_CODE, 20, name=UNKNOWN_NAME)
    page2 = _records(ENCAMPMENTS_CODE, 60) + _records(OTHER_CODE, 40)
    page3 = _records(ENCAMPMENTS_CODE, 37)

    s3 = FakeS3()
    with patch("fetch._do_request", side_effect=[(page1, None), (page2, None), (page3, None)]):
        result = fetch.sweep_day(s3, day, delay=0.0, dry_run=False)

    assert result["status"] == "done"
    assert result["records"] == 237
    assert result["pages"] == 3
    assert result["unmapped"] == 20

    other_key = f"{fetch.SWEEP_PREFIX}other/{day}.json"
    needles_key = f"{fetch.SWEEP_PREFIX}needles/{day}.json"
    encampments_key = f"{fetch.SWEEP_PREFIX}encampments/{day}.json"
    unmapped_key = f"{fetch.SWEEP_UNMAPPED_PREFIX}{day}.json"
    marker_key = f"{fetch.SWEEP_DONE_PREFIX}{day}.json"

    assert int(s3.objects[other_key]["Metadata"]["record-count"]) == 80
    assert int(s3.objects[needles_key]["Metadata"]["record-count"]) == 40
    assert int(s3.objects[encampments_key]["Metadata"]["record-count"]) == 97
    assert unmapped_key in s3.objects

    # Marker must be the LAST put_object call.
    put_keys = [c.kwargs["Key"] for c in s3.put_object.call_args_list]
    assert put_keys[-1] == marker_key
    assert marker_key not in put_keys[:-1]

    import json
    marker = json.loads(s3.objects[marker_key]["Body"])
    assert marker["slugs"] == {"other": 80, "needles": 40, "encampments": 97}
    assert marker["unmapped"] == {UNKNOWN_CODE: {"name": UNKNOWN_NAME, "count": 20}}
    assert marker["pages"] == 3
    assert marker["records"] == 237


def test_empty_day_writes_only_marker():
    day = date(2026, 2, 1)
    s3 = FakeS3()
    with patch("fetch._do_request", side_effect=[([], None)]):
        result = fetch.sweep_day(s3, day, delay=0.0, dry_run=False)

    assert result["status"] == "done"
    assert result["records"] == 0
    assert s3.put_object.call_count == 1
    marker_key = f"{fetch.SWEEP_DONE_PREFIX}{day}.json"
    assert marker_key in s3.objects

    import json
    marker = json.loads(s3.objects[marker_key]["Body"])
    assert marker["records"] == 0
    assert marker["slugs"] == {}
    assert marker["unmapped"] == {}


def test_page_two_failure_writes_nothing():
    day = date(2026, 3, 5)
    page1 = _records(OTHER_CODE, 100)
    s3 = FakeS3()

    with patch("fetch._do_request", side_effect=[(page1, None), Exception("boom")]):
        result = fetch.sweep_day(s3, day, delay=0.0, dry_run=False)

    assert result["status"] == "skipped"
    assert s3.put_object.call_count == 0


def test_verify_mismatch_rolls_back_all_written_objects():
    day = date(2026, 4, 10)
    page1 = _records(OTHER_CODE, 30) + _records(NEEDLES_CODE, 20)
    s3 = FakeS3()

    # Corrupt the stored metadata for one slug file right after it's written,
    # so verify_day sees a mismatch for it.
    real_put = s3._put_object

    def _put_and_corrupt(Bucket, Key, Body, **kwargs):
        real_put(Bucket, Key, Body, **kwargs)
        if "needles" in Key:
            s3.objects[Key]["Metadata"]["record-count"] = "999"

    s3.put_object = MagicMock(side_effect=_put_and_corrupt)

    with patch("fetch._do_request", side_effect=[(page1, None)]):
        result = fetch.sweep_day(s3, day, delay=0.0, dry_run=False)

    assert result["status"] == "skipped"
    marker_key = f"{fetch.SWEEP_DONE_PREFIX}{day}.json"
    assert marker_key not in s3.objects
    # Both slug files (the good one and the mismatched one) were rolled back.
    assert f"{fetch.SWEEP_PREFIX}other/{day}.json" not in s3.objects
    assert f"{fetch.SWEEP_PREFIX}needles/{day}.json" not in s3.objects


def test_run_sweep_skips_done_days_and_goes_newest_to_oldest():
    start = date(2026, 5, 1)
    end = date(2026, 5, 5)
    done = {"2026-05-03"}  # already done, should be skipped

    calls = []

    def _fake_sweep_day(s3, day, delay, dry_run):
        calls.append(day)
        return {"day": str(day), "status": "done", "records": 0, "pages": 1}

    with (
        patch("fetch.list_sweep_done", return_value=done),
        patch("fetch.sweep_day", side_effect=_fake_sweep_day),
        patch("fetch.wait_if_paused"),
    ):
        fetch.run_sweep(MagicMock(), start, end, delay=0.0, dry_run=True)

    expected = [date(2026, 5, 5), date(2026, 5, 4), date(2026, 5, 2), date(2026, 5, 1)]
    assert calls == expected


def test_main_summarize_stats_tolerates_errored_slug():
    all_stats = [
        {"slug": "other", "name": "Other", "fetched": 10, "skipped": 1},
        {"slug": "needles", "name": "Needles", "error": "boom"},
    ]
    summary = fetch.summarize_stats(all_stats)
    assert summary["total_fetched"] == 10
    assert summary["total_skipped"] == 1
    assert summary["errored"] == 1


# --- Finding 1: pause deadlock ---


def _pause_body(set_at: datetime, ttl_seconds: float = fetch.PAUSE_TTL_SECONDS) -> bytes:
    return json.dumps({
        "set_at": set_at.isoformat().replace("+00:00", "Z"),
        "ttl_seconds": ttl_seconds,
    }).encode("utf-8")


def test_wait_if_paused_waits_on_fresh_pause_then_returns_on_404():
    s3 = FakeS3()
    now = datetime.now(timezone.utc)
    s3.objects[fetch.SWEEP_PAUSE_KEY] = {
        "Body": _pause_body(now),
        "Metadata": {},
        "LastModified": now,
    }

    call_count = {"n": 0}

    def _sleep(_seconds):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Second poll finds the pause object gone.
            del s3.objects[fetch.SWEEP_PAUSE_KEY]

    with patch("fetch.time.sleep", side_effect=_sleep):
        fetch.wait_if_paused(s3)

    assert call_count["n"] == 1
    assert fetch.SWEEP_PAUSE_KEY not in s3.objects


def test_wait_if_paused_ignores_and_deletes_stale_json_pause():
    s3 = FakeS3()
    stale_set_at = datetime.now(timezone.utc) - timedelta(hours=3)
    s3.objects[fetch.SWEEP_PAUSE_KEY] = {
        "Body": _pause_body(stale_set_at, ttl_seconds=fetch.PAUSE_TTL_SECONDS),
        "Metadata": {},
        "LastModified": stale_set_at,
    }

    with patch("fetch.time.sleep") as mock_sleep:
        fetch.wait_if_paused(s3)

    mock_sleep.assert_not_called()
    assert fetch.SWEEP_PAUSE_KEY not in s3.objects


def test_wait_if_paused_ignores_stale_unparsable_pause_by_last_modified():
    s3 = FakeS3()
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    s3.objects[fetch.SWEEP_PAUSE_KEY] = {
        "Body": b"not-json",
        "Metadata": {},
        "LastModified": old,
    }

    with patch("fetch.time.sleep") as mock_sleep:
        fetch.wait_if_paused(s3)

    mock_sleep.assert_not_called()
    assert fetch.SWEEP_PAUSE_KEY not in s3.objects


def test_wait_if_paused_caps_total_wait_at_max_and_proceeds():
    s3 = FakeS3()
    now = datetime.now(timezone.utc)
    s3.objects[fetch.SWEEP_PAUSE_KEY] = {
        "Body": _pause_body(now),  # fresh every time it's re-read
        "Metadata": {},
        "LastModified": now,
    }

    # Simulate monotonic clock advancing past the cap after a couple of polls.
    times = iter([0.0, 100.0, fetch.PAUSE_MAX_WAIT_SECONDS + 1])

    with (
        patch("fetch.time.sleep"),
        patch("fetch.time.monotonic", side_effect=lambda: next(times)),
    ):
        fetch.wait_if_paused(s3)

    # Returned instead of looping forever; pause object is left in place
    # (it's still fresh — we just stopped waiting on it).
    assert fetch.SWEEP_PAUSE_KEY in s3.objects


# --- Finding 2: orphan slug files on crash mid-write ---


def test_save_day_exception_rolls_back_and_leaves_zero_objects():
    day = date(2026, 6, 1)
    page1 = _records(OTHER_CODE, 10) + _records(NEEDLES_CODE, 10)
    s3 = FakeS3()
    real_put = s3._put_object

    def _fail_needles(Bucket, Key, Body, **kwargs):
        if "needles" in Key:
            raise Exception("S3 write failed")
        real_put(Bucket, Key, Body, **kwargs)

    s3.put_object = MagicMock(side_effect=_fail_needles)

    with (
        patch("fetch._do_request", side_effect=[(page1, None)]),
        patch("fetch.time.sleep"),  # save_day's internal retry backoff
    ):
        result = fetch.sweep_day(s3, day, delay=0.0, dry_run=False)

    assert result["status"] == "skipped"
    assert "error" in result
    assert s3.objects == {}  # zero surviving objects, no marker


def test_rerun_after_crash_mid_write_writes_fresh_day():
    day = date(2026, 6, 1)
    page1 = _records(OTHER_CODE, 10) + _records(NEEDLES_CODE, 10)
    s3 = FakeS3()

    # Simulate a prior crashed attempt that left an orphaned slug file with
    # no _done/ marker (resume treats this day as not-done and retries it).
    other_key = f"{fetch.SWEEP_PREFIX}other/{day}.json"
    s3.objects[other_key] = {
        "Body": json.dumps(_records(OTHER_CODE, 999)).encode(),
        "Metadata": {"record-count": "999"},
        "LastModified": datetime.now(timezone.utc),
    }

    with patch("fetch._do_request", side_effect=[(page1, None)]):
        result = fetch.sweep_day(s3, day, delay=0.0, dry_run=False)

    assert result["status"] == "done"
    # Orphan was cleared and replaced with the fresh write, not left stacked.
    assert int(s3.objects[other_key]["Metadata"]["record-count"]) == 10
    marker_key = f"{fetch.SWEEP_DONE_PREFIX}{day}.json"
    assert marker_key in s3.objects


def test_marker_write_failure_rolls_back_slug_files():
    day = date(2026, 7, 1)
    page1 = _records(OTHER_CODE, 5)
    s3 = FakeS3()
    real_put = s3._put_object

    def _fail_marker(Bucket, Key, Body, **kwargs):
        if fetch.SWEEP_DONE_PREFIX in Key:
            raise Exception("marker write failed")
        real_put(Bucket, Key, Body, **kwargs)

    s3.put_object = MagicMock(side_effect=_fail_marker)

    with patch("fetch._do_request", side_effect=[(page1, None)]):
        result = fetch.sweep_day(s3, day, delay=0.0, dry_run=False)

    assert result["status"] == "skipped"
    assert "error" in result
    assert s3.objects == {}


# --- Finding 3: O(days) manifest ---


def test_run_sweep_manifest_is_prior_manifest_plus_this_runs_days():
    start = date(2026, 8, 1)
    end = date(2026, 8, 2)
    s3 = FakeS3()

    prior_manifest = {
        "slug_counts": {"other": 5},
        "unmapped_codes": {"X": {"name": "X", "count": 1, "first_seen": "2026-07-01", "last_seen": "2026-07-01"}},
    }
    s3.objects[fetch.SWEEP_MANIFEST_KEY] = {
        "Body": json.dumps(prior_manifest).encode(),
        "Metadata": {},
        "LastModified": datetime.now(timezone.utc),
    }

    def _fake_sweep_day(s3, day, delay, dry_run):
        return {
            "day": str(day),
            "status": "done",
            "records": 10,
            "pages": 1,
            "slugs": {"other": 10},
            "unmapped_codes": {},
        }

    with (
        patch("fetch.list_sweep_done", return_value=set()),
        patch("fetch.sweep_day", side_effect=_fake_sweep_day),
        patch("fetch.wait_if_paused"),
    ):
        fetch.run_sweep(s3, start, end, delay=0.0, dry_run=False)

    # No get_object was ever issued against a _done/ marker key — only the
    # manifest itself was read (at start).
    done_marker_reads = [
        c for c in s3.get_object.call_args_list if fetch.SWEEP_DONE_PREFIX in c.kwargs.get("Key", "")
    ]
    assert done_marker_reads == []

    manifest = json.loads(s3.objects[fetch.SWEEP_MANIFEST_KEY]["Body"])
    # Prior count (5) plus two days x 10 = 25.
    assert manifest["slug_counts"]["other"] == 25
    assert manifest["unmapped_codes"]["X"]["count"] == 1
    assert manifest["days_done"] == 2


def test_rebuild_manifest_does_full_scan_of_done_markers():
    s3 = FakeS3()
    day1, day2 = "2026-09-01", "2026-09-02"
    for day_str, count in ((day1, 3), (day2, 4)):
        marker = {"slugs": {"other": count}, "unmapped": {}}
        s3.objects[f"{fetch.SWEEP_DONE_PREFIX}{day_str}.json"] = {
            "Body": json.dumps(marker).encode(),
            "Metadata": {},
            "LastModified": datetime.now(timezone.utc),
        }

    with patch("fetch.list_sweep_done", return_value={day1, day2}):
        fetch.rebuild_sweep_manifest(s3, date(2026, 9, 1), date(2026, 9, 2))

    manifest = json.loads(s3.objects[fetch.SWEEP_MANIFEST_KEY]["Body"])
    assert manifest["slug_counts"]["other"] == 7
    assert manifest["days_done"] == 2


# --- Finding 4 (per audit Q4): per-type mode must not touch the pause key
# unless --coordinate-sweep is passed ---


def test_per_type_mode_does_not_touch_pause_key_by_default(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(fetch, "get_s3_client", lambda: s3)
    monkeypatch.setattr(fetch, "BUCKET", "test-bucket")
    monkeypatch.setattr(
        fetch, "fetch_type",
        lambda *a, **k: {"slug": "other", "name": "Other", "fetched": 0, "skipped": 0, "existing": 0, "days_needed": 0},
    )
    monkeypatch.setattr(
        sys, "argv",
        ["fetch.py", "--type", "other", "--start", "2026-01-01", "--end", "2026-01-01"],
    )

    fetch.main()

    pause_puts = [c for c in s3.put_object.call_args_list if c.kwargs.get("Key") == fetch.SWEEP_PAUSE_KEY]
    pause_deletes = [c for c in s3.delete_object.call_args_list if c.kwargs.get("Key") == fetch.SWEEP_PAUSE_KEY]
    assert pause_puts == []
    assert pause_deletes == []


def test_per_type_mode_writes_and_clears_pause_key_with_coordinate_flag(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(fetch, "get_s3_client", lambda: s3)
    monkeypatch.setattr(fetch, "BUCKET", "test-bucket")
    monkeypatch.setattr(
        fetch, "fetch_type",
        lambda *a, **k: {"slug": "other", "name": "Other", "fetched": 0, "skipped": 0, "existing": 0, "days_needed": 0},
    )
    monkeypatch.setattr(
        sys, "argv",
        ["fetch.py", "--type", "other", "--coordinate-sweep", "--start", "2026-01-01", "--end", "2026-01-01"],
    )

    fetch.main()

    pause_puts = [c for c in s3.put_object.call_args_list if c.kwargs.get("Key") == fetch.SWEEP_PAUSE_KEY]
    pause_deletes = [c for c in s3.delete_object.call_args_list if c.kwargs.get("Key") == fetch.SWEEP_PAUSE_KEY]
    assert len(pause_puts) == 1
    assert len(pause_deletes) == 1
    assert fetch.SWEEP_PAUSE_KEY not in s3.objects
