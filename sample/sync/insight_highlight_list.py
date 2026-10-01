"""insight.highlight_list — 会议线索: 会议核心要点信息流（分页, 端点最大页 50, 返回 DataFrame）。

固定按发布时间倒序; 🔴 5 积分/条, 务必带 size（省略 size 估算超过 1000 积分会被拒绝, 要全量传 confirm=True）。
按偏移最多取到第 10000 条; content 是 HTML 片段（<p> 包裹、小标题 <strong>）; research_area 不认申万码。
异步用法相同, 路径为 gangtise.async_.insight.highlight_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(gangtise.insight.highlight_list(size=5), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 证券
    show_result(
        gangtise.insight.highlight_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）; from_ + 条数不能超过 10000
            size=10,  # 条数（5 积分/条）; 单页上限 50, 超出自动翻页
            start_time="2026-09-01 00:00:00",  # 起始时间: yyyy-MM-dd HH:mm:ss, 也接受 yyyy-MM-dd
            end_time="2026-09-07 23:59:59",  # 结束时间
            security=[
                "600519.SH",
                "09992.HK",
            ],  # 证券代码, 大小写敏感; 港股 5 位数字; 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 按研究方向过滤 + 原始返回
    show_result(
        gangtise.insight.highlight_list(
            size=5,
            research_area="100800101",  # 中信行业码 1008001xx 或 Gangtise 方向码 122000xxx; 不认申万码
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # confirm=True: 省略 size 且估算超过 1000 积分（约 200 条）时确认全量拉取


if __name__ == "__main__":
    main()
