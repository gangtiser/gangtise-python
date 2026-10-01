"""vault.stock_pool_add_stock — 向股票池批量添加证券（免费, 写操作）。

返回 {successList, failList}。代码要带市场后缀且大小写敏感（600519.SH / 00700.HK / AAPL.O）;
写错的代码进 failList 而不报错——failList 非空时 SDK 发 UserWarning 并给结果标 partial=True。
重复添加已在池内的证券算成功; 单池上限 10000 只。
异步用法相同, 路径为 gangtise.async_.vault.stock_pool_add_stock(...)。

本示例会改动账号数据: 把 POOL_ID 填好后再运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 池 ID 取自 vault.stock_pool_list(); 留空则不发请求。
POOL_ID = ""


def main():
    if not POOL_ID:
        raise SystemExit("请先填好 POOL_ID——本示例会向真实的股票池添加证券。")
    result = gangtise.vault.stock_pool_add_stock(
        pool_id=POOL_ID,  # 目标股票池 ID（必填）
        security=["600519.SH", "00700.HK", "AAPL.O"],  # 证券代码（必填）, 支持单值或列表
    )
    if result.get("partial"):
        print("部分失败:", result["failList"])  # [{securityCode, failReason}]
    show_result(result, __file__)


if __name__ == "__main__":
    main()
