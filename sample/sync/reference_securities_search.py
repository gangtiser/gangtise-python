"""reference.securities_search — 模糊搜索 GTS 证券代码（返回 DataFrame）。

通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.reference.securities_search(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 按名称/代码/拼音/英文模糊搜索
    show_result(
        gangtise.reference.securities_search(
            keyword="平安银行",  # 搜索关键词, 支持 名称/代码/拼音/英文
        ),
        __file__,
    )

    # 示例 2 · 限定分类 + 控制返回条数
    show_result(
        gangtise.reference.securities_search(
            keyword="600519",  # 也可直接用证券代码搜索
            category="stock",  # 分类: stock=股票 dr=存托凭证 index=指数 fund=基金 bond=债券
            top=5,  # 每个查询返回的最大候选数, 默认 10, 最大 10
        ),
        __file__,
    )

    # 示例 3 · 债券代码（用于 gangtise.bond）; 可转债在任何分类下都可能出现, 只取 category 等于所查类别的行
    show_result(
        gangtise.reference.securities_search(
            keyword="甬金转债",
            category="bond",
        ),
        __file__,
    )

    # 示例 4 · 多分类（列表入参）+ 原始返回
    show_result(
        gangtise.reference.securities_search(
            keyword="ping an",  # 关键词支持英文/拼音
            category=["stock", "index"],  # 分类支持单值或列表: stock/dr/index/fund/bond
            top=10,  # 上限 10
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
