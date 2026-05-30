"""quote.minute_kline — A 股分钟 K 线（仅 SH/SZ/BJ）, 返回 DataFrame。

通过多组示例覆盖全部参数；可选参数的取值范围已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
注意: 本接口仅支持单只 A 股代码（不支持列表 / "all"）, 时间参数精确到秒。
异步用法相同, 路径为 gangtise.async_.quote.minute_kline(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 单只 A 股某交易日的分钟 K 线
    show_result(
        gangtise.quote.minute_kline(
            security="000001.SZ",  # A 股代码, 后缀 .SH/.SZ/.BJ; 仅支持单只（非列表）
            start_time="2026-05-28 09:30:00",  # 开始时间, 格式 yyyy-MM-dd HH:mm:ss
            end_time="2026-05-28 15:00:00",  # 结束时间, 格式 yyyy-MM-dd HH:mm:ss
            limit=10,  # 单次返回条数上限; 默认 5000, 最大 10000
        ),
        __file__,
    )

    # 示例 2 · 指定返回字段
    show_result(
        gangtise.quote.minute_kline(
            security="600519.SH",
            start_time="2026-05-28 09:30:00",
            end_time="2026-05-28 11:30:00",
            field=["time", "open", "close", "high", "low", "volume"],  # 返回字段, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 原始返回（不转 DataFrame）
    show_result(
        gangtise.quote.minute_kline(
            security="000001.SZ",
            start_time="2026-05-28 13:00:00",
            end_time="2026-05-28 15:00:00",
            raw=True,  # True=返回服务端原始 data（含 fieldList/list 矩阵）, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选用法:
    #   field=<字段名或列表>       仅返回所需字段（如 open/close/volume）; 省略则用服务端默认字段


if __name__ == "__main__":
    main()
