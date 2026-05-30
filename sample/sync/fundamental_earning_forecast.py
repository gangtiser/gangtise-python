"""fundamental.earning_forecast — 盈利预测（卖方一致预期），返回 DataFrame。

服务端返回按 (更新日期 x 预测年度) 嵌套的数据, wrapper 已展平为一行一条;
latest=True（默认）仅保留最新一次更新。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.fundamental.earning_forecast(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 仅传必填证券代码, 默认 latest=True 取最新一次预测
    show_result(
        gangtise.fundamental.earning_forecast(security_code="000001.SZ"),  # 单个证券代码
        __file__,
    )

    # 示例 2 · 时间窗 + 一致预期指标过滤 + 保留全部历史更新
    show_result(
        gangtise.fundamental.earning_forecast(
            security_code="600519.SH",  # 单个证券代码, 如 000001.SZ/600519.SH
            start_date="2025-01-01",  # 起始日期 YYYY-MM-DD（省略时默认 end_date 前 1 年）
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD（省略时默认当天）
            consensus=["netIncome", "eps"],  # 一致预期指标, 支持单值或列表; 见下方枚举
            latest=False,  # False=保留全部更新日期; True（默认）=仅最新一次
        ),
        __file__,
    )

    # 示例 3 · 单一指标 + 原始返回
    show_result(
        gangtise.fundamental.earning_forecast(
            security_code="000001.SZ",
            consensus="roe",  # 单值; 枚举见下
            raw=True,  # True=返回服务端原始嵌套 data, 不展平/不转 DataFrame
        ),
        __file__,
    )
    # consensus 一致预期指标可选值（取自 cli.ts）:
    #   netIncome=净利润  netIncomeYoy=净利润同比  eps=每股收益  pe=市盈率
    #   bps=每股净资产    pb=市净率              peg=PEG       roe=净资产收益率  ps=市销率


if __name__ == "__main__":
    main()
