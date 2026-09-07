# ruff: noqa: RUF001, RUF003
# (Disabled file-wide: ERROR_HINTS values are user-facing Chinese strings that
# intentionally use fullwidth punctuation, and the Chinese comments documenting
# each code group do the same.)
from __future__ import annotations

import re
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
    # 2026-08-09 起两种成因都实测到：整库未开通（如帕米尔专家纪要需单独购买）与
    # 单条记录不可见。list 撞上多为前者。
    "999004": "整库/整接口未开通（如帕米尔专家纪要需单独购买），或该条记录本账号不可见——list 撞上多为前者，先确认该数据库是否已开通。",
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
    # 2026-08-14 起 list 类端点把单页上限（50）也归到此码，不再只是「一次要太多行」。
    "100006": "缩短日期范围或调小 size / limit（list 类端点单页上限为 50，SDK 会自动翻页，直发 raw 请求时要自己遵守）。",
    # 按参数名判断，不要按域预判：ai.management_discuss_* 的 report_date 是 date 型，
    # 而同属 ai 的 knowledge_batch 收时间戳或 datetime。
    "110001": '看参数名：`*_date` 用 YYYY-MM-DD，`*_time` 用 "YYYY-MM-DD HH:mm:ss"（ai.knowledge_batch 与 insight 的 A 股公告接口收时间戳或 datetime，SDK 统一转 13 位毫秒）。',
    "110002": "起始晚于结束——检查 start_date/end_date 或 start_time/end_time 的先后。",
    # 超出的是账号数据权限的时间下界，不是单次窗口太宽——fiscal_year=2015 这种整个
    # 区间都在界外的请求，怎么缩窗口都还是这个码（CLI 实测 2026-08-08）。
    "110003": "查询时间超出本账号的数据权限范围——把日期移进范围内（整个区间都早于下界时缩短窗口无用），或联系客户经理开通更长历史。",
    "120001": "用 `gangtise.reference.securities_search()` 确认代码与后缀（如 600519.SH / 00700.HK）。",
    "130001": "未找到数据——先核对查询条件；EDE 指标端点此码也可能是未开通该指标权限，仍失败联系客户经理。",
    # 2026-08-14 起下载类把「file_type 非法」拆到 130005、「资源未生成」拆到 130003，
    # 但历史上两者都归过此码，所以提示保留对 file_type 的指引。
    "130002": "确认下载 ID 有效且本账号可见；下载类还需检查 file_type 取值是否合法。",
    "130003": "资源未生成或该条记录未附带文件——换一条有附件的记录（列表里 hasAttachment / hasFile 为 true 的），或稍后再试。",
    # 下载类各有各的 ID 参数（report_id / announcement_id / chunk_id / summary_id /
    # conference_id / record_id / file_id / article_id / independent_opinion_id）；
    # data_id 是异步 *_check 用的，不产生此码。
    "130004": "下载 ID 需为数字，检查该方法的 *_id 参数是否传对。",
    "130005": "对照方法 docstring 检查 file_type / content_type 取值。",
    "140001": "稍后用对应 *_check 方法查询。",
    # 两类来源共用此码：AI 异步生成失败，以及 EDE 的参数/表达式错误（CLI 实测
    # 2026-08-02：枚举越界、表达式语法错误）。两者都是终态、都不该重试。
    "140002": "终态失败，重试同一请求不会变——按 msg 改参数后重新提交；EDE 的指标参数名/枚举以 gangtise.indicator.search() 的 parameterList 为准。",
    # ── 接口专有层 2xxxxx ──
    "210001": "换一篇，或改用对应 list 方法取正文摘要。",
    "220001": "改用对应 list 方法取正文摘要。",
    "230001": "只有自己上传的文件可下载。",
    # 2026-08-07 新增码。私域模块，vault.wechat_* 就在这个模块下且明确要求「已绑定
    # 并激活群消息助理」，所以 SDK 够得着，不能当作不可达而不给提示。
    "230002": "微信账号未绑定——群消息类接口要求先在 Gangtise 端绑定并激活群消息助理、且助理已入群。",
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

# Hints keyed on the server's MESSAGE rather than its code. Used where one code
# covers many causes and only the message identifies which — 100003 is the
# catch-all for every EDE input error, so its per-code hint can only be generic.
#
# ⚠️ Each rule requires ALL of its patterns to match, and the order matters
# (first match wins). A single alternation would be wrong: the server sends both a
# JOINED sentence (「不支持参数 A; 缺少必填参数 B」, which pins down exactly which key
# to swap) and a HALF sentence (only「不支持参数 A」, which proves the key was
# rejected but says nothing about what to use instead). Asserting a replacement on
# the half sentence sends the caller to a key that will also be rejected — found by
# gangtise-mcp 2026-08-15 on `scr_exchg_mkt`, whose parameterList is EMPTY, where
# the assertive hint told the user to pass `reportDate` and that failed too. The
# CLI carried the single-alternation form through v0.34.1 and split it the same way
# in v0.35.0 `errors.ts`; see bug/closed.md U1.
#
# ⚠️ Do NOT restate any of this as a rule about code prefixes. Surveys say
# otherwise: most indicators take reportDate only, many take tradeDate only,
# div_cash_yld takes BOTH, div_cash_yr / div_cash_paid_ratio take NEITHER (they
# want fiscalYear), a family of frcst_* needs fiscalYear AND tradeDate, and a
# handful of static-attribute indicators take no parameter at all. Prefixes cut
# across it — some finc_* and div_* want reportDate while some is_* and cf_* want
# tradeDate. Every hint points at indicator.search's parameterList.
#
# ⚠️ Counts are deliberately NOT stated here. Every sweep so far has been a keyword
# sample, not an enumeration, and two of them disagreed on which static-attribute
# indicators exist (see bug/closed.md U2) — a number written here would read
# as exhaustive and be wrong the moment the catalogue changes.
_MULTI_NOTE = "以 gangtise.indicator.search() 返回的 parameterList 为准，别按指标 code 前缀推断。"

# Each entry is (codes, must-match patterns, must-NOT-match patterns, hint).
# The `not_match` half is what makes the split independent of list ORDER: the
# discriminator between「拼接句」and「半句」is the presence of the other half, and
# encoding that explicitly beats relying on a more-specific rule being listed first
# (the CLI converged on the same `notMatch` shape independently). A test reverses
# this list and asserts identical outcomes.
_MESSAGE_HINTS: list[
    tuple[frozenset[str], tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...], str]
] = [
    # 点名「缺 reportDate」——无论拼接句还是半句，都能唯一确定要的是 reportDate。
    (
        frozenset({"100001", "100003"}),
        (re.compile(r"缺少必填参数[:：]?\s*reportDate"),),
        (),
        "msg 点名的那个指标要的是 reportDate（报告期），不是 date 下发的 tradeDate："
        '给它补 indicator_param={"<指标code>": {"reportDate": "YYYY-MM-DD"}}'
        '（条件选股按变量写，如 {"F1": {"reportDate": ...}}），date 仍要保留。' + _MULTI_NOTE,
    ),
    # 拼接句：拒收 reportDate **且**缺 tradeDate ⇒ 这是个交易日指标，删掉多传的
    # reportDate 即可——删掉后 SDK 会自动把 date 作为 tradeDate 注入，那半句一并消失。
    (
        frozenset({"100001", "100003"}),
        (
            re.compile(r"不支持参数\s*reportDate"),
            re.compile(r"缺少必填参数[:：]?\s*tradeDate"),
        ),
        (),
        "msg 点名的那个指标要的是 tradeDate（交易日），不吃 reportDate："
        "把 indicator_param 里该指标的 reportDate 删掉即可——删掉后 date 会自动作为 "
        "tradeDate 下发，不需要另外补。" + _MULTI_NOTE,
    ),
    # 半句：只说拒收 reportDate。删掉是对的，但**不能承诺**删掉就能出数——该指标可能
    # 连 tradeDate 都不吃，删完会撞上下面那条。
    (
        frozenset({"100001", "100003"}),
        (re.compile(r"不支持参数\s*reportDate"),),
        (
            re.compile(r"缺少必填参数[:：]?\s*tradeDate"),
            # 两个键都被拒时（如「不支持 tradeDate; 不支持 reportDate; 缺少 fiscalYear」）
            # 让给下一条规则：它点名了逃生口与 fiscalYear，是更有用的那条。缺了这一条，
            # 该 msg 会同时命中两条规则、由列表顺序决定胜负。
            re.compile(r"不支持参数\s*tradeDate"),
        ),
        "msg 点名的那个指标不接受 reportDate：先把 indicator_param 里该指标的 reportDate "
        "删掉，再按它真正要的键补（可能是 tradeDate，也可能是 fiscalYear，"
        "或者一个日期都不要）。" + _MULTI_NOTE,
    ),
    # 半句：只说拒收 tradeDate，没说缺什么。**这一条最容易断错**，所以只描述现状 +
    # 给出确定可行的两条路，不断言该换成哪个键。
    (
        frozenset({"100001", "100003"}),
        (re.compile(r"不支持参数\s*tradeDate"),),
        (re.compile(r"缺少必填参数[:：]?\s*reportDate"),),
        "msg 点名的那个指标不接受 tradeDate，而 cross_section / screener 默认会把 date "
        "作为 tradeDate 下发给每个指标。两条路：① 显式传空参数抑制注入——"
        'indicator_param={"<指标code>": {}}（条件选股写 {"F1": {}}），'
        "适用于一个日期都不要的静态属性（上市日期 / 上市市场 / 主营业务 等）；"
        "只要 fiscalYear 的（股利支付率 / 年度现金分红总额）则写 "
        '{"<指标code>": {"fiscalYear": "2025"}}。'
        "② 改用 gangtise.indicator.time_series()，它不下发单日期参数。" + _MULTI_NOTE,
    ),
    # 半句：没有任何键被拒，只是缺 tradeDate。SDK 见到已声明的 reportDate 就不再注入
    # tradeDate，所以这是「两个日期都必填」那类指标（如 div_cash_yld）的形态。
    (
        frozenset({"100001", "100003"}),
        (re.compile(r"缺少必填参数[:：]?\s*tradeDate"),),
        (re.compile(r"不支持参数\s*reportDate"),),
        "msg 点名的那个指标还需要 tradeDate，而 SDK 这次没有注入它——因为你已经给该指标"
        '传了 reportDate（或用 "tradeDate": None 显式抑制过）。'
        '在 indicator_param 里该指标下再补一条 "tradeDate": "YYYY-MM-DD" 即可'
        "（两个日期都必填的指标就是这个形态）。" + _MULTI_NOTE,
    ),
]


def _message_hint(code: str | None, message: str) -> str | None:
    """First rule whose `match` patterns ALL hit and whose `not_match` patterns all
    miss. The `not_match` half makes the outcome independent of rule order."""
    if code is None:
        return None
    for codes, patterns, forbidden, hint in _MESSAGE_HINTS:
        if (
            code in codes
            and all(p.search(message) for p in patterns)
            and not any(p.search(message) for p in forbidden)
        ):
            return hint
    return None


# Context-specific override for the EDE data-fetch endpoints (cross-section /
# time-series), where 999999 means "no data for this query", not the generic
# system error above. indicator.search keeps the generic hint — it takes only a
# keyword, so date/scope/param guidance would be nonsense (TS v0.28.2).
EDE_NO_DATA_HINT = (
    "EDE 的 999999 多为查询无数据——先核对："
    "日期匹配指标周期（财务/MRQ 用报告期末如 2025-12-31、日频估值用交易日）、"
    "标的在 scopeList 覆盖内、parameterList 中 required 参数已补；确认应有数据再重试。"
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
        # Set when this error is about a RESPONSE SHAPE the endpoint cannot
        # legitimately produce (a ``data: null`` where ``{list}`` is contractual),
        # never about the request. A caller that fans a query out — the K-line
        # sharder — must treat it as ONE bad shard, not as the systemic failure
        # (rate limit, no permission, retries exhausted) that stops the remaining
        # shards from being dispatched at all (TS v0.38.0 ``markStructural``).
        self.structural = False
        # Precedence: message-specific > per-code. The message rule identifies a
        # narrower cause than the code alone (one code, many causes). A call site
        # with even more context still wins — it assigns ``.hint`` after construction.
        self.hint: str | None = _message_hint(code, message) or (
            ERROR_HINTS.get(code) if code else None
        )

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
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value)
        # Fall back to the envelope the payload was unwrapped from. A shape error
        # raised past the transport only ever holds the inner payload, which
        # carries no traceId of its own — see _transport.TracedDict.
        carried = getattr(self.details, "envelope_trace_id", None)
        return str(carried) if isinstance(carried, str) else None

    def __str__(self) -> str:
        base = super().__str__()
        trace = self.trace_id
        if trace:
            base = f"{base} [trace {trace}]"
        return f"{base} — {self.hint}" if self.hint else base
