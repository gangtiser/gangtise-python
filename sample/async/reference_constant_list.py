"""reference.constant_list — 列出某分类下的全部常量值（返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步路径为 gangtise.async_.reference.constant_list(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 平铺分类: 中信一级行业（行字段 constantId / constantName / level）
    show_result(
        await gangtise.async_.reference.constant_list(
            # 分类编码, 取值见 reference.constant_category():
            #   citicIndustry=中信一级行业 swIndustry=申万一级行业 gangtiseIndustry=Gangtise行业
            #   domesticCity=国内城市 regionCategory=区域分类
            category="citicIndustry",
        ),
        __file__,
    )

    # 示例 2 · 树形分类 + 原始返回: 树形分类的父节点含 children, 需要层级用 raw=True 自行递归
    show_result(
        await gangtise.async_.reference.constant_list(
            # 树形分类: aShareAnnouncementCategory=A股公告分类 hkShareAnnouncementCategory=港股公告分类
            category="aShareAnnouncementCategory",
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame（保留 children 层级）
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
