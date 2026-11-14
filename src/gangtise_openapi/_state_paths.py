"""``file`` and ``output`` may not point at the SDK's own state (TS v0.52.1 ``statePaths.ts``):
the directory holding the token cache (a live access token) and the title cache, or a token
cache moved elsewhere (``GANGTISE_TOKEN_CACHE_PATH``). Reading it would send the token out
with an upload; writing there would replace it. The target is resolved by the OS (symlinks,
``..``) and compared by device and inode up its parents, so another spelling of the same
place (case on a case-insensitive disk included) is refused too. Before that place exists, by
the deepest directory on its path that does and the names below that one, under that
directory's own case rule. A link inside the state directory that points out of it is refused
as an ``output``: a write replaces the link itself."""

from __future__ import annotations

import os
import string
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gangtise_openapi._config import DEFAULT_TOKEN_CACHE_PATH
from gangtise_openapi._errors import ValidationError

_Identity = tuple[int, int]
_SWAP_ASCII_CASE = str.maketrans(
    string.ascii_letters, string.ascii_uppercase + string.ascii_lowercase
)


def _identity(path: str) -> _Identity | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return stat.st_dev, stat.st_ino


def _entry_identity(path: str) -> _Identity | None:
    try:
        stat = os.lstat(path)
    except OSError:
        return None
    return stat.st_dev, stat.st_ino


def _absolute(path: str | Path) -> str:
    # Not abspath: it folds ``..`` as text, before the OS has followed a link in front of it.
    text = os.fspath(Path(path).expanduser())
    return text if os.path.isabs(text) else os.getcwd() + os.sep + text


def _physical(absolute: str) -> str:
    # realpath follows a link before folding the ``..`` after it, as the OS does; a part
    # that does not exist yet is appended as written.
    return os.path.realpath(absolute)


def _entry(absolute: str) -> str:
    # The directory entry the path names: a write replaces it, not what a link there points at.
    parent = _physical(os.path.dirname(absolute))
    return os.path.normpath(os.path.join(parent, os.path.basename(absolute)))


def _as_written(name: str) -> str:
    return name


def _ignores_case(directory: str) -> bool:
    """Whether names in this existing directory compare ignoring case. Asked of an entry inside
    it — its name with the case of its ASCII letters swapped reaches the same entry or not — so a
    mount point answers for its own disk, not the one it is mounted on. ASCII letters only: every
    disk that ignores case folds them, while some other letters do not swap back (a dotless i
    swaps to I, which such a disk reads as i). A directory with no such entry, or one that cannot be read, cannot
    say: it reads as ignoring case, so a path that may be the token cache is refused rather than
    written over."""
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                swapped = entry.name.translate(_SWAP_ASCII_CASE)
                if swapped == entry.name:
                    continue
                own = _entry_identity(os.path.join(directory, entry.name))
                if own is None:  # gone since the listing: it says nothing, ask the next one
                    continue
                return own == _entry_identity(os.path.join(directory, swapped))
    except OSError:
        pass
    return True


@dataclass(frozen=True)
class _Place:
    """A state path as it can be compared: an existing entry by identity — not by spelling: on a
    case-sensitive disk /mnt/Cache and /mnt/cache are two directories — and the names below it
    under its case rule. ``within``: a path under the place is refused too."""

    anchor: _Identity
    below: tuple[str, ...]
    fold: Callable[[str], str]
    within: bool

    def reached_by(self, names: list[str]) -> bool:
        if len(names) < len(self.below) or (not self.within and len(names) > len(self.below)):
            return False
        return all(self.fold(name) == own for name, own in zip(names, self.below, strict=False))


def _named_in(spot: str, within: bool) -> _Place | None:
    """The place an entry has by name: the deepest existing directory above it, and the names
    below that one under its case rule."""
    existing, below = os.path.dirname(spot), [os.path.basename(spot)]
    anchor = _identity(existing)
    while anchor is None and os.path.dirname(existing) != existing:
        below.insert(0, os.path.basename(existing))
        existing = os.path.dirname(existing)
        anchor = _identity(existing)
    if anchor is None:
        return None
    fold: Callable[[str], str] = str.lower if _ignores_case(existing) else _as_written
    return _Place(anchor, tuple(fold(name) for name in below), fold, within)


def _places_of(path: Path, *, within: bool) -> list[_Place]:
    """A state path every way it can be reached. By the identity of what is there now: another
    name for it (a hard link) is refused too. And by directory and name, both for the entry the
    path names and for where it resolves (a linked token cache): either can be replaced under its
    name (a refresh renames a new token file over it) between this check and the write."""
    absolute = _absolute(path)
    resolved = _physical(absolute)
    places = []
    own = _identity(resolved)
    if own is not None:
        places.append(_Place(own, (), _as_written, within))
    for spot in dict.fromkeys((_entry(absolute), resolved)):
        place = _named_in(spot, within)
        if place is not None:
            places.append(place)
    return places


def _is_state(path: str, places: list[_Place]) -> bool:
    # Up the path's parents: one that is a place's anchor, with the names below it the place's own.
    names: list[str] = []
    current = path
    while True:
        identity = _identity(current)
        if identity is not None and any(
            place.anchor == identity and place.reached_by(names) for place in places
        ):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        names.insert(0, os.path.basename(current))
        current = parent


def assert_not_state_path(target: str | Path, *, param: str, token_cache_path: Path) -> None:
    state_dir = DEFAULT_TOKEN_CACHE_PATH.parent
    places = [
        *_places_of(state_dir, within=True),
        *_places_of(token_cache_path, within=False),
    ]
    absolute = _absolute(target)
    # Where the OS reads, and the entry a write replaces: a rename over a link replaces
    # the link, so a link in the state directory pointing out of it still counts as in it.
    # Uploads pass the file's real path, for which the two are the same.
    if _is_state(_physical(absolute), places) or _is_state(_entry(absolute), places):
        raise ValidationError(
            f"{param}={os.fspath(target)!r} points at gangtise's own state ({state_dir}, or "
            f"the token cache {token_cache_path}), which holds the access token: refused. "
            "Pass a path outside it."
        )
