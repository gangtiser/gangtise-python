"""tool.file_parse — 提交 PDF 解析任务（异步）, 返回 task_id。

**0.8 积分/页, 提交时一次性扣费**；取结果免费（见 tool_file_parse_check）。
上传前本地校验后缀 / 非空 / ≤100MB, 免得为一次注定失败的上传付出传输时间。
该端点标 no-replay 且超时下限 300 秒——100MB 上传不会被默认 30 秒超时掐断,
也不会因重放而重复扣费。
异步用法相同, 路径为 gangtise.async_.tool.file_parse(...)。

运行前把 SOURCE_PDF 指向一个真实 PDF；本示例默认不发请求（避免误扣费）。
"""

from __future__ import annotations

from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise

# 换成你要解析的 PDF 路径后再运行。
SOURCE_PDF = Path("sample_downloads/example.pdf")


def main():
    if not SOURCE_PDF.is_file():
        raise SystemExit(
            f"Set SOURCE_PDF to a real PDF first (missing: {SOURCE_PDF}). "
            "This sample bills 0.8 credits per page at submit time."
        )

    # 提交后拿到 task_id, 交给 tool.file_parse_check 取结果 ZIP。
    task_id = gangtise.tool.file_parse(
        file=SOURCE_PDF,  # 本地 PDF 路径（必填）, 仅 .pdf、非空、≤100MB
    )
    show_result({"taskId": task_id}, __file__)


if __name__ == "__main__":
    main()
