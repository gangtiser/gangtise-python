import json
import os
import threading
import time
from pathlib import Path

from gangtise_openapi._title_cache import (
    TITLE_CACHE_MAX_PER_ENDPOINT,
    TITLE_CACHE_TTL_MS,
    TitleCache,
    extract_titles,
)


def test_set_and_lookup_roundtrip(tmp_path):
    cache = TitleCache(tmp_path / "titles.json")
    cache.set_titles("insight.research.list", {"r1": "标题A"})
    assert cache.lookup("insight.research.list", "r1") == "标题A"


def test_lookup_miss(tmp_path):
    cache = TitleCache(tmp_path / "titles.json")
    assert cache.lookup("insight.research.list", "r1") is None


def test_persists_to_disk(tmp_path):
    path = tmp_path / "titles.json"
    cache_one = TitleCache(path)
    cache_one.set_titles("ep", {"x": "y"})
    cache_one.flush()
    cache_two = TitleCache(path)
    assert cache_two.lookup("ep", "x") == "y"


def test_ttl_expires(tmp_path):
    path = tmp_path / "titles.json"
    stale_ts = int(time.time() * 1000) - TITLE_CACHE_TTL_MS - 1000
    path.write_text(json.dumps({"ep": {"titles": {"x": "y"}, "ts": stale_ts}}))
    cache = TitleCache(path)
    assert cache.lookup("ep", "x") is None


def test_corrupt_file_treated_as_empty(tmp_path):
    path = tmp_path / "titles.json"
    path.write_text("not json", encoding="utf8")
    cache = TitleCache(path)
    assert cache.lookup("ep", "x") is None


def test_extract_titles_from_rows():
    rows = [
        {"reportId": "r1", "title": "标题A", "other": "x"},
        {"reportId": "r2", "title": "标题B"},
        {"reportId": "r3"},  # missing title - skip
        {"title": "标题C"},  # missing id - skip
    ]
    out = extract_titles(rows, id_field="reportId", title_field="title")
    assert out == {"r1": "标题A", "r2": "标题B"}


def test_set_titles_merges():
    cache = TitleCache(None)
    cache.set_titles("ep", {"a": "1", "b": "2"})
    cache.set_titles("ep", {"b": "B", "c": "3"})
    assert cache.lookup("ep", "a") == "1"
    assert cache.lookup("ep", "b") == "B"
    assert cache.lookup("ep", "c") == "3"


def test_set_titles_skips_rewrite_when_unchanged(tmp_path):
    cache = TitleCache(tmp_path / "titles.json")
    cache.set_titles("ep", {"a": "1"})
    cache.flush()
    assert cache._dirty is False
    # Re-recording identical titles must not dirty the cache — a list call that
    # surfaces nothing new should not trigger a full-file rewrite.
    cache.set_titles("ep", {"a": "1"})
    assert cache._dirty is False
    # A genuinely new title still dirties it.
    cache.set_titles("ep", {"b": "2"})
    assert cache._dirty is True


def test_set_titles_caps_per_endpoint():
    cache = TitleCache(None)
    n = TITLE_CACHE_MAX_PER_ENDPOINT
    cache.set_titles("ep", {str(i): f"t{i}" for i in range(n + 50)})
    stored = cache._data["ep"]["titles"]
    assert len(stored) == n
    # Keeps the most-recently-seen titles, evicts the earliest.
    assert cache.lookup("ep", str(n + 49)) == f"t{n + 49}"
    assert cache.lookup("ep", "0") is None


def test_load_caps_oversized_entry(tmp_path):
    path = tmp_path / "titles.json"
    n = TITLE_CACHE_MAX_PER_ENDPOINT
    fresh_ts = int(time.time() * 1000)
    big = {str(i): f"t{i}" for i in range(n + 100)}
    path.write_text(json.dumps({"ep": {"titles": big, "ts": fresh_ts}}), encoding="utf8")
    cache = TitleCache(path)
    stored = cache._data["ep"]["titles"]
    assert len(stored) == n
    assert cache.lookup("ep", str(n + 99)) == f"t{n + 99}"
    assert cache.lookup("ep", "0") is None


def test_load_drops_entry_with_non_dict_titles(tmp_path):
    # A half-corrupt entry (titles not a dict) is dropped on load, not carried
    # forward — otherwise the next set_titles() would AttributeError on existing.get.
    path = tmp_path / "titles.json"
    fresh_ts = int(time.time() * 1000)
    path.write_text(
        json.dumps({"ep": {"titles": ["not", "a", "dict"], "ts": fresh_ts}}),
        encoding="utf8",
    )
    cache = TitleCache(path)
    assert "ep" not in cache._data  # corrupt entry dropped, not retained
    # A subsequent record on the same key still works (no crash, starts a fresh dict).
    cache.set_titles("ep", {"x": "y"})
    assert cache.lookup("ep", "x") == "y"


def test_flush_creates_file_0600_atomically(tmp_path, monkeypatch):
    # Cache may hold non-public report titles; the on-disk file is created 0600 at
    # open() time (not write-then-chmod) and renamed atomically — mirrors the token
    # cache. spy on os.open distinguishes this from the old write_text path (0666).
    path = tmp_path / "titles.json"
    cache = TitleCache(path)
    cache.set_titles("ep", {"x": "标题"})
    opens: list[int] = []
    real_open = os.open

    def spy(file, flags, mode=0o777, *args, **kwargs):
        opens.append(mode)
        return real_open(file, flags, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    cache.flush()
    assert opens == [0o600]
    assert (path.stat().st_mode & 0o777) == 0o600


def test_write_arriving_during_a_flush_is_not_lost(tmp_path, monkeypatch):
    """A set_titles() racing an in-flight flush() must still reach disk.

    The TS CLI had to retrofit this (v0.34.1): its flush snapshotted the data,
    awaited the write, and any write landing during that await was attached to the
    already-resolving promise and never persisted — both awaits returned normally,
    so nothing looked wrong. Python's cache holds one lock across the whole
    read-modify-write, so the racing write blocks until the flush finishes and then
    marks the cache dirty again.

    The writer is started from INSIDE the flush's critical section and observed to
    be blocked there, so the test cannot pass by having the writer finish before the
    flush began — the interleaving a start-then-release version would silently allow.
    It is joined from the MAIN thread, after flush() has released the lock: joining
    inside the critical section could only ever time out, and flushing before the
    writer lands would read `_dirty == False` and skip the write.
    """
    path = tmp_path / "titles.json"
    cache = TitleCache(path)
    cache.set_titles("ep", {"a": "第一条"})

    writers: list[threading.Thread] = []
    observed: list[tuple[bool, bool]] = []
    real_replace = Path.replace

    def slow_replace(self, target):
        writer = threading.Thread(target=cache.set_titles, args=("ep", {"b": "第二条"}))
        writers.append(writer)
        writer.start()
        # Still inside flush()'s lock. Both facts are what the guarantee rests on:
        # the lock is held across the write, and the racing writer is stuck on it.
        writer.join(timeout=0.2)
        observed.append((cache._lock.locked(), writer.is_alive()))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", slow_replace)
    cache.flush()
    monkeypatch.undo()

    assert observed == [(True, True)], f"the write was not blocked by the flush lock: {observed}"
    writers[0].join(timeout=5)
    assert not writers[0].is_alive()

    cache.flush()
    assert json.loads(path.read_text(encoding="utf8"))["ep"]["titles"] == {
        "a": "第一条",
        "b": "第二条",
    }


def test_concurrent_writers_all_survive(tmp_path):
    """Every concurrent set_titles() has to end up in the same merged object.

    The TS sibling bug (v0.34.1) was in loadInto: concurrent callers each built
    their own object and the last one overwrote the rest. Python loads once, in
    __init__, and merges under the lock — so N writers produce N entries.
    """
    cache = TitleCache(tmp_path / "titles.json")
    threads = [
        threading.Thread(target=cache.set_titles, args=("ep", {f"id{i}": f"标题{i}"}))
        for i in range(32)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    cache.flush()
    titles = json.loads((tmp_path / "titles.json").read_text(encoding="utf8"))["ep"]["titles"]
    assert titles == {f"id{i}": f"标题{i}" for i in range(32)}
