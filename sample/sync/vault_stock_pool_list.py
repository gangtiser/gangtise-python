"""vault.stock_pool_list — 股票池 ID 与名称列表（个人或所属租户, 返回 DataFrame）。

space_type 选个人（1, 默认）或所属租户（2）的股票池; 拿到的 poolId 传给 vault.stock_pool_stocks 时
要带同一 space_type。
异步用法相同, 路径为 gangtise.async_.vault.stock_pool_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 默认调用: 返回全部股票池, 转为 DataFrame
    show_result(gangtise.vault.stock_pool_list(), __file__)

    # 示例 2 · 所属租户的股票池 + 原始返回: 服务端 data 含 poolList 等原始字段
    show_result(
        gangtise.vault.stock_pool_list(
            space_type=2,  # 1=个人自选股股票池（默认）, 2=所属租户的股票池; 无权限报 999004
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
