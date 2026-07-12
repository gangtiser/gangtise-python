import threading
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import quote

import anyio
import httpx
import pytest
import respx

from gangtise_openapi._auth import TokenCache
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._download import (
    _parse_content_disposition,
    _sanitize_filename,
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


def _cfg_without_token(tmp_path: Path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token=None,
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def _cache(token: str) -> TokenCache:
    return TokenCache(
        access_token=token,
        expires_in=3600,
        time=int(time.time()),
        expires_at=int(time.time()) + 3600,
    )


def test_sanitize_filename_strips_control_chars_and_nul():
    # CLI v0.21.0 parity: control chars + NUL (\x00-\x1f) join the forbidden set so
    # a server-supplied filename can't break the file write or smuggle escapes.
    assert _sanitize_filename("a\x00b\x1fc") == "a_b_c"
    assert _sanitize_filename("tab\tnew\nline") == "tab_new_line"
    # existing forbidden chars still handled alongside control chars
    assert _sanitize_filename("a/b\x01c") == "a_b_c"


def test_parse_content_disposition_decodes_rfc5987_case_insensitively():
    assert (
        _parse_content_disposition("attachment; filename*=utf-8''%E5%B9%B4%E6%8A%A5.pdf")
        == "年报.pdf"
    )
    assert (
        _parse_content_disposition("attachment; filename*=UTF-8''%E5%B9%B4%E6%8A%A5.pdf")
        == "年报.pdf"
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


def test_download_follows_302_to_presigned_url_and_drops_auth(tmp_path: Path) -> None:
    # A download endpoint may 302 to a presigned object-store URL on another host.
    # httpx defaults to follow_redirects=False, so without the explicit opt-in the empty
    # redirect body would land on disk. It must follow the hop AND, because it's
    # cross-origin, must not forward the Authorization bearer to the storage host.
    out_path = tmp_path / "report.pdf"
    with respx.mock(assert_all_called=True) as router:
        router.get("https://api.test/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                302, headers={"location": "https://storage.test/signed/report.pdf"}
            )
        )
        storage = router.get("https://storage.test/signed/report.pdf").mock(
            return_value=httpx.Response(
                200, content=b"%PDF-signed", headers={"content-type": "application/pdf"}
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
    assert path.read_bytes() == b"%PDF-signed"
    # Bearer must not leak to the object store (httpx strips it on the cross-origin hop).
    assert "authorization" not in {k.lower() for k in storage.calls.last.request.headers}


@pytest.mark.anyio
async def test_download_async_follows_302_to_presigned_url_and_drops_auth(tmp_path: Path) -> None:
    out_path = tmp_path / "report.pdf"
    with respx.mock(assert_all_called=True) as router:
        router.get("https://api.test/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                302, headers={"location": "https://storage.test/signed/report.pdf"}
            )
        )
        storage = router.get("https://storage.test/signed/report.pdf").mock(
            return_value=httpx.Response(
                200, content=b"%PDF-signed", headers={"content-type": "application/pdf"}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path == out_path
    assert path.read_bytes() == b"%PDF-signed"
    assert "authorization" not in {k.lower() for k in storage.calls.last.request.headers}


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


def test_download_auto_filename_suffixes_existing_file(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=[
                httpx.Response(
                    200,
                    content=b"first",
                    headers={
                        "content-disposition": 'attachment; filename="same.pdf"',
                        "content-type": "application/pdf",
                    },
                ),
                httpx.Response(
                    200,
                    content=b"second",
                    headers={
                        "content-disposition": 'attachment; filename="same.pdf"',
                        "content-type": "application/pdf",
                    },
                ),
            ]
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            first = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
            second = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r2"},
                output=None,
                fallback_name="report-r2",
            )
    assert first.name == "same.pdf"
    assert second.name == "same-1.pdf"
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"


def test_download_truncates_overlong_auto_filename(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    long_name = ("会" * 90) + ".pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={
                    "content-disposition": f"attachment; filename*=UTF-8''{quote(long_name)}",
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
    assert len(path.name.encode("utf8")) <= 210
    assert path.name.endswith(".pdf")
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


def test_download_auth_retry_reuses_concurrent_refreshed_token(tmp_path: Path) -> None:
    out_path = tmp_path / "out.pdf"
    holder: dict[str, GangtiseClient] = {}

    def download_side_effect(request: httpx.Request) -> httpx.Response:
        auth = request.headers["Authorization"]
        if auth == "Bearer stale":
            holder["client"]._memo_cache = _cache("fresh")
            return httpx.Response(
                200,
                json={"code": "0000001008", "status": False, "msg": "stale token"},
                headers={"content-type": "application/json"},
            )
        assert auth == "Bearer fresh"
        return httpx.Response(
            200,
            content=b"%PDF-after-shared-refresh",
            headers={"content-type": "application/pdf"},
        )

    with respx.mock(
        base_url="https://api.test", assert_all_called=True, assert_all_mocked=True
    ) as router:
        dl_route = router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=download_side_effect
        )
        with GangtiseClient(_config=_cfg_without_token(tmp_path)) as client:
            client._memo_cache = _cache("stale")
            holder["client"] = client
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path.read_bytes() == b"%PDF-after-shared-refresh"
    assert dl_route.call_count == 2


def test_download_retries_on_503_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
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
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
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


def test_presigned_error_redacts_signature_from_message(tmp_path: Path) -> None:
    # Signed URLs carry credentials in the query string — the exception text must
    # keep only scheme://host/path so signatures never land in terminal/CI logs.
    signed = "https://cdn.test/signed/report?X-Amz-Signature=SECRET&X-Amz-Expires=60"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"url": signed}},
                headers={"content-type": "application/json"},
            )
        )
        router.get(signed).mock(return_value=httpx.Response(403, text="denied"))
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
    message = str(exc.value)
    assert "SECRET" not in message and "X-Amz" not in message
    assert "https://cdn.test/signed/report" in message


def test_presigned_fetch_retries_network_error_without_rebilling_upstream(
    tmp_path: Path, monkeypatch
) -> None:
    # A transient network failure on the SIGNED URL retries (safe, unbilled);
    # the billed upstream endpoint must be requested exactly once.
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        upstream = router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"url": "https://cdn.test/s/f"}},
                headers={"content-type": "application/json"},
            )
        )
        cdn = router.get("https://cdn.test/s/f").mock(
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.Response(
                    200, content=b"%PDF-cdn", headers={"content-type": "application/pdf"}
                ),
            ]
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=tmp_path / "out.pdf",
                fallback_name="report-r1",
            )
    assert upstream.call_count == 1
    assert cdn.call_count == 2
    assert path.read_bytes() == b"%PDF-cdn"


def test_claim_auto_named_never_overwrites_and_scans_from_original_name(tmp_path: Path) -> None:
    # A racer took the desired name after our check; the commit loses to the NEXT
    # suffix scanned from the ORIGINAL name (report-2.pdf, not report-1-1.pdf) and
    # never clobbers the winner.
    from gangtise_openapi._download import _claim_auto_named

    desired = tmp_path / "report.pdf"
    desired.write_bytes(b"winner-0")
    (tmp_path / "report-1.pdf").write_bytes(b"winner-1")
    tmp = tmp_path / "report.pdf.part-abc"
    tmp.write_bytes(b"loser-content")
    final = _claim_auto_named(tmp, desired)
    tmp.unlink(missing_ok=True)  # the real writer's `finally` does this
    assert final == tmp_path / "report-2.pdf"
    assert desired.read_bytes() == b"winner-0"
    assert (tmp_path / "report-1.pdf").read_bytes() == b"winner-1"
    assert final.read_bytes() == b"loser-content"


def test_claim_auto_named_appears_atomically_without_zero_byte_window(
    tmp_path: Path, monkeypatch
) -> None:
    # os.link publishes the COMPLETE file in one step — the target must never be
    # observed as a 0-byte placeholder (regression from the O_EXCL-only v0.1.16).
    import gangtise_openapi._download as dl

    called = {"replace": False}
    orig = Path.replace

    def spy(self: Path, other: object) -> object:
        called["replace"] = True
        return orig(self, other)

    monkeypatch.setattr(Path, "replace", spy)  # fixture auto-undoes, even on failure
    dl_target = tmp_path / "doc.pdf"
    tmp = tmp_path / "doc.pdf.part-x"
    tmp.write_bytes(b"FULL")
    final = dl._claim_auto_named(tmp, dl_target)
    tmp.unlink(missing_ok=True)
    assert not called["replace"]  # hard-link path, no placeholder-then-replace
    assert final.read_bytes() == b"FULL"


def test_claim_via_placeholder_cleans_up_when_move_fails(tmp_path: Path, monkeypatch) -> None:
    # Fallback path (os.link unsupported): after O_EXCL reserves the name, a failed
    # move must unlink the placeholder so no bogus 0-byte file lingers, and the
    # error propagates. (Restores coverage the v0.1.17 diff dropped.)
    import gangtise_openapi._download as dl

    def no_link(src: object, dst: object) -> None:
        raise OSError(45, "operation not supported")  # force the placeholder path

    def boom_replace(self: Path, other: object) -> object:
        raise OSError(18, "cross-device link")  # EXDEV on the final move

    monkeypatch.setattr(dl.os, "link", no_link)
    monkeypatch.setattr(Path, "replace", boom_replace)
    target = tmp_path / "x.pdf"
    tmp = tmp_path / "x.pdf.part-q"
    tmp.write_bytes(b"DATA")
    with pytest.raises(OSError, match="cross-device"):
        dl._claim_auto_named(tmp, target)
    assert not target.exists()  # placeholder cleaned up, no 0-byte file left behind


def test_claim_via_placeholder_close_failure_still_lands_complete_file(
    tmp_path: Path, monkeypatch
) -> None:
    # Fallback path (os.link unsupported): a close-time OSError on the O_EXCL
    # placeholder fd (a flaky SMB/exFAT mount) must NOT abort the commit. The fd is
    # opened only to reserve the name; the load-bearing step is the rename of the
    # finished .part onto that name. If close aborted, the complete .part would be
    # deleted by the outer finally and only a 0-byte file would remain. Close is
    # best-effort — the complete bytes still land.
    import gangtise_openapi._download as dl

    def no_link(src: object, dst: object) -> None:
        raise OSError(45, "operation not supported")  # force the placeholder path

    real_close = dl.os.close
    calls = {"n": 0}

    def flaky_close(fd: int) -> None:
        calls["n"] += 1
        real_close(fd)  # actually release the fd so the test leaks nothing
        if calls["n"] == 1:
            raise OSError(5, "simulated close EIO")  # first close = the placeholder

    monkeypatch.setattr(dl.os, "link", no_link)
    monkeypatch.setattr(dl.os, "close", flaky_close)
    target = tmp_path / "report.pdf"
    tmp = tmp_path / "report.pdf.part-q"
    tmp.write_bytes(b"COMPLETE-PDF-BYTES")
    final = dl._claim_auto_named(tmp, target)
    assert final == target
    assert final.read_bytes() == b"COMPLETE-PDF-BYTES"  # complete file, not 0 bytes
    assert not tmp.exists()  # .part consumed by the rename


def test_claim_via_placeholder_scans_suffixes_without_clobber(tmp_path: Path, monkeypatch) -> None:
    # Fallback path also honors no-overwrite: a taken desired name -> next suffix.
    import gangtise_openapi._download as dl

    def no_link(src: object, dst: object) -> None:
        raise OSError(45, "operation not supported")

    monkeypatch.setattr(dl.os, "link", no_link)
    desired = tmp_path / "r.pdf"
    desired.write_bytes(b"winner")
    tmp = tmp_path / "r.pdf.part-q"
    tmp.write_bytes(b"loser")
    final = dl._claim_auto_named(tmp, desired)
    tmp.unlink(missing_ok=True)
    assert final == tmp_path / "r-1.pdf"
    assert desired.read_bytes() == b"winner"
    assert final.read_bytes() == b"loser"


def test_claim_via_placeholder_raises_after_100_collisions(tmp_path: Path, monkeypatch) -> None:
    # The fallback path shares the refusal cap: once -1..-99 are all taken it must
    # refuse rather than clobber (exercises _claim_via_placeholder's _refuse_overwrite).
    import gangtise_openapi._download as dl

    def no_link(src: object, dst: object) -> None:
        raise OSError(45, "operation not supported")

    monkeypatch.setattr(dl.os, "link", no_link)
    (tmp_path / "r.pdf").write_bytes(b"0")
    for i in range(1, 100):
        (tmp_path / f"r-{i}.pdf").write_bytes(b"x")
    tmp = tmp_path / "r.pdf.part-q"
    tmp.write_bytes(b"loser")
    with pytest.raises(DownloadError, match="Refusing to overwrite"):
        dl._claim_auto_named(tmp, tmp_path / "r.pdf")


def test_claim_via_placeholder_cleanup_failure_preserves_original_error(
    tmp_path: Path, monkeypatch
) -> None:
    # If BOTH the move and the placeholder cleanup fail, the ORIGINAL move error must
    # propagate — a failing cleanup unlink must not mask it (needs two fs faults).
    import gangtise_openapi._download as dl

    def no_link(src: object, dst: object) -> None:
        raise OSError(45, "operation not supported")  # force the placeholder path

    def boom_replace(self: Path, other: object) -> object:
        raise OSError(18, "original-move-error")

    orig_unlink = Path.unlink

    def flaky_unlink(self: Path, *a: object, **k: object) -> None:
        if self.suffix == ".pdf":  # the placeholder candidate cleanup also fails
            raise OSError(13, "cleanup-also-fails")
        orig_unlink(self, *a, **k)

    monkeypatch.setattr(dl.os, "link", no_link)
    monkeypatch.setattr(Path, "replace", boom_replace)
    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    tmp = tmp_path / "x.pdf.part-q"
    tmp.write_bytes(b"DATA")
    with pytest.raises(OSError, match="original-move-error"):
        dl._claim_auto_named(tmp, tmp_path / "x.pdf")


def test_claim_auto_named_falls_back_to_placeholder_when_link_unsupported(
    tmp_path: Path, monkeypatch
) -> None:
    # On a filesystem without hard links (EPERM/EXDEV/…), fall back to the
    # O_EXCL placeholder path — still non-clobbering, download still lands.
    import gangtise_openapi._download as dl

    def no_link(src: object, dst: object) -> None:
        raise OSError(1, "operation not permitted")  # errno 1 = EPERM

    monkeypatch.setattr(dl.os, "link", no_link)
    target = tmp_path / "a.pdf"
    tmp = tmp_path / "a.pdf.part-z"
    tmp.write_bytes(b"CONTENT")
    final = dl._claim_auto_named(tmp, target)
    assert final == target
    assert final.read_bytes() == b"CONTENT"


def test_claim_auto_named_falls_back_on_unlisted_link_errno(tmp_path: Path, monkeypatch) -> None:
    # A filesystem that can't hard-link may report an errno the old whitelist
    # missed — macOS exFAT/SMB raise ENOTSUP (45, distinct from EOPNOTSUPP), and
    # Windows FAT maps to EINVAL. Any os.link OSError must fall back to the
    # placeholder, never re-raise and lose the finished download.
    import errno as _errno

    import gangtise_openapi._download as dl

    def no_link(src: object, dst: object) -> None:
        raise OSError(_errno.ENOTSUP, "operation not supported")

    monkeypatch.setattr(dl.os, "link", no_link)
    target = tmp_path / "a.pdf"
    tmp = tmp_path / "a.pdf.part-z"
    tmp.write_bytes(b"CONTENT")
    final = dl._claim_auto_named(tmp, target)
    assert final == target
    assert final.read_bytes() == b"CONTENT"


def test_claim_auto_named_raises_after_100_collisions(tmp_path: Path) -> None:
    # Refuse rather than clobber once -1..-99 are all taken (was _unique_path).
    from gangtise_openapi._download import _claim_auto_named

    (tmp_path / "report.pdf").write_bytes(b"0")
    for i in range(1, 100):
        (tmp_path / f"report-{i}.pdf").write_bytes(b"x")
    tmp = tmp_path / "report.pdf.part-y"
    tmp.write_bytes(b"loser")
    with pytest.raises(DownloadError, match="Refusing to overwrite"):
        _claim_auto_named(tmp, tmp_path / "report.pdf")


def test_redact_url_strips_userinfo_query_and_fragment() -> None:
    from gangtise_openapi._download import _redact_url

    redacted = _redact_url("https://alice:TOPSECRET@cdn.test:8443/f?X-Amz-Signature=S#frag")
    assert redacted == "https://cdn.test:8443/f"
    for secret in ("alice", "TOPSECRET", "X-Amz", "frag"):
        assert secret not in redacted


def test_redact_url_fails_closed_on_malformed_input() -> None:
    from gangtise_openapi._download import _redact_url

    # Scheme-confusion: `alice:` parses as the scheme, so a naive netloc-based
    # redactor would leak `alice://TOPSECRET@...`. Must collapse instead.
    assert _redact_url("alice:TOPSECRET@cdn.test/path?sig=X") == "redacted-url"
    # Invalid port (raises ValueError on .port) must not leak the raw value.
    assert _redact_url("https://cdn.test:PORTSECRET/p") == "redacted-url"
    # Non-http(s) schemes collapse too.
    assert _redact_url("ftp://user:pw@host/p") == "redacted-url"
    assert _redact_url("not a url") == "redacted-url"


def test_redact_url_collapses_non_ascii_authority() -> None:
    from gangtise_openapi._download import _redact_url

    # A malformed non-ASCII / IDNA authority (real IDN hosts are punycode/ASCII on
    # the wire) urlsplit preserves but httpx would reject — it must not be echoed
    # into the "fail-closed" message. (A \t/\r/\n in the host is a non-issue: urlsplit
    # strips those, yielding a clean host.)
    assert _redact_url("https://ex‍ample.test/f?sig=SECRET") == "redacted-url"


def test_redact_url_collapses_malformed_ipv4_authority() -> None:
    from gangtise_openapi._download import _redact_url

    # httpx.URL (the parser the fetcher actually uses) rejects 1.2.3.999 as an
    # invalid IPv4, but stdlib urlsplit accepts it as a plain reg-name and would
    # echo the bad authority. The redactor must fail closed to httpx's verdict so
    # the README claim ("畸形 authority 折叠为 redacted-url") holds.
    assert _redact_url("https://1.2.3.999/f?sig=SECRET") == "redacted-url"


def test_require_fetchable_url_rejects_malformed_before_fetch(tmp_path: Path) -> None:
    # A malformed signed URL (bad port) must raise a redacted DownloadError, not
    # let httpx.InvalidURL (not an httpx.HTTPError) escape with the raw secret.
    from gangtise_openapi._download import _require_fetchable_url

    with pytest.raises(DownloadError) as exc:
        _require_fetchable_url("https://cdn.test:PORTSECRET/p?sig=SECRET")
    assert "PORTSECRET" not in str(exc.value) and "SECRET" not in str(exc.value)
    _require_fetchable_url("https://cdn.test:8443/ok")  # valid -> no raise


def test_require_fetchable_url_rejects_httpx_invalid_forms() -> None:
    # stdlib urlsplit is laxer than httpx's parser: an embedded control char, a
    # malformed dotted-quad host, an IDNA-unencodable host, and leading whitespace
    # all pass urlsplit but make httpx raise InvalidURL (NOT an httpx.HTTPError) at
    # fetch time, escaping the download except-ladders unwrapped. The guard must
    # reject them up front as a redacted DownloadError (secret rides in the query,
    # which _redact_url strips).
    from gangtise_openapi._download import _require_fetchable_url

    for bad in (
        "https://cdn.test/f\tx?sig=SECRET",  # embedded tab
        "https://1.2.3.999/p?sig=SECRET",  # malformed IPv4 host
        " https://cdn.test/f?sig=SECRET",  # leading space -> httpx parses as relative
        "https://ex‍ample.test/f?sig=SECRET",  # zero-width joiner -> bad IDNA host
    ):
        with pytest.raises(DownloadError) as exc:
            _require_fetchable_url(bad)
        assert "SECRET" not in str(exc.value)
    _require_fetchable_url("https://cdn.test:8443/ok")  # valid -> no raise


def test_concurrent_auto_named_downloads_keep_both_files(tmp_path: Path, monkeypatch) -> None:
    # End-to-end: two output=None downloads resolving the same fallback name must
    # land as two files with intact contents — never a silent overwrite.
    monkeypatch.chdir(tmp_path)
    barrier = threading.Barrier(2)
    results: list[Path] = []
    errors: list[BaseException] = []

    def worker(client: GangtiseClient) -> None:
        try:
            barrier.wait(timeout=10)
            results.append(
                download_to_path(
                    client=client,
                    endpoint_key="insight.research.download",
                    query={"reportId": "r1"},
                    output=None,
                    fallback_name="same-name",
                )
            )
        except BaseException as exc:
            errors.append(exc)

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=[
                httpx.Response(200, content=b"AAA", headers={"content-type": "application/pdf"}),
                httpx.Response(200, content=b"BBB", headers={"content-type": "application/pdf"}),
            ]
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            threads = [threading.Thread(target=worker, args=(client,)) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
    assert not errors, errors
    assert len(results) == 2
    assert results[0] != results[1]
    contents = sorted(p.read_bytes() for p in results)
    assert contents == [b"AAA", b"BBB"]


def test_part_cleanup_failure_after_commit_does_not_mask_success(
    tmp_path: Path, monkeypatch
) -> None:
    # After os.link commits the COMPLETE file, the finally's `.part` unlink is
    # best-effort: if it fails (Windows AV lock, read-only/odd mount), the download
    # already landed — a raw OSError must NOT propagate and report failure, which
    # would prompt the user to re-invoke a no-replay billed endpoint.
    monkeypatch.chdir(tmp_path)
    orig_unlink = Path.unlink

    def flaky_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if ".part-" in self.name:
            raise OSError(13, "permission denied")  # EACCES cleaning up the .part
        orig_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/report-image/download/file").mock(
            return_value=httpx.Response(
                200, content=b"COMPLETE", headers={"content-type": "application/pdf"}
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.report-image.download",
                query={"chunkId": "c1"},
                output=None,
                fallback_name="doc",
            )
    assert path.read_bytes() == b"COMPLETE"  # committed file intact, no raise


def test_report_image_auto_name_gets_jpg_extension(tmp_path: Path, monkeypatch) -> None:
    # image/jpeg was missing from the MIME map: an auto-named report-image download
    # without Content-Disposition used to land as "report-image-c1" (no extension).
    monkeypatch.chdir(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/report-image/download/file").mock(
            return_value=httpx.Response(
                200, content=b"\xff\xd8jpeg", headers={"content-type": "image/jpeg"}
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.report-image.download",
                query={"chunkId": "c1"},
                output=None,
                fallback_name="report-image-c1",
            )
    assert path.name == "report-image-c1.jpg"


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
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
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
async def test_async_download_auth_retry_reuses_concurrent_refreshed_token(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out.pdf"
    holder: dict[str, AsyncGangtiseClient] = {}

    def download_side_effect(request: httpx.Request) -> httpx.Response:
        auth = request.headers["Authorization"]
        if auth == "Bearer stale":
            holder["client"]._memo_cache = _cache("fresh")
            return httpx.Response(
                200,
                json={"code": "0000001008", "status": False, "msg": "stale token"},
                headers={"content-type": "application/json"},
            )
        assert auth == "Bearer fresh"
        return httpx.Response(
            200,
            content=b"%PDF-after-shared-refresh",
            headers={"content-type": "application/pdf"},
        )

    with respx.mock(
        base_url="https://api.test", assert_all_called=True, assert_all_mocked=True
    ) as router:
        dl_route = router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=download_side_effect
        )
        async with AsyncGangtiseClient(_config=_cfg_without_token(tmp_path)) as client:
            client._memo_cache = _cache("stale")
            holder["client"] = client
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path.read_bytes() == b"%PDF-after-shared-refresh"
    assert dl_route.call_count == 2


@pytest.mark.anyio
async def test_async_download_retries_on_503_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
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
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
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
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
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
async def test_async_download_cleanup_does_not_await_unlink_during_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_run_sync = anyio.to_thread.run_sync

    async def fake_run_sync(func, *args, **kwargs):
        target = getattr(func, "func", func)
        if getattr(target, "__name__", "") == "unlink":
            raise RuntimeError("unlink cleanup must not depend on cancellable to_thread")
        return await original_run_sync(func, *args, **kwargs)

    monkeypatch.setattr("gangtise_openapi._download.anyio.to_thread.run_sync", fake_run_sync)
    response = httpx.Response(
        200,
        stream=_ExplodingAsyncStream(),
        headers={"content-type": "application/pdf"},
    )
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        with pytest.raises(httpx.ReadError):
            await _write_response_to_disk_async(
                client=client,
                response=response,
                output=tmp_path / "out.pdf",
                fallback_name="report-r1",
                title_lookup=None,
            )
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


def test_302_redirect_does_not_replay_billing_endpoint(tmp_path: Path, monkeypatch) -> None:
    # P0: a no-replay download that 302s to a CDN which then fails transiently must
    # retry only the (unbilled) CDN URL — never resend the billed upstream endpoint.
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        upstream = router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        cdn = router.get("https://cdn.test/o/f").mock(
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
            ]
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.summary.download",  # no-replay, billed
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert upstream.call_count == 1  # billed endpoint NOT replayed
    assert cdn.call_count == 2
    assert path.read_bytes() == b"%PDF"


@pytest.mark.anyio
async def test_302_redirect_does_not_replay_billing_endpoint_async(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        upstream = router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        cdn = router.get("https://cdn.test/o/f").mock(
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
            ]
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert upstream.call_count == 1
    assert cdn.call_count == 2
    assert path.read_bytes() == b"%PDF"


def test_302_redirect_without_location_raises_download_error(tmp_path: Path) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302)  # no Location header
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(DownloadError, match="no Location"),
        ):
            download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )


def test_redirect_to_json_error_envelope_raises_apierror(tmp_path: Path) -> None:
    # A 302 whose target answers 200 + application/json business-error envelope
    # must raise ApiError (as the direct download path does), NOT save the JSON
    # bytes as the "downloaded" file and return success.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        router.get("https://cdn.test/o/f").mock(
            return_value=httpx.Response(
                200, json={"code": "430004", "status": False, "msg": "x", "data": None}
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(ApiError) as exc,
        ):
            download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert exc.value.code == "430004"
    assert not (tmp_path / "out.pdf").exists()  # JSON error not written as a file


@pytest.mark.anyio
async def test_redirect_to_json_error_envelope_raises_apierror_async(tmp_path: Path) -> None:
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        router.get("https://cdn.test/o/f").mock(
            return_value=httpx.Response(
                200, json={"code": "430004", "status": False, "msg": "x", "data": None}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as exc:
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.summary.download",
                    query={"summaryId": "s1"},
                    output=tmp_path / "out.pdf",
                    fallback_name="s1",
                )
    assert exc.value.code == "430004"
    assert not (tmp_path / "out.pdf").exists()


def test_redirect_cdn_5xx_retries_then_succeeds(tmp_path: Path, monkeypatch) -> None:
    # A transient CDN 5xx/429 on the redirect hop must retry the (unbilled) signed
    # URL under the default policy, not fail the whole download on the first blip —
    # replaying the signed URL is billing-safe, the billed upstream is untouched.
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        upstream = router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        cdn = router.get("https://cdn.test/o/f").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
            ]
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert upstream.call_count == 1  # billed endpoint not replayed
    assert cdn.call_count == 2  # CDN 503 retried
    assert path.read_bytes() == b"%PDF"


@pytest.mark.anyio
async def test_redirect_cdn_5xx_retries_then_succeeds_async(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        upstream = router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        cdn = router.get("https://cdn.test/o/f").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
            ]
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert upstream.call_count == 1
    assert cdn.call_count == 2
    assert path.read_bytes() == b"%PDF"


def test_same_origin_rejects_explicit_zero_port() -> None:
    # "exact scheme+host+port" must treat an explicit :0 as a DIFFERENT origin from
    # the default port, not fold it via `port or default`. Otherwise the bearer
    # would be forwarded to https://api.test:0 as if it were the API origin.
    import gangtise_openapi._download as dl

    assert dl._same_origin("https://api.test/f", "https://api.test/f") is True  # sanity
    assert dl._same_origin("https://api.test:0/f", "https://api.test/f") is False


def test_same_origin_redirect_keeps_authorization(tmp_path: Path) -> None:
    # A same-origin 302 (Location on the API host) to a still-authenticated path
    # must carry the bearer on the follow-up GET — TS parity and a v0.1.16 compat
    # fix. A cross-origin CDN hop must NOT (covered separately).
    seen: dict[str, str | None] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                302, headers={"location": "https://api.test/protected/file"}
            )
        )
        router.get("/protected/file").mock(side_effect=capture)
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert seen["auth"] == "Bearer tok"  # bearer forwarded same-origin
    assert path.read_bytes() == b"%PDF"


@pytest.mark.anyio
async def test_same_origin_redirect_keeps_authorization_async(tmp_path: Path) -> None:
    seen: dict[str, str | None] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                302, headers={"location": "https://api.test/protected/file"}
            )
        )
        router.get("/protected/file").mock(side_effect=capture)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert seen["auth"] == "Bearer tok"
    assert path.read_bytes() == b"%PDF"


def test_cross_origin_redirect_drops_authorization(tmp_path: Path) -> None:
    # The bearer must NEVER leak to a cross-origin CDN hop (only scheme+host+port
    # exact-match origins keep it).
    seen: dict[str, str | None] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        router.get("https://cdn.test/o/f").mock(side_effect=capture)
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert seen["auth"] is None  # bearer must not cross the origin boundary


def test_redirect_target_auth_error_does_not_replay_billed_upstream(
    tmp_path: Path, monkeypatch
) -> None:
    # P1 regression: a followed target answering 200 + JSON auth envelope
    # (0000001008) must NOT drive download_to_path to refresh the token and replay
    # the billed upstream endpoint (double-bill on no-replay 50/篇). The auth error
    # surfaces as-is, with the upstream sent exactly once and no token refresh.
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda e, a: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(200, json=_LOGIN_JSON)
        )
        upstream = router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        router.get("https://cdn.test/o/f").mock(
            return_value=httpx.Response(
                200, json={"code": "0000001008", "status": False, "msg": "token", "data": None}
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(ApiError) as exc,
        ):
            download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert exc.value.code == "0000001008"
    assert upstream.call_count == 1  # billed upstream NOT replayed
    assert login.call_count == 0  # no token refresh for a followed-target auth error
    # The generic 0000001008 hint promises "会自动重新登录重试一次", but for a
    # followed-target auth error no re-login happens (login.call_count == 0) and a
    # manual retry would re-bill — surface the billing-safe followed-target hint.
    from gangtise_openapi._errors import FOLLOWED_TARGET_HINT

    assert exc.value.hint == FOLLOWED_TARGET_HINT
    assert "会自动重新登录" not in str(exc.value)


@pytest.mark.anyio
async def test_redirect_target_auth_error_does_not_replay_billed_upstream_async(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda e, a: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(200, json=_LOGIN_JSON)
        )
        upstream = router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        router.get("https://cdn.test/o/f").mock(
            return_value=httpx.Response(
                200, json={"code": "0000001008", "status": False, "msg": "token", "data": None}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as exc:
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.summary.download",
                    query={"summaryId": "s1"},
                    output=tmp_path / "out.pdf",
                    fallback_name="s1",
                )
    assert exc.value.code == "0000001008"
    assert upstream.call_count == 1
    assert login.call_count == 0
    from gangtise_openapi._errors import FOLLOWED_TARGET_HINT

    assert exc.value.hint == FOLLOWED_TARGET_HINT  # async mint site sets it too
    assert "会自动重新登录" not in str(exc.value)


def test_report_image_followed_target_999999_does_not_replay_billed_upstream(
    tmp_path: Path, monkeypatch
) -> None:
    # P1 regression (round 3): report-image is default-retry AND per-张 billed
    # (0.1 积分/张). A followed target answering 200 + JSON code=999999 is retryable
    # under the DEFAULT policy, so the outer loop would replay _download_once and
    # re-send the billed upstream (3x). from_followed_target must block EVERY outer
    # replay — not just the auth path — so the upstream is sent exactly once.
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda e, a: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(200, json=_LOGIN_JSON)
        )
        upstream = router.get("/application/open-insight/report-image/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        cdn = router.get("https://cdn.test/o/f").mock(
            return_value=httpx.Response(
                200, json={"code": "999999", "status": False, "msg": "sys", "data": None}
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(ApiError) as exc,
        ):
            download_to_path(
                client=client,
                endpoint_key="insight.report-image.download",
                query={"chunkId": "c1"},
                output=tmp_path / "img.jpg",
                fallback_name="c1",
            )
    assert exc.value.code == "999999"
    assert upstream.call_count == 1  # billed upstream NOT replayed
    assert cdn.call_count == 1  # target not retried by the outer loop
    assert login.call_count == 0
    # Billing-safe hint: must not tell the user to "retry later" (a manual retry
    # re-bills the upstream); it flags that the billed upstream already ran.
    from gangtise_openapi._errors import FOLLOWED_TARGET_HINT

    assert exc.value.hint == FOLLOWED_TARGET_HINT
    assert "请稍后重试" not in str(exc.value)


@pytest.mark.anyio
async def test_report_image_followed_target_999999_does_not_replay_billed_upstream_async(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda e, a: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(200, json=_LOGIN_JSON)
        )
        upstream = router.get("/application/open-insight/report-image/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://cdn.test/o/f"})
        )
        cdn = router.get("https://cdn.test/o/f").mock(
            return_value=httpx.Response(
                200, json={"code": "999999", "status": False, "msg": "sys", "data": None}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as exc:
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.report-image.download",
                    query={"chunkId": "c1"},
                    output=tmp_path / "img.jpg",
                    fallback_name="c1",
                )
    assert exc.value.code == "999999"
    assert upstream.call_count == 1
    assert cdn.call_count == 1
    assert login.call_count == 0
    from gangtise_openapi._errors import FOLLOWED_TARGET_HINT

    assert exc.value.hint == FOLLOWED_TARGET_HINT  # async mint site sets it too
    assert "请稍后重试" not in str(exc.value)


def test_presigned_url_chain_is_hop_limited(tmp_path: Path) -> None:
    # A self-referential {url} envelope must not recurse unbounded (RecursionError +
    # request storm from the public API); it fails with a bounded DownloadError.
    self_url = "https://cdn.test/loop"
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": self_url})
        )
        router.get(self_url).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"url": self_url}}
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(DownloadError, match="hop"),
        ):
            download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )


def test_same_origin_second_hop_keeps_authorization(tmp_path: Path) -> None:
    # A same-origin 302 -> target returns 200 + JSON {url: another same-origin URL}:
    # each hop re-decides exact-origin auth, so the SECOND same-origin hop must also
    # carry the bearer (it previously dropped it).
    seen: dict[str, str | None] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(302, headers={"location": "https://api.test/hop1"})
        )
        router.get("/hop1").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"url": "https://api.test/hop2"}},
            )
        )
        router.get("/hop2").mock(side_effect=capture)
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    assert seen["auth"] == "Bearer tok"  # 2nd same-origin hop kept the bearer
    assert path.read_bytes() == b"%PDF"


def test_check_deadline_raises_past_deadline() -> None:
    from gangtise_openapi._download import _check_deadline

    _check_deadline(None)  # no deadline -> no-op
    _check_deadline(time.monotonic() + 60)  # future -> no-op
    with pytest.raises(DownloadError, match="overall deadline"):
        _check_deadline(time.monotonic() - 1)


@pytest.mark.anyio
async def test_presigned_error_redacts_signature_from_message_async(tmp_path: Path) -> None:
    signed = "https://cdn.test/signed/report?X-Amz-Signature=SECRET"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"url": signed}},
                headers={"content-type": "application/json"},
            )
        )
        router.get(signed).mock(return_value=httpx.Response(403, text="denied"))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(DownloadError) as exc:
                await download_to_path_async(
                    client=client,
                    endpoint_key="insight.research.download",
                    query={"reportId": "r1"},
                    output=tmp_path / "out.pdf",
                    fallback_name="report-r1",
                )
    message = str(exc.value)
    assert "SECRET" not in message and "X-Amz" not in message
    assert "https://cdn.test/signed/report" in message


@pytest.mark.anyio
async def test_presigned_fetch_retries_network_error_async(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda error, attempt: 0.0)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        upstream = router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"url": "https://cdn.test/s/f"}},
                headers={"content-type": "application/json"},
            )
        )
        cdn = router.get("https://cdn.test/s/f").mock(
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.Response(
                    200, content=b"%PDF-cdn", headers={"content-type": "application/pdf"}
                ),
            ]
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            path = await download_to_path_async(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=tmp_path / "out.pdf",
                fallback_name="report-r1",
            )
    assert upstream.call_count == 1
    assert cdn.call_count == 2
    assert path.read_bytes() == b"%PDF-cdn"


@pytest.mark.anyio
async def test_concurrent_auto_named_downloads_keep_both_files_async(
    tmp_path: Path, monkeypatch
) -> None:
    # Async sibling of the sync race test: two output=None downloads resolving the
    # same fallback name must land as two files with intact contents.
    monkeypatch.chdir(tmp_path)
    results: list[Path] = []
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=[
                httpx.Response(200, content=b"AAA", headers={"content-type": "application/pdf"}),
                httpx.Response(200, content=b"BBB", headers={"content-type": "application/pdf"}),
            ]
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:

            async def run_one() -> None:
                results.append(
                    await download_to_path_async(
                        client=client,
                        endpoint_key="insight.research.download",
                        query={"reportId": "r1"},
                        output=None,
                        fallback_name="same-name",
                    )
                )

            async with anyio.create_task_group() as tg:
                tg.start_soon(run_one)
                tg.start_soon(run_one)
    assert len(results) == 2
    assert results[0] != results[1]
    assert sorted(p.read_bytes() for p in results) == [b"AAA", b"BBB"]
