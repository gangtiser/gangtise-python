"""vault.stock_pool_stocks — 列出股票池内的证券（返回 DataFrame）。

通过多组示例覆盖全部参数；poolId 取自 vault.stock_pool_list, 默认 all 表示全部池。
异步用法相同, 路径为 gangtise.async_.vault.stock_pool_stocks(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 默认调用: all=合并全部股票池
    show_result(gangtise.vault.stock_pool_stocks(pool_id="all"), __file__)

    # 示例 2 · 指定多个股票池（列表入参）+ 原始返回
    show_result(
        gangtise.vault.stock_pool_stocks(
            pool_id=["all"],  # 股票池 ID, 支持单值或列表; 真实 ID 见 vault.stock_pool_list
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
