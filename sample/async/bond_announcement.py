"""bond.announcement — 债券公告（需手动翻页, 响应无 total），返回 DataFrame。

0.4 积分/次、每翻一页扣一次, 超时 / 5xx 不自动重试。security 与 start_date/end_date 二选一
（同传或都不传本地拒绝）。page_no 从 1 起递增, 翻过末页返回空结果即停; 条件下一条都没有时
任何页码都抛 ApiError(130001)。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.bond.announcement(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 按债券代码查第 1 页
    show_result(
        await gangtise.async_.bond.announcement(
            security="019742.SH",  # 标准债券代码, 单值或列表; 与日期区间二选一
            page_size=50,  # 每页条数 1-200, 默认 50
        ),
        __file__,
    )

    # 示例 2 · 按公告日区间查第 2 页（此时返回的 securityCode 不带市场后缀）
    show_result(
        await gangtise.async_.bond.announcement(
            start_date="2026-09-18",  # 公告日起始 YYYY-MM-DD; 与 security 二选一
            end_date="2026-09-19",  # 公告日结束 YYYY-MM-DD
            page_no=2,  # 页码, 从 1 开始
            page_size=50,
        ),
        __file__,
    )

    # 示例 3 · 手动翻到底: 批量翻页传 page_size=200 省调用次数, 空页即停
    page_no = 1
    while True:
        page = await gangtise.async_.bond.announcement(
            security="019742.SH",
            page_no=page_no,
            page_size=200,
            field=["announcementDate", "securityCode"],  # 返回字段, 省略返回全部
        )
        if page.empty:
            break
        show_result(page, __file__)
        page_no += 1

    # 示例 4 · 原始返回
    show_result(await gangtise.async_.bond.announcement(security="019742.SH", raw=True), __file__)


if __name__ == "__main__":
    asyncio.run(main())
