from pathlib import Path

import httpx
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._download import download_to_path
from gangtise_openapi._errors import ApiError, DownloadError


def _cfg(tmp_path: Path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_download_with_explicit_output(tmp_path: Path) -> None:
    out_path = tmp_path / "report.pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"%PDF-fake",
                headers={"content-type": "application/pdf"},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path == out_path
    assert path.read_bytes() == b"%PDF-fake"


def test_download_uses_content_disposition_filename(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={
                    "content-disposition": 'attachment; filename="alpha.pdf"',
                    "content-type": "application/pdf",
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
    assert path.name == "alpha.pdf"
    assert path.read_bytes() == b"data"


def test_download_falls_back_when_no_filename(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-type": "application/pdf"},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
    assert path.name.startswith("report-r1")


def test_download_strips_path_traversal_from_content_disposition(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={
                    "content-disposition": 'attachment; filename="../../etc/passwd"',
                    "content-type": "application/pdf",
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
    # Filename gets stripped to just "passwd", landing in CWD.
    assert path.parent == tmp_path
    assert path.name == "passwd"


def test_download_raises_on_json_envelope_error(tmp_path: Path) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={"code": "999997", "status": False, "msg": "no permission"},
                headers={"content-type": "application/json"},
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(ApiError) as exc,
        ):
            download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=tmp_path / "out.pdf",
                fallback_name="report-r1",
            )
    assert exc.value.code == "999997"
    # No file should have been written.
    assert not (tmp_path / "out.pdf").exists()


def test_download_raises_on_json_non_envelope(tmp_path: Path) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={"url": "https://example.com/signed"},
                headers={"content-type": "application/json"},
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(DownloadError),
        ):
            download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=tmp_path / "out.pdf",
                fallback_name="report-r1",
            )
