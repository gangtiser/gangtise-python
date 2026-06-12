"""alternative.concept_info — 概念(主题指数)最新画像, 返回 dict。

返回单个截面对象(定义、投资逻辑、行业空间、竞争格局、关键事件 keyEvents 等), 因此为 dict。
concept_id 与 ai.theme_tracking 共用题材 id 命名空间, 用 reference.concept_search(keyword=...) 按名查询(机器人=121000130)。
返回 dict, 多次 show_result 会写同一 .md 路径互相覆盖, 故只保留 1 个执行示例, 其余用注释覆盖。
异步用法相同, 路径为 gangtise.async_.alternative.concept_info(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 · 取「机器人」主题的最新画像
    show_result(
        gangtise.alternative.concept_info(
            concept_id="121000130",  # 概念/主题指数 ID(机器人=121000130), 见 reference.concept_search(keyword=...)
        ),
        __file__,
    )

    # 其余用法(用注释覆盖, 避免 dict 写同一 .md 互相覆盖):
    #   换一个主题(题材 ID 见 reference.concept_search(keyword=...), 如 ai.theme_tracking 文档示例 121000342):
    #     gangtise.alternative.concept_info(concept_id="121000342")
    #   raw=True 仅为签名统一而保留, 返回内容与默认一致(同为该 dict):
    #     gangtise.alternative.concept_info(concept_id="121000130", raw=True)


if __name__ == "__main__":
    main()
