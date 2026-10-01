# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._download import download_to_path, download_to_path_async
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _as_named_list,
    _extract_rows,
    _request_body,
    _result_to_dataframe,
    _snake,
    _to_end_timestamp13,
    _to_timestamp13,
    _validate_choices,
    _validate_top,
)

# Enum whitelists. Only applied where the server was probed NOT to reject a bad
# value — it silently drops the condition and answers with the UNFILTERED set, so
# a typo masquerades as "these are the results" while billing for the full dump
# (TS v0.32.0).
_PAMIRS_CATEGORIES = ("companyAnalysis", "industryAnalysis")
_PAMIRS_MARKETS = ("aShares", "hkStocks", "usChinaConcept", "usStocks")
_PERFORMANCE_MARKETS = ("aShares", "hkStocks", "usChinaConcept", "usStocks")
_PERFORMANCE_CATEGORIES = (
    "performanceForecast",
    "performanceExpress",
    "performanceAnnouncement",
)

# Row ceiling applied when ``security`` is the only thing bounding a
# performance-calendar fetch. Far above any single company's calendar (a whole
# A-share history is dozens of rows), far below the 50k that auto-pagination would
# otherwise pull if the server ever stopped honouring securityList.
_SECURITY_ONLY_ROW_CAP = 1000


def _flag_implicit_cap_hit(data: Any, cap: int, from_: int) -> None:
    """Mark and announce a ``security``-only fetch that landed on the implicit cap
    with rows still unfetched.

    That is the signature of a filter that did not narrow anything: the rows on
    screen are then a truncated slice of the WHOLE calendar rather than one
    company's. ``total`` decides it — a result that happens to be exactly ``cap``
    rows long IS complete (``from + rows`` covers ``total``) and must not be
    flagged, or every automated caller reads a full answer as truncated.
    """
    if not isinstance(data, dict):
        return
    rows = data.get("list")
    if not isinstance(rows, list) or len(rows) < cap:
        return
    total = data.get("total")
    if isinstance(total, int) and from_ + len(rows) >= total:
        return
    data["partial"] = True
    warnings.warn(
        f"security was the only bound, so the fetch was capped at {cap} rows and more "
        f"remain (total={total}) — the filter may not have narrowed anything. Re-run "
        "with start_date/end_date or an explicit size.",
        stacklevel=3,
    )


# Opinion IDs per detail request: the endpoint's own ceiling, declared on both detail
# endpoints in the registry as ``billing.max_units``.
_DETAIL_BATCH = 20


class _OpinionDetails:
    """Batching and reconciliation for the two opinion detail endpoints (TS v0.41.0
    ``fetchOpinionDetails``; v0.43.1 per-element handling).

    Each endpoint takes at most 20 IDs per call and skips, WITHOUT an error, any ID it
    has no body for — a typo, an ID outside the account's data window, and possibly one
    published minutes ago. Batches go out one at a time (30 credits per returned body),
    and whatever did not come back is named in the result instead of silently absent.
    The sync and async wrappers drive the same object, so the rules live in one place.
    """

    def __init__(self, endpoint_key: str, id_list_field: str, id_field: str, ids: Any) -> None:
        self.endpoint_key = endpoint_key
        self.id_list_field = id_list_field
        self.id_field = id_field
        self.unique: list[Any] = list(dict.fromkeys(_as_list(ids, _snake(id_field)) or []))
        if not self.unique:
            raise ValidationError(f"{_snake(id_field)}: pass at least one opinion ID")
        self.rows: list[dict[str, Any]] = []
        self.unfetched: list[Any] = []
        self.unfetched_error: dict[str, Any] | None = None
        self.nulls = 0

    def batches(self) -> list[tuple[int, dict[str, Any]]]:
        return [
            (start, {self.id_list_field: self.unique[start : start + _DETAIL_BATCH]})
            for start in range(0, len(self.unique), _DETAIL_BATCH)
        ]

    def take(self, rows: list[Any]) -> None:
        """Keep one batch's bodies.

        An array by contract: both endpoints declare ``expects="array"``, so the
        transport has already refused any other layout — structurally, with its
        traceId — instead of letting a changed layout read as "no bodies" and report
        every paid-for ID as missing. That check does not look inside. Plain objects
        are bodies, paid for, and are kept whatever else the batch holds. A ``null``
        element reads as "no body": the reconciliation names its ID as missing. Any
        other element means the layout changed: the batch fails structurally AFTER its
        bodies are kept, the response riding on the error for its traceId.
        """
        bodies = [row for row in rows if isinstance(row, dict)]
        odd = sum(1 for row in rows if row is not None and not isinstance(row, dict))
        self.rows.extend(bodies)
        if odd:
            # ``ApiError.trace_id`` reads a dict ``details`` only, so the rows go under
            # ``data`` beside whatever envelope traceId the payload carries.
            error = ApiError(
                f"{self.endpoint_key} returned {odd} non-object element(s) in its body "
                "list — the response layout may have changed",
                details={"data": rows, "traceId": getattr(rows, "envelope_trace_id", None)},
            )
            error.structural = True
            raise error
        self.nulls += len(rows) - len(bodies)

    def fail(self, start: int, error: Exception) -> None:
        """A batch failed. With nothing delivered yet there is nothing to keep, so the
        error propagates as is. Otherwise the bodies already returned are paid for:
        keep them, and put what was not fetched (and why) in the result itself, so a
        script can re-run exactly those IDs."""
        if start == 0 and not self.rows:
            raise error
        kept = {str(row.get(self.id_field)) for row in self.rows}
        self.unfetched = [i for i in self.unique[start:] if str(i) not in kept]
        message = str(error.args[0]) if error.args else repr(error)
        self.unfetched_error = {"message": message}
        if isinstance(error, ApiError):
            self.unfetched_error.update(code=error.code, traceId=error.trace_id)
        batch_no = start // _DETAIL_BATCH + 1
        if self.unfetched:
            warnings.warn(
                f"{self.endpoint_key} failed on batch {batch_no} ({message}); "
                f"{len(self.unfetched)} ID(s) not fetched: "
                f"{', '.join(map(str, self.unfetched))}. The bodies already returned are "
                "kept — re-run for the IDs in unfetchedIds only.",
                UserWarning,
                stacklevel=4,
            )
        else:
            warnings.warn(
                f"{message} (batch {batch_no}); every ID in it came back with a body.",
                UserWarning,
                stacklevel=4,
            )

    def result(self) -> dict[str, Any]:
        returned = {str(row.get(self.id_field)) for row in self.rows}
        unfetched = {str(i) for i in self.unfetched}
        missing = [i for i in self.unique if str(i) not in returned and str(i) not in unfetched]
        out: dict[str, Any] = {"total": len(self.rows), "list": self.rows}
        if missing:
            nulls = f" ({self.nulls} came back as a null element)" if self.nulls else ""
            warnings.warn(
                f"no body returned for {len(missing)} ID(s): {', '.join(map(str, missing))}"
                f"{nulls} — the server gives no error for an ID it has no body for (e.g. a "
                "wrong ID; a just-published opinion may also not have its body yet). "
                "Result marked partial.",
                UserWarning,
                stacklevel=4,
            )
            out["missingIds"] = missing
        if self.unfetched:
            out["unfetchedIds"] = self.unfetched
            out["unfetchedError"] = self.unfetched_error
        if missing or self.unfetched:
            out["partial"] = True
        return out


# The title-lookup fallback fetches TITLE_LOOKUP_SIZE (200) list rows; this list bills
# 5 credits/row, so one friendly filename would cost 1000 credits — exactly AT the
# 1000-credit guard, so the guard would not stop it. The CLI never wired a title list
# for this download; the SDK refuses the flag instead of silently paying.
_INDEPENDENT_OPINION_NO_TITLE_LOOKUP = (
    "independent_opinion_download does not support resolve_title=True: the lookup "
    "reads 200 rows of insight.independent-opinion.list at 5 credits/row (1000 credits) "
    "for one filename. Call independent_opinion_list() first — its titles are cached "
    "and the download picks them up for free."
)


class Insight:
    """`gangtise.insight.*` — research / report / announcement endpoints."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    # ---- opinion ----

    def opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        research_area: FilterValue | None = None,
        chief: FilterValue | None = None,
        security: FilterValue | None = None,
        broker: FilterValue | None = None,
        industry: FilterValue | None = None,
        concept: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        source: FilterValue | None = None,
        with_content: bool = False,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询国内机构首席观点列表（insight.opinion.list；with_content=True 时
        insight.opinion.list-with-content）。

        🔴 **默认列表只含摘要**：brief 是正文前 200 字的截断，**1 积分/条**。要正文用
        opinion_detail(chief_opinion_id=...) 按 chiefOpinionId 取（content，30 积分/条），
        或 with_content=True 让列表直接带正文（旧版 v1 列表，**30 积分/条**，超时 / 5xx
        不自动重发）。只需判断相关性、做筛选时看 brief 就够，别默认开 with_content。

        ⚠️ with_content=True 返回的是**旧版结构**：标题与正文在 contentList.title /
        contentList.content（contentList 是对象，不是数组；DataFrame 里是一列
        contentList），顶层没有 title / brief；要统一成 opinion_detail 的结构就走
        list + detail。

        行字段（默认）：chiefOpinionId / publishTime / title / brief / author{chiefId,
        chiefName, researchAreaList, brokerID, brokerName} / securityList / industryList /
        conceptList / llmTagList；author.chiefId / chiefName 在机构点评类观点上为 null。

        llm_tag 取值 strongRcmd=强烈推荐 / earningsReview=业绩点评 / topBroker=头部券商 /
        newFortune=新财富团队；source 取值 realTime=实时 / openSource=开放来源。
        industry 用 citicIndustry 码（1008001xx）；申万码（104xx0000）也生效，但两套码的
        行业成分不同、取回的结果集不一致，同一批查询别混用。research_area 行业用
        citicIndustry 码、方向用 gangtiseIndustry 码（122000xxx），申万码在本端点返 0。

        计费见上（按返回条数计）。
        省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分
        拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "researchAreaList": _as_list(research_area, "research_area"),
                "chiefList": _as_list(chief, "chief"),
                "securityList": _as_list(security, "security"),
                "brokerList": _as_list(broker, "broker"),
                "industryList": _as_list(industry, "industry"),
                "conceptList": _as_list(concept, "concept"),
                "llmTagList": _as_list(llm_tag, "llm_tag"),
                "sourceList": _as_list(source, "source"),
            }
        )
        result = self._client._call(
            "insight.opinion.list-with-content" if with_content else "insight.opinion.list",
            body=body,
            confirm=confirm,
        )
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- summary ----

    def summary_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        source: FilterValue | None = None,
        research_area: FilterValue | None = None,
        security: FilterValue | None = None,
        institution: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        participant_role: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询纪要列表（insight.summary.list）。

        market 取值 aShares / hkStocks / usStocks / usChinaConcept（交易所后缀如 SH/SZ 会被拒为 100005）。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "sourceList": _as_list(source, "source"),
                "researchAreaList": _as_list(research_area, "research_area"),
                "securityList": _as_list(security, "security"),
                "institutionList": _as_list(institution, "institution"),
                "categoryList": _as_list(category, "category"),
                "marketList": _as_list(market, "market"),
                "participantRoleList": _as_list(participant_role, "participant_role"),
            }
        )
        result = self._client._call("insight.summary.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.summary.list",
            id_field="summaryId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def pamirs_summary_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        research_area: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询帕米尔专家纪要列表（insight.pamirs-summary.list）。

        这是一个**独立的专家纪要库**, 不是 summary_list 的筛选项, 需单独购买专家纪要数据库
        （未开通报 999004）, 且不受历史数据范围限制。

        筛选项是 summary_list 的真子集: 只有 search_type / rank_type / keyword /
        research_area / security / category / market——**没有** source / institution /
        participant_role。故意不复用 summary_list 的 body: 服务端会静默丢弃不认识的字段,
        照搬会让调用方以为过滤生效、实际拿到全量。

        category 取值 companyAnalysis / industryAnalysis; market 取值
        aShares / hkStocks / usChinaConcept / usStocks——两者都本地校验, 因为服务端对非法
        枚举是静默忽略该条件返回全量。research_area 中信码（1008001xx）与申万码
        （104xx0000）都认, 但方向码（122000xxx）在本端点返 0。

        ⚠️ 已知返回口径（实测 2026-08-08）: conceptList 在所有查法下都是空的（当前拿不到
        主题概念标签, 也没有 concept 过滤参数）; categoryList / marketList 只在用 category 或
        market 过滤时才回填——所以按这两个维度分组要靠过滤参数取, 别拉全量再本地分组。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "researchAreaList": _as_list(research_area, "research_area"),
                "securityList": _as_list(security, "security"),
                "categoryList": _validate_choices(
                    category, name="category", allowed=_PAMIRS_CATEGORIES
                ),
                "marketList": _validate_choices(market, name="market", allowed=_PAMIRS_MARKETS),
            }
        )
        result = self._client._call("insight.pamirs-summary.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.pamirs-summary.list",
            id_field="summaryId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def performance_calendar_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        security: FilterValue | None = None,
        market: FilterValue | None = None,
        category: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询财报日历（insight.performance-calendar.list）: 业绩预告 / 快报 / 公告。

        它是唯一按 **start_date / end_date**（yyyy-MM-dd, 过滤 publishDate）筛选的 insight
        列表, 其余用 start_time; 也没有 keyword / rank_type / search_type。
        market 取值 aShares / hkStocks / usChinaConcept / usStocks;
        category 取值 performanceForecast / performanceExpress / performanceAnnouncement——
        两者本地白名单校验, 拼错直接报错（服务端对错枚举是静默返全量, 按 0.1 积分/条计费）。

        ⚠️ 本接口数据量很大（含未来排期）, 省略 size 等于按分页上限拉满
        （1000 页 × 50 = 5 万条, 按 0.1 积分/条约 5000 积分）, 因此**至少要给一个约束**:
        完整日期区间 / security / 显式 size, 否则本地报错且不发请求。只给 security 时另加 1000 行隐式上限——
        撞上上限且仍有剩余会标 partial 并 warning。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        market_list = _validate_choices(market, name="market", allowed=_PERFORMANCE_MARKETS)
        category_list = _validate_choices(
            category, name="category", allowed=_PERFORMANCE_CATEGORIES
        )
        securities = _as_list(security, "security")
        explicitly_bounded = size is not None or bool(start_date and end_date)
        if not explicitly_bounded and not securities:
            raise ValidationError(
                "performance_calendar_list without a bound would auto-paginate the whole "
                "calendar — up to 50k rows at 0.1 credits each: pass start_date and "
                "end_date, or security, or an explicit size"
            )
        # `security` is only a real bound while the server honours securityList. It
        # does today (probed 2026-07-25: an unknown code returns total 0, it is not
        # silently ignored like a bad enum) — but a five-figure credit bill must not
        # rest on that staying true. One company's whole calendar is dozens of rows,
        # so the cap is invisible in normal use and turns a filter regression into a
        # truncated result instead of a 5000-credit pull.
        implicit_cap = None if explicitly_bounded else _SECURITY_ONLY_ROW_CAP
        body = _request_body(
            {
                "from": from_,
                "size": size if size is not None else implicit_cap,
                "startDate": start_date,
                "endDate": end_date,
                "marketList": market_list,
                "securityList": securities,
                "categoryList": category_list,
            }
        )
        result = self._client._call("insight.performance-calendar.list", body=body, confirm=confirm)
        if implicit_cap is not None:
            _flag_implicit_cap_hit(result, implicit_cap, from_)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.performance-calendar.list",
            id_field="performanceReportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- schedule (roadshow / site-visit / strategy / forum) ----
    #
    # v0.17.0 of the TS CLI tightened these four endpoints: each one accepts a
    # different subset of filters per the API spec, and the server silently
    # returned empty rows when given a field it doesn't recognise. The Python
    # SDK now mirrors the per-endpoint signatures exactly — unsupported kwargs
    # are removed rather than silently dropped, so callers get TypeError on
    # bad usage instead of empty DataFrames.

    def roadshow_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        institution: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        participant_role: FilterValue | None = None,
        broker_type: FilterValue | None = None,
        permission: FilterValue | None = None,
        location: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询路演日程列表（insight.roadshow.list）。

        category 路演类型取值 earningsCall（业绩会）/ strategyMeeting（策略会）/
        companyAnalysis（公司分析）/ industryAnalysis（行业分析）/ fundRoadshow
        （基金路演）；market 取值 aShares / hkStocks / usChinaConcept / usStocks；
        participant_role 取值 management / expert；broker_type 取值
        cnBroker / otherBroker；permission 取值 1=公开 / 2=私密；
        research_area 用 gangtiseIndustry 码（reference.constant_list 查询）；
        location 用 domesticCity 码。

        ⚠️ **`location` 目前不可用**：任何取值服务端都返回 `999999 系统内部错误`（四个日程类接口一致，2026-09-07 实测）。

        计费 **20 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area, "research_area"),
                "institutionList": _as_list(institution, "institution"),
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
                "marketList": _as_list(market, "market"),
                "participantRoleList": _as_list(participant_role, "participant_role"),
                "brokerTypeList": _as_list(broker_type, "broker_type"),
                "permission": _as_list(permission, "permission"),
                "locationList": _as_list(location, "location"),
            }
        )
        result = self._client._call("insight.roadshow.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def site_visit_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        institution: FilterValue | None = None,
        security: FilterValue | None = None,
        object_: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        permission: FilterValue | None = None,
        location: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询调研/实地走访日程列表（insight.site-visit.list）。

        object_ 取值 company / industry（请求字段 object）；category 调研形式取值
        single（单场）/ series（系列）；market 取值 aShares / hkStocks /
        usChinaConcept（site-visit 无 usStocks）；permission 取值 1=公开 / 2=私密；
        research_area 用 gangtiseIndustry 码；location 用 domesticCity 码。

        ⚠️ **`location` 目前不可用**：任何取值服务端都返回 `999999 系统内部错误`（四个日程类接口一致，2026-09-07 实测）。

        计费 **20 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area, "research_area"),
                "institutionList": _as_list(institution, "institution"),
                "securityList": _as_list(security, "security"),
                "objectList": _as_named_list(object_, "object_"),
                "categoryList": _as_list(category, "category"),
                "marketList": _as_list(market, "market"),
                "permission": _as_list(permission, "permission"),
                "locationList": _as_list(location, "location"),
            }
        )
        result = self._client._call("insight.site-visit.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def strategy_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        institution: FilterValue | None = None,
        location: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询线下策略会日程列表（insight.strategy.list）。

        服务端仅按 institution（主办机构 ID）和 location（domesticCity 城市/省份 ID）
        筛选，无 research_area / security / category 等。

        ⚠️ **`location` 目前不可用**：任何取值服务端都返回 `999999 系统内部错误`（四个日程类接口一致，2026-09-07 实测）。

        计费 **20 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "institutionList": _as_list(institution, "institution"),
                "locationList": _as_list(location, "location"),
            }
        )
        result = self._client._call("insight.strategy.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def forum_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        location: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询论坛/电话会日程列表（insight.forum.list）。

        服务端仅按 research_area（gangtiseIndustry 码）和 location（domesticCity 码）
        筛选，无 institution / security / category 等。

        ⚠️ **`location` 目前不可用**：任何取值服务端都返回 `999999 系统内部错误`（四个日程类接口一致，2026-09-07 实测）。

        计费 **20 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area, "research_area"),
                "locationList": _as_list(location, "location"),
            }
        )
        result = self._client._call("insight.forum.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- research ----

    def research_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        broker: FilterValue | None = None,
        security: FilterValue | None = None,
        industry: FilterValue | None = None,
        category: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        source: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询国内券商研报列表（insight.research.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "brokerList": _as_list(broker, "broker"),
                "securityList": _as_list(security, "security"),
                "industryList": _as_list(industry, "industry"),
                "categoryList": _as_list(category, "category"),
                "llmTagList": _as_list(llm_tag, "llm_tag"),
                "ratingList": _as_list(rating, "rating"),
                "ratingChangeList": _as_list(rating_change, "rating_change"),
                "minReportPages": min_pages,
                "maxReportPages": max_pages,
                "sourceList": _as_list(source, "source"),
            }
        )
        result = self._client._call("insight.research.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.research.list",
            id_field="reportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- foreign-report ----

    def foreign_report_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        region: FilterValue | None = None,
        category: FilterValue | None = None,
        industry: FilterValue | None = None,
        broker: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外研报列表（insight.foreign-report.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security, "security"),
                "regionList": _as_list(region, "region"),
                "categoryList": _as_list(category, "category"),
                "industryList": _as_list(industry, "industry"),
                "brokerList": _as_list(broker, "broker"),
                "llmTagList": _as_list(llm_tag, "llm_tag"),
                "ratingList": _as_list(rating, "rating"),
                "ratingChangeList": _as_list(rating_change, "rating_change"),
                "minReportPages": min_pages,
                "maxReportPages": max_pages,
            }
        )
        result = self._client._call("insight.foreign-report.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.foreign-report.list",
            id_field="reportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- announcement (A-share, 13-digit ms timestamps) ----

    def announcement_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: int | str | None = None,
        end_time: int | str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股公告列表（insight.announcement.list）。

        start_time/end_time 接受日期字符串或 10/13 位时间戳，按**北京时间**换算成 13 位毫秒发出
        （与运行机器的时区无关；10 位按秒换算）。**end_time 只写日期时按当日 23:59:59 换算**，
        所以 start_time 与 end_time 写同一天就是查这一整天。
        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        category 公告分类 ID，用 reference.constant_list(category="aShareAnnouncementCategory")
        查询；常用 103910200 财务报告 / 103910201 业绩预告 / 103910700 股权股本 等。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": _to_timestamp13(start_time, "start_time"),
                "endTime": _to_end_timestamp13(end_time, "end_time"),
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
            }
        )
        result = self._client._call("insight.announcement.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.announcement.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- announcement-hk (plain string timestamps) ----

    def announcement_hk_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股公告列表（insight.announcement-hk.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        category 港股公告分类 ID，用 reference.constant_list(category="hkShareAnnouncementCategory")
        查询。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
            }
        )
        result = self._client._call("insight.announcement-hk.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.announcement-hk.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- announcement-us (plain string timestamps) ----

    def announcement_us_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股公告列表（insight.announcement-us.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        security 传美股代码如 TSLA.O；category 美股公告分类 ID，用
        reference.constant_list(category="usShareAnnouncementCategory") 查询。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
            }
        )
        result = self._client._call("insight.announcement-us.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.announcement-us.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- foreign-opinion ----

    def foreign_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: FilterValue | None = None,
        region: FilterValue | None = None,
        industry: FilterValue | None = None,
        broker: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        with_content: bool = False,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外机构观点列表（insight.foreign-opinion.list；with_content=True 时
        insight.foreign-opinion.list-with-content）。

        🔴 **默认列表只含摘要**：brief（英文）/ briefTranslate（中文），取正文前 200 字，
        **1 积分/条**。原文与译文（content / contentTranslate）用
        foreign_opinion_detail(foreign_opinion_id=...) 按 foreignOpinionId 取（30 积分/条），
        或 with_content=True（旧版 v1 列表，**30 积分/条**，content / contentTranslate
        直接在顶层、不含 brief；超时 / 5xx 不自动重发）。

        行字段（默认）：foreignOpinionId / title / titleTranslate / brief / briefTranslate /
        publishTime / publisher{brokerId, brokerName} / securityList[]{securityCode,
        securityName, rating, ratingChange, targetPrice, currency} / industryList[] /
        region{regionCode, regionName}。

        rank_type 取值 1=综合 2=时间倒序。
        region 本接口只收 cn/cnHk/cnTw/us/jp/uk；regionCategory 的另外 13 个取值
        （sea/gl/fr/de/kr/in/ca/me/othAs/othEur/latAm/oce/af）在这里报 100005，
        尽管它们在 foreign_report_list 上都可用。
        industry 只收申万码（104xx0000）；中信码报 100005，即使 constant-category 里列了它。
        返回记录的 industryList 同时带两套码，回查时挑申万那条。

        计费见上（按返回条数计）。
        省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分
        拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "regionList": _as_list(region, "region"),
                "industryList": _as_list(industry, "industry"),
                "securityList": _as_list(security, "security"),
                "brokerList": _as_list(broker, "broker"),
                "ratingList": _as_list(rating, "rating"),
                "ratingChangeList": _as_list(rating_change, "rating_change"),
            }
        )
        result = self._client._call(
            "insight.foreign-opinion.list-with-content"
            if with_content
            else "insight.foreign-opinion.list",
            body=body,
            confirm=confirm,
        )
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def opinion_detail(
        self,
        *,
        chief_opinion_id: FilterValue,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """按 ID 取国内首席观点正文（insight.opinion.detail）。

        chief_opinion_id 取自 opinion_list 返回的 chiefOpinionId，支持单值或列表；
        去重后按 20 个一批依次请求（接口单次上限 20）。返回字段同 opinion_list 的行，另加 content（正文全文）。

        计费 **30 积分/条**，按返回条数计；超时 / 5xx 不自动重发（重发可能对已交付的正文
        再计一次费），偶发失败自行重跑。

        **没有有效正文的 ID 不报错、直接跳过**（ID 写错时即如此；刚发布的观点也可能暂时
        取不到，稍后重取）。SDK 比对请求与返回：缺的 ID 列在 missingIds；某一批请求失败或
        返回异常时，已取到的正文（包括这一批里已返回的）照常保留，没取到的 ID 列在
        unfetchedIds、原因在 unfetchedError（message / code / traceId），只需对这些 ID 重跑。
        两种情况都标 partial 并 warnings.warn；这些标记只在 raw=True 返回的 dict 里
        （{total, list, missingIds?, unfetchedIds?, unfetchedError?, partial?}），默认的
        DataFrame 只含 list。第一批就失败、一条正文都没拿到时直接抛出原错误。
        """
        result = self._fetch_details(
            "insight.opinion.detail", "chiefOpinionIdList", "chiefOpinionId", chief_opinion_id
        )
        if raw:
            return result
        return to_dataframe(result["list"], schema=None)

    def foreign_opinion_detail(
        self,
        *,
        foreign_opinion_id: FilterValue,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """按 ID 取海外机构观点原文与译文（insight.foreign-opinion.detail）。

        foreign_opinion_id 取自 foreign_opinion_list 返回的 foreignOpinionId，支持单值或列表；
        去重后按 20 个一批依次请求（接口单次上限 20）。返回字段同 foreign_opinion_list 的行，另加 content（原文）/ contentTranslate（中文译文）。

        计费 **30 积分/条**，按返回条数计；超时 / 5xx 不自动重发（重发可能对已交付的正文
        再计一次费），偶发失败自行重跑。

        **没有有效正文的 ID 不报错、直接跳过**（ID 写错时即如此；刚发布的观点也可能暂时
        取不到，稍后重取）。SDK 比对请求与返回：缺的 ID 列在 missingIds；某一批请求失败或
        返回异常时，已取到的正文（包括这一批里已返回的）照常保留，没取到的 ID 列在
        unfetchedIds、原因在 unfetchedError（message / code / traceId），只需对这些 ID 重跑。
        两种情况都标 partial 并 warnings.warn；这些标记只在 raw=True 返回的 dict 里
        （{total, list, missingIds?, unfetchedIds?, unfetchedError?, partial?}），默认的
        DataFrame 只含 list。第一批就失败、一条正文都没拿到时直接抛出原错误。
        """
        result = self._fetch_details(
            "insight.foreign-opinion.detail",
            "foreignOpinionIdList",
            "foreignOpinionId",
            foreign_opinion_id,
        )
        if raw:
            return result
        return to_dataframe(result["list"], schema=None)

    def _fetch_details(
        self, endpoint_key: str, id_list_field: str, id_field: str, ids: Any
    ) -> dict[str, Any]:
        job = _OpinionDetails(endpoint_key, id_list_field, id_field, ids)
        for start, body in job.batches():
            try:
                job.take(self._client._call(endpoint_key, body=body))
            except Exception as error:
                job.fail(start, error)
                break
        return job.result()

    # ---- highlight (meeting highlights feed) ----

    def highlight_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        security: FilterValue | None = None,
        research_area: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询会议线索（insight.highlight.list）：Gangtise 会议内容的核心要点信息流。

        固定按发布时间倒序，可按证券、研究方向与时间筛；没有 keyword / rank_type。

        🔴 **5 积分/条**，按返回条数计，务必带 size（先 size=1 看 total 探量级）。
        省略 size 时先取 1 条拿到 total 估算、显式 size 按 min(size, total) × 单价估算，
        超过 1000 积分（约 200 条）拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，
        或 confirm=True 确认全量。超时 / 5xx 不自动重发。单页上限 50，自动翻页。

        按偏移量**最多取到第 10000 条**（from_ + 条数不能超过 10000）：命中更多时取到第
        10000 条为止并标 partial；from_ 本身 ≥ 10000 本地拒绝。要更多请缩短时间范围分段取。

        start_time / end_time：yyyy-MM-dd HH:mm:ss，也接受 yyyy-MM-dd；可查历史前溯 3 个月（试用账号
        1 个月），超出账号数据权限窗口返回 110003。security 证券代码大小写敏感、需精确匹配：A 股 601702.SH、港股 5 位数字
        09992.HK、美股 AAPL.O；支持单值或列表。research_area 用中信行业码（1008001xx）或
        Gangtise 方向码（122000xxx），⚠️ **本端点不认申万码**。

        行字段：highlightId / title（会议名称）/ publishTime / content / securityList
        （securityCode + securityName）/ researchAreaList（researchAreaId + researchAreaName）。
        ⚠️ **content 是 HTML 片段**：整体由 <p> 包裹、各要点小标题由 <strong> 包裹，除这两种
        标签外不含其他标签；要纯文本自行去标签（如 re.sub(r"<[^>]+>", "", content)）。要点可能
        不关联任何证券（securityList 为 []），宏观 / 行业类会议尤其常见——按证券筛会漏掉这批。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "securityList": _as_list(security, "security"),
                "researchAreaList": _as_list(research_area, "research_area"),
            }
        )
        result = self._client._call("insight.highlight.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- independent-opinion ----

    def independent_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: FilterValue | None = None,
        industry: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外独立分析师观点列表（insight.independent-opinion.list）。

        rank_type 取值 1=综合 2=时间倒序。
        industry 只收申万码（104xx0000）；中信码报 100005，即使 constant-category 里列了它。

        计费 **5 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "industryList": _as_list(industry, "industry"),
                "securityList": _as_list(security, "security"),
                "ratingList": _as_list(rating, "rating"),
                "ratingChangeList": _as_list(rating_change, "rating_change"),
            }
        )
        result = self._client._call("insight.independent-opinion.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.independent-opinion.list",
            id_field="independentOpinionId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def official_account_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        account_id: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        industry: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询产业公众号资讯列表（insight.official-account.list）。

        search_type 取值 1=标题搜索（默认） 2=全文搜索。
        rank_type 取值 1=综合（默认） 2=时间倒序。
        category 文章类型可多选：news/law/report/view/data/event/meeting/
        notice/recruit/investEdu/brand/notes/other。
        keyword 需用数据中的具体词（如「泡泡玛特」），不能用整句白话。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "searchType": search_type,
                "rankType": rank_type,
                "keyword": keyword,
                "accountIdList": _as_list(account_id, "account_id"),
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
                "industryList": _as_list(industry, "industry"),
            }
        )
        result = self._client._call("insight.official-account.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.official-account.list",
            id_field="articleId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def qa_list(
        self,
        *,
        security_code: str,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: FilterValue | None = None,
        question_category: FilterValue | None = None,
        answer_important: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询投资者问答 QA（insight.qa.list）。

        按单只证券提取互动平台/电话会议/调研纪要中的提问与回答。
        source 问题来源可多选：conference=电话会议 interactive=互动平台
        survey=调研纪要。question_category 问题类型可多选（11 类）：
        productAndBusiness / capacityAndProjects / ordersAndCustomers /
        financialData / materialEvents / capitalOperations /
        shareholdersAndDividends / corporateGovernance / marketAndValuation /
        macroAndIndustry / risksAndOthers（枚举拼错服务端报 100003）。
        answer_important 答案是否涉及重要信息：1=是 0=否（可多选，省略=不筛）。
        start_time/end_time 格式 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss（字符串直传）。
        行字段：source / publishTime / question / answer / member（回答方身份）/
        securityCode / questionCategory / answerImportant。0.1 积分/条。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        # TS body shape (cli.ts): request keys are BARE (source / questionCategory /
        # answerImportant), not the *List convention.
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "securityCode": security_code,
                "startTime": start_time,
                "endTime": end_time,
                "source": _as_list(source, "source"),
                "questionCategory": _as_list(question_category, "question_category"),
                "answerImportant": _as_list(answer_important, "answer_important"),
            }
        )
        result = self._client._call("insight.qa.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    def report_image_list(
        self,
        *,
        keyword: str,
        top: int = 10,
        source_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索研报图片（insight.report-image.list）。

        返回 chunkId + 元数据，chunkId 供 report_image_download() 下载原图。
        top 默认 10、上限 20（超限服务端会静默截断，本地先报错）；source_id
        限定到某篇研报（可从研报列表或知识库取）。start_time/end_time 限定
        图片所属研报的发布时间。行字段：chunkId / title / sourceId / broker /
        category / typeList / industry / publishTime / page / totalPages /
        imageCaption / imageFootnote / pageContent。免费。
        """
        body = _request_body(
            {
                "keyword": keyword,
                "top": _validate_top(top, name="top", max_value=20),
                "sourceId": source_id,
                "startTime": start_time,
                "endTime": end_time,
            }
        )
        result = self._client._call("insight.report-image.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- Download endpoints ----

    def summary_download(
        self,
        *,
        summary_id: str,
        file_type: int | None = None,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载纪要原文/HTML（insight.summary.download）。

        file_type 取值 1=原文（默认） 2=HTML，仅对会议平台纪要生效。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        query: dict[str, str | int] = {"summaryId": summary_id}
        if file_type is not None:
            query["fileType"] = file_type
        return download_to_path(
            client=self._client,
            endpoint_key="insight.summary.download",
            query=query,
            output=output,
            fallback_name=f"summary-{summary_id}",
            title_lookup=("insight.summary.list", "summaryId", summary_id, resolve_title),
        )

    def pamirs_summary_download(
        self,
        *,
        summary_id: str,
        file_type: int | None = None,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载帕米尔专家纪要原文/HTML（insight.pamirs-summary.download）。

        file_type 取值 1=原文（默认） 2=HTML。需已开通专家纪要数据库。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        query: dict[str, str | int] = {"summaryId": summary_id}
        if file_type is not None:
            query["fileType"] = file_type
        return download_to_path(
            client=self._client,
            endpoint_key="insight.pamirs-summary.download",
            query=query,
            output=output,
            fallback_name=f"pamirs-summary-{summary_id}",
            title_lookup=("insight.pamirs-summary.list", "summaryId", summary_id, resolve_title),
        )

    def performance_calendar_download(
        self,
        *,
        performance_report_id: str,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载业绩报告原文 PDF（insight.performance-calendar.download）。

        A股 10 积分 / 港美股 20 积分; 仅 hasAttachment=True 的记录可下。
        省略 output 时用 title-cache 里的真实标题命名。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.performance-calendar.download",
            query={"performanceReportId": performance_report_id},
            output=output,
            fallback_name=f"performance-calendar-{performance_report_id}",
            title_lookup=(
                "insight.performance-calendar.list",
                "performanceReportId",
                performance_report_id,
                resolve_title,
            ),
        )

    def research_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载国内券商研报（insight.research.download）。

        file_type 取值 1=PDF（默认） 2=Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.research.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"research-{report_id}",
            title_lookup=("insight.research.list", "reportId", report_id, resolve_title),
        )

    def foreign_report_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载海外研报（insight.foreign-report.download）。

        file_type 取值 1=PDF（默认） 2=Markdown 3=中译PDF 4=中译Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.foreign-report.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"foreign-report-{report_id}",
            title_lookup=("insight.foreign-report.list", "reportId", report_id, resolve_title),
        )

    def announcement_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载 A 股公告（insight.announcement.download）。

        file_type 取值 1=PDF（默认） 2=Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-{announcement_id}",
            title_lookup=(
                "insight.announcement.list",
                "announcementId",
                announcement_id,
                resolve_title,
            ),
        )

    def announcement_hk_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载港股公告（insight.announcement-hk.download）。

        file_type 取值 1=原文（默认） 2=Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement-hk.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-hk-{announcement_id}",
            title_lookup=(
                "insight.announcement-hk.list",
                "announcementId",
                announcement_id,
                resolve_title,
            ),
        )

    def announcement_us_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载美股公告（insight.announcement-us.download）。

        file_type 取值 1=原文 PDF（默认） 2=Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement-us.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-us-{announcement_id}",
            title_lookup=(
                "insight.announcement-us.list",
                "announcementId",
                announcement_id,
                resolve_title,
            ),
        )

    def independent_opinion_download(
        self,
        *,
        independent_opinion_id: str,
        file_type: int,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载海外独立分析师观点（insight.independent-opinion.download）。

        file_type 必填，取值 1=原文HTML 2=中译HTML。

        文件名：先调过 independent_opinion_list() 时标题已进缓存，下载自动命中（免费）；否则用
        服务端文件名或 ``independent-opinion-<id>``。🔴 **不支持 resolve_title=True**（传了在发请求前
        报 ValidationError）：它的 list 按 5 积分/条计费，回查 200 条要 1000 积分，只为一个文件名
        （CLI 的该命令同样不提供标题回查）。参数保留只为签名兼容。
        """
        if resolve_title:
            raise ValidationError(_INDEPENDENT_OPINION_NO_TITLE_LOOKUP)
        return download_to_path(
            client=self._client,
            endpoint_key="insight.independent-opinion.download",
            query={
                "independentOpinionId": independent_opinion_id,
                "fileType": file_type,
            },
            output=output,
            fallback_name=f"independent-opinion-{independent_opinion_id}",
            title_lookup=(
                "insight.independent-opinion.list",
                "independentOpinionId",
                independent_opinion_id,
                False,  # cache only — see _INDEPENDENT_OPINION_NO_TITLE_LOOKUP
            ),
        )

    def official_account_download(
        self,
        *,
        article_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载产业公众号文章（insight.official-account.download）。

        file_type 取值 1=txt（默认） 2=HTML。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.official-account.download",
            query={"articleId": article_id, "fileType": file_type},
            output=output,
            fallback_name=f"official-account-{article_id}",
            title_lookup=("insight.official-account.list", "articleId", article_id, resolve_title),
        )

    def report_image_download(
        self,
        *,
        chunk_id: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载研报图片原图（insight.report-image.download）。

        chunk_id 取自 report_image_list() 返回的 chunkId；直接下载二进制
        原图（JPEG）。省略 output 时优先用服务端返回的文件名，无则按
        report-image-<chunkId> 命名。0.1 积分/张。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.report-image.download",
            query={"chunkId": chunk_id},
            output=output,
            fallback_name=f"report-image-{chunk_id}",
        )


class AsyncInsight:
    """Async mirror of `Insight`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        research_area: FilterValue | None = None,
        chief: FilterValue | None = None,
        security: FilterValue | None = None,
        broker: FilterValue | None = None,
        industry: FilterValue | None = None,
        concept: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        source: FilterValue | None = None,
        with_content: bool = False,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询国内机构首席观点列表（insight.opinion.list；with_content=True 时
        insight.opinion.list-with-content）。

        🔴 **默认列表只含摘要**：brief 是正文前 200 字的截断，**1 积分/条**。要正文用
        opinion_detail(chief_opinion_id=...) 按 chiefOpinionId 取（content，30 积分/条），
        或 with_content=True 让列表直接带正文（旧版 v1 列表，**30 积分/条**，超时 / 5xx
        不自动重发）。只需判断相关性、做筛选时看 brief 就够，别默认开 with_content。

        ⚠️ with_content=True 返回的是**旧版结构**：标题与正文在 contentList.title /
        contentList.content（contentList 是对象，不是数组；DataFrame 里是一列
        contentList），顶层没有 title / brief；要统一成 opinion_detail 的结构就走
        list + detail。

        行字段（默认）：chiefOpinionId / publishTime / title / brief / author{chiefId,
        chiefName, researchAreaList, brokerID, brokerName} / securityList / industryList /
        conceptList / llmTagList；author.chiefId / chiefName 在机构点评类观点上为 null。

        llm_tag 取值 strongRcmd=强烈推荐 / earningsReview=业绩点评 / topBroker=头部券商 /
        newFortune=新财富团队；source 取值 realTime=实时 / openSource=开放来源。
        industry 用 citicIndustry 码（1008001xx）；申万码（104xx0000）也生效，但两套码的
        行业成分不同、取回的结果集不一致，同一批查询别混用。research_area 行业用
        citicIndustry 码、方向用 gangtiseIndustry 码（122000xxx），申万码在本端点返 0。

        计费见上（按返回条数计）。
        省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分
        拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "researchAreaList": _as_list(research_area, "research_area"),
                "chiefList": _as_list(chief, "chief"),
                "securityList": _as_list(security, "security"),
                "brokerList": _as_list(broker, "broker"),
                "industryList": _as_list(industry, "industry"),
                "conceptList": _as_list(concept, "concept"),
                "llmTagList": _as_list(llm_tag, "llm_tag"),
                "sourceList": _as_list(source, "source"),
            }
        )
        result = await self._client._call(
            "insight.opinion.list-with-content" if with_content else "insight.opinion.list",
            body=body,
            confirm=confirm,
        )
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def summary_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        source: FilterValue | None = None,
        research_area: FilterValue | None = None,
        security: FilterValue | None = None,
        institution: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        participant_role: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询纪要列表（insight.summary.list）。

        market 取值 aShares / hkStocks / usStocks / usChinaConcept（交易所后缀如 SH/SZ 会被拒为 100005）。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "sourceList": _as_list(source, "source"),
                "researchAreaList": _as_list(research_area, "research_area"),
                "securityList": _as_list(security, "security"),
                "institutionList": _as_list(institution, "institution"),
                "categoryList": _as_list(category, "category"),
                "marketList": _as_list(market, "market"),
                "participantRoleList": _as_list(participant_role, "participant_role"),
            }
        )
        result = await self._client._call("insight.summary.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.summary.list",
            id_field="summaryId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def pamirs_summary_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        research_area: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询帕米尔专家纪要列表（insight.pamirs-summary.list）。

        这是一个**独立的专家纪要库**, 不是 summary_list 的筛选项, 需单独购买专家纪要数据库
        （未开通报 999004）, 且不受历史数据范围限制。

        筛选项是 summary_list 的真子集: 只有 search_type / rank_type / keyword /
        research_area / security / category / market——**没有** source / institution /
        participant_role。故意不复用 summary_list 的 body: 服务端会静默丢弃不认识的字段,
        照搬会让调用方以为过滤生效、实际拿到全量。

        category 取值 companyAnalysis / industryAnalysis; market 取值
        aShares / hkStocks / usChinaConcept / usStocks——两者都本地校验, 因为服务端对非法
        枚举是静默忽略该条件返回全量。research_area 中信码（1008001xx）与申万码
        （104xx0000）都认, 但方向码（122000xxx）在本端点返 0。

        ⚠️ 已知返回口径（实测 2026-08-08）: conceptList 在所有查法下都是空的（当前拿不到
        主题概念标签, 也没有 concept 过滤参数）; categoryList / marketList 只在用 category 或
        market 过滤时才回填——所以按这两个维度分组要靠过滤参数取, 别拉全量再本地分组。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "researchAreaList": _as_list(research_area, "research_area"),
                "securityList": _as_list(security, "security"),
                "categoryList": _validate_choices(
                    category, name="category", allowed=_PAMIRS_CATEGORIES
                ),
                "marketList": _validate_choices(market, name="market", allowed=_PAMIRS_MARKETS),
            }
        )
        result = await self._client._call("insight.pamirs-summary.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.pamirs-summary.list",
            id_field="summaryId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def performance_calendar_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        security: FilterValue | None = None,
        market: FilterValue | None = None,
        category: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询财报日历（insight.performance-calendar.list）: 业绩预告 / 快报 / 公告。

        它是唯一按 **start_date / end_date**（yyyy-MM-dd, 过滤 publishDate）筛选的 insight
        列表, 其余用 start_time; 也没有 keyword / rank_type / search_type。
        market 取值 aShares / hkStocks / usChinaConcept / usStocks;
        category 取值 performanceForecast / performanceExpress / performanceAnnouncement——
        两者本地白名单校验, 拼错直接报错（服务端对错枚举是静默返全量, 按 0.1 积分/条计费）。

        ⚠️ 本接口数据量很大（含未来排期）, 省略 size 等于按分页上限拉满
        （1000 页 × 50 = 5 万条, 按 0.1 积分/条约 5000 积分）, 因此**至少要给一个约束**:
        完整日期区间 / security / 显式 size, 否则本地报错且不发请求。只给 security 时另加 1000 行隐式上限——
        撞上上限且仍有剩余会标 partial 并 warning。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        market_list = _validate_choices(market, name="market", allowed=_PERFORMANCE_MARKETS)
        category_list = _validate_choices(
            category, name="category", allowed=_PERFORMANCE_CATEGORIES
        )
        securities = _as_list(security, "security")
        explicitly_bounded = size is not None or bool(start_date and end_date)
        if not explicitly_bounded and not securities:
            raise ValidationError(
                "performance_calendar_list without a bound would auto-paginate the whole "
                "calendar — up to 50k rows at 0.1 credits each: pass start_date and "
                "end_date, or security, or an explicit size"
            )
        # `security` is only a real bound while the server honours securityList. It
        # does today (probed 2026-07-25: an unknown code returns total 0, it is not
        # silently ignored like a bad enum) — but a five-figure credit bill must not
        # rest on that staying true. One company's whole calendar is dozens of rows,
        # so the cap is invisible in normal use and turns a filter regression into a
        # truncated result instead of a 5000-credit pull.
        implicit_cap = None if explicitly_bounded else _SECURITY_ONLY_ROW_CAP
        body = _request_body(
            {
                "from": from_,
                "size": size if size is not None else implicit_cap,
                "startDate": start_date,
                "endDate": end_date,
                "marketList": market_list,
                "securityList": securities,
                "categoryList": category_list,
            }
        )
        result = await self._client._call(
            "insight.performance-calendar.list", body=body, confirm=confirm
        )
        if implicit_cap is not None:
            _flag_implicit_cap_hit(result, implicit_cap, from_)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.performance-calendar.list",
            id_field="performanceReportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- schedule (roadshow / site-visit / strategy / forum) ----
    # See sync Insight class for the v0.17.0 tightening rationale.

    async def roadshow_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        institution: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        participant_role: FilterValue | None = None,
        broker_type: FilterValue | None = None,
        permission: FilterValue | None = None,
        location: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询路演日程列表（insight.roadshow.list）。

        category 路演类型取值 earningsCall（业绩会）/ strategyMeeting（策略会）/
        companyAnalysis（公司分析）/ industryAnalysis（行业分析）/ fundRoadshow
        （基金路演）；market 取值 aShares / hkStocks / usChinaConcept / usStocks；
        participant_role 取值 management / expert；broker_type 取值
        cnBroker / otherBroker；permission 取值 1=公开 / 2=私密；
        research_area 用 gangtiseIndustry 码（reference.constant_list 查询）；
        location 用 domesticCity 码。

        ⚠️ **`location` 目前不可用**：任何取值服务端都返回 `999999 系统内部错误`（四个日程类接口一致，2026-09-07 实测）。

        计费 **20 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area, "research_area"),
                "institutionList": _as_list(institution, "institution"),
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
                "marketList": _as_list(market, "market"),
                "participantRoleList": _as_list(participant_role, "participant_role"),
                "brokerTypeList": _as_list(broker_type, "broker_type"),
                "permission": _as_list(permission, "permission"),
                "locationList": _as_list(location, "location"),
            }
        )
        result = await self._client._call("insight.roadshow.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def site_visit_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        institution: FilterValue | None = None,
        security: FilterValue | None = None,
        object_: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        permission: FilterValue | None = None,
        location: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询调研/实地走访日程列表（insight.site-visit.list）。

        object_ 取值 company / industry（请求字段 object）；category 调研形式取值
        single（单场）/ series（系列）；market 取值 aShares / hkStocks /
        usChinaConcept（site-visit 无 usStocks）；permission 取值 1=公开 / 2=私密；
        research_area 用 gangtiseIndustry 码；location 用 domesticCity 码。

        ⚠️ **`location` 目前不可用**：任何取值服务端都返回 `999999 系统内部错误`（四个日程类接口一致，2026-09-07 实测）。

        计费 **20 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area, "research_area"),
                "institutionList": _as_list(institution, "institution"),
                "securityList": _as_list(security, "security"),
                "objectList": _as_named_list(object_, "object_"),
                "categoryList": _as_list(category, "category"),
                "marketList": _as_list(market, "market"),
                "permission": _as_list(permission, "permission"),
                "locationList": _as_list(location, "location"),
            }
        )
        result = await self._client._call("insight.site-visit.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def strategy_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        institution: FilterValue | None = None,
        location: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询线下策略会日程列表（insight.strategy.list）。

        服务端仅按 institution（主办机构 ID）和 location（domesticCity 城市/省份 ID）
        筛选，无 research_area / security / category 等。

        ⚠️ **`location` 目前不可用**：任何取值服务端都返回 `999999 系统内部错误`（四个日程类接口一致，2026-09-07 实测）。

        计费 **20 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "institutionList": _as_list(institution, "institution"),
                "locationList": _as_list(location, "location"),
            }
        )
        result = await self._client._call("insight.strategy.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def forum_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        location: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询论坛/电话会日程列表（insight.forum.list）。

        服务端仅按 research_area（gangtiseIndustry 码）和 location（domesticCity 码）
        筛选，无 institution / security / category 等。

        ⚠️ **`location` 目前不可用**：任何取值服务端都返回 `999999 系统内部错误`（四个日程类接口一致，2026-09-07 实测）。

        计费 **20 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area, "research_area"),
                "locationList": _as_list(location, "location"),
            }
        )
        result = await self._client._call("insight.forum.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def research_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        broker: FilterValue | None = None,
        security: FilterValue | None = None,
        industry: FilterValue | None = None,
        category: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        source: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询国内券商研报列表（insight.research.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "brokerList": _as_list(broker, "broker"),
                "securityList": _as_list(security, "security"),
                "industryList": _as_list(industry, "industry"),
                "categoryList": _as_list(category, "category"),
                "llmTagList": _as_list(llm_tag, "llm_tag"),
                "ratingList": _as_list(rating, "rating"),
                "ratingChangeList": _as_list(rating_change, "rating_change"),
                "minReportPages": min_pages,
                "maxReportPages": max_pages,
                "sourceList": _as_list(source, "source"),
            }
        )
        result = await self._client._call("insight.research.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.research.list",
            id_field="reportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def foreign_report_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        region: FilterValue | None = None,
        category: FilterValue | None = None,
        industry: FilterValue | None = None,
        broker: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外研报列表（insight.foreign-report.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security, "security"),
                "regionList": _as_list(region, "region"),
                "categoryList": _as_list(category, "category"),
                "industryList": _as_list(industry, "industry"),
                "brokerList": _as_list(broker, "broker"),
                "llmTagList": _as_list(llm_tag, "llm_tag"),
                "ratingList": _as_list(rating, "rating"),
                "ratingChangeList": _as_list(rating_change, "rating_change"),
                "minReportPages": min_pages,
                "maxReportPages": max_pages,
            }
        )
        result = await self._client._call("insight.foreign-report.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.foreign-report.list",
            id_field="reportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def announcement_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: int | str | None = None,
        end_time: int | str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股公告列表（insight.announcement.list）。

        start_time/end_time 接受日期字符串或 10/13 位时间戳，按**北京时间**换算成 13 位毫秒发出
        （与运行机器的时区无关；10 位按秒换算）。**end_time 只写日期时按当日 23:59:59 换算**，
        所以 start_time 与 end_time 写同一天就是查这一整天。
        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        category 公告分类 ID，用 reference.constant_list(category="aShareAnnouncementCategory")
        查询；常用 103910200 财务报告 / 103910201 业绩预告 / 103910700 股权股本 等。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": _to_timestamp13(start_time, "start_time"),
                "endTime": _to_end_timestamp13(end_time, "end_time"),
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
            }
        )
        result = await self._client._call("insight.announcement.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.announcement.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def announcement_hk_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股公告列表（insight.announcement-hk.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        category 港股公告分类 ID，用 reference.constant_list(category="hkShareAnnouncementCategory")
        查询。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
            }
        )
        result = await self._client._call(
            "insight.announcement-hk.list", body=body, confirm=confirm
        )
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.announcement-hk.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def announcement_us_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股公告列表（insight.announcement-us.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        security 传美股代码如 TSLA.O；category 美股公告分类 ID，用
        reference.constant_list(category="usShareAnnouncementCategory") 查询。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
            }
        )
        result = await self._client._call(
            "insight.announcement-us.list", body=body, confirm=confirm
        )
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.announcement-us.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def foreign_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: FilterValue | None = None,
        region: FilterValue | None = None,
        industry: FilterValue | None = None,
        broker: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        with_content: bool = False,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外机构观点列表（insight.foreign-opinion.list；with_content=True 时
        insight.foreign-opinion.list-with-content）。

        🔴 **默认列表只含摘要**：brief（英文）/ briefTranslate（中文），取正文前 200 字，
        **1 积分/条**。原文与译文（content / contentTranslate）用
        foreign_opinion_detail(foreign_opinion_id=...) 按 foreignOpinionId 取（30 积分/条），
        或 with_content=True（旧版 v1 列表，**30 积分/条**，content / contentTranslate
        直接在顶层、不含 brief；超时 / 5xx 不自动重发）。

        行字段（默认）：foreignOpinionId / title / titleTranslate / brief / briefTranslate /
        publishTime / publisher{brokerId, brokerName} / securityList[]{securityCode,
        securityName, rating, ratingChange, targetPrice, currency} / industryList[] /
        region{regionCode, regionName}。

        rank_type 取值 1=综合 2=时间倒序。
        region 本接口只收 cn/cnHk/cnTw/us/jp/uk；regionCategory 的另外 13 个取值
        （sea/gl/fr/de/kr/in/ca/me/othAs/othEur/latAm/oce/af）在这里报 100005，
        尽管它们在 foreign_report_list 上都可用。
        industry 只收申万码（104xx0000）；中信码报 100005，即使 constant-category 里列了它。
        返回记录的 industryList 同时带两套码，回查时挑申万那条。

        计费见上（按返回条数计）。
        省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分
        拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "regionList": _as_list(region, "region"),
                "industryList": _as_list(industry, "industry"),
                "securityList": _as_list(security, "security"),
                "brokerList": _as_list(broker, "broker"),
                "ratingList": _as_list(rating, "rating"),
                "ratingChangeList": _as_list(rating_change, "rating_change"),
            }
        )
        result = await self._client._call(
            "insight.foreign-opinion.list-with-content"
            if with_content
            else "insight.foreign-opinion.list",
            body=body,
            confirm=confirm,
        )
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def opinion_detail(
        self,
        *,
        chief_opinion_id: FilterValue,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """按 ID 取国内首席观点正文（insight.opinion.detail）。

        chief_opinion_id 取自 opinion_list 返回的 chiefOpinionId，支持单值或列表；
        去重后按 20 个一批依次请求（接口单次上限 20）。返回字段同 opinion_list 的行，另加 content（正文全文）。

        计费 **30 积分/条**，按返回条数计；超时 / 5xx 不自动重发（重发可能对已交付的正文
        再计一次费），偶发失败自行重跑。

        **没有有效正文的 ID 不报错、直接跳过**（ID 写错时即如此；刚发布的观点也可能暂时
        取不到，稍后重取）。SDK 比对请求与返回：缺的 ID 列在 missingIds；某一批请求失败或
        返回异常时，已取到的正文（包括这一批里已返回的）照常保留，没取到的 ID 列在
        unfetchedIds、原因在 unfetchedError（message / code / traceId），只需对这些 ID 重跑。
        两种情况都标 partial 并 warnings.warn；这些标记只在 raw=True 返回的 dict 里
        （{total, list, missingIds?, unfetchedIds?, unfetchedError?, partial?}），默认的
        DataFrame 只含 list。第一批就失败、一条正文都没拿到时直接抛出原错误。
        """
        result = await self._fetch_details(
            "insight.opinion.detail", "chiefOpinionIdList", "chiefOpinionId", chief_opinion_id
        )
        if raw:
            return result
        return to_dataframe(result["list"], schema=None)

    async def foreign_opinion_detail(
        self,
        *,
        foreign_opinion_id: FilterValue,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """按 ID 取海外机构观点原文与译文（insight.foreign-opinion.detail）。

        foreign_opinion_id 取自 foreign_opinion_list 返回的 foreignOpinionId，支持单值或列表；
        去重后按 20 个一批依次请求（接口单次上限 20）。返回字段同 foreign_opinion_list 的行，另加 content（原文）/ contentTranslate（中文译文）。

        计费 **30 积分/条**，按返回条数计；超时 / 5xx 不自动重发（重发可能对已交付的正文
        再计一次费），偶发失败自行重跑。

        **没有有效正文的 ID 不报错、直接跳过**（ID 写错时即如此；刚发布的观点也可能暂时
        取不到，稍后重取）。SDK 比对请求与返回：缺的 ID 列在 missingIds；某一批请求失败或
        返回异常时，已取到的正文（包括这一批里已返回的）照常保留，没取到的 ID 列在
        unfetchedIds、原因在 unfetchedError（message / code / traceId），只需对这些 ID 重跑。
        两种情况都标 partial 并 warnings.warn；这些标记只在 raw=True 返回的 dict 里
        （{total, list, missingIds?, unfetchedIds?, unfetchedError?, partial?}），默认的
        DataFrame 只含 list。第一批就失败、一条正文都没拿到时直接抛出原错误。
        """
        result = await self._fetch_details(
            "insight.foreign-opinion.detail",
            "foreignOpinionIdList",
            "foreignOpinionId",
            foreign_opinion_id,
        )
        if raw:
            return result
        return to_dataframe(result["list"], schema=None)

    async def _fetch_details(
        self, endpoint_key: str, id_list_field: str, id_field: str, ids: Any
    ) -> dict[str, Any]:
        job = _OpinionDetails(endpoint_key, id_list_field, id_field, ids)
        for start, body in job.batches():
            try:
                job.take(await self._client._call(endpoint_key, body=body))
            except Exception as error:
                job.fail(start, error)
                break
        return job.result()

    # ---- highlight (meeting highlights feed) ----

    async def highlight_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        security: FilterValue | None = None,
        research_area: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询会议线索（insight.highlight.list）：Gangtise 会议内容的核心要点信息流。

        固定按发布时间倒序，可按证券、研究方向与时间筛；没有 keyword / rank_type。

        🔴 **5 积分/条**，按返回条数计，务必带 size（先 size=1 看 total 探量级）。
        省略 size 时先取 1 条拿到 total 估算、显式 size 按 min(size, total) × 单价估算，
        超过 1000 积分（约 200 条）拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，
        或 confirm=True 确认全量。超时 / 5xx 不自动重发。单页上限 50，自动翻页。

        按偏移量**最多取到第 10000 条**（from_ + 条数不能超过 10000）：命中更多时取到第
        10000 条为止并标 partial；from_ 本身 ≥ 10000 本地拒绝。要更多请缩短时间范围分段取。

        start_time / end_time：yyyy-MM-dd HH:mm:ss，也接受 yyyy-MM-dd；可查历史前溯 3 个月（试用账号
        1 个月），超出账号数据权限窗口返回 110003。security 证券代码大小写敏感、需精确匹配：A 股 601702.SH、港股 5 位数字
        09992.HK、美股 AAPL.O；支持单值或列表。research_area 用中信行业码（1008001xx）或
        Gangtise 方向码（122000xxx），⚠️ **本端点不认申万码**。

        行字段：highlightId / title（会议名称）/ publishTime / content / securityList
        （securityCode + securityName）/ researchAreaList（researchAreaId + researchAreaName）。
        ⚠️ **content 是 HTML 片段**：整体由 <p> 包裹、各要点小标题由 <strong> 包裹，除这两种
        标签外不含其他标签；要纯文本自行去标签（如 re.sub(r"<[^>]+>", "", content)）。要点可能
        不关联任何证券（securityList 为 []），宏观 / 行业类会议尤其常见——按证券筛会漏掉这批。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "securityList": _as_list(security, "security"),
                "researchAreaList": _as_list(research_area, "research_area"),
            }
        )
        result = await self._client._call("insight.highlight.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def independent_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: FilterValue | None = None,
        industry: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外独立分析师观点列表（insight.independent-opinion.list）。

        rank_type 取值 1=综合 2=时间倒序。
        industry 只收申万码（104xx0000）；中信码报 100005，即使 constant-category 里列了它。

        计费 **5 积分/条**（按返回条数计），务必带 size。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "industryList": _as_list(industry, "industry"),
                "securityList": _as_list(security, "security"),
                "ratingList": _as_list(rating, "rating"),
                "ratingChangeList": _as_list(rating_change, "rating_change"),
            }
        )
        result = await self._client._call(
            "insight.independent-opinion.list", body=body, confirm=confirm
        )
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.independent-opinion.list",
            id_field="independentOpinionId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def official_account_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        account_id: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        industry: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询产业公众号资讯列表（insight.official-account.list）。

        search_type 取值 1=标题搜索（默认） 2=全文搜索。
        rank_type 取值 1=综合（默认） 2=时间倒序。
        category 文章类型可多选：news/law/report/view/data/event/meeting/
        notice/recruit/investEdu/brand/notes/other。
        keyword 需用数据中的具体词（如「泡泡玛特」），不能用整句白话。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。

        rank_type=1（综合）按关键词相关度挑选后仍按时间倒序排列（比条目 ID 集合才看得出差别）；
        没有 keyword 时两档结果一致，两档差别大小取决于关键词；search_type 不影响 1 取回哪些条目。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "searchType": search_type,
                "rankType": rank_type,
                "keyword": keyword,
                "accountIdList": _as_list(account_id, "account_id"),
                "securityList": _as_list(security, "security"),
                "categoryList": _as_list(category, "category"),
                "industryList": _as_list(industry, "industry"),
            }
        )
        result = await self._client._call(
            "insight.official-account.list", body=body, confirm=confirm
        )
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.official-account.list",
            id_field="articleId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def qa_list(
        self,
        *,
        security_code: str,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: FilterValue | None = None,
        question_category: FilterValue | None = None,
        answer_important: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询投资者问答 QA（insight.qa.list）。

        按单只证券提取互动平台/电话会议/调研纪要中的提问与回答。
        source 问题来源可多选：conference=电话会议 interactive=互动平台
        survey=调研纪要。question_category 问题类型可多选（11 类）：
        productAndBusiness / capacityAndProjects / ordersAndCustomers /
        financialData / materialEvents / capitalOperations /
        shareholdersAndDividends / corporateGovernance / marketAndValuation /
        macroAndIndustry / risksAndOthers（枚举拼错服务端报 100003）。
        answer_important 答案是否涉及重要信息：1=是 0=否（可多选，省略=不筛）。
        start_time/end_time 格式 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss（字符串直传）。
        行字段：source / publishTime / question / answer / member（回答方身份）/
        securityCode / questionCategory / answerImportant。0.1 积分/条。

        计费 0.1 积分/条（按返回条数计）。省略 size 时按 total × 单价估算、
        显式 size 按 min(size, total) × 单价估算，超过 1000 积分拒绝（ValidationError，不再往下拉）；
        传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        # TS body shape (cli.ts): request keys are BARE (source / questionCategory /
        # answerImportant), not the *List convention.
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "securityCode": security_code,
                "startTime": start_time,
                "endTime": end_time,
                "source": _as_list(source, "source"),
                "questionCategory": _as_list(question_category, "question_category"),
                "answerImportant": _as_list(answer_important, "answer_important"),
            }
        )
        result = await self._client._call("insight.qa.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def report_image_list(
        self,
        *,
        keyword: str,
        top: int = 10,
        source_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索研报图片（insight.report-image.list）。

        返回 chunkId + 元数据，chunkId 供 report_image_download() 下载原图。
        top 默认 10、上限 20（超限服务端会静默截断，本地先报错）；source_id
        限定到某篇研报（可从研报列表或知识库取）。start_time/end_time 限定
        图片所属研报的发布时间。行字段：chunkId / title / sourceId / broker /
        category / typeList / industry / publishTime / page / totalPages /
        imageCaption / imageFootnote / pageContent。免费。
        """
        body = _request_body(
            {
                "keyword": keyword,
                "top": _validate_top(top, name="top", max_value=20),
                "sourceId": source_id,
                "startTime": start_time,
                "endTime": end_time,
            }
        )
        result = await self._client._call("insight.report-image.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def summary_download(
        self,
        *,
        summary_id: str,
        file_type: int | None = None,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载纪要原文/HTML（insight.summary.download）。

        file_type 取值 1=原文（默认） 2=HTML，仅对会议平台纪要生效。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        query: dict[str, str | int] = {"summaryId": summary_id}
        if file_type is not None:
            query["fileType"] = file_type
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.summary.download",
            query=query,
            output=output,
            fallback_name=f"summary-{summary_id}",
            title_lookup=("insight.summary.list", "summaryId", summary_id, resolve_title),
        )

    async def pamirs_summary_download(
        self,
        *,
        summary_id: str,
        file_type: int | None = None,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载帕米尔专家纪要原文/HTML（insight.pamirs-summary.download）。

        file_type 取值 1=原文（默认） 2=HTML。需已开通专家纪要数据库。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        query: dict[str, str | int] = {"summaryId": summary_id}
        if file_type is not None:
            query["fileType"] = file_type
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.pamirs-summary.download",
            query=query,
            output=output,
            fallback_name=f"pamirs-summary-{summary_id}",
            title_lookup=("insight.pamirs-summary.list", "summaryId", summary_id, resolve_title),
        )

    async def performance_calendar_download(
        self,
        *,
        performance_report_id: str,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载业绩报告原文 PDF（insight.performance-calendar.download）。

        A股 10 积分 / 港美股 20 积分; 仅 hasAttachment=True 的记录可下。
        省略 output 时用 title-cache 里的真实标题命名。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.performance-calendar.download",
            query={"performanceReportId": performance_report_id},
            output=output,
            fallback_name=f"performance-calendar-{performance_report_id}",
            title_lookup=(
                "insight.performance-calendar.list",
                "performanceReportId",
                performance_report_id,
                resolve_title,
            ),
        )

    async def research_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载国内券商研报（insight.research.download）。

        file_type 取值 1=PDF（默认） 2=Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.research.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"research-{report_id}",
            title_lookup=("insight.research.list", "reportId", report_id, resolve_title),
        )

    async def foreign_report_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载海外研报（insight.foreign-report.download）。

        file_type 取值 1=PDF（默认） 2=Markdown 3=中译PDF 4=中译Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.foreign-report.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"foreign-report-{report_id}",
            title_lookup=("insight.foreign-report.list", "reportId", report_id, resolve_title),
        )

    async def announcement_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载 A 股公告（insight.announcement.download）。

        file_type 取值 1=PDF（默认） 2=Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.announcement.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-{announcement_id}",
            title_lookup=(
                "insight.announcement.list",
                "announcementId",
                announcement_id,
                resolve_title,
            ),
        )

    async def announcement_hk_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载港股公告（insight.announcement-hk.download）。

        file_type 取值 1=原文（默认） 2=Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.announcement-hk.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-hk-{announcement_id}",
            title_lookup=(
                "insight.announcement-hk.list",
                "announcementId",
                announcement_id,
                resolve_title,
            ),
        )

    async def announcement_us_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载美股公告（insight.announcement-us.download）。

        file_type 取值 1=原文 PDF（默认） 2=Markdown。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.announcement-us.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-us-{announcement_id}",
            title_lookup=(
                "insight.announcement-us.list",
                "announcementId",
                announcement_id,
                resolve_title,
            ),
        )

    async def independent_opinion_download(
        self,
        *,
        independent_opinion_id: str,
        file_type: int,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载海外独立分析师观点（insight.independent-opinion.download）。

        file_type 必填，取值 1=原文HTML 2=中译HTML。

        文件名：先调过 independent_opinion_list() 时标题已进缓存，下载自动命中（免费）；否则用
        服务端文件名或 ``independent-opinion-<id>``。🔴 **不支持 resolve_title=True**（传了在发请求前
        报 ValidationError）：它的 list 按 5 积分/条计费，回查 200 条要 1000 积分，只为一个文件名
        （CLI 的该命令同样不提供标题回查）。参数保留只为签名兼容。
        """
        if resolve_title:
            raise ValidationError(_INDEPENDENT_OPINION_NO_TITLE_LOOKUP)
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.independent-opinion.download",
            query={
                "independentOpinionId": independent_opinion_id,
                "fileType": file_type,
            },
            output=output,
            fallback_name=f"independent-opinion-{independent_opinion_id}",
            title_lookup=(
                "insight.independent-opinion.list",
                "independentOpinionId",
                independent_opinion_id,
                False,  # cache only — see _INDEPENDENT_OPINION_NO_TITLE_LOOKUP
            ),
        )

    async def official_account_download(
        self,
        *,
        article_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载产业公众号文章（insight.official-account.download）。

        file_type 取值 1=txt（默认） 2=HTML。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.official-account.download",
            query={"articleId": article_id, "fileType": file_type},
            output=output,
            fallback_name=f"official-account-{article_id}",
            title_lookup=("insight.official-account.list", "articleId", article_id, resolve_title),
        )

    async def report_image_download(
        self,
        *,
        chunk_id: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载研报图片原图（insight.report-image.download）。

        chunk_id 取自 report_image_list() 返回的 chunkId；直接下载二进制
        原图（JPEG）。省略 output 时优先用服务端返回的文件名，无则按
        report-image-<chunkId> 命名。0.1 积分/张。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.report-image.download",
            query={"chunkId": chunk_id},
            output=output,
            fallback_name=f"report-image-{chunk_id}",
        )
