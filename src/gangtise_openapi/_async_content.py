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
# The 2026-07-17 overhaul renumbers these to 140001 RESULT_GENERATING (409) and
# 140002 PROCESSING_FAILED (500). Probed by the CLI 2026-07-20: the server still
# answers with the legacy codes, so the new ones are a forward guard — but an
# expensive one to omit. A poll that does not recognize the pending code aborts on
# the first attempt and voids a job already billed 50 credits.
PENDING_CODES = frozenset({CODE_PENDING, "140001"})
FAILED_CODES = frozenset({CODE_TERMINAL, "140002"})


def next_delay_seconds(attempt: int) -> float:
    grown = _INITIAL_DELAY_S * (_GROWTH ** (attempt - 1))
    return min(_MAX_DELAY_S, float(round(grown)))


Fetcher = Callable[[], Any]
Sleeper = Callable[[float], None]


def _classify(error: ApiError) -> str:
    if error.code in PENDING_CODES:
        return "pending"
    if error.code in FAILED_CODES:
        return "terminal"
    return "other"


def _terminal_error(error: ApiError) -> ApiError:
    """Re-raise a terminal generation failure without swallowing what the server
    said. This error replaces the original, so it has to carry code / msg /
    traceId — otherwise the failure is unreportable to Gangtise support. It also
    has to warn about the cost: re-checking the dataId is free, but resubmitting
    the generation job bills again for a verdict that will not change."""
    return ApiError(
        f"Content generation failed (terminal {error.code}): {error.args[0]}. "
        "Re-checking this dataId will not change it; resubmitting the generation "
        "task bills again for the same result — change the parameters first.",
        code=error.code,
        status_code=error.status_code,
        details=error.details,
    )


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
                raise _terminal_error(error) from error
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
                raise _terminal_error(error) from error
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
