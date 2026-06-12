from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from gangtise_openapi._errors import ConfigError


@dataclass(frozen=True)
class TokenCache:
    access_token: str
    expires_in: int
    time: int
    expires_at: int
    uid: int | None = None
    user_name: str | None = None
    tenant_id: int | None = None


_BUFFER_SECONDS = 300


def normalize_token(token: str) -> str:
    return token if token.startswith("Bearer ") else f"Bearer {token}"


def is_cache_valid(cache: TokenCache | None, buffer_seconds: int = _BUFFER_SECONDS) -> bool:
    if cache is None or not cache.access_token or not cache.expires_at:
        return False
    now = int(time.time())
    return (cache.expires_at - buffer_seconds) > now


def read_token_cache(path: Path) -> TokenCache | None:
    try:
        raw = path.read_text(encoding="utf8")
    except OSError:
        return None
    try:
        data: object = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    access_token = data.get("accessToken")
    expires_at = data.get("expiresAt")
    if not isinstance(access_token, str) or not isinstance(expires_at, int):
        return None
    expires_in_raw = data.get("expiresIn", 0)
    time_raw = data.get("time", 0)
    uid = data.get("uid")
    user_name = data.get("userName")
    tenant_id = data.get("tenantId")
    return TokenCache(
        access_token=access_token,
        expires_in=int(expires_in_raw) if isinstance(expires_in_raw, int) else 0,
        time=int(time_raw) if isinstance(time_raw, int) else 0,
        expires_at=expires_at,
        uid=uid if isinstance(uid, int) else None,
        user_name=user_name if isinstance(user_name, str) else None,
        tenant_id=tenant_id if isinstance(tenant_id, int) else None,
    )


def write_token_cache(path: Path, cache: TokenCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "accessToken": cache.access_token,
        "expiresIn": cache.expires_in,
        "time": cache.time,
        "expiresAt": cache.expires_at,
        "uid": cache.uid,
        "userName": cache.user_name,
        "tenantId": cache.tenant_id,
    }
    # Atomic write: temp file + rename to avoid partial reads. The tmp name
    # carries pid + timestamp so concurrent writers (token.json is shared with
    # the npm CLI and other processes) never clobber each other's temp file.
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{int(time.time() * 1000)}")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def require_credentials(access_key: str | None, secret_key: str | None) -> tuple[str, str]:
    if not access_key or not secret_key:
        raise ConfigError("Missing GANGTISE_ACCESS_KEY or GANGTISE_SECRET_KEY")
    return access_key, secret_key
