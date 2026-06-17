# gangtise-openapi

[Gangtise OpenAPI](https://open.gangtise.com) 的 Python SDK。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.17.0 功能对齐，覆盖 74 个上游接口，并提供本地鉴权状态辅助工具。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

### 0.1.9 - 2026-06-17
- 新增产业公众号资讯接口（对齐 CLI v0.18.0）：`insight.official_account_list` 按关键词/公众号/证券/文章类型（枚举）/行业分页检索，支持 `search_type`（1=标题 2=全文）与 `rank_type`（1=综合 2=时间倒序）；`insight.official_account_download` 按 `article_id` 下载文章为 txt（默认 `file_type=1`）或 HTML（`file_type=2`）。同步+异步双实现，下载走 title 缓存解析文件名。

### 0.1.8 - 2026-06-16
- 服务端把 token 挤掉（他处登录）导致本会话失效时，自动重新登录并重试一次（错误码 `0000001008` 加入 auth 重试集合，`_call` 与下载、同步与异步四条路径全覆盖），不再需要手动重新登录；补充对应中文错误提示。对齐 CLI v0.17.2。

### 0.1.7 - 2026-06-16
- 修复并发下载临时文件竞态：两个解析到同一目标文件名的下载（同一 id 下载两次、标题相同、或显式相同 `output`）此前共用 `<目标>.part`，字节交错且互删对方临时文件（表现为 `DownloadError: No such file`）；改为每次下载用唯一后缀 `.part-<uuid>`。
- 异步下载不再因 `mkdir`/`replace`/`unlink` 等元数据 syscall 阻塞事件循环（改走 `anyio.to_thread`）。
- 内部清理：`reference.securities_search`、`alternative.edb_search` 改用共享 `_extract_rows`；测试从 413 增至 431（并发下载回归、财报列式矩阵转置、异步 body 映射、异步轮询重试）。

### 0.1.6 - 2026-06-15
- 对齐 TS CLI v0.16.0/v0.17.0：新增 5 个 `reference` 接口（constant/concept/sector），下线 6 个本地 lookup 表；4 个日程列表（路演/调研/策略会/论坛）各自精简为服务端实际支持的筛选项，传入不支持的参数现在抛 `TypeError` 而非静默返回空表；`announcement_list` 删除服务端始终忽略的 `announcement_type` 参数。
- 修复 `ai.knowledge_batch` 传空列表时向服务端发送 `"resourceTypes":[]`（TS 会省略该字段，可能导致 API 报错）。
- 修复 `is_all_market(["all", "000001.SZ"])` 误触发全市场分片（TS 只对恰好 `["all"]` 分片）。
- 对齐 `410110`/`410111` 错误提示文案（提及 `*-check` 命令与"终态"描述）。

### 0.1.5 - 2026-06-12
- 健壮性：并发遇到失效令牌只触发一次登录；失效的 `GANGTISE_TOKEN` 环境变量不再反复拖慢每次调用；异步分页/分片失败抛回 `ApiError`（不再是 `ExceptionGroup`）；K 线分片部分失败不再丢弃已取数据（结果带 `partial`/`failedShards` 标记）；缓存写盘失败不再影响请求本身。
- 下载：令牌失效自动刷新重试、瞬时错误退避重试、支持预签名 URL 响应、4xx 保留业务错误码与中文提示、异步下载不再阻塞事件循环。
- `gangtise.configure(...)` 现对 `gangtise.async_` 同样生效；facade 域属性支持 IDE 补全与类型检查。
- 性能：列式 K 线直接构建 DataFrame（提速 2-3 倍）；全市场日 K 回填跳过纯周末分片（少发约 29% 请求）。
- 对齐 TS CLI：`earning_forecast` 缺省自动取最近一年；时间参数换算与 `toTimestamp13` 一致；补齐 5 个错误码提示。
- 全部公开方法新增中文 docstring（含枚举取值）；测试从 222 个增至 402 个。

## 安装

```bash
pip install gangtise-openapi
```

需要 Python 3.10+。

## 配置

```bash
export GANGTISE_ACCESS_KEY=ak_xxx
export GANGTISE_SECRET_KEY=sk_xxx
```

（也可在创建 `GangtiseClient` 时直接传入 `access_key=` 和 `secret_key=`；直接构造的 client 需配合域封装类调用接口：`from gangtise_openapi.domains import Quote; Quote(client).day_kline(...)`。）令牌缓存文件位于 `~/.config/gangtise/token.json`，与 npm CLI 共用同一份。

## 快速开始

```python
from gangtise_openapi import gangtise

# 表格类接口返回 pandas DataFrame
df = gangtise.quote.day_kline(
    security="000001.SH",
    start_date="2026-01-01",
    end_date="2026-01-31",
)

# 传 raw=True 获取底层 dict/list
result = gangtise.insight.opinion_list(industry=1, size=20, raw=True)

# 异步
import asyncio

async def main():
    df = await gangtise.async_.quote.day_kline(security="000001.SH")

asyncio.run(main())
```

## 示例

每个公开的 SDK 方法都配有可独立运行、便于客户自测的脚本。

```bash
uv run python sample/sync/quote_day_kline.py
uv run python sample/async/quote_day_kline.py
```

返回 DataFrame 的示例会直接打印 DataFrame；文本或 dict/list 响应会以标准 Markdown 文件写入 `sample_outputs/`；下载类示例会把真实文件写入 `sample_downloads/`，并尽量保留服务端提供或原始的文件名与扩展名。

运行说明见 `sample/README.md`，完整的方法参数文档见 `sample/API_PARAMETERS.md`。

## 接口

SDK 覆盖 9 个领域下的 74 个上游接口：

- `gangtise.auth.*` — 登录、状态
- `gangtise.lookup.*` — 本地查表（券商机构、会议机构）
- `gangtise.reference.*` — 证券搜索（GTS 代码）、常量分类与常量值（行业/城市/公告分类/区域）、题材 ID 搜索、板块 ID 搜索与成分股
- `gangtise.insight.*` — 观点、研报、公告、日程
- `gangtise.quote.*` — K 线、实时行情
- `gangtise.fundamental.*` — 财务报表、估值、股东、盈利预测
- `gangtise.ai.*` — AI 生成的洞察（一页通、同业对比、业绩点评等）
- `gangtise.vault.*` — 个人云盘、会议记录、股票池、微信
- `gangtise.alternative.*` — 经济指标（EDB）、题材（概念）指数画像与成分股

Python 封装接受与 CLI 参数相同的入参，只是用 `snake_case` 代替 `--kebab-case`。例如 CLI 的 `--start-date` 对应 Python 的 `start_date`。

## 许可证

MIT
