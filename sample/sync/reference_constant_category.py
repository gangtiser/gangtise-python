"""reference.constant_category — 列出常量分类及各分类适用的接口参数（返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.reference.constant_category(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 列出全部常量分类（无业务参数）
    # 返回字段: category / categoryName / structureType(flat=平铺 tree=树形) / maxLevel / usageScopes
    # 分类包括: citicIndustry=中信一级行业 swIndustry=申万一级行业 gangtiseIndustry=Gangtise行业
    #   domesticCity=国内城市 aShareAnnouncementCategory=A股公告分类(tree)
    #   hkShareAnnouncementCategory=港股公告分类(tree) regionCategory=区域分类
    show_result(gangtise.reference.constant_category(), __file__)

    # 示例 2 · 原始返回: usageScopes（apiName + paramName 嵌套结构）在 raw 下更易读
    show_result(
        gangtise.reference.constant_category(
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
