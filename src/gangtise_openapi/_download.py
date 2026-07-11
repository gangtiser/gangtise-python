from __future__ import annotations

import errno
import json
import os
import re
import time
import uuid
from functools import partial
from pathlib import Path
from typing import NoReturn
from urllib.parse import unquote, urlsplit

import anyio
import httpx

from gangtise_openapi._auth import normalize_token
from gangtise_openapi._client import AUTH_RETRY_CODES, AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._endpoints import EndpointDef, lookup
from gangtise_openapi._errors import ApiError, DownloadError
from gangtise_openapi._transport import (
    _apply_policy_hint,
    _retry_delay,
    is_envelope,
    is_retryable_error,
    parse_retry_after_ms,
    unwrap_envelope,
)

# Matches request_json's default max_retries (see _transport.py).
_MAX_RETRIES = 2

_DISPOSITION_RE = re.compile(
    r"filename\*?\s*=\s*(?:(?:[^']*)''([^;]+)|\"?([^\";]+)\"?)",
    re.IGNORECASE,
)
_MIME_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
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
    raw = match.group(1) or match.group(2)
    return unquote(raw)


def _extension_for(content_type: str | None) -> str:
    if not content_type:
        return ""
    lower = content_type.split(";")[0].strip().lower()
    return _MIME_EXTENSIONS.get(lower, "")


def _redact_url(url: str) -> str:
    """Reduce a URL to ``scheme://host[:port]/path`` for error messages, dropping
    the query (signatures), fragment, and ``user:password@`` userinfo.

    Fail closed: anything that is not an absolute http(s) URL with a host and a
    valid port collapses to ``"redacted-url"`` rather than risk leaking. A bare
    ``alice:SECRET@host/p`` parses with scheme ``alice`` (not http/https) and an
    invalid port raises ``ValueError`` on ``parts.port`` — both are caught here
    so no secret can survive in a message."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            return "redacted-url"
        host = parts.hostname
        if not host:
            return "redacted-url"
        port = parts.port  # raises ValueError on a non-numeric / out-of-range port
        if ":" in host:
            # urlsplit strips the brackets from an IPv6 literal; re-add them.
            host = f"[{host}]"
        if port is not None:
            host = f"{host}:{port}"
        return f"{parts.scheme}://{host}{parts.path}"
    except ValueError:
        return "redacted-url"


def _require_fetchable_url(url: str) -> None:
    """Reject a would-be download URL that is not an absolute http(s) URL with a
    host and a valid port BEFORE handing it to httpx. ``httpx.InvalidURL`` (e.g.
    a bad port) is not an ``httpx.HTTPError``, so it would otherwise escape the
    fetch loop unwrapped and carry the raw (secret-bearing) URL in its message."""
    try:
        parts = urlsplit(url)
        ok = parts.scheme in ("http", "https") and bool(parts.hostname)
        if ok:
            parts.port  # raises ValueError on an invalid port  # noqa: B018
    except ValueError:
        ok = False
    if not ok:
        raise DownloadError(
            f"refusing to fetch a non-http(s) or malformed download URL ({_redact_url(url)})"
        )


TitleLookup = tuple[str, str, str]  # (list_endpoint_key, id_field, id_value)


_FORBIDDEN_FILENAME_CHARS = r'/\:*?"<>|'


def _sanitize_filename(name: str) -> str:
    table = {ord(c): "_" for c in _FORBIDDEN_FILENAME_CHARS}
    # Control chars + NUL (\x00-\x1f) too: a server-supplied name could otherwise
    # break the file write or smuggle terminal escapes (CLI v0.21.0 parity).
    table.update(dict.fromkeys(range(0x20), "_"))
    return name.translate(table).strip()


def _has_known_extension(name: str) -> bool:
    return Path(name).suffix.lower() in _KNOWN_EXTENSIONS


def _append_extension_if_needed(name: str, ext: str) -> str:
    if not ext or name.lower().endswith(ext.lower()) or _has_known_extension(name):
        return name
    return f"{name}{ext}"


def _truncate_filename(name: str, max_bytes: int = 200) -> str:
    if len(name.encode("utf8")) <= max_bytes:
        return name
    ext = Path(name).suffix
    stem = name[: -len(ext)] if ext else name
    while len(stem) > 1 and len(f"{stem}{ext}".encode()) > max_bytes:
        stem = stem[:-1]
    return f"{stem}{ext}"


def _suffixed(base: Path, i: int) -> Path:
    """`base` with ``-i`` before the extension: report.pdf → report-1.pdf."""
    ext = base.suffix
    stem = base.name[: -len(ext)] if ext else base.name
    return base.with_name(f"{stem}-{i}{ext}")


def _auto_target(name: str) -> Path:
    """The *desired* auto-derived path (cwd + sanitized name). Uniquification is
    deferred to `_claim_auto_named`, which reserves the name atomically — resolving
    it here (check-then-use) would both race and, on a later collision, suffix the
    already-suffixed name (report-1-1.pdf instead of report-2.pdf)."""
    return Path.cwd() / _truncate_filename(name)


def _raise_download_http_error(
    status_code: int, text: str, retry_after_ms: float | None = None
) -> NoReturn:
    """Raise the appropriate error for an HTTP >=400 download response.

    If the body is a business envelope, unwrap_envelope raises ApiError with
    the upstream code (and Chinese hint). Otherwise raise a generic ApiError
    carrying the status code so 429/5xx remain retryable (TS parity). A
    Retry-After from the response rides along so a rate-limited download
    honors the server's window instead of default backoff.
    """
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if is_envelope(parsed):
        # Raises ApiError with code/hint on business failure; an ok=True
        # envelope on a 4xx (unexpected) falls through to the generic error.
        try:
            unwrap_envelope(parsed, status_code=status_code)
        except ApiError as error:
            error.retry_after_ms = retry_after_ms
            raise
    raise ApiError(
        f"download failed: HTTP {status_code} {text[:200]}",
        status_code=status_code,
        details=parsed if parsed is not None else text[:500],
        retry_after_ms=retry_after_ms,
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
                if token == client._config.token:
                    client._env_token_rejected = True
                token = client._get_token(force_refresh=True, stale_token=token)
                continue
            # Download endpoints carry per-篇 billing too (summary / foreign-report /
            # my-conference at 50/篇) — honor the endpoint's retry policy here as well.
            if attempt >= _MAX_RETRIES or not is_retryable_error(error, endpoint.retry):
                _apply_policy_hint(endpoint, error)
                raise
            time.sleep(_retry_delay(error, attempt))
            attempt += 1
        except httpx.HTTPError as error:
            if attempt >= _MAX_RETRIES or not is_retryable_error(error, endpoint.retry):
                raise DownloadError(f"download failed: {error}") from error
            time.sleep(_retry_delay(error, attempt))
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
        # Do NOT auto-follow redirects here. A download endpoint may 3xx to a
        # presigned object-store URL, but if httpx followed inline, a failure on
        # the CDN hop would surface as a connect-phase error on THIS (billed,
        # possibly no-replay) request and trigger a replay of the billing
        # endpoint. Instead we read the Location and hand it to the signed-URL
        # fetcher, whose retry loop only ever replays the (unbilled) signed URL.
        # Deliberate divergence from TS client.ts, which follows inline and shares
        # this replay hazard.
        follow_redirects=False,
    ) as response:
        if 300 <= response.status_code < 400:
            return _follow_download_redirect(
                client=client,
                response=response,
                output=output,
                fallback_name=fallback_name,
                title_lookup=title_lookup,
            )
        if response.status_code >= 400:
            response.read()
            _raise_download_http_error(
                response.status_code,
                response.text,
                parse_retry_after_ms(response.headers.get("retry-after"), time.time()),
            )

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


# errnos meaning "this filesystem can't hard-link" (FAT, some network mounts,
# cross-device): fall back to the O_EXCL placeholder. Any OTHER OSError from
# os.link is a real failure and must propagate, not silently degrade.
_LINK_UNSUPPORTED_ERRNOS = frozenset(
    e
    for e in (
        getattr(errno, "EPERM", None),
        getattr(errno, "EXDEV", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOSYS", None),
        getattr(errno, "EACCES", None),
    )
    if e is not None
)


def _claim_auto_named(tmp: Path, desired: Path) -> Path:
    """Publish a completed auto-named download without ever overwriting another
    file, scanning suffixes ``-1..-99`` from the ORIGINAL ``desired`` name.

    Primary path — ``os.link``: hard-link the finished ``.part`` onto the target
    so the *complete* file appears in a single step (no 0-byte window); an
    existing name raises ``FileExistsError`` → try the next suffix. On a
    filesystem without hard-link support, fall back to an ``O_CREAT|O_EXCL``
    placeholder + ``replace`` — still atomic-claim and non-clobbering (it only
    replaces its OWN placeholder), at the cost of a brief 0-byte window. Explicit
    ``output=`` paths keep plain overwrite semantics and never come through here.
    """
    for i in range(0, 100):
        candidate = desired if i == 0 else _suffixed(desired, i)
        try:
            os.link(tmp, candidate)
        except FileExistsError:
            continue
        except OSError as exc:
            if exc.errno in _LINK_UNSUPPORTED_ERRNOS:
                return _claim_via_placeholder(tmp, desired)
            raise
        return candidate
    raise DownloadError(
        f"Refusing to overwrite: 100 files already share the name {desired.name!r} — "
        "pass output= or clean up the directory"
    )


def _claim_via_placeholder(tmp: Path, desired: Path) -> Path:
    """Hard-link-free fallback for `_claim_auto_named`: reserve the name with
    ``O_CREAT|O_EXCL`` (atomic, non-clobbering), then move the ``.part`` onto our
    own placeholder. A brief 0-byte window exists between reserve and move; it is
    accepted only on filesystems that cannot hard-link."""
    for i in range(0, 100):
        candidate = desired if i == 0 else _suffixed(desired, i)
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        os.close(fd)
        try:
            # Replacing our OWN just-reserved placeholder — never someone else's file.
            tmp.replace(candidate)
        except OSError:
            candidate.unlink(missing_ok=True)
            raise
        return candidate
    raise DownloadError(
        f"Refusing to overwrite: 100 files already share the name {desired.name!r} — "
        "pass output= or clean up the directory"
    )


def _check_deadline(deadline: float | None) -> None:
    """Overall transfer deadline for presigned-URL downloads. httpx read timeouts
    are idle-type — a stream trickling one byte per interval resets them forever;
    the generous total budget (10x the per-request timeout, TS v0.27.0) bounds the
    whole transfer without killing large legitimate downloads."""
    if deadline is not None and time.monotonic() > deadline:
        raise DownloadError(
            "download exceeded its overall deadline (10x request timeout); "
            "the connection is trickling — retry or raise GANGTISE_TIMEOUT_MS"
        )


def _write_response_to_disk(
    *,
    client: GangtiseClient,
    response: httpx.Response,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
    deadline: float | None = None,
) -> Path:
    content_disposition = response.headers.get("content-disposition")
    content_type = response.headers.get("content-type")
    target, auto_named = _decide_target(
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
                _check_deadline(deadline)
                fh.write(chunk)
        if auto_named:
            target = _claim_auto_named(tmp, target)
        else:
            tmp.replace(target)
    except OSError as exc:
        raise DownloadError(f"failed to write to {target}: {exc}") from exc
    finally:
        # No-op after a successful replace; cleans up the .part file when the
        # stream fails mid-flight (httpx errors are not OSError subclasses).
        tmp.unlink(missing_ok=True)
    return target


def _redirect_target(response: httpx.Response) -> str:
    """Resolve a download redirect's Location (absolute or relative) against the
    request URL. Raises DownloadError (no raw URL) when it is missing or unusable
    — never leaks a malformed Location into the message."""
    location = response.headers.get("location")
    if not location:
        raise DownloadError(
            f"download redirect (HTTP {response.status_code}) had no Location header"
        )
    try:
        return str(response.url.join(location))
    except (httpx.InvalidURL, ValueError) as exc:
        raise DownloadError(
            f"download redirect (HTTP {response.status_code}) had an unusable Location"
        ) from exc


def _follow_download_redirect(
    *,
    client: GangtiseClient,
    response: httpx.Response,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    """Route a 3xx download response to the signed-URL fetcher (safe to replay)."""
    target = _redirect_target(response)
    response.read()  # drain the redirect body before opening the next stream
    return _download_presigned_url(
        client=client,
        url=target,
        output=output,
        fallback_name=fallback_name,
        title_lookup=title_lookup,
    )


def _download_presigned_url(
    *,
    client: GangtiseClient,
    url: str,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    """Fetch the actual file bytes from a presigned object-store URL.

    Network-level failures retry with the default policy — replaying the SIGNED
    URL is always safe (no billing); the billed upstream endpoint is never
    re-requested on this path (TS ``downloadUrlTo`` parity). HTTP >= 400 raises
    ``DownloadError`` and is NOT retried: signed URLs expire, so replaying a 403
    is useless. Each attempt gets its own hard deadline (10x the request
    timeout) because the idle-type read timeouts reset on every byte.
    """
    _require_fetchable_url(url)
    http = client._http_client()
    attempt = 0
    while True:
        deadline = time.monotonic() + 10.0 * (client._config.timeout_ms / 1000.0)
        try:
            with http.stream("GET", url, follow_redirects=True) as response:
                if response.status_code >= 400:
                    raise DownloadError(
                        f"presigned URL fetch failed: HTTP {response.status_code} "
                        f"({_redact_url(url)})"
                    )
                return _write_response_to_disk(
                    client=client,
                    response=response,
                    output=output,
                    fallback_name=fallback_name,
                    title_lookup=title_lookup,
                    deadline=deadline,
                )
        except httpx.HTTPError as error:
            if attempt >= _MAX_RETRIES or not is_retryable_error(error):
                raise DownloadError(
                    f"presigned URL fetch failed: {error} ({_redact_url(url)})"
                ) from error
            time.sleep(_retry_delay(error, attempt))
            attempt += 1


def _decide_target(
    *,
    client: GangtiseClient,
    output: str | Path | None,
    fallback_name: str,
    content_disposition: str | None,
    content_type: str | None,
    title_lookup: TitleLookup | None,
) -> tuple[Path, bool]:
    """Resolve the on-disk target. Returns ``(path, auto_named)`` — auto-derived
    names commit via :func:`_link_claim` (no-overwrite), explicit ``output``
    keeps plain overwrite semantics."""
    if output is not None:
        return Path(output).expanduser(), False
    ext_from_mime = _extension_for(content_type)
    if title_lookup is not None:
        list_key, id_field, id_value = title_lookup
        title = client._resolve_title(list_key, id_field, id_value)
        if title:
            sanitized = _sanitize_filename(title)
            if sanitized:
                return _auto_target(_append_extension_if_needed(sanitized, ext_from_mime)), True
    disposition_name = _parse_content_disposition(content_disposition)
    if disposition_name:
        # Use only the basename and sanitize - prevent path traversal from the server.
        safe_name = _sanitize_filename(Path(disposition_name).name)
        if safe_name:
            return _auto_target(_append_extension_if_needed(safe_name, ext_from_mime)), True
    safe_fallback = _sanitize_filename(fallback_name) or "download"
    return _auto_target(_append_extension_if_needed(safe_fallback, ext_from_mime)), True


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
                if token == client._config.token:
                    client._env_token_rejected = True
                token = await client._get_token(force_refresh=True, stale_token=token)
                continue
            # Download endpoints carry per-篇 billing too (summary / foreign-report /
            # my-conference at 50/篇) — honor the endpoint's retry policy here as well.
            if attempt >= _MAX_RETRIES or not is_retryable_error(error, endpoint.retry):
                _apply_policy_hint(endpoint, error)
                raise
            await anyio.sleep(_retry_delay(error, attempt))
            attempt += 1
        except httpx.HTTPError as error:
            if attempt >= _MAX_RETRIES or not is_retryable_error(error, endpoint.retry):
                raise DownloadError(f"download failed: {error}") from error
            await anyio.sleep(_retry_delay(error, attempt))
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
        # See _download_once: upstream must not auto-follow, or a CDN-hop failure
        # would replay this (possibly no-replay, billed) request. Hand the Location
        # to the signed-URL fetcher instead.
        follow_redirects=False,
    ) as response:
        if 300 <= response.status_code < 400:
            return await _follow_download_redirect_async(
                client=client,
                response=response,
                output=output,
                fallback_name=fallback_name,
                title_lookup=title_lookup,
            )
        if response.status_code >= 400:
            await response.aread()
            _raise_download_http_error(
                response.status_code,
                response.text,
                parse_retry_after_ms(response.headers.get("retry-after"), time.time()),
            )

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
    deadline: float | None = None,
) -> Path:
    content_disposition = response.headers.get("content-disposition")
    content_type = response.headers.get("content-type")
    target, auto_named = await _decide_target_async(
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
                _check_deadline(deadline)
                await fh.write(chunk)
        if auto_named:
            target = await anyio.to_thread.run_sync(_claim_auto_named, tmp, target)
        else:
            await anyio.to_thread.run_sync(tmp.replace, target)
    except OSError as exc:
        raise DownloadError(f"failed to write to {target}: {exc}") from exc
    finally:
        # No-op after a successful replace; cleans up the .part file when the
        # stream fails mid-flight (httpx errors are not OSError subclasses).
        tmp.unlink(missing_ok=True)
    return target


async def _follow_download_redirect_async(
    *,
    client: AsyncGangtiseClient,
    response: httpx.Response,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    """Async mirror of `_follow_download_redirect`."""
    target = _redirect_target(response)
    await response.aread()  # drain the redirect body before opening the next stream
    return await _download_presigned_url_async(
        client=client,
        url=target,
        output=output,
        fallback_name=fallback_name,
        title_lookup=title_lookup,
    )


async def _download_presigned_url_async(
    *,
    client: AsyncGangtiseClient,
    url: str,
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None,
) -> Path:
    """Async mirror of `_download_presigned_url` (same retry / redaction / deadline
    contract)."""
    _require_fetchable_url(url)
    http = client._http_client()
    attempt = 0
    while True:
        deadline = time.monotonic() + 10.0 * (client._config.timeout_ms / 1000.0)
        try:
            async with http.stream("GET", url, follow_redirects=True) as response:
                if response.status_code >= 400:
                    raise DownloadError(
                        f"presigned URL fetch failed: HTTP {response.status_code} "
                        f"({_redact_url(url)})"
                    )
                return await _write_response_to_disk_async(
                    client=client,
                    response=response,
                    output=output,
                    fallback_name=fallback_name,
                    title_lookup=title_lookup,
                    deadline=deadline,
                )
        except httpx.HTTPError as error:
            if attempt >= _MAX_RETRIES or not is_retryable_error(error):
                raise DownloadError(
                    f"presigned URL fetch failed: {error} ({_redact_url(url)})"
                ) from error
            await anyio.sleep(_retry_delay(error, attempt))
            attempt += 1


async def _decide_target_async(
    *,
    client: AsyncGangtiseClient,
    output: str | Path | None,
    fallback_name: str,
    content_disposition: str | None,
    content_type: str | None,
    title_lookup: TitleLookup | None,
) -> tuple[Path, bool]:
    """Async mirror of `_decide_target` (same ``(path, auto_named)`` contract)."""
    if output is not None:
        return Path(output).expanduser(), False
    ext_from_mime = _extension_for(content_type)
    if title_lookup is not None:
        list_key, id_field, id_value = title_lookup
        title = await client._resolve_title(list_key, id_field, id_value)
        if title:
            sanitized = _sanitize_filename(title)
            if sanitized:
                return _auto_target(_append_extension_if_needed(sanitized, ext_from_mime)), True
    disposition_name = _parse_content_disposition(content_disposition)
    if disposition_name:
        # Use only the basename and sanitize - prevent path traversal from the server.
        safe_name = _sanitize_filename(Path(disposition_name).name)
        if safe_name:
            return _auto_target(_append_extension_if_needed(safe_name, ext_from_mime)), True
    safe_fallback = _sanitize_filename(fallback_name) or "download"
    return _auto_target(_append_extension_if_needed(safe_fallback, ext_from_mime)), True
