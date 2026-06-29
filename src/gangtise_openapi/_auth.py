# ruff: noqa: RUF001
# (RUF001 disabled file-wide: require_credentials' message is user-facing
# Chinese text that intentionally uses fullwidth punctuation.)
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
    # Atomic write: create a fresh 0600 temp file, then rename over the target.
    # The temp must be 0600 *from the first byte* — writing then chmod-ing would
    # leave a brief window where the bearer token sits in a umask-default (often
    # 0644) world-readable file. os.open(..., 0o600) sets the mode at creation,
    # and O_EXCL refuses to follow a pre-existing file/symlink at the temp path.
    # rename is atomic and carries 0600 to the target, tightening any pre-existing
    # lax-permission token.json too (CLI v0.21.0 parity). The tmp name carries
    # pid + millis so concurrent writers (token.json is shared with the npm CLI
    # and other processes) never clobber each other's temp file.
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{int(time.time() * 1000)}")
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            f.write(json.dumps(payload, indent=2))
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def require_credentials(access_key: str | None, secret_key: str | None) -> tuple[str, str]:
    if not access_key or not secret_key:
        missing = ", ".join(
            name
            for name, present in (
                ("GANGTISE_ACCESS_KEY", access_key),
                ("GANGTISE_SECRET_KEY", secret_key),
            )
            if not present
        )
        raise ConfigError(
            f"缺少环境变量: {missing}（未导出到当前进程环境）\n"
            "注意：在 shell 里赋值还不够，必须导出（export），Python 进程才读得到：\n"
            "  bash/zsh:  export GANGTISE_ACCESS_KEY=... GANGTISE_SECRET_KEY=...\n"
            "  fish:      set -gx GANGTISE_ACCESS_KEY ...; set -gx GANGTISE_SECRET_KEY ...\n"
            "或在代码里显式传入：gangtise.configure(access_key=..., secret_key=...)\n"
            "验证：env | grep GANGTISE（能列出对应行才算导出成功）"
        )
    return access_key, secret_key
