from __future__ import annotations

import json
import re
import time
import uuid
from functools import partial
from pathlib import Path
from typing import NoReturn

import anyio
import httpx

from gangtise_openapi._auth import normalize_token
from gangtise_openapi._client import AUTH_RETRY_CODES, AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._endpoints import EndpointDef, lookup
from gangtise_openapi._errors import ApiError, DownloadError
from gangtise_openapi._transport import (
    _backoff_delay,
    is_envelope,
    is_retryable_error,
    unwrap_envelope,
)

# Matches request_json's default max_retries (see _transport.py).
_MAX_RETRIES = 2

_DISPOSITION_RE = re.compile(r"filename\*?=(?:UTF-8''([^;]+)|\"?([^\";]+)\"?)")
_MIME_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "audio/mpeg": ".mp3",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/octet-stream": "",
}
_KNOWN_EXTENSIONS = {ext for ext in _MIME_EXTENSIONS.values() if ext}


def _parse_content_disposition(header: str | None) -> str | None:
    if not header:
        return None
    match = _DISPOSITION_RE.search(header)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _extension_for(content_type: str | None) -> str:
    if not content_type:
        return ""
    lower = content_type.split(";")[0].strip().lower()
    return _MIME_EXTENSIONS.get(lower, "")


TitleLookup = tuple[str, str, str]  # (list_endpoint_key, id_field, id_value)


_FORBIDDEN_FILENAME_CHARS = r'/\:*?"<>|'


def _sanitize_filename(name: str) -> str:
    table = {ord(c): "_" for c in _FORBIDDEN_FILENAME_CHARS}
    return name.translate(table).strip()


def _has_known_extension(name: str) -> bool:
    return Path(name).suffix.lower() in _KNOWN_EXTENSIONS


def _append_extension_if_needed(name: str, ext: str) -> str:
    if not ext or name.lower().endswith(ext.lower()) or _has_known_extension(name):
        return name
    return f"{name}{ext}"


def _raise_download_http_error(status_code: int, text: str) -> NoReturn:
    """Raise the appropriate error for an HTTP >=400 download response.

    If the body is a business envelope, unwrap_envelope raises ApiError with
    the upstream code (and Chinese hint). Otherwise raise a generic ApiError
    carrying the status code so 429/5xx remain retryable (TS parity).
    """
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if is_envelope(parsed):
        # Raises ApiError with code/hint on business failure; an ok=True
        # envelope on a 4xx (unexpected) falls through to the generic error.
        unwrap_envelope(parsed, status_code=status_code)
    raise ApiError(
        f"download failed: HTTP {status_code} {text[:200]}",
        status_code=status_code,
        details=parsed if parsed is not None else text[:500],
    )


def download_to_path(
    *,
    client: GangtiseClient,
    endpoint_key: str,
    query: dict[str, str | int],
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None = None,
) -> Path:
    """Stream a download endpoint to disk.

    Retries transient failures (429/5xx, network errors, API code 999999) with
    the same policy as the JSON request path, and force-refreshes the token
    once on auth errors (8000014/8000015/0000001008). If the endpoint answers with a JSON
    envelope whose data carries a presigned `url`, that URL is fetched instead.

    Resolution order for the output filename when `output` is None:
      1. Title cache hit on `title_lookup` (if provided)
      2. List-endpoint fallback fetch - calls the list endpoint with
         `from=0, size=TITLE_LOOKUP_SIZE` and scans for `id_field == id_value`
      3. `Content-Disposition` filename
      4. `<fallback_name><ext-from-mime>`
    """
    endpoint = lookup(endpoint_key)
    if endpoint.kind != "download":
        raise DownloadError(f"endpoint {endpoint_key} is not a download endpoint")

    token = client._get_token()
    attempt = 0
    auth_retried = False
    while True:
        try:
            return _download_once(
                client=client,
                endpoint=endpoint,
                query=query,
                token=token,
                output=output,
                fallback_name=fallback_name,
                title_lookup=title_lookup,
            )
        except ApiError as error:
            if (
                not auth_retried
                and error.code in AUTH_RETRY_CODES
                and client._config.access_key
                and client._config.secret_key
            ):
                auth_retried = True
                token = client._get_token(force_refresh=True)
                continue
            if attempt >= _MAX_RETRIES or not is_retryable_error(error):
                raise
            time.sleep(_backoff_delay(attempt))
            attempt += 1
        except httpx.HTTPError as error:
            if attempt >= _MAX_RETRIES or not is_retryable_error(error):
                raise DownloadError(f"download failed: {error}") from error
            time.sleep(_backoff_delay(attempt))
            attempt += 1


def _download_once(
    *,
    client: GangtiseClient,
    endpoint: EndpointDef,
    query: dict[str, str | int],
    token: str,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    headers: dict[str, str] = {"Authorization": normalize_token(token)}

    http = client._http_client()
    with http.stream(
        endpoint.method,
        endpoint.path,
        params=query,
        headers=headers,
    ) as response:
        if response.status_code >= 400:
            response.read()
            _raise_download_http_error(response.status_code, response.text)

        # JSON 200 = envelope error, presigned-URL metadata, or non-file payload.
        content_type_header = response.headers.get("content-type", "")
        if "application/json" in content_type_header.lower():
            response.read()
            try:
                parsed = response.json()
            except ValueError as err:
                raise DownloadError(
                    f"download returned JSON content-type but body not parseable: "
                    f"{response.text[:200]}"
                ) from err
            # unwrap_envelope raises ApiError on business failure; non-envelope
            # payloads pass through unchanged (TS parity).
            data = unwrap_envelope(parsed, status_code=response.status_code)
            if isinstance(data, dict) and isinstance(data.get("url"), str):
                # Presigned-URL response: fetch the actual file from that URL.
                return _download_presigned_url(
                    client=client,
                    url=data["url"],
                    output=output,
                    fallback_name=fallback_name,
                    title_lookup=title_lookup,
                )
            raise DownloadError(
                f"download endpoint returned JSON, not a file: {response.text[:200]}"
            )

        return _write_response_to_disk(
            client=client,
            response=response,
            output=output,
            fallback_name=fallback_name,
            title_lookup=title_lookup,
        )


def _part_path(target: Path) -> Path:
    """Return a unique temp path for streaming ``target`` to disk.

    The random token is essential: two concurrent downloads that resolve to the
    same ``target`` must not share one ``.part`` file, or their byte streams
    interleave into one handle and each task's cleanup unlinks the other's file.
    Unlike the token / title caches (which guard cross-*process* writers with
    pid+timestamp), this race is in-process, so the suffix must be unique per call.
    """
    return target.with_suffix(target.suffix + f".part-{uuid.uuid4().hex}")


def _write_response_to_disk(
    *,
    client: GangtiseClient,
    response: httpx.Response,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    content_disposition = response.headers.get("content-disposition")
    content_type = response.headers.get("content-type")
    target = _decide_target(
        client=client,
        output=output,
        fallback_name=fallback_name,
        content_disposition=content_disposition,
        content_type=content_type,
        title_lookup=title_lookup,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = _part_path(target)
    try:
        with tmp.open("wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)
        tmp.replace(target)
    except OSError as exc:
        raise DownloadError(f"failed to write to {target}: {exc}") from exc
    finally:
        # No-op after a successful replace; cleans up the .part file when the
        # stream fails mid-flight (httpx errors are not OSError subclasses).
        tmp.unlink(missing_ok=True)
    return target


def _download_presigned_url(
    *,
    client: GangtiseClient,
    url: str,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    http = client._http_client()
    try:
        with http.stream("GET", url) as response:
            if response.status_code >= 400:
                raise DownloadError(
                    f"presigned URL fetch failed: HTTP {response.status_code} ({url})"
                )
            return _write_response_to_disk(
                client=client,
                response=response,
                output=output,
                fallback_name=fallback_name,
                title_lookup=title_lookup,
            )
    except httpx.HTTPError as error:
        raise DownloadError(f"presigned URL fetch failed: {error} ({url})") from error


def _decide_target(
    *,
    client: GangtiseClient,
    output: str | Path | None,
    fallback_name: str,
    content_disposition: str | None,
    content_type: str | None,
    title_lookup: TitleLookup | None,
) -> Path:
    if output is not None:
        return Path(output).expanduser()
    ext_from_mime = _extension_for(content_type)
    if title_lookup is not None:
        list_key, id_field, id_value = title_lookup
        title = client._resolve_title(list_key, id_field, id_value)
        if title:
            sanitized = _sanitize_filename(title)
            return Path.cwd() / _append_extension_if_needed(sanitized, ext_from_mime)
    disposition_name = _parse_content_disposition(content_disposition)
    if disposition_name:
        # Use only the basename and sanitize - prevent path traversal from the server.
        safe_name = _sanitize_filename(Path(disposition_name).name)
        if safe_name:
            return Path.cwd() / _append_extension_if_needed(safe_name, ext_from_mime)
    return Path.cwd() / f"{fallback_name}{ext_from_mime}"


async def download_to_path_async(
    *,
    client: AsyncGangtiseClient,
    endpoint_key: str,
    query: dict[str, str | int],
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None = None,
) -> Path:
    """Async counterpart to `download_to_path` — streams a download endpoint
    to disk using `httpx.AsyncClient`. Resolution rules match the sync version.
    """
    endpoint = lookup(endpoint_key)
    if endpoint.kind != "download":
        raise DownloadError(f"endpoint {endpoint_key} is not a download endpoint")

    token = await client._get_token()
    attempt = 0
    auth_retried = False
    while True:
        try:
            return await _download_once_async(
                client=client,
                endpoint=endpoint,
                query=query,
                token=token,
                output=output,
                fallback_name=fallback_name,
                title_lookup=title_lookup,
            )
        except ApiError as error:
            if (
                not auth_retried
                and error.code in AUTH_RETRY_CODES
                and client._config.access_key
                and client._config.secret_key
            ):
                auth_retried = True
                token = await client._get_token(force_refresh=True)
                continue
            if attempt >= _MAX_RETRIES or not is_retryable_error(error):
                raise
            await anyio.sleep(_backoff_delay(attempt))
            attempt += 1
        except httpx.HTTPError as error:
            if attempt >= _MAX_RETRIES or not is_retryable_error(error):
                raise DownloadError(f"download failed: {error}") from error
            await anyio.sleep(_backoff_delay(attempt))
            attempt += 1


async def _download_once_async(
    *,
    client: AsyncGangtiseClient,
    endpoint: EndpointDef,
    query: dict[str, str | int],
    token: str,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    headers: dict[str, str] = {"Authorization": normalize_token(token)}

    http = client._http_client()
    async with http.stream(
        endpoint.method,
        endpoint.path,
        params=query,
        headers=headers,
    ) as response:
        if response.status_code >= 400:
            await response.aread()
            _raise_download_http_error(response.status_code, response.text)

        # JSON 200 = envelope error, presigned-URL metadata, or non-file payload.
        content_type_header = response.headers.get("content-type", "")
        if "application/json" in content_type_header.lower():
            await response.aread()
            try:
                parsed = response.json()
            except ValueError as err:
                raise DownloadError(
                    f"download returned JSON content-type but body not parseable: "
                    f"{response.text[:200]}"
                ) from err
            # unwrap_envelope raises ApiError on business failure; non-envelope
            # payloads pass through unchanged (TS parity).
            data = unwrap_envelope(parsed, status_code=response.status_code)
            if isinstance(data, dict) and isinstance(data.get("url"), str):
                # Presigned-URL response: fetch the actual file from that URL.
                return await _download_presigned_url_async(
                    client=client,
                    url=data["url"],
                    output=output,
                    fallback_name=fallback_name,
                    title_lookup=title_lookup,
                )
            raise DownloadError(
                f"download endpoint returned JSON, not a file: {response.text[:200]}"
            )

        return await _write_response_to_disk_async(
            client=client,
            response=response,
            output=output,
            fallback_name=fallback_name,
            title_lookup=title_lookup,
        )


async def _write_response_to_disk_async(
    *,
    client: AsyncGangtiseClient,
    response: httpx.Response,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    content_disposition = response.headers.get("content-disposition")
    content_type = response.headers.get("content-type")
    target = await _decide_target_async(
        client=client,
        output=output,
        fallback_name=fallback_name,
        content_disposition=content_disposition,
        content_type=content_type,
        title_lookup=title_lookup,
    )
    await anyio.to_thread.run_sync(partial(target.parent.mkdir, parents=True, exist_ok=True))
    tmp = _part_path(target)
    try:
        async with await anyio.open_file(tmp, "wb") as fh:
            async for chunk in response.aiter_bytes():
                await fh.write(chunk)
        await anyio.to_thread.run_sync(tmp.replace, target)
    except OSError as exc:
        raise DownloadError(f"failed to write to {target}: {exc}") from exc
    finally:
        # No-op after a successful replace; cleans up the .part file when the
        # stream fails mid-flight (httpx errors are not OSError subclasses).
        await anyio.to_thread.run_sync(partial(tmp.unlink, missing_ok=True))
    return target


async def _download_presigned_url_async(
    *,
    client: AsyncGangtiseClient,
    url: str,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    http = client._http_client()
    try:
        async with http.stream("GET", url) as response:
            if response.status_code >= 400:
                raise DownloadError(
                    f"presigned URL fetch failed: HTTP {response.status_code} ({url})"
                )
            return await _write_response_to_disk_async(
                client=client,
                response=response,
                output=output,
                fallback_name=fallback_name,
                title_lookup=title_lookup,
            )
    except httpx.HTTPError as error:
        raise DownloadError(f"presigned URL fetch failed: {error} ({url})") from error


async def _decide_target_async(
    *,
    client: AsyncGangtiseClient,
    output: str | Path | None,
    fallback_name: str,
    content_disposition: str | None,
    content_type: str | None,
    title_lookup: TitleLookup | None,
) -> Path:
    if output is not None:
        return Path(output).expanduser()
    ext_from_mime = _extension_for(content_type)
    if title_lookup is not None:
        list_key, id_field, id_value = title_lookup
        title = await client._resolve_title(list_key, id_field, id_value)
        if title:
            sanitized = _sanitize_filename(title)
            return Path.cwd() / _append_extension_if_needed(sanitized, ext_from_mime)
    disposition_name = _parse_content_disposition(content_disposition)
    if disposition_name:
        # Use only the basename and sanitize - prevent path traversal from the server.
        safe_name = _sanitize_filename(Path(disposition_name).name)
        if safe_name:
            return Path.cwd() / _append_extension_if_needed(safe_name, ext_from_mime)
    return Path.cwd() / f"{fallback_name}{ext_from_mime}"
