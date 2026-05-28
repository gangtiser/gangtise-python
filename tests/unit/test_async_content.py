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
