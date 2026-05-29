from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

TITLE_CACHE_TTL_MS = 24 * 60 * 60 * 1000
TITLE_LOOKUP_SIZE = 200


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
        except OSError:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
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
                pruned[key] = entry
        return pruned

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
        with self._lock:
            existing = self._data.get(endpoint_key, {}).get("titles", {})
            merged = {**existing, **titles}
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
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(
                self._path.suffix + f".tmp-{os.getpid()}-{int(time.time() * 1000)}"
            )
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False),
                encoding="utf8",
            )
            os.chmod(tmp, 0o600)
            tmp.replace(self._path)
            self._dirty = False
