"""tool.web_search — 联网搜索: 转载去重、信源分级（T0–T3）的投研定向检索（1 积分/次, 返回 DataFrame）。

⚠️ 排序是「信源等级 → 发布日期 → 相关性」, 首条不等于最相关; publishTime 判不出时为 null,
freshness 取 day/week/month 时这批一并滤掉。零结果与报错不扣积分; total=0 时用 raw=True 看 hints。
异步用法相同, 路径为 gangtise.async_.tool.web_search(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 轻搜: 默认 10 条摘要
    show_result(gangtise.tool.web_search(query="减持新规"), __file__)

    # 示例 2 · 收窄: 定向站点 + 只要高等级信源 + 近一周
    show_result(
        gangtise.tool.web_search(
            query="减持新规",  # 必填, 1-200 字符, 原样发送（服务端不做意图改写）
            size=10,  # 1-20, 默认 10
            site=[
                "csrc.gov.cn",
                "sse.com.cn",
            ],  # 注册域或子域, 最多 10 个（去重后计）, 相互之间为或
            min_tier="T1",  # 最低信源等级: T0 / T1 / T2 / T3（T3=不过滤）
            freshness="week",  # 时效: day / week / month / none（默认）
        ),
        __file__,
    )

    # 示例 3 · 精读: 返回网页正文 + 原始返回
    show_result(
        gangtise.tool.web_search(
            query="减持新规",
            site="csrc.gov.cn",
            include_content=True,  # 返回正文 content（Markdown）; 此时 size 上限 5、省略默认也取 5
            max_content_chars=6000,  # 每条正文上限 1000-20000（默认 8000）, 超出截断并置 contentTruncated
            size=2,
            raw=True,  # True=返回 {query, total, hints, list}, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
