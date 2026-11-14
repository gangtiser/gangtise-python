"""``file`` and ``output`` may not point at the SDK's own state (TS v0.52.0 ``statePaths.ts``):
the directory holding the token cache (a live access token) and the title cache, or a token
cache moved elsewhere (``GANGTISE_TOKEN_CACHE_PATH``). Reading it would send the token out
with an upload; writing there would replace it. The target is resolved by the OS (symlinks,
``..``) and compared by device and inode up its parents, so another spelling of the same
place (case on a case-insensitive disk included) is refused too. A path inside the state
directory is refused even before that directory exists, and so is a link inside it that
points out: a write replaces the link itself."""

from __future__ import annotations

import os
from pathlib import Path

from gangtise_openapi._config import DEFAULT_TOKEN_CACHE_PATH
from gangtise_openapi._errors import ValidationError


def _identity(path: str) -> tuple[int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return stat.st_dev, stat.st_ino


def _physical(path: str | Path) -> str:
    # realpath, not abspath: it follows a link before folding the ``..`` after it, as the
    # OS does; a part that does not exist yet is appended as written.
    return os.path.realpath(Path(path).expanduser())


def _inside(place: str, guarded: set[tuple[int, int]], state_dir: str, token_cache: str) -> bool:
    # A state directory or token cache that does not exist yet has no inode to compare:
    # its path stands in, compared without case — on a case-insensitive disk another
    # spelling names the same place (on a case-sensitive one the refusal costs nothing).
    folded, state = place.casefold(), state_dir.casefold()
    if folded in (state, token_cache.casefold()) or folded.startswith(state + os.sep):
        return True
    current = place
    while True:
        identity = _identity(current)
        if identity is not None and identity in guarded:
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def assert_not_state_path(target: str | Path, *, param: str, token_cache_path: Path) -> None:
    state_dir = DEFAULT_TOKEN_CACHE_PATH.parent
    guarded = {
        identity
        for identity in (_identity(str(state_dir)), _identity(str(token_cache_path)))
        if identity is not None
    }
    given = Path(target).expanduser()
    # Where the OS reads, and the entry a write replaces: a rename over a link replaces
    # the link, so a link in the state directory pointing out of it still counts as in it.
    places = (_physical(given), os.path.normpath(os.path.join(_physical(given.parent), given.name)))
    if any(
        _inside(place, guarded, _physical(state_dir), _physical(token_cache_path))
        for place in places
    ):
        raise ValidationError(
            f"{param}={os.fspath(target)!r} points at gangtise's own state ({state_dir}, or "
            f"the token cache {token_cache_path}), which holds the access token: refused. "
            "Pass a path outside it."
        )
