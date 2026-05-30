"""ai.management_discuss_earnings_call — 从业绩说明会提取管理层讨论（返回 dict）。

返回 dict, 故只保留 1 个执行示例(多次写同名 .md 会互相覆盖); 其余维度用注释展示。
异步用法相同, 路径为 gangtise.async_.ai.management_discuss_earnings_call(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 管理层讨论(来自业绩说明会): 报告期 + 证券代码 + 讨论维度
    show_result(
        gangtise.ai.management_discuss_earnings_call(
            report_date="2025-12-31",  # 报告期日期(如 2025-06-30 或 2025-12-31)
            security_code="000001.SZ",  # 单个证券代码
            # 讨论维度(必填; 本接口无 all 选项), 取值:
            #   businessOperation=经营情况
            #   financialPerformance=财务表现 / developmentAndRisk=发展与风险
            dimension="businessOperation",
        ),
        __file__,
    )
    # 其它维度示例(注释展示, 不执行——dict 返回会覆盖同名输出):
    #   dimension="financialPerformance"   # 财务表现
    #   dimension="developmentAndRisk"     # 发展与风险
    #   raw=True                           # 返回服务端原始 data


if __name__ == "__main__":
    main()
