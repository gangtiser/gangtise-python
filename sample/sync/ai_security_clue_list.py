"""ai.security_clue_list — AI 证券线索列表（分页, 端点最大页 500, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.ai.security_clue_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 按证券查询(最简): 必填时间窗 + 查询模式
    show_result(
        gangtise.ai.security_clue_list(
            start_time="2026-05-01",  # 起始时间(必填)
            end_time="2026-05-28",  # 结束时间(必填)
            query_mode="bySecurity",  # 查询模式: bySecurity=按证券, byIndustry=按行业
            size=5,  # 分页大小; 省略则按最大页 500 自动翻页
        ),
        __file__,
    )

    # 示例 2 · 按证券 + 来源过滤 + 分页偏移
    show_result(
        gangtise.ai.security_clue_list(
            start_time="2026-05-01",
            end_time="2026-05-28",
            query_mode="bySecurity",  # bySecurity=按证券 / byIndustry=按行业
            from_=0,  # 分页起始偏移(映射为请求字段 from)
            size=10,  # 分页大小
            gts_code=["000001.SZ", "600519.SH"],  # GTS 证券代码, 支持单值或列表
            source="research",  # 来源过滤, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 按行业查询 + 原始返回
    show_result(
        gangtise.ai.security_clue_list(
            start_time="2026-05-01",
            end_time="2026-05-28",
            query_mode="byIndustry",  # byIndustry=按行业聚合线索
            size=5,
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 参数说明: gts_code 在 byIndustry 模式下可改传申万行业代码(见 reference.sector_constituents(sector_id="2000000014"))。


if __name__ == "__main__":
    main()
