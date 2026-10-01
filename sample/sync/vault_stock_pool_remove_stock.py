"""vault.stock_pool_remove_stock — 从股票池批量移出证券（免费, 写操作）。

返回 {successList, failList}; 代码规则同 stock_pool_add_stock。移出本就不在池内的证券算成功;
单条失败进 failList, SDK 发 UserWarning 并给结果标 partial=True。
异步用法相同, 路径为 gangtise.async_.vault.stock_pool_remove_stock(...)。

本示例会改动账号数据: 把 POOL_ID 填好后再运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 池 ID 取自 vault.stock_pool_list(); 留空则不发请求。
POOL_ID = ""


def main():
    if not POOL_ID:
        raise SystemExit("请先填好 POOL_ID——本示例会从真实的股票池里移除证券。")
    result = gangtise.vault.stock_pool_remove_stock(
        pool_id=POOL_ID,  # 目标股票池 ID（必填）
        security="600519.SH",  # 证券代码（必填）, 支持单值或列表
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
