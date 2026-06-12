"""ai.theme_tracking — 获取主题/题材跟踪日报（返回结构化 dict）。

返回 dict, 故只保留 1 个执行示例(多次写同名 .md 会互相覆盖); 其余参数组合用注释展示。
异步用法相同, 路径为 gangtise.async_.ai.theme_tracking(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 主题跟踪日报: 必填主题 ID + 业务日期
    show_result(
        await gangtise.async_.ai.theme_tracking(
            theme_id="121000130",  # 主题/题材 ID(如 机器人=121000130; 见 reference.concept_search(keyword=...))
            date="2026-05-28",  # 业务日期 YYYY-MM-dd
            type_="morning",  # 报告类型: morning=早报, night=晚报; 支持单值或列表
        ),
        __file__,
    )
    # 其它示例(注释展示, 不执行——dict 返回会覆盖同名输出):
    #   # 不指定 type_(返回该日全部报告类型):
    #   await gangtise.async_.ai.theme_tracking(theme_id="121000130", date="2026-05-28")
    #   # 同时取早报与晚报(列表入参):
    #   await gangtise.async_.ai.theme_tracking(
    #       theme_id="121000130", date="2026-05-28", type_=["morning", "night"]
    #   )
    #   # raw=True 返回服务端原始 data:
    #   await gangtise.async_.ai.theme_tracking(theme_id="121000130", date="2026-05-28", raw=True)


if __name__ == "__main__":
    asyncio.run(main())
