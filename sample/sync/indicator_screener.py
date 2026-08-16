"""indicator.screener — 条件选股: 按表达式从证券/板块范围里筛出命中的股票（返回 DataFrame）。

indicator 是 {变量: 指标码} 绑定, 变量名必须是 F + 正整数; expression 用这些变量组合筛选。
同一个指标可以绑到两个变量取不同参数, 所以 indicator_param 按**变量**索引, 不是按 code。
输出同 cross_section 的宽表（每行一只命中的证券）。
异步用法相同, 路径为 gangtise.async_.indicator.screener(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 单条件筛选
    show_result(
        gangtise.indicator.screener(
            date="2026-08-07",  # 数据日期 YYYY-MM-DD（必填）; 作为每个变量的 tradeDate 下发
            expression="F1 >= 500",  # 筛选表达式, 只能引用已绑定的变量
            indicator={"F1": "qte_mkt_cptl"},  # 变量 → 指标码
            security="600519.SH",  # 证券代码或板块 ID（reference.sector_search 的 sectorId）
        ),
        __file__,
    )

    # 示例 2 · 多条件 + 按变量索引的单指标参数
    show_result(
        gangtise.indicator.screener(
            date="2026-08-07",
            expression="F1 >= 500 && F2 <= 30",  # 支持 && || 与括号
            indicator={"F1": "qte_mkt_cptl", "F2": "finc_pe_ttm"},
            security="1234567890",  # 板块 ID: 服务端展开成成分股
            indicator_param={"F1": {"scale": "8"}},  # 按变量索引（不是按 code）: 8=亿
            key_by="code",  # 列头来源: name=服务端显示名（默认） code=indicatorCode
        ),
        __file__,
    )

    # 示例 3 · 文本匹配（仅 dataType 为 string 的指标）+ 原始返回
    show_result(
        gangtise.indicator.screener(
            date="2026-08-07",
            expression="F1 contains '酒'",  # 也支持 notcontains
            indicator={"F1": "pty_op_scope"},
            security="1234567890",
            raw=True,  # True=返回服务端原始 data, 不做矩阵摊平
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
