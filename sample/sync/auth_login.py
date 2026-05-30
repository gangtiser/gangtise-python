"""auth.login — 强制登录（或复用本地缓存 token）并返回 Bearer 鉴权头（返回 dict）。

该方法无业务参数：凭据取自环境变量 GANGTISE_ACCESS_KEY / GANGTISE_SECRET_KEY，
token 缓存落盘于 ~/.config/gangtise/token.json（与 npm CLI 共享）。
返回值含敏感 token，下方用 mask_sensitive 脱敏后再展示。
异步用法相同, 路径为 gangtise.async_.auth.login()。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def mask_sensitive(value):
    """递归地把字符串值替换为 [redacted]，避免把真实 token 写进示例输出。"""
    if isinstance(value, dict):
        return {key: mask_sensitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    if isinstance(value, str) and value:
        return "[redacted]"
    return value


def main():
    # 唯一示例 · 登录并取回鉴权头（无入参）
    # 返回形如 {"Authorization": "Bearer <token>"}; 已缓存且未过期时不会真正发起网络请求。
    result = gangtise.auth.login()
    show_result(mask_sensitive(result), __file__)
    # 该方法没有可选参数; 鉴权信息全部来自以下环境变量:
    #   GANGTISE_ACCESS_KEY  访问密钥
    #   GANGTISE_SECRET_KEY  访问私钥
    #   GANGTISE_TOKEN       （可选）直接提供 token, 跳过密钥换取


if __name__ == "__main__":
    main()
