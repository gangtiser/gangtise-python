"""insight.foreign_opinion_detail — 按 ID 取海外机构观点原文与译文（30 积分/条, 每批 20 个 ID）。

先用 insight.foreign_opinion_list 拿 foreignOpinionId（列表只含摘要 brief / briefTranslate, 1 积分/条）,
再按 ID 取 content（原文）/ contentTranslate（中文译文）。缺失 ID 的处理同 insight.opinion_detail:
raw=True 的返回里列在 missingIds / unfetchedIds 并标 partial, 同时发 UserWarning。
异步用法相同, 路径为 gangtise.async_.insight.foreign_opinion_detail(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 先取 2 条摘要拿到 foreignOpinionId（1 积分/条）
    listing = gangtise.insight.foreign_opinion_list(region="us", size=2, raw=True)
    ids = [row["foreignOpinionId"] for row in listing["list"]]

    # 示例 1 · 按 ID 取原文与译文: 支持单值或列表, 去重后按 20 个一批依次请求
    show_result(gangtise.insight.foreign_opinion_detail(foreign_opinion_id=ids), __file__)

    # 示例 2 · 原始返回: {total, list, missingIds?, unfetchedIds?, unfetchedError?, partial?}
    show_result(
        gangtise.insight.foreign_opinion_detail(
            foreign_opinion_id=ids[
                :1
            ],  # foreignOpinionId, 来自 foreign_opinion_list; 支持单值或列表
            raw=True,  # True=返回 dict（含缺失 / 未取到 ID 的标记）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
