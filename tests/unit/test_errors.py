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
