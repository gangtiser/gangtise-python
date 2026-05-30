"""vault.drive_list — 个人网盘文件列表（分页, 端点最大页 50）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.vault.drive_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 个文件
    show_result(gangtise.vault.drive_list(size=5), __file__)

    # 示例 2 · 常用过滤: 关键词 + 时间窗 + 空间类型
    show_result(
        gangtise.vault.drive_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="平安银行",  # 搜索关键词
            space_type=1,  # 空间类型: 1=我的文件, 2=租户文件; 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 文件类型多值过滤 + 原始返回
    show_result(
        gangtise.vault.drive_list(
            file_type=[
                1,
                2,
            ],  # 文件类型代码（数值）, 支持单值或列表; CLI 未列举具体编码, 见网盘前端筛选项
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
