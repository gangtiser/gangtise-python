import json
import time

from gangtise_openapi._title_cache import TITLE_CACHE_TTL_MS, TitleCache, extract_titles


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
