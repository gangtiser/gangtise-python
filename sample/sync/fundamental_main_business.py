"""fundamental.main_business — 主营业务构成（按产品/行业/地区拆分），返回 DataFrame。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.fundamental.main_business(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 仅传必填证券代码, breakdown 默认 product（按产品）
    show_result(
        gangtise.fundamental.main_business(security_code="600519.SH"),  # 单个证券代码
        __file__,
    )

    # 示例 2 · 按行业拆分 + 时间窗 + 报告期
    show_result(
        gangtise.fundamental.main_business(
            security_code="600519.SH",  # 单个证券代码, 如 000001.SZ/600519.SH
            start_date="2023-01-01",  # 起始日期 YYYY-MM-DD
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD
            breakdown="industry",  # 拆分维度: product=产品 / industry=行业 / region=地区
            period="annual",  # 报告期: interim=中报 / annual=年报, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 按地区拆分 + 指定字段 + 原始返回
    show_result(
        gangtise.fundamental.main_business(
            security_code="600519.SH",
            breakdown="region",  # region=按地区拆分
            period=["interim", "annual"],  # 支持单值或列表
            field=["name", "revenue", "revenueRatio"],  # 返回字段, 支持单值或列表; 省略则用默认字段
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
