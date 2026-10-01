"""quote.index_day_kline — 指数日 K 线（SH/SZ/BJ 指数）, 返回 DataFrame。

⚠️ 已下线（deprecated）: 新代码直接用 quote.day_kline 传同样的指数代码——本接口没有
day_kline 做不到的能力, 返回字段与 day_kline 相同, 不含指数名称。
要指数名称用 reference.securities_search(keyword=<指数代码>, category="index") 的 gtsName。
没有全市场关键字: 接口对 "all" 返回空结果、不报错, SDK 在发请求前直接拒绝;
全部沪深京指数目前没有一次拿全的写法, 要逐个传指数代码。

通过几组示例演示常用参数，可选参数的取值范围写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.quote.index_day_kline(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 沪深 300 指数最近一段日 K 线
    show_result(
        await gangtise.async_.quote.index_day_kline(
            security="000300.SH",  # 指数代码, 后缀 .SH/.SZ/.BJ; 支持单值或列表; 不收 "all"
            start_date="2026-05-01",  # 开始日期 YYYY-MM-DD; 省略默认结束日往前 1 年
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD; 省略默认最新交易日
            limit=10,  # 单次返回条数上限; 默认 6000, 最大 10000
        ),
        __file__,
    )

    # 示例 2 · 多只指数（列表入参）+ 指定返回字段
    show_result(
        await gangtise.async_.quote.index_day_kline(
            security=["000300.SH", "399006.SZ"],  # 支持单值或列表（沪深300 / 创业板指）
            start_date="2026-05-01",
            end_date="2026-05-28",
            field=[
                "securityCode",  # 多只时 SDK 会自动补 securityCode / tradeDate; 写全了就不补
                "tradeDate",
                "open",
                "close",
                "volume",
            ],  # 返回字段, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 原始返回（不转 DataFrame）
    show_result(
        await gangtise.async_.quote.index_day_kline(
            security="000001.SH",  # 上证综指
            start_date="2026-05-20",
            end_date="2026-05-28",
            raw=True,  # True=返回服务端原始 data（含 fieldList/list 矩阵）, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选用法:
    #   field=<字段名或列表>       仅返回所需字段（字段同 day_kline, 不含指数名称）; 省略则用服务端默认字段


if __name__ == "__main__":
    asyncio.run(main())
