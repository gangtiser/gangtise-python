"""alternative.concept_securities — 概念(主题指数)的成分证券, 分组。

默认返回扁平化 DataFrame: 每行一只证券, 列为
groupName / securityCode / securityName / isKey(是否关键个股)/ inclusionReason(纳入理由)。
raw=True 返回服务端嵌套分组 dict(securityDetail -> [{groupName, securityList:[...]}])。
concept_id 与 ai.theme_tracking 共用题材 id 命名空间, 用 lookup.theme_ids 按名查询(机器人=121000130)。
异步用法相同, 路径为 gangtise.async_.alternative.concept_securities(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 · 取「机器人」主题的成分证券(默认扁平化 DataFrame, 每行一只证券)
    show_result(
        await gangtise.async_.alternative.concept_securities(
            concept_id="121000130",  # 概念/主题指数 ID(机器人=121000130), 见 lookup.theme_ids
        ),
        __file__,
    )

    # 其余用法(用注释覆盖, 避免 raw 分组 dict 写 .md 与上面的 DataFrame 输出语义混淆):
    #   换一个主题(题材 ID 见 lookup.theme_ids, 如 ai.theme_tracking 文档示例 121000342):
    #     await gangtise.async_.alternative.concept_securities(concept_id="121000342")
    #   raw=True 返回嵌套分组 dict, 不做扁平化:
    #     await gangtise.async_.alternative.concept_securities(concept_id="121000130", raw=True)


if __name__ == "__main__":
    asyncio.run(main())
