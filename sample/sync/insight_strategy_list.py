"""insight.strategy_list — 策略会日程列表（分页, 端点最大页 50, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.insight.strategy_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(gangtise.insight.strategy_list(size=5), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 关键词 + 证券 + 对象类型
    show_result(
        gangtise.insight.strategy_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="中期策略",  # 关键词
            security="000001.SZ",  # 证券代码, 支持单值或列表
            object_="industry",  # 对象类型: company=公司 / industry=行业（映射为 object）
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        gangtise.insight.strategy_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            market=["SH", "SZ"],  # 市场, 支持单值或列表; 例如 SH/SZ/HK/US
            permission=[1],  # 权限/可见性, 数字列表, 支持单值或列表
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数:
    #   research_area=<研究领域ID>    见 lookup.research_areas; 支持单值或列表
    #   institution=<机构ID>          机构过滤, 支持单值或列表
    #   category=<分类>               分类名称过滤, 支持单值或列表; 取值参考 lookup 接口
    #   participant_role=<参与方角色> 参与方角色名称过滤, 支持单值或列表
    #   broker_type=<券商类型>        券商类型名称过滤, 支持单值或列表


if __name__ == "__main__":
    main()
