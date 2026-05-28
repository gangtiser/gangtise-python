from __future__ import annotations

import re
from pathlib import Path

from gangtise_openapi._auth import normalize_token
from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._endpoints import lookup
from gangtise_openapi._errors import DownloadError

_DISPOSITION_RE = re.compile(r"filename\*?=(?:UTF-8''([^;]+)|\"?([^\";]+)\"?)")


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
    return {
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "text/html": ".html",
        "application/octet-stream": "",
    }.get(lower, "")


TitleLookup = tuple[str, str, str]  # (list_endpoint_key, id_field, id_value)


_FORBIDDEN_FILENAME_CHARS = r'/\:*?"<>|'


def _sanitize_filename(name: str) -> str:
    table = {ord(c): "_" for c in _FORBIDDEN_FILENAME_CHARS}
    return name.translate(table).strip()


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
            raise DownloadError(
                f"download failed: HTTP {response.status_code} {response.text[:200]}"
            )
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
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
            tmp.replace(target)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise DownloadError(f"failed to write to {target}: {exc}") from exc
    return target


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
            if ext_from_mime and not sanitized.lower().endswith(ext_from_mime.lower()):
                sanitized += ext_from_mime
            return Path.cwd() / sanitized
    disposition_name = _parse_content_disposition(content_disposition)
    if disposition_name:
        return Path.cwd() / disposition_name
    return Path.cwd() / f"{fallback_name}{ext_from_mime}"
