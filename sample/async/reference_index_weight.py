"""reference.index_weight — 指数成分股及权重（免费, 返回 DataFrame）。

🔴 只有每月最后一个交易日有数: 其他日期与写错的指数代码都返回空结果、不报错(SDK 告警点名)。
通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.reference.index_weight(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 沪深300 某月末的成分股权重(weight 单位 %, 合计约 100)
    show_result(
        await gangtise.async_.reference.index_weight(
            index="000300.SH",  # 指数代码, 单值或列表; 不确定用 securities_search(category="index")
            date="2026-10-30",  # 交易日, 须是某月最后一个交易日
        ),
        __file__,
    )

    # 示例 2 · 多个指数合在一张表里(按 indexCode 区分) + 原始返回
    show_result(
        await gangtise.async_.reference.index_weight(
            index=["000300.SH", "000905.SH"],
            date="2026-09-30",
            raw=True,  # True=返回服务端原始 data({total, list}), 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
