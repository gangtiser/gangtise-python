"""reference.official_account_search — 按名称/机构/关键字搜索公众号 ID（返回 DataFrame）。

返回 accountId（喂 insight.official_account_list 的 account_id）; 按 matchScore 降序; 免费。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.reference.official_account_search(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 按公众号名/机构搜索（省略 category=全部, 含未分类）
    show_result(
        gangtise.reference.official_account_search(
            keyword="中信证券",  # 公众号名称/所属机构/关键字（必填）
        ),
        __file__,
    )

    # 示例 2 · 限定分类 + 控制条数
    show_result(
        gangtise.reference.official_account_search(
            keyword="研究",
            category=[  # 分类, 支持单值或列表; 部分公众号不属四类（category 为 null）,
                "broker",  # 券商团队      传 category 会漏掉未分类公众号, 要全量就别传
                "media",  # 媒体
            ],  # 另有 listedCompany=上市公司 / government=政府官方
            top=5,  # 最大返回数, 默认 10, 上限 10
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.reference.official_account_search(
            keyword="人民日报",
            top=3,
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
