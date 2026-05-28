# ruff: noqa: RUF001
# (RUF001 disabled file-wide: ERROR_HINTS values are user-facing Chinese
# strings that intentionally use fullwidth punctuation.)
from __future__ import annotations

from typing import Any

ERROR_HINTS: dict[str, str] = {
    "999999": "Gangtise 系统错误，请稍后重试。",
    "999997": "当前账号未开通该接口权限。",
    "999995": "当前账号积分不足。",
    "900002": "请求缺少 uid。",
    "900001": "请求参数为空或缺少必填项。",
    "8000014": "GANGTISE_ACCESS_KEY 错误。",
    "8000015": "GANGTISE_SECRET_KEY 错误。",
    "8000016": "开发账号状态异常。",
    "8000018": "开发账号已到期。",
    "903301": "今日调用次数已达上限。",
    "410110": "内容生成中，请稍后重试。",
    "410111": "内容生成失败，请勿重试。",
}


class GangtiseError(Exception):
    """Base class for all gangtise-openapi exceptions."""


class ConfigError(GangtiseError):
    """Missing or invalid configuration (env vars, cache file)."""


class ValidationError(GangtiseError):
    """Local argument validation failed before the request was issued."""


class DownloadError(GangtiseError):
    """Filesystem error while streaming a download."""


class ApiError(GangtiseError):
    """HTTP 4xx/5xx or business-envelope failure."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details
        self.hint: str | None = ERROR_HINTS.get(code) if code else None

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} — {self.hint}" if self.hint else base
