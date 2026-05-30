"""vault.wechat_message_list — 微信群消息列表（分页, 端点最大页 50）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.vault.wechat_message_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 关键词 + 取 5 条
    show_result(gangtise.vault.wechat_message_list(size=5, keyword="平安银行"), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 消息类型 + 标签
    show_result(
        gangtise.vault.wechat_message_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="银行",  # 搜索关键词
            category="text",  # 消息类型: text/image/documents/url; 支持单值或列表
            # 标签: roadShow=路演, research=调研, strategyMeeting=策略会, meetingSummary=会议纪要,
            #   industryComment=行业点评, companyComment=公司点评, earningsReview=业绩点评; 支持单值或列表
            tag="research",
        ),
        __file__,
    )

    # 示例 3 · 按证券 + 行业过滤（列表入参）+ 原始返回
    show_result(
        gangtise.vault.wechat_message_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            industry=1,  # 申万行业 ID, 支持单值或列表（见 lookup.industries）
            category=["documents", "url"],  # 消息类型, 支持单值或列表
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表, 需传入真实 ID）:
    #   wechat_group_id=<微信群ID>   见 vault.wechat_chatroom_list


if __name__ == "__main__":
    main()
