"""lookup.broker_orgs — 券商/机构字典（本地数据, 无网络请求, 返回 DataFrame）。

返回 id/name 两列, 可作为其它接口 broker 过滤参数的取值来源（如 insight.opinion_list）。
本接口无业务参数。异步用法相同, 路径为 gangtise.async_.lookup.broker_orgs(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 最简调用: 取全部券商/机构字典（id/name）
    show_result(gangtise.lookup.broker_orgs(), __file__)

    # 其余可选参数:
    #   raw=True   True=返回服务端原始 data（list）, 不转 DataFrame


if __name__ == "__main__":
    main()
