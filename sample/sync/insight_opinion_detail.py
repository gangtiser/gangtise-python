"""insight.opinion_detail — 按 ID 取国内首席观点正文（30 积分/条, 每批 20 个 ID, 返回 DataFrame）。

先用 insight.opinion_list 拿 chiefOpinionId（列表只含 200 字摘要 brief, 1 积分/条）, 再按 ID 取正文 content。
没有正文的 ID 不报错、直接跳过: raw=True 的返回里列在 missingIds 并标 partial, 同时发 UserWarning;
某一批失败时已取到的正文保留, 没取到的 ID 在 unfetchedIds、原因在 unfetchedError, 只对这些 ID 重跑即可。
异步用法相同, 路径为 gangtise.async_.insight.opinion_detail(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 先取 2 条摘要拿到 chiefOpinionId（1 积分/条）
    listing = gangtise.insight.opinion_list(security="600519.SH", size=2, raw=True)
    ids = [row["chiefOpinionId"] for row in listing["list"]]

    # 示例 1 · 按 ID 取正文: 支持单值或列表, 去重后按 20 个一批依次请求
    show_result(gangtise.insight.opinion_detail(chief_opinion_id=ids), __file__)

    # 示例 2 · 原始返回: {total, list, missingIds?, unfetchedIds?, unfetchedError?, partial?}
    show_result(
        gangtise.insight.opinion_detail(
            chief_opinion_id=ids[:1],  # chiefOpinionId, 来自 opinion_list; 支持单值或列表
            raw=True,  # True=返回 dict（含缺失 / 未取到 ID 的标记）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
