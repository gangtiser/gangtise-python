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


def _now_ms() -> int:
    return int(time.time() * 1000)


def test_flush_keeps_titles_another_process_wrote_meanwhile(tmp_path):
    # TS v0.44.0 mergeFromDisk. Another process (a second SDK run, or the npm CLI that
    # shares this file) rewrites it from its own snapshot after this one loaded: a
    # title this one already has, one it lacks, and an endpoint it never listed. This
    # process's next flush must not put its older snapshot back over them.
    path = tmp_path / "titles.json"
    cache = TitleCache(path)
    cache.set_titles("ep", {"1": "one"})
    cache.flush()
    path.write_text(
        json.dumps(
            {
                "ep": {"ts": _now_ms(), "titles": {"1": "another title", "2": "two"}},
                "other": {"ts": _now_ms(), "titles": {"a": "A"}},
            }
        ),
        encoding="utf8",
    )
    cache.set_titles("ep", {"3": "three"})
    cache.flush()

    data = TitleCache(path)._data
    # This process wins the clash on "1"; the other process's "2" and "other" survive.
    assert data["ep"]["titles"] == {"1": "one", "2": "two", "3": "three"}
    assert data["other"]["titles"] == {"a": "A"}


def test_flush_merge_over_the_cap_keeps_this_processs_titles(tmp_path):
    # Small integer-like ids written here must survive a merge with a full endpoint
    # written elsewhere: the cap evicts the other process's ids, never ours.
    path = tmp_path / "titles.json"
    cache = TitleCache(path)
    cache.set_titles("ep", {"1": "mine one", "2": "mine two"})
    cache.flush()
    n = TITLE_CACHE_MAX_PER_ENDPOINT
    others = {str(1000 + i): f"other {i}" for i in range(n)}
    path.write_text(json.dumps({"ep": {"ts": _now_ms(), "titles": others}}), encoding="utf8")
    cache.set_titles("ep", {"3": "mine three"})
    cache.flush()

    titles = TitleCache(path)._data["ep"]["titles"]
    assert len(titles) == n
    assert [titles.get("1"), titles.get("2"), titles.get("3")] == [
        "mine one",
        "mine two",
        "mine three",
    ]


def test_flush_merge_skips_expired_and_malformed_disk_entries(tmp_path):
    path = tmp_path / "titles.json"
    cache = TitleCache(path)
    stale_ts = _now_ms() - TITLE_CACHE_TTL_MS - 1000
    path.write_text(
        json.dumps(
            {
                "stale": {"ts": stale_ts, "titles": {"x": "old"}},
                "broken": {"ts": _now_ms(), "titles": ["not", "a", "dict"]},
            }
        ),
        encoding="utf8",
    )
    cache.set_titles("ep", {"1": "one"})
    cache.flush()
    assert set(json.loads(path.read_text(encoding="utf8"))) == {"ep"}


def test_a_title_with_a_lone_surrogate_does_not_stop_the_cache_persisting(tmp_path):
    """A title that cannot be encoded must not stay in memory: it would make every later
    flush fail, and the cache would silently never reach disk again in that process."""
    from gangtise_openapi._title_cache import TitleCache

    path = tmp_path / "title.json"
    cache = TitleCache(path)
    cache.set_titles("insight.research.list", {"1": "坏\udc80标题"})
    cache.flush()
    cache.set_titles("insight.research.list", {"2": "正常标题"})
    cache.flush()
    fresh = TitleCache(path)
    assert fresh.lookup("insight.research.list", "2") == "正常标题"
    assert fresh.lookup("insight.research.list", "1") == "坏�标题"


def test_a_lone_surrogate_loaded_from_the_shared_file_does_not_block_flushes(tmp_path):
    """The CLI writes a lone surrogate as a valid JSON escape; loaded
    back (or merged in at flush) it made every flush fail, so no new title persisted."""
    import json
    import time

    from gangtise_openapi._title_cache import TitleCache

    path = tmp_path / "title.json"
    now = int(time.time() * 1000)
    raw = {"insight.research.list": {"titles": {"1": "坏\udc80"}, "ts": now}}
    path.write_text(json.dumps(raw))  # ensure_ascii: written as the \\udc80 escape
    cache = TitleCache(path)
    cache.set_titles("insight.research.list", {"2": "正常"})
    cache.flush()
    # And the merge path: another writer drops the same escape in before our next flush.
    path.write_text(json.dumps({"insight.summary.list": {"titles": {"9": "x\udc81"}, "ts": now}}))
    cache.set_titles("insight.research.list", {"3": "又一个"})
    cache.flush()
    fresh = TitleCache(path)
    assert fresh.lookup("insight.research.list", "2") == "正常"
    assert fresh.lookup("insight.research.list", "3") == "又一个"
    assert fresh.lookup("insight.summary.list", "9") == "x�"
