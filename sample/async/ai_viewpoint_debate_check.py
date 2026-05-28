from __future__ import annotations

import asyncio
import os

from _utils import show_result

from gangtise_openapi import ApiError, gangtise


async def main():
    data_id = os.environ.get("GANGTISE_SAMPLE_VIEWPOINT_DEBATE_DATA_ID")
    if not data_id:
        raise SystemExit(
            "Set GANGTISE_SAMPLE_VIEWPOINT_DEBATE_DATA_ID to a dataId returned by the corresponding wait=False sample."
        )
    try:
        result = await gangtise.async_.ai.viewpoint_debate_check(
            data_id=data_id,
        )
    except ApiError as exc:
        if exc.code != "410110":
            raise
        result = {"data_id": data_id, "status": "pending", "message": str(exc)}
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
