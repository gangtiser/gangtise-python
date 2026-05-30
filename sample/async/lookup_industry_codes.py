"""lookup.industry_codes — 申万行业代码字典（本地数据, 无网络请求, 返回 DataFrame）。

返回 name/code 两列, 用于 ai.security_clue 的 gts_code 入参取值。
本接口无业务参数。同步用法相同, 路径为 gangtise.lookup.industry_codes(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 最简调用: 取全部申万行业代码字典（name/code）
    show_result(await gangtise.async_.lookup.industry_codes(), __file__)

    # 其余可选参数:
    #   raw=True   True=返回服务端原始 data（list）, 不转 DataFrame


if __name__ == "__main__":
    asyncio.run(main())
