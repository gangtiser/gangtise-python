from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

TITLE_CACHE_TTL_MS = 24 * 60 * 60 * 1000
TITLE_LOOKUP_SIZE = 200
# Hard cap on titles retained per endpoint. The cache merges every list call's
# titles forever; without a cap a hot endpoint (e.g. insight.announcement.list)
# grew past 300k entries / tens of MB — re-parsed on every client init and
# rewritten on every list call. Keep only the most-recently-seen N.
TITLE_CACHE_MAX_PER_ENDPOINT = 10_000


def _cap_titles(titles: dict[str, str]) -> dict[str, str]:
    """Trim a per-endpoint titles dict to the most-recent ``MAX`` entries.

    Dicts preserve insertion order, so the tail holds the most recently added
    ids — exactly the ones a download is most likely to resolve next.
    """
    if len(titles) <= TITLE_CACHE_MAX_PER_ENDPOINT:
        return titles
    return dict(list(titles.items())[-TITLE_CACHE_MAX_PER_ENDPOINT:])


_SURROGATES = re.compile("[\ud800-\udfff]")


def _encodable(text: str) -> str:
    """``text`` with any lone surrogate replaced by U+FFFD, so it encodes as UTF-8."""
    return _SURROGATES.sub("\ufffd", text) if isinstance(text, str) else text


def _live_entries(parsed: Any) -> dict[str, dict[str, Any]]:
    """The usable endpoint entries of a parsed cache file: fresh (within the TTL) and
    well-formed, each capped. Anything else yields ``{}``."""
    if not isinstance(parsed, dict):
        return {}
    # Drop endpoint entries past the TTL so the on-disk cache self-bounds
    # instead of growing without limit (it had reached tens of MB). Stale
    # entries are pruned from memory now and from disk on the next flush.
    now_ms = int(time.time() * 1000)
    pruned: dict[str, dict[str, Any]] = {}
    for key, entry in parsed.items():
        if not isinstance(entry, dict):
            continue
        ts = entry.get("ts")
        if isinstance(ts, int) and (now_ms - ts) <= TITLE_CACHE_TTL_MS:
            titles = entry.get("titles")
            if not isinstance(titles, dict):
                # Drop a half-corrupt entry (titles not a dict) rather than carry
                # it forward: set_titles() does existing.get(...) and lookup()
                # assumes a dict, so a bad value would crash the next list call.
                continue
            # Sanitized here too, not only in set_titles: the npm CLI shares this file and
            # writes a lone surrogate as a valid JSON escape (``"\\udc80"``), which loads
            # back as one — and one such title would make every flush of this process fail.
            titles = {_encodable(k): _encodable(v) for k, v in titles.items()}
            if len(titles) > TITLE_CACHE_MAX_PER_ENDPOINT:
                titles = _cap_titles(titles)
            pruned[key] = {**entry, "titles": titles}
    return pruned


def extract_titles(
    rows: Iterable[Any],
    *,
    id_field: str,
    title_field: str = "title",
) -> dict[str, str]:
    """Pull (id, title) pairs from a list of dicts, skipping any row that
    lacks either field. Mirrors TS `extractTitles` in titleCache.ts.
    """
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ident = row.get(id_field)
        title = row.get(title_field)
        if ident is None or not isinstance(title, str) or not title:
            continue
        out[str(ident)] = title
    return out


class TitleCache:
    """Per-process snapshot of `~/.config/gangtise/title-cache.json`.

    `path=None` means in-memory only - useful for tests and when the config
    explicitly disables the disk cache.
    """

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = self._load()
        self._dirty = False

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._path is None:
            return {}
        try:
            raw = self._path.read_text(encoding="utf8")
        except (OSError, UnicodeDecodeError):  # a non-UTF-8 file is a corrupt cache
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return _live_entries(parsed)

    def _merge_from_disk(self) -> None:
        """Fold in what other processes (another SDK process, or the npm CLI, which
        shares this file) flushed since this one loaded it, so a flush does not put a
        stale snapshot back over their titles (TS v0.44.0 ``mergeFromDisk``). No
        cross-process lock: two overlapping flushes still race, but only over the
        moment between this read and the rename rather than a whole run. This
        process's titles win a clash and are the ones the per-endpoint cap keeps.
        Caller holds ``self._lock``."""
        for key, theirs in self._load().items():
            mine = self._data.get(key)
            if mine is None:
                self._data[key] = theirs
                continue
            my_titles = mine["titles"]
            # Theirs first, mine last: _cap_titles keeps the tail, so on overflow it is
            # the other process's ids that go. (Unlike JS objects, a dict keeps insertion
            # order for integer-like ids too, so no separate "fresh keys" list is needed.)
            others = {k: v for k, v in theirs["titles"].items() if k not in my_titles}
            self._data[key] = {
                "titles": _cap_titles({**others, **my_titles}),
                "ts": max(theirs["ts"], mine["ts"]),
            }
        # Same bound as a load: drop what went past the TTL while this process ran.
        self._data = _live_entries(self._data)

    def lookup(self, endpoint_key: str, id_value: str) -> str | None:
        with self._lock:
            entry = self._data.get(endpoint_key)
            if not entry:
                return None
            ts = entry.get("ts")
            if not isinstance(ts, int) or (int(time.time() * 1000) - ts) > TITLE_CACHE_TTL_MS:
                return None
            titles = entry.get("titles")
            if not isinstance(titles, dict):
                return None
            value = titles.get(str(id_value))
            return value if isinstance(value, str) else None

    def set_titles(self, endpoint_key: str, titles: dict[str, str]) -> None:
        if not titles:
            return
        # A lone surrogate (a server string escaping ``\udc80``) cannot be written as
        # UTF-8: kept as is, it would make EVERY later flush of this process fail, and
        # the whole cache would silently stop persisting. Replaced on the way in.
        titles = {_encodable(k): _encodable(v) for k, v in titles.items()}
        with self._lock:
            existing = self._data.get(endpoint_key, {}).get("titles", {})
            # Skip the write when the call surfaces nothing new — most repeat
            # list calls re-report ids already cached, and a full-file flush for
            # a no-op is the dominant cost.
            if all(existing.get(k) == v for k, v in titles.items()):
                return
            merged = _cap_titles({**existing, **titles})
            self._data[endpoint_key] = {
                "titles": merged,
                "ts": int(time.time() * 1000),
            }
            self._dirty = True

    def flush(self) -> None:
        if self._path is None:
            return
        with self._lock:
            if not self._dirty:
                return
            self._merge_from_disk()
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(
                self._path.suffix + f".tmp-{os.getpid()}-{int(time.time() * 1000)}"
            )
            # Create the temp 0600 from the first byte (not write-then-chmod, which
            # leaves a brief world-readable window) and rename atomically. Mirrors
            # _auth.write_token_cache — the cache can hold non-public report titles.
            fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf8") as f:
                    f.write(json.dumps(self._data, ensure_ascii=False))
                tmp.replace(self._path)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
            self._dirty = False
