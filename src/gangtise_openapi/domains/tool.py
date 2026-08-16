# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
"""`gangtise.tool.*` — 异步文件解析（PDF → Markdown + 图片）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import anyio

from gangtise_openapi._async_content import (
    FAILED_CODES,
    PENDING_CODES,
    POLL_MAX_ATTEMPTS,
    next_delay_seconds,
)
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._download import download_to_path, download_to_path_async
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._logging import get_logger
from gangtise_openapi._transport import UploadFile, is_transient_error

logger = get_logger()

# Server-side upload cap (spec: <=100MB, <=500 pages). Checked locally so a doomed
# 100MB+ upload fails instantly instead of after a long transfer — and, since the
# job is billed at submit time, before anything can be charged.
FILE_PARSE_MAX_BYTES = 100 * 1024 * 1024


def _read_pdf(file: str | Path) -> UploadFile:
    """Validate and load the PDF. Billed at submit time (0.8 credits/page), so
    every reason to reject a file is checked before the request goes out."""
    path = Path(file).expanduser().resolve()
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ValidationError(f"file not found: {file}") from error
    if not path.is_file():
        raise ValidationError(f"not a file: {file}")
    if size == 0:
        raise ValidationError(f"file is empty: {file}")
    if size > FILE_PARSE_MAX_BYTES:
        raise ValidationError(
            f"file is {size / 1024 / 1024:.1f}MB — the parse API accepts at most 100MB"
        )
    if path.suffix.lower() != ".pdf":
        raise ValidationError(f"only PDF files are supported: {file}")
    return UploadFile(filename=path.name, data=path.read_bytes(), content_type="application/pdf")


def _task_id(result: Any) -> str:
    task_id = result.get("taskId") if isinstance(result, dict) else None
    if task_id is None or task_id == "":
        raise ApiError(
            "File parse task was accepted but the response carried no taskId — the "
            "submission is already billed, so report this with the trace id rather "
            "than resubmitting",
            details=result,
        )
    return str(task_id)


def _is_pending(error: BaseException) -> bool:
    """The server answers a not-yet-ready result with the generating code
    (140001, legacy 410110). Shared with the AI async endpoints so the
    "still generating" judgement lives in exactly one place."""
    return isinstance(error, ApiError) and error.code in PENDING_CODES


def _reraise_if_terminal(error: BaseException) -> None:
    if isinstance(error, ApiError) and error.code in FAILED_CODES:
        raise ApiError(
            f"File parse failed (terminal {error.code}): {error.args[0]}. Re-checking "
            "this task_id will not change it; resubmitting bills the pages again.",
            code=error.code,
            status_code=error.status_code,
            details=error.details,
        ) from error


class Tool:
    """`gangtise.tool.*` — PDF 解析（异步任务）。"""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def file_parse(self, *, file: str | Path) -> str:
        """提交 PDF 解析任务（tool.file-parse.submit），返回 task_id。

        **0.8 积分/页, 提交时一次性扣费**；取结果免费。上传前本地校验后缀 / 非空 /
        ≤100MB, 免得为一次注定失败的上传付出传输时间。该端点标 no-replay 且超时下限
        300 秒——100MB 上传不会被默认 30 秒超时掐断, 也不会因重放而重复扣费。

        拿到 task_id 后用 file_parse_check() 取结果 ZIP（含 file.md + images/）。
        """
        upload = _read_pdf(file)
        result = self._client._call("tool.file-parse.submit", body=upload)
        return _task_id(result)

    def file_parse_check(
        self,
        *,
        task_id: str,
        output: str | Path | None = None,
        wait: bool = False,
    ) -> Path:
        """取解析结果 ZIP（tool.file-parse.result），落盘并返回路径。

        免费。结果未就绪时服务端返回「生成中」码（140001 / 旧 410110）——
        wait=False（默认）直接抛 ApiError, wait=True 则按与 AI 异步接口相同的退避预算
        （约 316 秒, 覆盖官方约 3 分钟）轮询到就绪。ZIP 里是 file.md 与 images/。
        """
        if not wait:
            return self._fetch_result(task_id, output)
        for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
            try:
                return self._fetch_result(task_id, output)
            except Exception as error:
                _reraise_if_terminal(error)
                if not _is_pending(error):
                    # The task is already paid for: a blip must not void the wait.
                    # Transient errors consume the attempt, anything else (bad
                    # task_id, no permission) aborts.
                    if not is_transient_error(error):
                        raise
                    logger.warning(
                        "[gangtise] file-parse attempt %d/%d hit a transient error (%s); "
                        "continuing to wait",
                        attempt,
                        POLL_MAX_ATTEMPTS,
                        str(error)[:80],
                    )
            if attempt < POLL_MAX_ATTEMPTS:
                time.sleep(next_delay_seconds(attempt))
        raise ApiError(
            f"File parse result not ready after {POLL_MAX_ATTEMPTS} attempts; the task is "
            "still valid — re-check the same task_id later (fetching the result is free)",
            code=next(iter(sorted(PENDING_CODES))),
        )

    def _fetch_result(self, task_id: str, output: str | Path | None) -> Path:
        return download_to_path(
            client=self._client,
            endpoint_key="tool.file-parse.result",
            query={},
            body={"taskId": task_id},
            output=output,
            fallback_name=f"file-parse-{task_id}",
        )


class AsyncTool:
    """Async mirror of `Tool`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def file_parse(self, *, file: str | Path) -> str:
        """提交 PDF 解析任务（tool.file-parse.submit），返回 task_id。

        **0.8 积分/页, 提交时一次性扣费**；取结果免费。上传前本地校验后缀 / 非空 /
        ≤100MB, 免得为一次注定失败的上传付出传输时间。该端点标 no-replay 且超时下限
        300 秒——100MB 上传不会被默认 30 秒超时掐断, 也不会因重放而重复扣费。

        拿到 task_id 后用 file_parse_check() 取结果 ZIP（含 file.md + images/）。
        """
        upload = await anyio.to_thread.run_sync(_read_pdf, file)
        result = await self._client._call("tool.file-parse.submit", body=upload)
        return _task_id(result)

    async def file_parse_check(
        self,
        *,
        task_id: str,
        output: str | Path | None = None,
        wait: bool = False,
    ) -> Path:
        """取解析结果 ZIP（tool.file-parse.result），落盘并返回路径。

        免费。结果未就绪时服务端返回「生成中」码（140001 / 旧 410110）——
        wait=False（默认）直接抛 ApiError, wait=True 则按与 AI 异步接口相同的退避预算
        （约 316 秒, 覆盖官方约 3 分钟）轮询到就绪。ZIP 里是 file.md 与 images/。
        """
        if not wait:
            return await self._fetch_result(task_id, output)
        for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
            try:
                return await self._fetch_result(task_id, output)
            except Exception as error:
                _reraise_if_terminal(error)
                if not _is_pending(error):
                    if not is_transient_error(error):
                        raise
                    logger.warning(
                        "[gangtise] file-parse attempt %d/%d hit a transient error (%s); "
                        "continuing to wait",
                        attempt,
                        POLL_MAX_ATTEMPTS,
                        str(error)[:80],
                    )
            if attempt < POLL_MAX_ATTEMPTS:
                await anyio.sleep(next_delay_seconds(attempt))
        raise ApiError(
            f"File parse result not ready after {POLL_MAX_ATTEMPTS} attempts; the task is "
            "still valid — re-check the same task_id later (fetching the result is free)",
            code=next(iter(sorted(PENDING_CODES))),
        )

    async def _fetch_result(self, task_id: str, output: str | Path | None) -> Path:
        return await download_to_path_async(
            client=self._client,
            endpoint_key="tool.file-parse.result",
            query={},
            body={"taskId": task_id},
            output=output,
            fallback_name=f"file-parse-{task_id}",
        )
