from __future__ import annotations

import os

from _utils import show_result

from gangtise_openapi import ApiError, gangtise


def main():
    data_id = os.environ.get("GANGTISE_SAMPLE_EARNINGS_REVIEW_DATA_ID")
    if not data_id:
        raise SystemExit(
            "Set GANGTISE_SAMPLE_EARNINGS_REVIEW_DATA_ID to a dataId returned by the corresponding wait=False sample."
        )
    try:
        result = gangtise.ai.earnings_review_check(
            data_id=data_id,
        )
    except ApiError as exc:
        if exc.code != "410110":
            raise
        result = {"data_id": data_id, "status": "pending", "message": str(exc)}
    show_result(result, __file__)


if __name__ == "__main__":
    main()
