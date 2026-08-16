"""indicator.time_series — EDE 时序数据: 多指标 × 单证券 或 单指标 × 多证券（返回 DataFrame）。

每行一个日期。指标码用 indicator.search 查询。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.indicator.time_series(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 多指标 × 单证券: 列为各指标
    show_result(
        gangtise.indicator.time_series(
            start_date="2025-01-01",  # 起始日期 YYYY-MM-DD（必填）
            end_date="2025-06-30",  # 结束日期 YYYY-MM-DD（必填）
            indicator=["qte_close", "qte_open"],  # 指标码, 支持单值或列表
            security="600519.SH",  # 单证券 -> 列为各指标
        ),
        __file__,
    )

    # 示例 2 · 单指标 × 多证券: 列为各证券 + 可选参数
    show_result(
        gangtise.indicator.time_series(
            start_date="2025-01-01",
            end_date="2025-06-30",
            indicator="qte_close",  # 单指标 -> 列为各证券
            security=["600519.SH", "000001.SZ"],
            calendar_type="TD",  # 日历: ND=自然日 TD=交易日 WD=工作日（默认 TD）
            currency="CNY",  # 币种: DFT/CNY/HKD/USD/EUR/GBP/JPY/TWD/MOP/AUD（默认 DFT）
            scale="0",  # 数量级: 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）
            indicator_param={"qte_close": {"adjustType": "2"}},  # 单指标参数, 此处 2=前复权
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.indicator.time_series(
            start_date="2025-01-01",
            end_date="2025-06-30",
            indicator="qte_close",
            security="600519.SH",
            raw=True,  # True=返回服务端原始 data, 不做矩阵摊平
        ),
        __file__,
    )

    # 示例 4 · 列头改用代码: 单指标 × 多证券时列名为 securityCode（多指标 × 单证券则为
    # indicatorCode）。服务端按自己的顺序返回列, 位置索引不可靠。
    show_result(
        gangtise.indicator.time_series(
            start_date="2025-01-01",
            end_date="2025-06-30",
            indicator="qte_close",
            security=["600519.SH", "000001.SZ"],
            key_by="code",  # 列头来源: name=服务端显示名（默认） code=indicatorCode / securityCode
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
