# gangtise-openapi

[Gangtise OpenAPI](https://open.gangtise.com) 的 Python SDK。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.17.0 功能对齐，覆盖 74 个上游接口，并提供本地鉴权状态辅助工具。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

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

### 0.1.4 - 2026-05-30
- 新增 `alternative.concept_info` / `alternative.concept_securities`：题材（概念）指数画像与成分股；`concept_id` 与 `ai.theme_tracking` 共用题材 ID 体系，可经 `gangtise.lookup.theme_ids()` 按名称查询。
- `quote.index_day_kline` 透传上游新增的 `securityName` 列（如「上证指数」）。
- title 缓存优化：单端点标题数封顶、无新增内容时不再重写——此前会无限增长至约 58 MB，现单次写入约 1.7 MB。

### 0.1.3 - 2026-05-29
- 修复 `quote.realtime` / `quote.minute_kline` / `quote.day_kline` 与 `reference.securities_search` 列名错配导致整列为 None：改为按响应 `fieldList` 动态取列，不再硬编码列名。

### 0.1.2 - 2026-05-29
- 列式响应（`{fieldList, list:[[...]]}`）的 DataFrame 转换（新增 `normalize_rows`），修复财务报表 / 估值 / 主营构成等接口的空表问题。
- `GANGTISE_VERBOSE` 调试日志真正生效；异步客户端不再因磁盘 I/O 阻塞事件循环。
- `fundamental.earning_forecast` 改为返回 DataFrame；各 domain 的公共 helper 合并去重。

### 0.1.1 - 2026-05-28
- 为所有公开方法补齐可独立运行的示例脚本（`sample/sync/`、`sample/async/`）与完整参数文档 `sample/API_PARAMETERS.md`，并统一示例输出与下载文件命名。

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
