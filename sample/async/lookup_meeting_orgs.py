"""lookup.meeting_orgs — 会议主办机构字典（本地数据, 无网络请求, 返回 DataFrame）。

返回 id/name 两列, 可作为会议类接口机构过滤参数的取值来源。
本接口无业务参数。同步用法相同, 路径为 gangtise.lookup.meeting_orgs(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 最简调用: 取全部会议主办机构字典（id/name）
    show_result(await gangtise.async_.lookup.meeting_orgs(), __file__)

    # 其余可选参数:
    #   raw=True   True=返回服务端原始 data（list）, 不转 DataFrame


if __name__ == "__main__":
    asyncio.run(main())
