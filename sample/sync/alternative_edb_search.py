"""alternative.edb_search — 按关键词搜索行业经济指标(EDB)库, 返回指标列表。

通过多组示例覆盖全部参数;可选参数的枚举值已在注释中标注(取自 gangtise CLI 文档, 未杜撰)。
异步用法相同, 路径为 gangtise.async_.alternative.edb_search(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 按关键词搜索, 取前 5 条
    show_result(gangtise.alternative.edb_search(keyword="空调", limit=5), __file__)

    # 示例 2 · 另一关键词 + 更大返回上限
    show_result(
        gangtise.alternative.edb_search(
            keyword="平安银行",  # 搜索关键词(按指标名称匹配)
            limit=50,  # 返回条数上限, 默认 100, 最大 200
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.alternative.edb_search(
            keyword="光伏",  # 搜索关键词
            limit=10,  # 返回条数上限
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
