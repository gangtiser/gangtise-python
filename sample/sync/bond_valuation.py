"""bond.valuation — 上清所估值（估值价格/收益率/久期/凸性/PVBP），返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。日期必填; 历史范围正式账号前溯 5 年、试用 3 年,
start_date 早于可回溯下界时整批 110003。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.bond.valuation(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 必填参数: 不传 confidence_level 时服务端默认只返回「推荐」的估值
    show_result(
        gangtise.bond.valuation(
            security="019742.SH",  # 标准债券代码, 单值或列表
            start_date="2026-09-15",  # 估值日起始 YYYY-MM-DD（必填）
            end_date="2026-09-19",  # 估值日结束 YYYY-MM-DD（必填）
        ),
        __file__,
    )

    # 示例 2 · 查「不推荐」的估值 + 原始返回
    show_result(
        gangtise.bond.valuation(
            security="019742.SH",
            start_date="2026-09-15",
            end_date="2026-09-19",
            confidence_level="不推荐",  # 估值可信度: 推荐 / 不推荐; 要看全部需两个值分别查
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   field=[...]   返回字段, 省略返回全部; 写错字段名整批 100003


if __name__ == "__main__":
    main()
