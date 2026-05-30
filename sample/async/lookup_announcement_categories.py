"""lookup.announcement_categories — 公告分类代码字典（本地数据, 无网络请求, 返回 DataFrame）。

返回 id/name/level/parentId 四列, 可作为公告类接口分类过滤参数的取值来源。
本接口无业务参数。同步用法相同, 路径为 gangtise.lookup.announcement_categories(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 最简调用: 取全部公告分类代码字典（id/name/level/parentId）
    show_result(await gangtise.async_.lookup.announcement_categories(), __file__)

    # 其余可选参数:
    #   raw=True   True=返回服务端原始 data（list）, 不转 DataFrame


if __name__ == "__main__":
    asyncio.run(main())
