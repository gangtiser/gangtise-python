"""ai.earnings_review_check — 非阻塞查询财报点评结果（按 dataId 单次检查, 返回 dict）。

需要先运行 ai_earnings_review.py(wait=False)拿到 dataId, 通过环境变量
GANGTISE_SAMPLE_EARNINGS_REVIEW_DATA_ID 传入。code 410110=仍在生成(pending), 不抛错。
异步用法相同, 路径为 gangtise.async_.ai.earnings_review_check(...)。
"""

from __future__ import annotations

import asyncio
import os

from _utils import show_result

from gangtise_openapi import ApiError, gangtise


async def main():
    data_id = os.environ.get("GANGTISE_SAMPLE_EARNINGS_REVIEW_DATA_ID")
    if not data_id:
        raise SystemExit(
            "Set GANGTISE_SAMPLE_EARNINGS_REVIEW_DATA_ID to a dataId returned by the corresponding wait=False sample."
        )
    try:
        result = await gangtise.async_.ai.earnings_review_check(
            data_id=data_id,  # 异步生成任务 ID(由 earnings_review wait=False 返回)
            # raw=True  # 可选: 返回服务端原始 data
        )
    except ApiError as exc:
        if exc.code != "410110":  # 410110=内容仍在生成中(pending), 稍后重试; 其它码照常抛出
            raise
        result = {"data_id": data_id, "status": "pending", "message": str(exc)}
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
