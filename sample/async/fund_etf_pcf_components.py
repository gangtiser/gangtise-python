"""fund.etf_pcf_components — ETF 申赎成分清单（只有最新一份清单；componentCode 由 SDK 按名称匹配补上）。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.etf_pcf_components(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用
    show_result(
        await gangtise.async_.fund.etf_pcf_components(
            security="510300.SH",  # ETF 交易代码, 后缀大写（.SH / .SZ）; 单值或列表
        ),
        __file__,
    )

    # 示例 2 · 接口原样返回（不补 componentCode、不转 DataFrame）
    show_result(
        await gangtise.async_.fund.etf_pcf_components(
            security="159967.SZ",  # ETF 交易代码, 后缀大写（.SH / .SZ）; 单值或列表
            component_code=False,  # False=不按名称匹配成分代码, 不发额外的（免费）查询
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
