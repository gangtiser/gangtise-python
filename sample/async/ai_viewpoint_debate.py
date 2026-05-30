"""ai.viewpoint_debate — AI 观点辩论/PK（异步生成: 先取 dataId, 再轮询内容）。

wait=True 会阻塞轮询至内容完成(最长约 3 分钟); 示例用 wait=False 立即返回 dataId,
再配合 ai_viewpoint_debate_check.py 取结果, 避免示例长时间阻塞。
异步用法相同, 路径为 gangtise.async_.ai.viewpoint_debate(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 提交观点辩论任务并立即返回 dataId(不阻塞)
    result = await gangtise.async_.ai.viewpoint_debate(
        viewpoint="白酒行业估值修复具备持续性",  # 待辩论的投资观点文本(建议不超过 1000 字)
        wait=False,  # False=立即返回 {data_id, status}; True=阻塞轮询至内容完成
    )
    show_result(result, __file__)
    # 拿到 data_id 后, 用 ai_viewpoint_debate_check.py(传入 GANGTISE_SAMPLE_VIEWPOINT_DEBATE_DATA_ID)取结果。
    # 其余用法(注释展示):
    #   wait=True   阻塞直至内容生成完成(返回完整 dict, 最长约 3 分钟)
    #   raw=True    返回服务端原始 data


if __name__ == "__main__":
    asyncio.run(main())
