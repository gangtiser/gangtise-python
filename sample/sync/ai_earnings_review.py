"""ai.earnings_review — AI 财报点评（异步生成: 先取 dataId, 再轮询内容）。

wait=True 会阻塞轮询至内容完成(最长约 3 分钟); 示例用 wait=False 立即返回 dataId,
再配合 ai_earnings_review_check.py 取结果, 避免示例长时间阻塞。
异步用法相同, 路径为 gangtise.async_.ai.earnings_review(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 提交财报点评任务并立即返回 dataId(不阻塞)
    result = gangtise.ai.earnings_review(
        security_code="000001.SZ",  # 单个证券代码
        period="2025annual",  # 报告期: 如 2025annual=年报, 2025interim=中报, 2025q3=三季报
        wait=False,  # False=立即返回 {data_id, status}; True=阻塞轮询至内容完成
    )
    show_result(result, __file__)
    # 拿到 data_id 后, 用 ai_earnings_review_check.py(传入 GANGTISE_SAMPLE_EARNINGS_REVIEW_DATA_ID)取结果。
    # 其余用法(注释展示):
    #   period 其它取值: "2025interim"(中报) / "2025q3"(三季报) / "2026q1"(一季报)
    #   wait=True   阻塞直至内容生成完成(返回完整 dict, 最长约 3 分钟)
    #   raw=True    返回服务端原始 data


if __name__ == "__main__":
    main()
