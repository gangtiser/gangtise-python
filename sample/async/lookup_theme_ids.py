"""lookup.theme_ids — 题材/概念 ID 字典（本地数据, 无网络请求, 返回 DataFrame）。

返回 id/name 两列, 用于 ai.theme_tracking 的 theme_id、alternative.concept_info 的
concept_id 等入参取值（如 机器人=121000130）。
本接口无业务参数。同步用法相同, 路径为 gangtise.lookup.theme_ids(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 最简调用: 取全部题材/概念 ID 字典（id/name）
    show_result(await gangtise.async_.lookup.theme_ids(), __file__)

    # 其余可选参数:
    #   raw=True   True=返回服务端原始 data（list）, 不转 DataFrame


if __name__ == "__main__":
    asyncio.run(main())
