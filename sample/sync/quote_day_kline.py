"""quote.day_kline — A 股日 K 线（SH/SZ/BJ）, 返回 DataFrame。

通过多组示例覆盖全部参数；可选参数的取值范围已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
security="all" 时按日期窗口自动分片（每片 1 个交易日）并并发拉取后合并。
异步用法相同, 路径为 gangtise.async_.quote.day_kline(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取单只 A 股最近一段日 K 线
    show_result(
        gangtise.quote.day_kline(
            security="000001.SZ",  # A 股代码, 后缀 .SH/.SZ/.BJ; 支持单值或列表; "all"=全市场
            start_date="2026-05-01",  # 开始日期 YYYY-MM-DD; 省略默认结束日往前 1 年
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD; 省略默认最新交易日
            limit=10,  # 单次返回条数上限; 默认 6000, 最大 10000
        ),
        __file__,
    )

    # 示例 2 · 多只证券（列表入参）+ 指定返回字段
    show_result(
        gangtise.quote.day_kline(
            security=["000001.SZ", "600519.SH"],  # 支持单值或列表
            start_date="2026-05-01",
            end_date="2026-05-28",
            field=[
                "tradeDate",
                "open",
                "close",
                "high",
                "low",
                "volume",
            ],  # 返回字段, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 原始返回（不转 DataFrame）
    show_result(
        gangtise.quote.day_kline(
            security="600519.SH",
            start_date="2026-05-20",
            end_date="2026-05-28",
            raw=True,  # True=返回服务端原始 data（含 fieldList/list 矩阵）, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选用法:
    #   security="all"            全市场: 配合 start_date/end_date 自动按 1 交易日/片分片并发拉取
    #   field=<字段名或列表>       仅返回所需字段（如 open/close/volume）; 省略则用服务端默认字段


if __name__ == "__main__":
    main()
