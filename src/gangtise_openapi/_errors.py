# ruff: noqa: RUF001, RUF003
# (Disabled file-wide: ERROR_HINTS values are user-facing Chinese strings that
# intentionally use fullwidth punctuation, and the Chinese comments documenting
# each code group do the same.)
from __future__ import annotations

from typing import Any

# Keyed by the code as a string — every envelope code is run through ``str()``
# first, which matters because the 2026-07-17 overhaul emits the new codes as JSON
# *numbers* while legacy codes stay strings.
#
# Both generations are listed on purpose. Probed by the TS CLI 2026-07-20: the
# rollout is partial — the business layer already answers with the new codes
# (999011 / 130001 / 130002 / 100003 / 999010), but the outer token filter still
# emits 0000001007 / 0000001008 / 900002. Dropping either set leaves a live code
# hintless.
#
# The hint is appended after the server's own msg, so it must carry the *action*,
# never restate the diagnosis — "资源不存在 — 资源不存在，确认 ID 有效" reads as a stutter.
ERROR_HINTS: dict[str, str] = {
    # ── 服务统一层 999xxx ──
    "999001": "检查 GANGTISE_TOKEN 或 GANGTISE_ACCESS_KEY / GANGTISE_SECRET_KEY 是否已设置。",
    "999002": "有 AK/SK 时 SDK 会自动重新登录重试一次，否则请重新登录。",
    "999003": "定制接口需联系客户经理开通。",
    "999004": "换一条本账号可见的记录重试。",
    "999005": "联系客户经理充值，或缩小查询范围降低消耗。",
    "999006": "触发限流，稍后再试或联系客户经理提额；429 所有端点都退避重试，5xx 仅普通端点重试（贵档 no-replay 端点的 5xx 不重放，但其 429 仍重试）。",
    # SDK 的 method / Content-Type / 请求体均由端点表固定，这四类正常发不出来；
    # 出现即服务端行为变化，请带 trace 报障。
    "999007": "该端点的 HTTP 方法由 SDK 端点表固定，出现此码说明服务端行为已变化，请带 trace 报障。",
    "999008": "Content-Type 由 SDK 固定为 application/json，出现此码请带 trace 报障。",
    "999009": "请求体无法解析——检查传入参数里是否有无法 JSON 序列化的值。",
    "999010": "该接口路径可能已下线，升级 gangtise-openapi 到最新版；仍失败请带 trace 报障。",
    "999011": "检查 GANGTISE_ACCESS_KEY / GANGTISE_SECRET_KEY 是否写反或未设置。",
    "999012": "联系客户经理。",
    "999013": "联系客户经理续期。",
    "999014": "联系客户经理。",
    "999015": "联系客户经理开通长期 token。",
    "999016": "联系客户经理登记当前出口 IP。",
    "999999": "请稍后重试；持续失败请带上面的 trace 报障。",
    # ── 业务通用层 1xxxxx ──
    "100001": "对照方法签名检查必填参数。",
    "100002": "检查数值 / 字符串参数是否传反。",
    # 实测两种形态都有：类型/范围错的 msg 带字段名与范围，枚举错的 msg 只有笼统的
    # 「参数值非法」。条件句让两种形态都读得通。
    "100003": "msg 已指明字段名或取值范围时直接按 msg 改；msg 只说「参数值非法」时多为枚举参数拼写错误（如 source / question_category / answer_important），对照方法 docstring 列出的合法值检查。",
    "100004": "检查 size / from_ 是否为非负数且未超单页上限。",
    "100005": "对照方法 docstring 列出的合法取值检查。",
    "100006": "缩短日期范围或调小 size / limit。",
    # 按参数名判断，不要按域预判：ai.management_discuss_* 的 report_date 是 date 型，
    # 而同属 ai 的 knowledge_batch 收时间戳或 datetime。
    "110001": '看参数名：`*_date` 用 YYYY-MM-DD，`*_time` 用 "YYYY-MM-DD HH:mm:ss"（ai.knowledge_batch 与 insight 的 A 股公告接口收时间戳或 datetime，SDK 统一转 13 位毫秒）。',
    "110002": "起始晚于结束——检查 start_date/end_date 或 start_time/end_time 的先后。",
    "110003": "缩短查询窗口后重试。",
    "120001": "用 `gangtise.reference.securities_search()` 确认代码与后缀（如 600519.SH / 00700.HK）。",
    "130001": "未找到数据——先核对查询条件；EDE 指标端点此码也可能是未开通该指标权限，仍失败联系客户经理。",
    "130002": "确认下载 ID 有效且本账号可见；下载类还需检查 file_type 取值是否合法（非法 file_type 也归此码）。",
    "130003": "该条记录可能未附带文件。",
    # 下载类各有各的 ID 参数（report_id / announcement_id / chunk_id / summary_id /
    # conference_id / record_id / file_id / article_id / independent_opinion_id）；
    # data_id 是异步 *_check 用的，不产生此码。
    "130004": "下载 ID 需为数字，检查该方法的 *_id 参数是否传对。",
    "130005": "对照方法 docstring 检查 file_type / content_type 取值。",
    "140001": "稍后用对应 *_check 方法查询。",
    "140002": "异步生成失败（终态）——换参数重新提交，重试同一 data_id 不会变。",
    # ── 接口专有层 2xxxxx ──
    "210001": "换一篇，或改用对应 list 方法取正文摘要。",
    "220001": "改用对应 list 方法取正文摘要。",
    "230001": "只有自己上传的文件可下载。",
    "240001": "换更早的 period（如 2025q3 → 2025interim）。",
    "240002": "改述后重新提交。",
    "240003": "对照方法 docstring 检查取值。",
    "250001": "检查 resource_type 与 source_id 组合（两者都来自 knowledge_batch 返回）。",
    # ── 旧码（2026-07-20 实测仍在线，或历史遗留） ──
    "0000001007": "请求未携带 Bearer token，检查 GANGTISE_TOKEN 或 AK/SK 是否已设置。",
    "0000001008": "Token 已失效（多为他处登录挤掉本会话）；有 AK/SK 时 SDK 会自动重新登录重试一次，否则请重新登录。",
    "900001": "对照方法签名检查必填参数。",
    "900002": "请求方法不正确（服务端 msg 为「请求类型有误」）——出现此码说明服务端行为已变化，请带 trace 报障。",
    "903301": "次日再试，或联系客户经理提额。",
    # EDE 专有旧码，未被 2026-07-17 重排收编，但仍是 indicator 取数的主要报错。
    "410001": "补齐 indicator / security；time_series 不支持「多指标 × 多证券」，改用 gangtise.indicator.cross_section()。",
    "410106": "读 `gangtise.indicator.search(raw=True)` 的 parameterList，用 indicator_param 补上 required=True 的参数（如 periodNum / startDate / fiscalYear）。",
    "410004": "换证券或日期确认该条件下本应有数据；仍失败多为未开通该指标，联系客户经理。",
    "410110": "稍后用对应 *_check 方法查询。",
    "410111": "终态，换参数后重新提交，重试同一请求不会变。",
    "430004": "确认 report_id 有效，或更换 file_type 重试（官方未文档化错误码）。",
    "430007": "缩短日期范围或调小 limit。",
    "433007": "检查 resource_type 与 source_id 组合（两者都来自 knowledge_batch 返回）。",
    "8000014": "检查 GANGTISE_ACCESS_KEY 是否正确、是否与 SECRET_KEY 写反。",
    "8000015": "检查 GANGTISE_SECRET_KEY 是否正确、是否与 ACCESS_KEY 写反。",
    "8000016": "联系客户经理核查账号状态。",
    "8000018": "联系客户经理续期。",
    "999995": "联系客户经理充值，或缩小查询范围降低消耗。",
    "999997": "联系客户经理开通。",
    "10011401": "联系客户经理开通白名单。",
}

# Context-specific override for the EDE indicator endpoints, where 999999 means
# "no data for this query", not the generic system error above.
EDE_NO_DATA_HINT = (
    "EDE 的 999999 多为查询无数据（节假日 / 未来日期 / 未覆盖标的）"
    "——先检查查询条件，确认应有数据再重试。"
)

# Override for per-call billed (no-replay) endpoints: the SDK deliberately did
# not retry because the request may already have executed and billed — the
# generic "请稍后重试" would invite a manual double-bill.
NO_REPLAY_UNCERTAIN_HINT = (
    "Gangtise 系统错误；该接口按次计费且此请求可能已被服务端执行"
    "（SDK 按 no-replay 策略未自动重试）——请先核实结果/扣费，再决定是否手动重试。"
)

# Override for an error surfaced from a FOLLOWED redirect/presigned target: the
# billed upstream already executed successfully (the download 3xx'd/returned a
# {url} past it), so the generic "请稍后重试" / "会自动重新登录重试" hints would
# invite the user to re-issue the whole download and re-bill the upstream. The SDK
# does NOT auto-replay such an error (see ApiError.from_followed_target).
FOLLOWED_TARGET_HINT = (
    "该错误来自下载跳转后的目标（计费上游此前已成功执行）——SDK 不会自动重放上游。"
    "请勿据此重试整个下载，否则会重新调用（并可能重新计费）已执行的上游；"
    "请先核实结果/扣费，再决定是否手动重试。"
)


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
        retry_after_ms: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details
        # Server-specified Retry-After (ms) so the transport backoff can honor it
        # instead of the exponential schedule.
        self.retry_after_ms = retry_after_ms
        # Set by the download layer when this error was surfaced from a FOLLOWED
        # redirect/presigned target (i.e. past the billed upstream request that
        # already succeeded). The upstream retry loop must never replay the billed
        # endpoint for such an error — ANY code (auth 0000001008, retryable 999999,
        # or other), since the billed request already ran; replaying double-bills.
        self.from_followed_target = False
        self.hint: str | None = ERROR_HINTS.get(code) if code else None

    @property
    def trace_id(self) -> str | None:
        """Server-side correlation id from the 2026-07-17 envelope
        (``{code, errorType, msg, status, data, traceId}``). Read off ``details``
        rather than threading another constructor arg through every call site.
        Worth surfacing: it is the only handle Gangtise support can trace a
        failure by."""
        if not isinstance(self.details, dict):
            return None
        value = self.details.get("traceId")
        return str(value) if isinstance(value, (str, int)) else None

    def __str__(self) -> str:
        base = super().__str__()
        trace = self.trace_id
        if trace:
            base = f"{base} [trace {trace}]"
        return f"{base} — {self.hint}" if self.hint else base
