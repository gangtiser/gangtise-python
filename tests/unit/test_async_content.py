import pytest

from gangtise_openapi._async_content import (
    POLL_MAX_ATTEMPTS,
    next_delay_seconds,
    poll_content,
)
from gangtise_openapi._errors import ApiError


def test_poll_max_attempts():
    assert POLL_MAX_ATTEMPTS == 14


def test_next_delay_sequence():
    # 5s, 8s, 13s, 20s, 30s, 30s, ...
    sequence = [next_delay_seconds(attempt) for attempt in range(1, 8)]
    assert sequence == [5, 8, 13, 20, 30, 30, 30]


def test_poll_returns_on_first_ready():
    calls = []

    def fetch():
        calls.append(1)
        return {"content": "ready"}

    out = poll_content(fetch, sleep=lambda s: None)
    assert out == {"content": "ready"}
    assert len(calls) == 1


def test_poll_retries_on_410110_then_succeeds():
    state = {"i": 0}
    delays: list[float] = []

    def fetch():
        state["i"] += 1
        if state["i"] < 3:
            raise ApiError("pending", code="410110")
        return {"content": "done"}

    out = poll_content(fetch, sleep=delays.append)
    assert out == {"content": "done"}
    assert state["i"] == 3
    assert delays == [5.0, 8.0]


def test_poll_terminal_failure_raises_immediately():
    def fetch():
        raise ApiError("terminal", code="410111")

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    assert exc.value.code == "410111"


def test_poll_unrelated_error_propagates():
    def fetch():
        raise ApiError("auth bad", code="8000014")

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    assert exc.value.code == "8000014"


def test_poll_exhaustion_raises():
    def fetch():
        raise ApiError("pending", code="410110")

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    assert "14 attempts" in str(exc.value)


def test_poll_missing_content_keeps_polling():
    state = {"i": 0}

    def fetch():
        state["i"] += 1
        if state["i"] < 2:
            return {"content": None}
        return {"content": "ready"}

    out = poll_content(fetch, sleep=lambda s: None)
    assert out == {"content": "ready"}


def test_poll_tolerates_transient_error_and_continues():
    # TS v0.27.0 parity: one 5xx after the transport's own retries must not void
    # the wait — the dataId is still valid; the blip consumes one attempt.
    state = {"i": 0}

    def fetch():
        state["i"] += 1
        if state["i"] == 1:
            raise ApiError("upstream busy", status_code=503)
        return {"content": "done"}

    out = poll_content(fetch, sleep=lambda s: None)
    assert out == {"content": "done"}
    assert state["i"] == 2


def test_poll_tolerates_network_error_and_continues():
    import httpx

    state = {"i": 0}

    def fetch():
        state["i"] += 1
        if state["i"] == 1:
            raise httpx.ConnectError("refused")
        return {"content": "done"}

    out = poll_content(fetch, sleep=lambda s: None)
    assert out == {"content": "done"}


def test_poll_aborts_on_non_transient_error():
    def fetch():
        raise ApiError("no credits", code="999995", status_code=403)

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    assert exc.value.code == "999995"


def test_poll_transient_errors_still_bounded_by_max_attempts():
    state = {"i": 0}

    def fetch():
        state["i"] += 1
        raise ApiError("busy", status_code=503)

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None, max_attempts=3)
    # Transient errors consume attempts; after the budget the pending timeout raises.
    assert state["i"] == 3
    assert exc.value.code == "410110"


# ── TS v0.28.0: the 2026-07-17 renumbering of the async status codes ──
# Probed by the CLI 2026-07-20: the server still emits the legacy 410110/410111,
# so the new codes are a forward guard. Getting them wrong is expensive — a poll
# that does not recognize the pending code aborts a job already billed 50 credits.


def test_poll_treats_140001_as_pending():
    state = {"i": 0}

    def fetch():
        state["i"] += 1
        if state["i"] < 3:
            raise ApiError("生成中", code="140001", status_code=409)
        return {"content": "done"}

    out = poll_content(fetch, sleep=lambda s: None)
    assert out == {"content": "done"}
    assert state["i"] == 3


def test_poll_treats_140002_as_terminal():
    def fetch():
        raise ApiError("生成失败", code="140002", status_code=500)

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    assert exc.value.code == "140002"


def test_terminal_error_keeps_server_message_and_trace():
    # The terminal branch swallows the original error, so this line is the user's
    # only record of it — it must carry code / msg / traceId, and warn that
    # resubmitting re-bills.
    def fetch():
        raise ApiError(
            "敏感内容拦截",
            code="410111",
            status_code=400,
            details={"traceId": "830965044897325056"},
        )

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    text = str(exc.value)
    assert "敏感内容拦截" in text
    assert "830965044897325056" in text
    assert exc.value.trace_id == "830965044897325056"
