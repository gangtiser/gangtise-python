"""alternative.edb_data — 按指标 ID 拉取行业经济指标(EDB)时间序列数据。

indicator_id 需先用 alternative.edb_search 按关键词搜出真实 ID, 这里沿用该取数链路。
通过示例与注释覆盖全部参数;可选参数的枚举值已在注释中标注(取自 gangtise CLI 文档, 未杜撰)。
异步用法相同, 路径为 gangtise.async_.alternative.edb_data(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 先用 edb_search 拿到一个真实指标 ID(required 参数必须为真实值)
    indicators = await gangtise.async_.alternative.edb_search(keyword="空调", limit=1)
    if indicators.empty:
        raise SystemExit("No EDB indicator found for keyword '空调'.")
    indicator_id = str(indicators.iloc[0].get("indicatorId") or indicators.iloc[0].get("id"))

    # 示例 · 单个指标的时间序列
    show_result(
        await gangtise.async_.alternative.edb_data(
            indicator_id=indicator_id,  # EDB 指标 ID, 支持单值或列表(列表最多 10 个)
            start_date="2026-01-01",  # 开始日期, 格式 YYYY-MM-DD
            end_date="2026-05-28",  # 结束日期, 格式 YYYY-MM-DD
        ),
        __file__,
    )

    # 其余用法(用注释覆盖, 避免依赖具体真实 ID 而执行报错):
    #   多指标一次性拉取(列表最多 10 个, 返回宽表按指标分列):
    #     await gangtise.async_.alternative.edb_data(
    #         indicator_id=["<指标ID-1>", "<指标ID-2>"],
    #         start_date="2026-01-01",
    #         end_date="2026-05-28",
    #     )
    #   raw=True 返回服务端原始 data(含 fieldList/dataList 矩阵, 不转 DataFrame):
    #     await gangtise.async_.alternative.edb_data(
    #         indicator_id=indicator_id,
    #         start_date="2026-01-01",
    #         end_date="2026-05-28",
    #         raw=True,
    #     )


if __name__ == "__main__":
    asyncio.run(main())
