"""insight.strategy_list — 策略会日程列表（分页, 端点最大页 50, 返回 DataFrame）。

通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
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
            institution=[1],  # 机构 ID, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        gangtise.insight.strategy_list(
            institution=[1, 2],  # 机构 ID, 支持单值或列表
            keyword="策略",  # 关键词
            size=20,  # 按条计费（10 积分/条）: 带 size 取一部分; 要全量改传 confirm=True
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数:
    #   institution=<机构ID>          机构过滤, 支持单值或列表
    #   location=<城市码>             domesticCity 码（如上海 "156310000"）; 传城市名报 999999


if __name__ == "__main__":
    main()
