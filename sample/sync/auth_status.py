"""auth.status — 查看当前 token 状态, 不强制发起网络登录（返回 dict）。

该方法无业务参数：读取环境变量与本地缓存文件 ~/.config/gangtise/token.json，
返回 has_env_token / has_cached_token 以及缓存中的过期时间、uid、用户名、租户 ID。
返回值含敏感信息，下方用 mask_sensitive 脱敏后再展示。
异步用法相同, 路径为 gangtise.async_.auth.status()。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def mask_sensitive(value):
    """递归地把字符串值替换为 [redacted]，避免把真实 token / 用户信息写进示例输出。"""
    if isinstance(value, dict):
        return {key: mask_sensitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    if isinstance(value, str) and value:
        return "[redacted]"
    return value


def main():
    # 唯一示例 · 检查鉴权状态（无入参, 不触发网络登录）
    # 返回字段:
    #   has_env_token     是否设置了 GANGTISE_TOKEN 环境变量
    #   has_cached_token  本地缓存文件中是否有可用 access_token
    #   cache             缓存详情: access_token / expires_at / uid / user_name / tenant_id
    result = gangtise.auth.status()
    show_result(mask_sensitive(result), __file__)
    # 该方法没有可选参数。


if __name__ == "__main__":
    main()
