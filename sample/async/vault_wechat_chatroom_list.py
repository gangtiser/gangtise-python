"""vault.wechat_chatroom_list — 微信群 chatroomId 列表（返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数语义已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.vault.wechat_chatroom_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取前 5 个群
    show_result(await gangtise.async_.vault.wechat_chatroom_list(size=5), __file__)

    # 示例 2 · 按群名称过滤 + 分页
    show_result(
        await gangtise.async_.vault.wechat_chatroom_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=20,  # 分页大小, 默认 20
            room_name="投研",  # 微信群名称, 支持单值或列表; 多值请求时会拼成逗号分隔字符串
        ),
        __file__,
    )

    # 示例 3 · 多群名称（列表入参）+ 原始返回
    show_result(
        await gangtise.async_.vault.wechat_chatroom_list(
            room_name=["投研", "策略"],  # 群名称列表, 内部以逗号拼接
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
