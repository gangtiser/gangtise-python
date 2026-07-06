"""reference.institution_search — 按关键词搜索机构 ID（返回 DataFrame）。

输入机构名/简称返回 institutionId 及适用接口参数（usageScopes）; 覆盖各接口的 broker/institution 入参; 免费。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.reference.institution_search(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 按机构名/简称搜索（省略 category=全部机构类型）
    show_result(
        gangtise.reference.institution_search(
            keyword="招商",  # 搜索关键词, 机构名/简称
        ),
        __file__,
    )

    # 示例 2 · 限定机构类型 + 控制返回条数
    show_result(
        gangtise.reference.institution_search(
            keyword="中信",
            category=[  # 机构类型, 支持单值或列表; 省略=全部
                "domesticBroker",  # 境内券商
                "opinionInstitution",  # 观点机构
            ],  # 另有 foreignInstitution / leadInstitution / foreignOpinionInstitution
            top=5,  # 最大返回数, 默认 10, 最大 10
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.reference.institution_search(
            keyword="高盛",
            category="foreignInstitution",  # 外资机构
            top=10,  # 上限 10
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
