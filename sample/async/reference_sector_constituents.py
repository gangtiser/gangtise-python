"""reference.sector_constituents — 列出板块的全量成分股（返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步路径为 gangtise.async_.reference.sector_constituents(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 申万一级行业指数 成分（行字段 gtsCode / gtsName, 31 行 821xxx.SWI）
    # sector_id 必须来自 reference.sector_search()
    # （题材 conceptId 与板块 sectorId 是两套 ID, 不通用; 返回 0 条通常是 ID 体系传错）
    show_result(
        await gangtise.async_.reference.sector_constituents(
            sector_id="2000000014",  # 板块 ID, 来自 sector_search（2000000014=申万一级行业指数）
        ),
        __file__,
    )

    # 示例 2 · 原始返回
    show_result(
        await gangtise.async_.reference.sector_constituents(
            sector_id="2000000014",
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
