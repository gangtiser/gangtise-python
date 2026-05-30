"""quote.realtime — 实时行情快照（A 股 / 港股 / 美股）, 返回 DataFrame。

通过多组示例覆盖全部参数；可选参数的取值范围已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
security 既可传具体代码（支持列表）, 也可传市场关键词整体取该市场快照。
异步用法相同, 路径为 gangtise.async_.quote.realtime(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 单只 A 股实时快照
    show_result(
        gangtise.quote.realtime(
            security="600519.SH",  # 证券代码, 支持单值或列表; 也可传市场关键词
        ),
        __file__,
    )

    # 示例 2 · 跨市场多只证券（列表入参）+ 指定返回字段
    show_result(
        gangtise.quote.realtime(
            security=["000001.SZ", "00700.HK", "AAPL.O"],  # A 股 / 港股 / 美股混合, 支持单值或列表
            field=["securityCode", "securityName", "price", "changeRatio", "volume"],  # 返回字段
        ),
        __file__,
    )

    # 示例 3 · 市场关键词取整体快照 + 原始返回
    show_result(
        gangtise.quote.realtime(
            security="hkStocks",  # 市场关键词: aShares=全 A 股 / hkStocks=全港股 / usStocks=全美股
            raw=True,  # True=返回服务端原始 data（含 fieldList/list 矩阵）, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选用法:
    #   security="aShares"        取全 A 股实时快照（市场关键词, 等价 hkStocks/usStocks）
    #   field=<字段名或列表>       仅返回所需字段; 省略则用服务端默认字段


if __name__ == "__main__":
    main()
