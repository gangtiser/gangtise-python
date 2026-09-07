"""indicator.cross_section — EDE 截面数据: 多指标 × 多证券, 单日期（返回 DataFrame）。

每行一只证券, 每列一个指标。指标码用 indicator.search 查询。
date 会作为每个指标各自的 tradeDate 下发（服务端 2026-08-01 起废弃根级 date）。
⚠️ 判据只看一个键: 注入的 tradeDate 会被拒, 当且仅当该指标的 parameterList 里没有
tradeDate。按 search 返回的 parameterList 分四种: ① 有 tradeDate → 不用管;
② 无 tradeDate 有 reportDate（is_* 那族）→ 传 reportDate; ③ 无 tradeDate 但有别的参数
→ 传那些参数再加 "tradeDate": None; ④ parameterList 为空 → 传 {}。别按 code 前缀推断。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步路径为 gangtise.async_.indicator.cross_section(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 单指标 + 多证券, 单日期
    show_result(
        await gangtise.async_.indicator.cross_section(
            date="2025-06-30",  # 数据日期 YYYY-MM-DD（必填）
            indicator="qte_close",  # 指标码, 支持单值或列表
            security=["600519.SH", "000001.SZ"],  # 证券代码, 支持单值或列表
        ),
        __file__,
    )

    # 示例 2 · 多指标 + 单位/复权 等可选参数
    show_result(
        await gangtise.async_.indicator.cross_section(
            date="2025-06-30",
            indicator=["qte_close", "qte_pre_close"],  # 多指标
            security="600519.SH",
            currency="CNY",  # 币种: DFT/CNY/HKD/USD/EUR/GBP/JPY/TWD/MOP/AUD（默认 DFT）
            scale="8",  # 数量级: 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）
            indicator_param={"qte_close": {"adjustType": "2"}},  # 单指标参数; 2=前复权 3=后复权
            # ⚠️ 复权参数名是 adjustType, 不是 adjustmentType——服务端对错参数名是
            # 静默忽略并退回不复权, 拿到的数看着正常实则错（实测茅台 2024-01-02:
            # adjustType=3 → 13609.6168 后复权, 错名 → 1685.01 不复权）。
        ),
        __file__,
    )

    # 示例 3 · 不吃 tradeDate 的指标: 按 parameterList 抑制注入
    show_result(
        await gangtise.async_.indicator.cross_section(
            date="2026-08-13",
            indicator=["pty_shr_reg", "scr_exchg_mkt"],
            security="600519.SH",
            indicator_param={
                # 情形③ parameterList=[currency, scale], 无 tradeDate:
                # 传参数 + None 标记, 写成 {} 会把 currency/scale 一起丢掉
                "pty_shr_reg": {"currency": "CNY", "tradeDate": None},
                # 情形④ parameterList 为空
                "scr_exchg_mkt": {},
            },
        ),
        __file__,
    )

    # 示例 4 · 原始返回
    show_result(
        await gangtise.async_.indicator.cross_section(
            date="2025-06-30",
            indicator="qte_close",
            security="000001.SZ",
            raw=True,  # True=返回服务端原始 data, 不做矩阵摊平
        ),
        __file__,
    )

    # 示例 5 · 列头改用指标码: 服务端按自己的顺序返回列（实测请求 [cf_finc_exp,
    # cf_finc_exp_qtr] 会回 [cf_finc_exp_qtr, cf_finc_exp]）, 位置索引不可靠;
    # code 模式下列名就是你传进去的 indicatorCode, 批量按 code 回填用这个。
    show_result(
        await gangtise.async_.indicator.cross_section(
            date="2025-06-30",
            indicator=["cf_finc_exp", "cf_finc_exp_qtr"],
            security="600519.SH",
            # cf_* 是报告期指标: 拒收注入的 tradeDate, 要按 code 各自传 reportDate
            indicator_param={
                "cf_finc_exp": {"reportDate": "2025-06-30"},
                "cf_finc_exp_qtr": {"reportDate": "2025-06-30"},
            },
            key_by="code",  # 列头来源: name=服务端显示名（默认） code=indicatorCode
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
