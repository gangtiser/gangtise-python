# ruff: noqa: RUF001, RUF003
# (Disabled file-wide: the hint fixtures quote the server's own Chinese error
# messages verbatim, and the comments explaining them use fullwidth punctuation.)
import pytest

from gangtise_openapi._errors import (
    ERROR_HINTS,
    ApiError,
    ConfigError,
    DownloadError,
    GangtiseError,
    ValidationError,
)


def test_exception_hierarchy():
    assert issubclass(ConfigError, GangtiseError)
    assert issubclass(ApiError, GangtiseError)
    assert issubclass(ValidationError, GangtiseError)
    assert issubclass(DownloadError, GangtiseError)


def test_api_error_carries_metadata():
    err = ApiError("boom", code="999997", status_code=403, details={"raw": "x"})
    assert err.code == "999997"
    assert err.status_code == 403
    assert err.details == {"raw": "x"}


def test_api_error_known_code_attaches_hint():
    # v0.28.0 reworded every hint to give the next ACTION rather than restate the
    # server's msg — "no permission — 未开通该接口权限" was a stutter.
    err = ApiError("permission denied", code="999997")
    assert "联系客户经理" in err.hint
    assert "联系客户经理" in str(err)


@pytest.mark.parametrize(
    ("code", "fragment"),
    [
        ("410004", "未开通该指标"),
        ("430004", "file_type"),
        ("430007", "缩短日期范围"),
        ("433007", "resource_type"),
        ("10011401", "白名单"),
    ],
)
def test_api_error_ts_v0_15_1_hints(code, fragment):
    # ERROR_HINTS catch-up with TS v0.15.1 (errors.ts).
    err = ApiError("boom", code=code)
    assert err.hint is not None
    assert fragment in err.hint
    assert fragment in str(err)


def test_api_error_token_invalidation_hint():
    # 0000001008 = server-side token invalidation (TS v0.17.2 errors.ts); the
    # SDK auto re-logins and replays once when AK/SK are present.
    err = ApiError("boom", code="0000001008")
    assert err.hint is not None
    assert "失效" in err.hint


def test_api_error_unknown_code_no_hint():
    err = ApiError("weird", code="123456")
    assert err.hint is None
    assert str(err) == "weird"


def test_api_error_no_code():
    err = ApiError("network down")
    assert err.code is None
    assert err.hint is None


def test_config_error_subclass_only():
    with pytest.raises(GangtiseError):
        raise ConfigError("missing key")


# ── TS v0.28.0: traceId is the only handle Gangtise support can trace a failure by ──


def test_api_error_exposes_trace_id_from_envelope():
    err = ApiError(
        "系统错误",
        code="999999",
        details={"code": 999999, "msg": "系统错误", "traceId": "830965044897325056"},
    )
    assert err.trace_id == "830965044897325056"
    assert "[trace 830965044897325056]" in str(err)


def test_api_error_trace_id_coerces_numeric_envelope_value():
    err = ApiError("boom", code="999999", details={"traceId": 830965044897325056})
    assert err.trace_id == "830965044897325056"


@pytest.mark.parametrize("details", [None, {}, {"traceId": None}, "not-a-dict"])
def test_api_error_trace_id_absent(details):
    err = ApiError("boom", code="999999", details=details)
    assert err.trace_id is None
    assert "[trace" not in str(err)


# ── TS v0.28.0: the 2026-07-17 three-tier error-code overhaul ──
# 999xxx service layer / 1xxxxx business-common layer / 2xxxxx endpoint-specific.

_NEW_CODES = (
    [f"9990{n:02d}" for n in range(1, 17)]
    + ["999999"]
    + [f"10000{n}" for n in range(1, 7)]
    + ["110001", "110002", "110003", "120001"]
    + [f"13000{n}" for n in range(1, 6)]
    + ["140001", "140002"]
    + ["210001", "220001", "230001", "240001", "240002", "240003", "250001"]
)


def test_new_code_table_covers_all_41_public_codes():
    assert len(_NEW_CODES) == 41
    missing = [code for code in _NEW_CODES if code not in ERROR_HINTS]
    assert missing == []


@pytest.mark.parametrize(
    ("code", "fragment"),
    [
        # Both generations stay listed: probed 2026-07-20 the rollout is partial —
        # the business layer answers with new codes while the token filter still
        # emits the legacy ones.
        ("0000001007", "GANGTISE_TOKEN"),
        ("0000001008", "重新登录"),
        ("999002", "重新登录"),
        ("999011", "GANGTISE_SECRET_KEY"),
        # EDE legacy codes, never folded into the 2026-07-17 renumbering but the
        # two most common indicator failures.
        ("410001", "indicator"),
        ("410106", "indicator_param"),
        # SDK wording, not CLI wording.
        ("130002", "file_type"),
        ("110001", "*_date"),
        ("110002", "start_time"),
    ],
)
def test_v0_28_hints(code, fragment):
    err = ApiError("boom", code=code)
    assert err.hint is not None
    assert fragment in err.hint


def test_900002_hint_states_the_probed_meaning():
    # Probed by the CLI 2026-07-20: the server uses 900002 for "请求方法不正确"
    # (HTTP 405). The old table said "请求缺少 uid", which sends debugging the
    # wrong way entirely.
    hint = ApiError("boom", code="900002").hint
    assert hint is not None
    assert "uid" not in hint
    assert "方法" in hint


# ── message-level hints (CLI v0.34.1, rules split per gangtise-mcp C7) ──


@pytest.mark.parametrize(
    ("message", "must_contain", "must_not_contain"),
    [
        # 拼接句：能唯一确定该换 reportDate。
        (
            "不支持参数 tradeDate; 缺少必填参数 reportDate",
            "要的是 reportDate",
            "不接受 tradeDate，而 cross_section",
        ),
        # 半句「缺 reportDate」：同样确定。
        ("缺少必填参数:reportDate", "要的是 reportDate", None),
        # 拼接句：拒 reportDate 且缺 tradeDate ⇒ 删掉 reportDate 就好。
        (
            "不支持参数 reportDate; 缺少必填参数 tradeDate",
            "要的是 tradeDate",
            "还需要 tradeDate",
        ),
        # 半句「拒 reportDate」：删掉是对的，但不能承诺删完就出数。
        ("指标 x 不支持参数 reportDate", "不接受 reportDate", "要的是 tradeDate"),
        # 🔴 半句「拒 tradeDate」：只证明 tradeDate 被拒，推不出要 reportDate。
        # 这是 gangtise-mcp 2026-08-15 在 scr_exchg_mkt 上抓到的形态——它的
        # parameterList 是空的，照断言式提示去补 reportDate 会再次被拒。
        (
            "指标 scr_exchg_mkt 不支持参数 tradeDate",
            "不接受 tradeDate",
            "要的是 reportDate",
        ),
        # 半句「缺 tradeDate」：两个日期都必填那类。
        ("缺少必填参数: tradeDate", "还需要 tradeDate", "不接受"),
    ],
)
def test_message_hint_rules_do_not_assert_a_key_the_message_does_not_name(
    message, must_contain, must_not_contain
):
    hint = ApiError(message, code="100003").hint
    assert hint is not None
    assert must_contain in hint
    if must_not_contain is not None:
        assert must_not_contain not in hint


def test_half_sentence_tradedate_hint_offers_both_working_routes():
    # It cannot say which key to use, so it must give routes that are known to
    # work: the explicit empty-param opt-out, and the time-series endpoint.
    hint = ApiError("不支持参数 tradeDate", code="100003").hint
    assert hint is not None
    assert "{}" in hint
    assert "time_series" in hint


def test_joined_sentence_wins_over_the_half_sentence_rule():
    # Rule order is load-bearing: the joined sentence contains the half sentence's
    # pattern too, and the joined reading is the more specific one.
    hint = ApiError("不支持参数 tradeDate; 缺少必填参数 reportDate", code="100003").hint
    assert hint is not None and "要的是 reportDate" in hint


def test_report_date_message_hint_beats_the_generic_code_hint():
    # 100003 is the catch-all for every EDE input error, so its per-code hint can
    # only be generic. The message is what identifies this cause — and it names the
    # missing parameter without saying which kwarg supplies it.
    error = ApiError("不支持参数 tradeDate; 缺少必填参数 reportDate", code="100003")
    assert error.hint is not None
    assert "indicator_param" in error.hint
    assert error.hint != ERROR_HINTS["100003"]


def test_report_date_message_hint_also_fires_on_100001():
    # The server sends the same sentence under either code: is_op_rev answers
    # 100003, div_cash_yld answers 100001 (probed by the CLI 2026-08-15).
    error = ApiError("缺少必填参数:reportDate", code="100001")
    assert error.hint is not None
    assert "reportDate" in error.hint
    assert error.hint != ERROR_HINTS["100001"]


def test_report_date_hint_does_not_claim_a_code_prefix_rule():
    # A 170-indicator survey killed the tidy "is_*/bs_*/cf_* need reportDate" story:
    # 7 finc_* and 3 div_* want reportDate while 8 is_* and 4 cf_* want tradeDate.
    # The hint must point at parameterList instead of asserting a prefix rule.
    hint = ApiError("缺少必填参数 reportDate", code="100003").hint
    assert hint is not None
    assert "parameterList" in hint


def test_unrelated_message_keeps_the_per_code_hint():
    assert ApiError("参数值非法", code="100003").hint == ERROR_HINTS["100003"]


def test_message_hint_does_not_fire_without_a_code():
    assert ApiError("缺少必填参数 reportDate").hint is None


def test_call_site_override_still_wins_over_the_message_hint():
    # A call site with more context assigns .hint after construction; precedence is
    # override > message > per-code.
    error = ApiError("缺少必填参数 reportDate", code="100003")
    error.hint = "context-specific"
    assert error.hint == "context-specific"


def test_message_hint_outcome_is_independent_of_rule_order():
    # The discriminator between a joined sentence and a half sentence is encoded in
    # each rule's `not_match`, not in "the more specific rule happens to be listed
    # first". Reversing the list must change nothing — otherwise a future reorder
    # (or an insertion in the middle) silently re-routes a hint.
    from gangtise_openapi._errors import _MESSAGE_HINTS, _message_hint

    shapes = [
        "不支持参数 tradeDate; 缺少必填参数 reportDate",
        "缺少必填参数:reportDate",
        "不支持参数 reportDate; 缺少必填参数 tradeDate",
        "指标 x 不支持参数 reportDate",
        "指标 scr_exchg_mkt 不支持参数 tradeDate",
        "缺少必填参数: tradeDate",
        # Three clauses: the caller tried BOTH date keys on an indicator that takes
        # neither. This is the shape where two rules used to fire at once and list
        # order picked the winner.
        "不支持参数 tradeDate; 不支持参数 reportDate; 缺少必填参数 fiscalYear",
        "参数值非法",
    ]
    baseline = [_message_hint("100003", m) for m in shapes]
    _MESSAGE_HINTS.reverse()
    try:
        reversed_out = [_message_hint("100003", m) for m in shapes]
    finally:
        _MESSAGE_HINTS.reverse()
    assert reversed_out == baseline


def test_every_message_shape_matches_exactly_one_rule():
    # A strictly stronger property than the reverse test, over the same shapes:
    # "exactly one rule claims it" implies "order cannot change the outcome", and
    # it also catches a newly added rule that overlaps an existing one — which a
    # reverse-only test would let through as long as both orderings agreed.
    from gangtise_openapi._errors import _MESSAGE_HINTS

    shapes = [
        "不支持参数 tradeDate; 缺少必填参数 reportDate",
        "缺少必填参数:reportDate",
        "不支持参数 tradeDate",
        "不支持参数 reportDate; 缺少必填参数 tradeDate",
        "不支持参数 reportDate",
        "缺少必填参数 tradeDate",
        "不支持参数 tradeDate; 不支持参数 reportDate; 缺少必填参数 fiscalYear",
    ]
    for msg in shapes:
        matched = [
            i
            for i, (codes, patterns, forbidden, _) in enumerate(_MESSAGE_HINTS)
            if "100003" in codes
            and all(p.search(msg) for p in patterns)
            and not any(p.search(msg) for p in forbidden)
        ]
        assert len(matched) == 1, f"{msg!r} matched rules {matched}"


def test_both_keys_refused_routes_to_the_escape_hatch_rule():
    # 不支持 A; 不支持 B; 缺少 fiscalYear — the "delete reportDate and add what it
    # really wants" rule would be the unhelpful answer here: the message already
    # says what it wants. The non-assertive rule names the escape hatch and
    # fiscalYear, so it has to win.
    hint = ApiError(
        "不支持参数 tradeDate; 不支持参数 reportDate; 缺少必填参数 fiscalYear", code="100003"
    ).hint
    assert hint is not None
    assert "fiscalYear" in hint
    assert "{}" in hint
