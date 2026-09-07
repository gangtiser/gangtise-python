"""quote.minute_kline — 分钟 K 线（仅沪深, 不含北交所）, 返回 DataFrame。

通过多组示例覆盖全部参数；可选参数的取值范围已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
注意: 接口本身一次只收一只（不支持 "all"）; 传列表时 SDK 会逐只并发请求再按传入顺序合并。
时间参数精确到秒。
本接口只保留近期分钟数据（实测约五周），示例日期过旧会返回空表——
跑不出数据时先把日期换成最近的交易日，其它示例共用的日期在这里不适用。
异步用法相同, 路径为 gangtise.async_.quote.minute_kline(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 单只 A 股某交易日的分钟 K 线
    show_result(
        gangtise.quote.minute_kline(
            security="000001.SZ",  # 沪深代码 .SH/.SZ, 也可传 ETF / 指数; 支持单值或列表
            start_time="2026-08-28 09:30:00",  # 开始时间, 格式 yyyy-MM-dd HH:mm:ss
            end_time="2026-08-28 15:00:00",  # 结束时间, 格式 yyyy-MM-dd HH:mm:ss
            limit=10,  # 单次返回条数上限; 默认 6000, 最大 10000
        ),
        __file__,
    )

    # 示例 2 · 指定返回字段
    show_result(
        gangtise.quote.minute_kline(
            security="600519.SH",
            start_time="2026-08-28 09:30:00",
            end_time="2026-08-28 11:30:00",
            field=[
                "securityCode",
                "tradeTime",
                "open",
                "close",
                "high",
                "low",
                "volume",
            ],  # 返回字段; 身份列要自己写进来
        ),
        __file__,
    )

    # 示例 3 · 原始返回（不转 DataFrame）
    show_result(
        gangtise.quote.minute_kline(
            security="000001.SZ",
            start_time="2026-08-28 13:00:00",
            end_time="2026-08-28 15:00:00",
            raw=True,  # True=返回服务端原始 data（含 fieldList/list 矩阵）, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选用法:
    #   field=<字段名或列表>       仅返回所需字段（如 open/close/volume）; 省略则用服务端默认字段


if __name__ == "__main__":
    main()
