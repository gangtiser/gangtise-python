"""reference.overseas_account_search — 按名称片段搜索海外观点账号 ID（返回 DataFrame）。

返回 accountId（喂 insight.overseas_opinion_list 的 account）; 子串匹配、英文不区分大小写,
按英文账号名查; 按 matchScore 降序; 免费。
通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.reference.overseas_account_search(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 账号名片段（必填）, 省略 size 取全部
    show_result(
        await gangtise.async_.reference.overseas_account_search(
            keyword="bloomberg",  # 英文账号名片段; 中文名（如「彭博」）查不到
        ),
        __file__,
    )

    # 示例 2 · 分页 + 原始返回
    show_result(
        await gangtise.async_.reference.overseas_account_search(
            keyword="elo",  # 任意位置子串匹配: 命中 Elon Musk 与 Financelot
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=5,  # 返回条数; 省略取全部
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
