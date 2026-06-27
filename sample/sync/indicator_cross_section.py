"""indicator.cross_section — EDE 截面数据: 多指标 × 多证券, 单日期（返回 DataFrame）。

每行一只证券, 每列一个指标。指标码用 indicator.search 查询。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.indicator.cross_section(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 单指标 + 多证券, 单日期
    show_result(
        gangtise.indicator.cross_section(
            date="2025-06-30",  # 数据日期 YYYY-MM-DD（必填）
            indicator="qte_close",  # 指标码, 支持单值或列表
            security=["600519.SH", "000001.SZ"],  # 证券代码, 支持单值或列表
        ),
        __file__,
    )

    # 示例 2 · 多指标 + 单位/复权 等可选参数
    show_result(
        gangtise.indicator.cross_section(
            date="2025-06-30",
            indicator=["qte_close", "qte_open"],  # 多指标
            security="600519.SH",
            currency="CNY",  # 币种: DFT/CNY/HKD/USD/EUR/GBP/JPY/TWD/MOP/AUD（默认 DFT）
            scale="8",  # 数量级: 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）
            indicator_param={"qte_close": {"adjustmentType": "2"}},  # 单指标参数, 此处 2=前复权
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.indicator.cross_section(
            date="2025-06-30",
            indicator="qte_close",
            security="000001.SZ",
            raw=True,  # True=返回服务端原始 data, 不做矩阵摊平
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
