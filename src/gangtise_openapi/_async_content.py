from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import anyio

from gangtise_openapi._errors import ApiError
from gangtise_openapi._logging import get_logger
from gangtise_openapi._transport import is_transient_error

logger = get_logger()

POLL_MAX_ATTEMPTS = 14
_INITIAL_DELAY_S = 5.0
_MAX_DELAY_S = 30.0
_GROWTH = 1.6

CODE_PENDING = "410110"
CODE_TERMINAL = "410111"


def next_delay_seconds(attempt: int) -> float:
    grown = _INITIAL_DELAY_S * (_GROWTH ** (attempt - 1))
    return min(_MAX_DELAY_S, float(round(grown)))


Fetcher = Callable[[], Any]
Sleeper = Callable[[float], None]


def _classify(error: ApiError) -> str:
    if error.code == CODE_PENDING:
        return "pending"
    if error.code == CODE_TERMINAL:
        return "terminal"
    return "other"


def _keep_waiting_on_transient(error: BaseException, attempt: int, max_attempts: int) -> None:
    """AI generation windows are exactly when the server is busiest: one 5xx /
    network blip (after the transport's own retries) must not void minutes of
    waiting — the dataId is still valid. Transient errors consume this attempt
    and polling continues; anything else (no credits, bad params) aborts."""
    if not is_transient_error(error):
        raise error
    logger.warning(
        "[gangtise] poll attempt %d/%d hit a transient error (%s); continuing to wait",
        attempt,
        max_attempts,
        str(error)[:80],
    )


def poll_content(
    fetch: Fetcher,
    *,
    sleep: Sleeper = time.sleep,
    max_attempts: int = POLL_MAX_ATTEMPTS,
) -> Any:
    last_pending: ApiError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fetch()
        except ApiError as error:
            kind = _classify(error)
            if kind == "terminal":
                raise ApiError(
                    "Content generation failed (terminal). Do not retry.",
                    code=CODE_TERMINAL,
                ) from error
            if kind == "other":
                _keep_waiting_on_transient(error, attempt, max_attempts)
            else:
                last_pending = error
        except Exception as error:
            # Network-level failure (not an ApiError) after transport retries.
            _keep_waiting_on_transient(error, attempt, max_attempts)
        else:
            if isinstance(result, dict) and result.get("content") is not None:
                return result
        if attempt < max_attempts:
            sleep(next_delay_seconds(attempt))
    raise ApiError(
        f"Content not available after {max_attempts} attempts",
        code=CODE_PENDING,
    ) from last_pending


AsyncFetcher = Callable[[], Any]


async def poll_content_async(
    fetch: AsyncFetcher,
    *,
    max_attempts: int = POLL_MAX_ATTEMPTS,
) -> Any:
    last_pending: ApiError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await fetch()
        except ApiError as error:
            kind = _classify(error)
            if kind == "terminal":
                raise ApiError(
                    "Content generation failed (terminal). Do not retry.",
                    code=CODE_TERMINAL,
                ) from error
            if kind == "other":
                _keep_waiting_on_transient(error, attempt, max_attempts)
            else:
                last_pending = error
        except Exception as error:
            # Network-level failure (not an ApiError) after transport retries.
            _keep_waiting_on_transient(error, attempt, max_attempts)
        else:
            if isinstance(result, dict) and result.get("content") is not None:
                return result
        if attempt < max_attempts:
            await anyio.sleep(next_delay_seconds(attempt))
    raise ApiError(
        f"Content not available after {max_attempts} attempts",
        code=CODE_PENDING,
    ) from last_pending
