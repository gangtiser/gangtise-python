# ruff: noqa: RUF001, RUF002
# (RUF001/RUF002 disabled file-wide: docstrings and hints are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
"""`gangtise.tool.*` — 异步文件解析（PDF → Markdown + 图片）与联网搜索。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import anyio
import pandas as pd

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
from gangtise_openapi.domains._common import (
    _as_list,
    _refuse_empty,
    _request_body,
    _result_to_dataframe,
)

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
        terminal = ApiError(
            f"File parse failed (terminal {error.code}): {error.args[0]}. Re-checking "
            "this task_id will not change it; resubmitting bills the pages again.",
            code=error.code,
            status_code=error.status_code,
            details=error.details,
        )
        # The generic 410111 / 140002 hint names the AI generators' data_id.
        terminal.hint = (
            "终态失败，再查同一 task_id 不会变。文件有问题（损坏、加密、超页数）就换文件再提交；"
            "重新提交会按页再次计费。"
        )
        raise terminal from error


_WEB_SEARCH_FRESHNESS = ("day", "week", "month", "none")
_WEB_SEARCH_TIERS = ("T0", "T1", "T2", "T3")
_WEB_SEARCH_MAX_SITES = 10


def _web_search_body(
    *,
    query: str,
    size: int | None,
    freshness: str | None,
    min_tier: str | None,
    site: str | list[str] | None,
    include_content: bool,
    max_content_chars: int | None,
) -> dict[str, Any]:
    """Validate and build the tool.web-search body (TS v0.41.0 / v0.44.0).

    Every refusal here happens before the credit is spent. The size ceiling drops to
    5 with page bodies on, so the DEFAULT follows it: ``include_content=True`` alone
    must not fail on a size nobody passed, while an explicit size over 5 is refused
    naming the flag that lowered the cap. Sites are counted after de-duplication, as
    the server counts them."""
    effective = size if size is not None else (5 if include_content else 10)
    if not isinstance(effective, int) or isinstance(effective, bool) or not 1 <= effective <= 20:
        raise ValidationError(f"size must be an integer between 1 and 20 (got {effective!r})")
    if include_content and effective > 5:
        raise ValidationError(
            f"size {effective} with include_content=True: this endpoint caps size at 5 "
            "when page bodies are requested. Lower size, or drop include_content to "
            "fetch up to 20 snippets."
        )
    for name, value, allowed in (
        ("freshness", freshness, _WEB_SEARCH_FRESHNESS),
        ("min_tier", min_tier, _WEB_SEARCH_TIERS),
    ):
        if value is not None and value not in allowed:
            raise ValidationError(f"invalid {name}: {value!r} is not one of {'/'.join(allowed)}")
    # Trimmed, blanks dropped, de-duplicated — the cap counts distinct domains (TS).
    _refuse_empty(site, "site")
    sites = list(
        dict.fromkeys(
            s.strip() if isinstance(s, str) else s
            for s in _as_list(site, "site") or []
            if not (isinstance(s, str) and not s.strip())
        )
    )
    if len(sites) > _WEB_SEARCH_MAX_SITES:
        raise ValidationError(
            f"site takes at most {_WEB_SEARCH_MAX_SITES} distinct domains, got {len(sites)}"
        )
    if max_content_chars is not None and (
        not isinstance(max_content_chars, int)
        or isinstance(max_content_chars, bool)
        or not 1000 <= max_content_chars <= 20000
    ):
        raise ValidationError(
            f"max_content_chars must be an integer between 1000 and 20000 "
            f"(got {max_content_chars!r})"
        )
    return _request_body(
        {
            "query": query,
            "size": effective,
            "freshness": freshness,
            "minTier": min_tier,
            "siteList": sites or None,
            "includeContent": True if include_content else None,
            "maxContentChars": max_content_chars,
        }
    )


class Tool:
    """`gangtise.tool.*` — PDF 解析（异步任务）与联网搜索。"""

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

    def web_search(
        self,
        *,
        query: str,
        size: int | None = None,
        freshness: str | None = None,
        min_tier: str | None = None,
        site: str | list[str] | None = None,
        include_content: bool = False,
        max_content_chars: int | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """联网搜索（tool.web-search）：对公开互联网做投研定向检索。

        服务端已做转载去重、信源分级（T0–T3）、黑名单剔除与内容特征打标。

        query 必填，1–200 字符，**原样发送**——服务端不做意图推断或改写，要限定站点
        显式用 site。size 1–20，默认 10；include_content=True 时上限降为 5、省略 size
        默认也取 5（显式传大于 5 本地报错）。size 指去重与过滤之后的条数，不足不补。
        freshness 取值 day / week / month / none（默认不过滤）；min_tier 取值
        T0 / T1 / T2 / T3（T3 = 不过滤，低于该等级不返回）。site 为注册域或子域
        （如 csrc.gov.cn），支持单值或列表，最多 10 个（按去重后计），相互之间是「或」
        关系，子域按后缀匹配。include_content=True 返回网页正文 content（Markdown；
        个别页面取不到正文时为 null）；max_content_chars 1000–20000（默认 8000，仅
        include_content 时生效），超出截断并置 contentTruncated=True。

        ⚠️ **排序是「信源等级 tier 升序 → publishTime 降序 → 相关性」，首条不等于最相关**。
        publishTime 是规则判定的发布日期，判不出为 null（不表示网页没有日期）；freshness
        取 day / week / month 时 publishTime 为 null 的结果一并被滤掉。indexTime 是索引
        时间、不保证是发布时间，做时点判断用 publishTime。flags 特征标：rumor 传闻 /
        forward 转载稿 / disclaimer 含免责声明 / toutSuspect 疑似荐股 / paywall 付费墙。

        计费 **1 积分/次**，与返回条数、是否带正文无关；零结果与报错不扣。超时 / 5xx
        不自动重发。默认返回结果列表的 DataFrame；raw=True 返回
        {query, total, hints, list}——total=0 时 hints 给出放宽建议，要读 hints 用 raw=True。
        """
        body = _web_search_body(
            query=query,
            size=size,
            freshness=freshness,
            min_tier=min_tier,
            site=site,
            include_content=include_content,
            max_content_chars=max_content_chars,
        )
        result = self._client._call("tool.web-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

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

    async def web_search(
        self,
        *,
        query: str,
        size: int | None = None,
        freshness: str | None = None,
        min_tier: str | None = None,
        site: str | list[str] | None = None,
        include_content: bool = False,
        max_content_chars: int | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """联网搜索（tool.web-search）：对公开互联网做投研定向检索。

        服务端已做转载去重、信源分级（T0–T3）、黑名单剔除与内容特征打标。

        query 必填，1–200 字符，**原样发送**——服务端不做意图推断或改写，要限定站点
        显式用 site。size 1–20，默认 10；include_content=True 时上限降为 5、省略 size
        默认也取 5（显式传大于 5 本地报错）。size 指去重与过滤之后的条数，不足不补。
        freshness 取值 day / week / month / none（默认不过滤）；min_tier 取值
        T0 / T1 / T2 / T3（T3 = 不过滤，低于该等级不返回）。site 为注册域或子域
        （如 csrc.gov.cn），支持单值或列表，最多 10 个（按去重后计），相互之间是「或」
        关系，子域按后缀匹配。include_content=True 返回网页正文 content（Markdown；
        个别页面取不到正文时为 null）；max_content_chars 1000–20000（默认 8000，仅
        include_content 时生效），超出截断并置 contentTruncated=True。

        ⚠️ **排序是「信源等级 tier 升序 → publishTime 降序 → 相关性」，首条不等于最相关**。
        publishTime 是规则判定的发布日期，判不出为 null（不表示网页没有日期）；freshness
        取 day / week / month 时 publishTime 为 null 的结果一并被滤掉。indexTime 是索引
        时间、不保证是发布时间，做时点判断用 publishTime。flags 特征标：rumor 传闻 /
        forward 转载稿 / disclaimer 含免责声明 / toutSuspect 疑似荐股 / paywall 付费墙。

        计费 **1 积分/次**，与返回条数、是否带正文无关；零结果与报错不扣。超时 / 5xx
        不自动重发。默认返回结果列表的 DataFrame；raw=True 返回
        {query, total, hints, list}——total=0 时 hints 给出放宽建议，要读 hints 用 raw=True。
        """
        body = _web_search_body(
            query=query,
            size=size,
            freshness=freshness,
            min_tier=min_tier,
            site=site,
            include_content=include_content,
            max_content_chars=max_content_chars,
        )
        result = await self._client._call("tool.web-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def _fetch_result(self, task_id: str, output: str | Path | None) -> Path:
        return await download_to_path_async(
            client=self._client,
            endpoint_key="tool.file-parse.result",
            query={},
            body={"taskId": task_id},
            output=output,
            fallback_name=f"file-parse-{task_id}",
        )
