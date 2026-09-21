"""Tests for sweep mode: fetch_day_all, group_by_slug, sweep_day, run_sweep."""

from datetime import date
from unittest.mock import MagicMock, patch

import fetch

OTHER_CODE = fetch.SERVICE_TYPES["other"][0]
NEEDLES_CODE = fetch.SERVICE_TYPES["needles"][0]
ENCAMPMENTS_CODE = fetch.SERVICE_TYPES["encampments"][0]
UNKNOWN_CODE = "Some Dept:Unknown Reason:Mystery Type"
UNKNOWN_NAME = "Mystery Type"


def _records(code: str, n: int, name: str = "x") -> list[dict]:
    return [{"service_code": code, "service_name": name, "id": f"{code}-{i}"} for i in range(n)]


class FakeS3:
    """Minimal S3 stand-in that tracks put_object bodies so verify_day/head_object
    can be answered consistently, and records call order for assertions."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.put_object = MagicMock(side_effect=self._put_object)
        self.head_object = MagicMock(side_effect=self._head_object)
        self.delete_object = MagicMock(side_effect=self._delete_object)
        self.get_object = MagicMock(side_effect=self._get_object)

    def _put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[Key] = {"Body": Body, "Metadata": kwargs.get("Metadata", {})}

    def _head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Exception("404 Not Found")
        return {"Metadata": self.objects[Key]["Metadata"]}

    def _get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Exception("404 Not Found")
        body = self.objects[Key]["Body"]

        class _Body:
            def read(_self):
                return body

        return {"Body": _Body()}

    def _delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


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
