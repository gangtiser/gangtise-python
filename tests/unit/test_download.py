import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import anyio
import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._download import (
    _write_response_to_disk,
    _write_response_to_disk_async,
    download_to_path,
    download_to_path_async,
)
from gangtise_openapi._errors import ERROR_HINTS, ApiError, DownloadError


def _cfg(tmp_path: Path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


_LOGIN_JSON = {
    "code": "000000",
    "status": True,
    "data": {
        "accessToken": "refreshed",
        "expiresIn": 3600,
        "time": 0,
        "uid": 1,
        "userName": "x",
        "tenantId": 1,
    },
}


class _ExplodingSyncStream(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        yield b"partial"
        raise httpx.ReadError("connection lost")


class _ExplodingAsyncStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"partial"
        raise httpx.ReadError("connection lost")


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


def test_download_appends_text_extension_to_title_cache_name(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"plain text",
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            client._record_list_titles(
                list_endpoint_key="insight.summary.list",
                id_field="summaryId",
                title_field="title",
                rows=[{"summaryId": "s1", "title": "Alpha Summary"}],
            )
            path = download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=None,
                fallback_name="summary-s1",
                title_lookup=("insight.summary.list", "summaryId", "s1"),
            )
    assert path.name == "Alpha Summary.txt"
    assert path.read_text() == "plain text"


def test_download_keeps_existing_title_extension_when_mime_disagrees(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-vault/drive/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"doc",
                headers={"content-type": "application/msword"},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            client._record_list_titles(
                list_endpoint_key="vault.drive.list",
                id_field="fileId",
                title_field="title",
                rows=[{"fileId": "f1", "title": "Original Name.docx"}],
            )
            path = download_to_path(
                client=client,
                endpoint_key="vault.drive.download",
                query={"fileId": "f1"},
                output=None,
                fallback_name="file-f1",
                title_lookup=("vault.drive.list", "fileId", "f1"),
            )
    assert path.name == "Original Name.docx"


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
    assert path.name == "passwd.pdf"


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
                json={"note": "no file here"},
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


def test_download_refreshes_token_and_retries_on_auth_error(tmp_path: Path) -> None:
    out_path = tmp_path / "out.pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(200, json=_LOGIN_JSON)
        )
        dl_route = router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"code": "8000014", "status": False, "msg": "bad access key"},
                    headers={"content-type": "application/json"},
                ),
                httpx.Response(
                    200,
                    content=b"%PDF-after-refresh",
                    headers={"content-type": "application/pdf"},
                ),
            ]
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path.read_bytes() == b"%PDF-after-refresh"
    assert dl_route.call_count == 2
    assert dl_route.calls.last.request.headers["Authorization"] == "Bearer refreshed"


def test_download_retries_on_503_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._backoff_delay", lambda attempt: 0.0)
    out_path = tmp_path / "out.pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        dl_route = router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=[
                httpx.Response(503, text="service unavailable"),
                httpx.Response(
                    200,
                    content=b"%PDF-retried",
                    headers={"content-type": "application/pdf"},
                ),
            ]
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path.read_bytes() == b"%PDF-retried"
    assert dl_route.call_count == 2


def test_download_retry_exhaustion_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gangtise_openapi._download._backoff_delay", lambda attempt: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        dl_route = router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(503, text="boom")
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
    assert exc.value.status_code == 503
    assert dl_route.call_count == 3  # initial + 2 retries


def test_download_follows_presigned_url(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"url": "https://cdn.test/signed/report"},
                },
                headers={"content-type": "application/json"},
            )
        )
        router.get("https://cdn.test/signed/report").mock(
            return_value=httpx.Response(
                200,
                content=b"%PDF-presigned",
                headers={
                    "content-disposition": 'attachment; filename="signed.pdf"',
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
    assert path.name == "signed.pdf"
    assert path.read_bytes() == b"%PDF-presigned"


def test_download_presigned_fetch_failure_raises_download_error(tmp_path: Path) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"url": "https://cdn.test/signed/report"},
                },
                headers={"content-type": "application/json"},
            )
        )
        router.get("https://cdn.test/signed/report").mock(
            return_value=httpx.Response(403, text="denied")
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(DownloadError) as exc,
        ):
            download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=tmp_path / "out.pdf",
                fallback_name="report-r1",
            )
    assert "https://cdn.test/signed/report" in str(exc.value)
    assert not (tmp_path / "out.pdf").exists()


def test_download_4xx_envelope_raises_api_error_with_code_and_hint(tmp_path: Path) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                400,
                json={"code": "999997", "msg": "no permission"},
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
    assert exc.value.hint == ERROR_HINTS["999997"]


def test_download_cleans_up_part_file_on_midstream_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._backoff_delay", lambda attempt: 0.0)
    out_path = tmp_path / "out.pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=lambda request: httpx.Response(
                200,
                stream=_ExplodingSyncStream(),
                headers={"content-type": "application/pdf"},
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
                output=out_path,
                fallback_name="report-r1",
            )
    assert not out_path.exists()
    assert list(tmp_path.glob("*.part*")) == []


def test_download_resolves_title_via_list_fallback(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/summary/v2/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"summaryId": "s1", "title": "Cold Cache Summary"}],
                    },
                },
            )
        )
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"plain text",
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=None,
                fallback_name="summary-s1",
                title_lookup=("insight.summary.list", "summaryId", "s1"),
            )
    assert path.name == "Cold Cache Summary.txt"
    assert path.read_text() == "plain text"


def test_download_falls_back_to_disposition_when_list_fetch_fails(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/summary/v2/getList").mock(
            return_value=httpx.Response(
                200,
                json={"code": "999997", "status": False, "msg": "no permission"},
            )
        )
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"plain text",
                headers={
                    "content-disposition": 'attachment; filename="degrade.txt"',
                    "content-type": "text/plain; charset=utf-8",
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=None,
                fallback_name="summary-s1",
                title_lookup=("insight.summary.list", "summaryId", "s1"),
            )
    assert path.name == "degrade.txt"


# ─── async siblings ───


@pytest.mark.anyio
async def test_async_download_uses_content_disposition_filename(
    tmp_path: Path, monkeypatch: object
) -> None:
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
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
    assert path.name == "alpha.pdf"
    assert path.read_bytes() == b"data"


@pytest.mark.anyio
async def test_async_download_falls_back_when_no_filename(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-type": "application/pdf"},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
    assert path.name.startswith("report-r1")


@pytest.mark.anyio
async def test_async_download_raises_on_json_envelope_error(tmp_path: Path) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={"code": "999997", "status": False, "msg": "no permission"},
                headers={"content-type": "application/json"},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as exc:
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.research.download",
                    query={"reportId": "r1"},
                    output=tmp_path / "out.pdf",
                    fallback_name="report-r1",
                )
    assert exc.value.code == "999997"
    assert not (tmp_path / "out.pdf").exists()


@pytest.mark.anyio
async def test_async_download_raises_on_json_non_envelope(tmp_path: Path) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={"note": "no file here"},
                headers={"content-type": "application/json"},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(DownloadError):
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.research.download",
                    query={"reportId": "r1"},
                    output=tmp_path / "out.pdf",
                    fallback_name="report-r1",
                )


@pytest.mark.anyio
async def test_async_download_refreshes_token_and_retries_on_auth_error(tmp_path: Path) -> None:
    out_path = tmp_path / "out.pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(200, json=_LOGIN_JSON)
        )
        dl_route = router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"code": "8000014", "status": False, "msg": "bad access key"},
                    headers={"content-type": "application/json"},
                ),
                httpx.Response(
                    200,
                    content=b"%PDF-after-refresh",
                    headers={"content-type": "application/pdf"},
                ),
            ]
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path.read_bytes() == b"%PDF-after-refresh"
    assert dl_route.call_count == 2
    assert dl_route.calls.last.request.headers["Authorization"] == "Bearer refreshed"


@pytest.mark.anyio
async def test_async_download_retries_on_503_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._backoff_delay", lambda attempt: 0.0)
    out_path = tmp_path / "out.pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        dl_route = router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=[
                httpx.Response(503, text="service unavailable"),
                httpx.Response(
                    200,
                    content=b"%PDF-retried",
                    headers={"content-type": "application/pdf"},
                ),
            ]
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path.read_bytes() == b"%PDF-retried"
    assert dl_route.call_count == 2


@pytest.mark.anyio
async def test_async_download_retry_exhaustion_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._backoff_delay", lambda attempt: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        dl_route = router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(503, text="boom")
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as exc:
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.research.download",
                    query={"reportId": "r1"},
                    output=tmp_path / "out.pdf",
                    fallback_name="report-r1",
                )
    assert exc.value.status_code == 503
    assert dl_route.call_count == 3  # initial + 2 retries


@pytest.mark.anyio
async def test_async_download_follows_presigned_url(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"url": "https://cdn.test/signed/report"},
                },
                headers={"content-type": "application/json"},
            )
        )
        router.get("https://cdn.test/signed/report").mock(
            return_value=httpx.Response(
                200,
                content=b"%PDF-presigned",
                headers={
                    "content-disposition": 'attachment; filename="signed.pdf"',
                    "content-type": "application/pdf",
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
    assert path.name == "signed.pdf"
    assert path.read_bytes() == b"%PDF-presigned"


@pytest.mark.anyio
async def test_async_download_presigned_fetch_failure_raises_download_error(
    tmp_path: Path,
) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"url": "https://cdn.test/signed/report"},
                },
                headers={"content-type": "application/json"},
            )
        )
        router.get("https://cdn.test/signed/report").mock(
            return_value=httpx.Response(403, text="denied")
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(DownloadError) as exc:
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.research.download",
                    query={"reportId": "r1"},
                    output=tmp_path / "out.pdf",
                    fallback_name="report-r1",
                )
    assert "https://cdn.test/signed/report" in str(exc.value)
    assert not (tmp_path / "out.pdf").exists()


@pytest.mark.anyio
async def test_async_download_4xx_envelope_raises_api_error_with_code_and_hint(
    tmp_path: Path,
) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                400,
                json={"code": "999997", "msg": "no permission"},
                headers={"content-type": "application/json"},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as exc:
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.research.download",
                    query={"reportId": "r1"},
                    output=tmp_path / "out.pdf",
                    fallback_name="report-r1",
                )
    assert exc.value.code == "999997"
    assert exc.value.hint == ERROR_HINTS["999997"]


@pytest.mark.anyio
async def test_async_download_cleans_up_part_file_on_midstream_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._backoff_delay", lambda attempt: 0.0)
    out_path = tmp_path / "out.pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=lambda request: httpx.Response(
                200,
                stream=_ExplodingAsyncStream(),
                headers={"content-type": "application/pdf"},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(DownloadError):
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.research.download",
                    query={"reportId": "r1"},
                    output=out_path,
                    fallback_name="report-r1",
                )
    assert not out_path.exists()
    assert list(tmp_path.glob("*.part*")) == []


@pytest.mark.anyio
async def test_async_download_resolves_title_via_list_fallback(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/summary/v2/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"summaryId": "s1", "title": "Cold Cache Summary"}],
                    },
                },
            )
        )
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"plain text",
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=None,
                fallback_name="summary-s1",
                title_lookup=("insight.summary.list", "summaryId", "s1"),
            )
    assert path.name == "Cold Cache Summary.txt"
    assert path.read_text() == "plain text"


@pytest.mark.anyio
async def test_async_download_falls_back_to_disposition_when_list_fetch_fails(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/summary/v2/getList").mock(
            return_value=httpx.Response(
                200,
                json={"code": "999997", "status": False, "msg": "no permission"},
            )
        )
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"plain text",
                headers={
                    "content-disposition": 'attachment; filename="degrade.txt"',
                    "content-type": "text/plain; charset=utf-8",
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=None,
                fallback_name="summary-s1",
                title_lookup=("insight.summary.list", "summaryId", "s1"),
            )
    assert path.name == "degrade.txt"


# --- Concurrent-download temp-file isolation (regression) ---------------------
#
# Two downloads that resolve to the same target must not share one ".part" temp
# file: if they do, their byte streams interleave into one handle and each task's
# cleanup deletes the other's file. The barrier forces both writers to be
# mid-stream at the same instant so the collision is deterministic, not flaky.


class _BarrierResponse:
    """Duck-typed sync response that pauses mid-stream at a barrier."""

    def __init__(self, payload: bytes, barrier: threading.Barrier) -> None:
        self.headers: dict[str, str] = {}
        self._payload = payload
        self._barrier = barrier

    def iter_bytes(self) -> Iterator[bytes]:
        half = len(self._payload) // 2
        yield self._payload[:half]
        self._barrier.wait()
        yield self._payload[half:]


class _AsyncBarrier:
    """Two-party barrier for a single-threaded event loop (no lock needed)."""

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._count = 0
        self._event = anyio.Event()

    async def wait(self) -> None:
        self._count += 1
        if self._count >= self._parties:
            self._event.set()
        else:
            await self._event.wait()


class _BarrierAsyncResponse:
    """Duck-typed async response that pauses mid-stream at a barrier."""

    def __init__(self, payload: bytes, barrier: _AsyncBarrier) -> None:
        self.headers: dict[str, str] = {}
        self._payload = payload
        self._barrier = barrier

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        half = len(self._payload) // 2
        yield self._payload[:half]
        await self._barrier.wait()
        yield self._payload[half:]


def test_download_concurrent_same_target_no_collision(tmp_path: Path) -> None:
    target = tmp_path / "report.pdf"
    barrier = threading.Barrier(2, timeout=5)
    errors: list[Exception] = []

    with GangtiseClient(_config=_cfg(tmp_path)) as client:

        def run(payload: bytes) -> None:
            try:
                _write_response_to_disk(
                    client=client,
                    response=_BarrierResponse(payload, barrier),  # type: ignore[arg-type]
                    output=target,
                    fallback_name="x",
                    title_lookup=None,
                )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=run, args=(b"AAAAAAAA",)),
            threading.Thread(target=run, args=(b"BBBBBBBB",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert errors == [], f"concurrent downloads raised: {errors}"
    assert target.read_bytes() in (b"AAAAAAAA", b"BBBBBBBB")
    assert list(tmp_path.glob("*.part*")) == []


@pytest.mark.anyio
async def test_async_download_concurrent_same_target_no_collision(tmp_path: Path) -> None:
    target = tmp_path / "report.pdf"
    barrier = _AsyncBarrier(2)
    errors: list[Exception] = []

    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:

        async def run(payload: bytes) -> None:
            try:
                await _write_response_to_disk_async(
                    client=client,
                    response=_BarrierAsyncResponse(payload, barrier),  # type: ignore[arg-type]
                    output=target,
                    fallback_name="x",
                    title_lookup=None,
                )
            except Exception as exc:
                errors.append(exc)

        async with anyio.create_task_group() as tg:
            tg.start_soon(run, b"AAAAAAAA")
            tg.start_soon(run, b"BBBBBBBB")

    assert errors == [], f"concurrent downloads raised: {errors}"
    assert target.read_bytes() in (b"AAAAAAAA", b"BBBBBBBB")
    assert list(tmp_path.glob("*.part*")) == []
