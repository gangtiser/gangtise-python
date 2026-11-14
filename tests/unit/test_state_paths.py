"""``file`` / ``output`` may not point at the SDK's own state; a directory is no ``output``;
a renamed non-PDF is no PDF — all refused before any request (TS v0.52.0)."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import httpx
import pytest
import respx

from gangtise_openapi import _state_paths
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ValidationError
from gangtise_openapi._state_paths import assert_not_state_path
from gangtise_openapi.domains.insight import AsyncInsight, Insight
from gangtise_openapi.domains.tool import Tool
from gangtise_openapi.domains.vault import Vault

_PARSE_SUBMIT = "/application/open-tool/file-parse/submit"
_UPLOAD = "/application/open-vault/drive/uploadFile"


@pytest.fixture
def state(tmp_path, monkeypatch) -> Path:
    """A stand-in for ~/.config/gangtise holding the token cache, so the tests neither
    depend on nor touch the real one."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    token = state_dir / "token.json"
    token.write_text("{}")
    monkeypatch.setattr(_state_paths, "DEFAULT_TOKEN_CACHE_PATH", token)
    (tmp_path / "outside").mkdir()
    return state_dir


def _refused(target, token_cache_path) -> None:
    with pytest.raises(ValidationError, match="points at gangtise's own state"):
        assert_not_state_path(target, param="output", token_cache_path=token_cache_path)


def _allowed(target, token_cache_path) -> None:
    assert_not_state_path(target, param="output", token_cache_path=token_cache_path)


def test_refuses_the_token_cache_and_any_path_in_the_state_directory(state):
    token = state / "token.json"
    _refused(token, token)
    _refused(state / "title-cache.json", token)
    _refused(state / "new" / "deeper.json", token)
    _refused(state, token)
    _allowed(state.parent / "outside" / "export.csv", token)
    _allowed(state.parent / "state-like" / "token.json", token)


def test_follows_a_symlink_and_a_linked_directory_before_dotdot(state):
    token = state / "token.json"
    outside = state.parent / "outside"
    (outside / "token-link.json").symlink_to(token)
    _refused(outside / "token-link.json", token)
    # outside/sub-link → state/sub: the OS reads outside/sub-link/../token.json as
    # state/token.json, while folding ``..`` as text would read it as outside/token.json.
    (state / "sub").mkdir()
    (outside / "sub-link").symlink_to(state / "sub")
    _refused(f"{outside / 'sub-link'}{os.sep}..{os.sep}token.json", token)


def test_refuses_a_moved_token_cache_before_it_exists_too(state):
    moved = state.parent / "outside" / "moved" / "token.json"
    _refused(moved, moved)
    moved.parent.mkdir()
    moved.write_text("{}")
    _refused(moved, moved)
    _allowed(moved.parent / "export.csv", moved)


def _disk_ignores_case(directory: Path) -> bool:
    """The temporary directory's disk: macOS ignores case by default, Linux CI does not."""
    probe = directory / "case-probe"
    probe.write_text("")
    try:
        return (directory / "CASE-PROBE").exists()
    finally:
        probe.unlink()


def test_refuses_the_state_directory_and_paths_in_it_before_it_exists(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setattr(_state_paths, "DEFAULT_TOKEN_CACHE_PATH", missing / "token.json")
    token = missing / "token.json"
    _refused(missing, token)
    _refused(missing / "title-cache.json", token)
    _refused(f"{missing}{os.sep}", token)
    # Another spelling of the same place where the disk ignores case; elsewhere another directory.
    other_case = _refused if _disk_ignores_case(tmp_path) else _allowed
    other_case(tmp_path / "Missing" / "title-cache.json", token)
    other_case(tmp_path / "MISSING" / "TOKEN.JSON", token)
    _allowed(tmp_path / "missing-like" / "export.csv", token)


def test_tells_a_token_cache_from_a_file_differing_only_in_case_by_the_disks_rule(tmp_path):
    # Token.json is not created yet; token.json beside it is another file where names are
    # case-sensitive, and the same one where case is ignored.
    (tmp_path / "probe.txt").write_text("")
    token = tmp_path / "cased" / "Token.json"
    _refused(token, token)
    other_case = _refused if _disk_ignores_case(tmp_path) else _allowed
    other_case(tmp_path / "cased" / "token.json", token)
    _allowed(tmp_path / "cased" / "export.csv", token)


@pytest.mark.parametrize("ignores_case", [True, False])
def test_the_case_rule_is_the_existing_directorys_own(tmp_path, monkeypatch, ignores_case):
    # A volume mounted on a disk with the other rule: the rule of the deepest existing
    # directory on the token cache's path decides, whatever the disk under it does.
    monkeypatch.setattr(_state_paths, "_ignores_case", lambda directory: ignores_case)
    token = tmp_path / "cased" / "Token.json"
    (_refused if ignores_case else _allowed)(tmp_path / "cased" / "token.json", token)
    _refused(token, token)


def test_reads_the_case_rule_from_an_entry_with_ascii_letters(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    # Nothing to ask: read as ignoring case, so a possible token cache is refused, not overwritten.
    assert _state_paths._ignores_case(str(empty)) is True
    token = empty / "cased" / "Token.json"
    _refused(empty / "cased" / "token.json", token)
    _allowed(empty / "cased" / "other.json", token)
    # A name without ASCII letters cannot say either.
    (empty / "数据").write_text("")
    assert _state_paths._ignores_case(str(empty)) is True
    (empty / "probe.txt").write_text("")
    assert _state_paths._ignores_case(str(empty)) is _disk_ignores_case(tmp_path)


@pytest.mark.skipif(
    not Path("/System/Volumes/Data").is_dir(), reason="macOS firmlinks reach a directory twice"
)
def test_compares_the_existing_directory_by_identity_not_spelling(tmp_path, monkeypatch):
    # /System/Volumes/Data/<path> is the same directory as <path>, under another spelling that
    # realpath keeps: before the state directory exists, its parent is known by its inode.
    real = Path(os.path.realpath(tmp_path))
    alias = Path("/System/Volumes/Data") / real.relative_to("/")
    if not alias.is_dir():
        pytest.skip("temporary directory not on the data volume")
    missing = real / "missing"
    monkeypatch.setattr(_state_paths, "DEFAULT_TOKEN_CACHE_PATH", missing / "token.json")
    _refused(alias / "missing", missing / "token.json")
    _refused(alias / "missing" / "token.json", missing / "token.json")
    _allowed(alias / "export.csv", missing / "token.json")


def test_refuses_another_name_for_the_token_cache(state):
    # A hard link is the token file itself under another name.
    token = state / "token.json"
    alias = state.parent / "outside" / "alias.json"
    os.link(token, alias)
    _refused(alias, token)


def test_refuses_a_token_cache_replaced_while_the_check_runs(tmp_path, monkeypatch):
    # A refresh renames a new token file over the cache: its path stays the cache while the
    # inode read at the start of the check is gone.
    cache = tmp_path / "refreshing" / "token.json"
    cache.parent.mkdir()
    cache.write_text("{}")
    real = os.path.realpath(cache)
    stat = os.stat
    replaced = []

    def stat_then_replace(path, *args, **kwargs):
        result = stat(path, *args, **kwargs)
        if not replaced and os.fspath(path) == real:
            replaced.append(True)
            (cache.parent / "next").write_text("{}")
            os.replace(cache.parent / "next", cache)
        return result

    monkeypatch.setattr(_state_paths.os, "stat", stat_then_replace)
    _refused(cache, cache)
    assert replaced


def test_refuses_a_link_in_the_state_directory_that_points_out_of_it(state):
    token = state / "token.json"
    outside = state.parent / "outside"
    (outside / "real.json").write_text("{}")
    # A rename over the link replaces the link, in the state directory.
    (state / "title-cache.json").symlink_to(outside / "real.json")
    _refused(state / "title-cache.json", token)
    (outside / "link.json").symlink_to(outside / "real.json")
    _allowed(outside / "link.json", token)


# ---------------------------------------------------------------- uploads


def _client_config(seeded_config, state: Path):
    # The token cache in the state directory, as by default.
    token = state / "token.json"
    token.write_text(seeded_config.token_cache_path.read_text())
    return dataclasses.replace(seeded_config, token_cache_path=token)


def _split_path(base: Path, name: str, secret: bytes, decoy: bytes) -> tuple[str, Path]:
    """A path whose text and whose OS resolution name different files: ``link/../state/
    <name>`` reads as ``<base>/state/<name>`` while the OS, following the link first, lands
    on ``<base>/decoy/state/<name>``."""
    (base / "state").mkdir(parents=True, exist_ok=True)
    (base / "decoy" / "sub").mkdir(parents=True)
    (base / "decoy" / "state").mkdir()
    (base / "state" / name).write_bytes(secret)
    (base / "decoy" / "state" / name).write_bytes(decoy)
    (base / "link").symlink_to(base / "decoy" / "sub")
    return f"{base}{os.sep}link{os.sep}..{os.sep}state{os.sep}{name}", base / "state" / name


def test_file_parse_refuses_a_state_file_even_through_a_pdf_symlink(tmp_path, seeded_config, state):
    config = _client_config(seeded_config, state)
    secret = state / "token.pdf"
    secret.write_bytes(b"%PDF-1.4 not really\n")
    link = tmp_path / "outside" / "innocent.pdf"
    link.symlink_to(secret)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(_PARSE_SUBMIT)
        with GangtiseClient(_config=config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="own state"):
                Tool(client).file_parse(file=link)
    assert not route.called


def test_file_parse_refuses_a_renamed_non_pdf_and_takes_a_header_after_leading_bytes(
    tmp_path, seeded_config
):
    renamed = tmp_path / "renamed.pdf"
    renamed.write_bytes(b'{"accessToken":"x"}')
    lead = tmp_path / "lead.pdf"
    lead.write_bytes(b" " * 500 + b"%PDF-1.7\n")
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PARSE_SUBMIT).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"taskId": "1"}}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match="no %PDF- header"):
                Tool(client).file_parse(file=renamed)
            assert Tool(client).file_parse(file=lead) == "1"
    assert route.call_count == 1


def test_file_parse_takes_the_suffix_and_name_from_the_path_given(tmp_path, seeded_config):
    # report.pdf → a file without a suffix: a PDF under the name given, sent as report.pdf.
    target = tmp_path / "blob"
    target.write_bytes(b"%PDF-1.7\n")
    (tmp_path / "report.pdf").symlink_to(target)
    # x.txt → y.pdf: not a .pdf under the name given.
    (tmp_path / "y.pdf").write_bytes(b"%PDF-1.7\n")
    (tmp_path / "x.txt").symlink_to(tmp_path / "y.pdf")
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PARSE_SUBMIT).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"taskId": "1"}}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            assert Tool(client).file_parse(file=tmp_path / "report.pdf") == "1"
            with pytest.raises(ValidationError, match="only PDF files"):
                Tool(client).file_parse(file=tmp_path / "x.txt")
    assert route.call_count == 1
    assert b'filename="report.pdf"' in route.calls.last.request.read()


def test_drive_upload_reads_the_file_the_guard_checked_under_the_name_given(
    tmp_path, seeded_config, state
):
    given, cache = _split_path(tmp_path / "outside", "token.json", b"SECRET", b"decoy")
    # The text names the moved token cache; the OS reaches the decoy. A given token keeps
    # the client off the (fake) cache.
    config = dataclasses.replace(seeded_config, token_cache_path=cache, token="tok")
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_UPLOAD).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"fileId": "1"}}
            )
        )
        with GangtiseClient(_config=config) as client:
            Vault(client).drive_upload(file=given)
    content = route.calls.last.request.read()
    assert b"decoy" in content
    assert b"SECRET" not in content
    assert b'filename="token.json"' in content


def test_drive_upload_refuses_the_token_cache(seeded_config, state):
    config = _client_config(seeded_config, state)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(_UPLOAD)
        with GangtiseClient(_config=config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="own state"):
                Vault(client).drive_upload(file=state / "token.json")
    assert not route.called


# ---------------------------------------------------------------- download output


_DOWNLOAD = "/application/open-insight/research/download/file"


@pytest.mark.parametrize("kind", ["existing", "trailing-separator", "state", "link-in-state"])
def test_a_download_refuses_a_directory_or_state_output_before_any_request(
    tmp_path, seeded_config, state, kind
):
    config = _client_config(seeded_config, state)
    (tmp_path / "outside" / "real.json").write_text("{}")
    (state / "title-cache.json").symlink_to(tmp_path / "outside" / "real.json")
    output = {
        "existing": tmp_path / "outside",
        "trailing-separator": f"{tmp_path / 'new-dir'}{os.sep}",
        "state": state / "token.json",
        "link-in-state": state / "title-cache.json",
    }[kind]
    match = "is a directory" if kind in ("existing", "trailing-separator") else "own state"
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.get(_DOWNLOAD)
        with GangtiseClient(_config=config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match=match):
                Insight(client).research_download(report_id="r1", file_type=1, output=output)
    assert not route.called


def test_a_download_refuses_the_state_directory_before_it_exists(
    tmp_path, seeded_config, monkeypatch
):
    # First use with a given token: no token cache, so no state directory yet.
    missing = tmp_path / "missing"
    monkeypatch.setattr(_state_paths, "DEFAULT_TOKEN_CACHE_PATH", missing / "token.json")
    config = dataclasses.replace(
        seeded_config, token_cache_path=missing / "token.json", token="tok"
    )
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.get(_DOWNLOAD)
        with GangtiseClient(_config=config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="own state"):
                Insight(client).research_download(report_id="r1", file_type=1, output=missing)
    assert not route.called
    assert not missing.exists()


@pytest.mark.anyio
async def test_an_async_download_refuses_a_directory_output_before_any_request(
    tmp_path, seeded_config
):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.get(_DOWNLOAD)
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match="is a directory"):
                await AsyncInsight(client).research_download(
                    report_id="r1", file_type=1, output=tmp_path
                )
    assert not route.called


def test_file_parse_reads_the_file_the_guard_checked(tmp_path, seeded_config):
    given, cache = _split_path(
        tmp_path / "outside", "token.pdf", b"%PDF-1.4 SECRET", b"%PDF-1.4 decoy"
    )
    config = dataclasses.replace(seeded_config, token_cache_path=cache, token="tok")
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PARSE_SUBMIT).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"taskId": "1"}}
            )
        )
        with GangtiseClient(_config=config) as client:
            Tool(client).file_parse(file=given)
    content = route.calls.last.request.read()
    assert b"%PDF-1.4 decoy" in content
    assert b"SECRET" not in content
