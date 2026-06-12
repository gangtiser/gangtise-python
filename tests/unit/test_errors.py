import pytest

from gangtise_openapi._errors import (
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
    err = ApiError("permission denied", code="999997")
    assert "未开通" in err.hint
    assert "未开通" in str(err)


@pytest.mark.parametrize(
    ("code", "fragment"),
    [
        ("410004", "数据未找到"),
        ("430004", "file_type"),
        ("430007", "缩短日期范围"),
        ("433007", "resourceType"),
        ("10011401", "白名单"),
    ],
)
def test_api_error_ts_v0_15_1_hints(code, fragment):
    # ERROR_HINTS catch-up with TS v0.15.1 (errors.ts).
    err = ApiError("boom", code=code)
    assert err.hint is not None
    assert fragment in err.hint
    assert fragment in str(err)


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
