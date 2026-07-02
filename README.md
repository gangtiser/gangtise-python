# gangtise-openapi

[Gangtise OpenAPI](https://open.gangtise.com) 的 Python SDK。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.21.0 功能对齐，覆盖 84 个上游接口，并提供本地鉴权状态辅助工具。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

### 0.1.12 - 2026-07-02
- 对齐 CLI HEAD 对抗审查修复（含行为变更）：`insight.*` 纯日期串 `YYYY-MM-DD` 改按**本地午夜**锚定（此前 UTC 午夜，非 UTC 用户查询窗口偏一天）；`fundamental.earning_forecast` 仅传 `end_date` 时缺省起点改为锚定该日期前一年（此前锚定今天）；`normalize_token` 大小写不敏感剥 `bearer ` 前缀，避免 `Bearer bearer ...`。
- 下载更稳：自动命名遇同名加 `-1..-99` 后缀防批量覆盖、超长名截到 ≤200 UTF-8 字节且保留扩展名、`Content-Disposition` 的 RFC 5987 `filename*=UTF-8''` 大小写不敏感百分号解码（中文名正确落地）；鉴权重试复用他处已刷新的 token；异步清理 `.part` 改同步 `finally`，取消时也不漏删。
- 分页更稳：`MAX_PAGES` 上限改为生成扇出请求时即刻生效（损坏的 `total` 不再撑爆内存/挂死）；空或短首页不再重复请求同一偏移；异步畸形/空扇出页标 `partial`。
- 异步门面：不再跨 `asyncio.run()` 复用旧事件循环的 `httpx.AsyncClient`（消除 “Event loop is closed”）；`reset()`/`configure(replace=True)` 会关闭缓存的异步客户端。
- 发布 CI：`uv sync --locked`、发版前校验 README/CHANGELOG 含该 tag、PyPI 发布 action 钉到 commit SHA。

### 0.1.11 - 2026-06-29
- 对齐 CLI v0.21.0：`vault.wechat_chatroom_list` 省略 `size` 改为拉取全部群（接口不返回 total，按页串行翻到末页、单页上限 50；传 `size=N` 仅取前 N 条）；下载文件名额外剥离控制字符/NUL。
- 安全：token 缓存与 title 缓存改为创建即 `0600`（`os.open(O_EXCL)`）+ 原子 rename，消除“先写后 chmod”的短暂可读窗口。
- 数据完整性：扇出分页与 K 线分片遇 2xx 畸形响应时标记 `partial` 并告警、不再静默丢行；修复串行分页取满即误报 MAX_PAGES 截断；title 缓存加载丢弃半损坏 entry；pytest 默认 `-m "not live"`，裸跑不再打真实 API。

### 0.1.10 - 2026-06-27
- 新增证券级数据指标（EDE）域 `gangtise.indicator.*`（同步+异步，对齐 CLI v0.19.0）：`search` 按关键词搜指标码、`cross_section` 取多指标×多证券单日截面、`time_series` 取多指标×单证券（或单指标×多证券）时序；自动把 `values` 矩阵摊平成宽表（每行一证券/一日期，指标名作列）、剥离内层双层信封（内层失败码抛 `ApiError`）；`indicator_param={"qte_close":{"adjustmentType":"2"}}` 设置前复权等单指标参数。
- 新增美股接口（对齐 CLI v0.20.0）：`insight.announcement_us_list` / `announcement_us_download`（镜像港股公告，`file_type` 1=原文PDF 2=Markdown）；`fundamental.income_statement_us` / `balance_sheet_us` / `cash_flow_us`。
- 新增 `ai.stock_summary_list`（个股看点，每证券精炼研究摘要；`security` 必填，空值抛 `ValidationError` 防全市场积分误耗）与 `reference.chiefs_search`（按姓名/机构/团队搜首席 ID）。
- `ai.hot_topic` 的 `with_related_securities`/`with_close_reading` 改为按布尔下发，传 `False` 真正发送 `false`（此前省略字段、服务端走默认）；`announcement_hk_download` 新增 `file_type`（1=原文 2=Markdown）；缺失凭证报错改为指明缺哪个变量并提示 `export` / `gangtise.configure(...)`。
- 分页改为 fail-soft：扇出分页某页遇不可重试错误（限频/无权限）时保留已取页并发出 `UserWarning`，不再整体抛错；raw 结果带 `partial`/`failedPages`（`raw=True` 可见；默认 DataFrame 路径丢这些键、以 warning 为准），与 K 线分片容错一致（同步+异步）；`ai.knowledge_batch` 传空 `query` 改为抛 `ValidationError`。

### 0.1.9 - 2026-06-17
- 新增产业公众号资讯接口（对齐 CLI v0.18.0）：`insight.official_account_list` 按关键词/公众号/证券/文章类型（枚举）/行业分页检索，支持 `search_type`（1=标题 2=全文）与 `rank_type`（1=综合 2=时间倒序）；`insight.official_account_download` 按 `article_id` 下载文章为 txt（默认 `file_type=1`）或 HTML（`file_type=2`）。同步+异步双实现，下载走 title 缓存解析文件名。

### 0.1.8 - 2026-06-16
- 服务端把 token 挤掉（他处登录）导致本会话失效时，自动重新登录并重试一次（错误码 `0000001008` 加入 auth 重试集合，`_call` 与下载、同步与异步四条路径全覆盖），不再需要手动重新登录；补充对应中文错误提示。对齐 CLI v0.17.2。

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

SDK 覆盖 10 个领域下的 84 个上游接口：

- `gangtise.auth.*` — 登录、状态
- `gangtise.lookup.*` — 本地查表（券商机构、会议机构）
- `gangtise.reference.*` — 证券搜索（GTS 代码）、常量分类与常量值（行业/城市/公告分类/区域）、题材 ID 搜索、板块 ID 搜索与成分股
- `gangtise.insight.*` — 观点、研报、公告、日程
- `gangtise.quote.*` — K 线、实时行情
- `gangtise.fundamental.*` — 财务报表、估值、股东、盈利预测
- `gangtise.ai.*` — AI 生成的洞察（一页通、同业对比、业绩点评等）
- `gangtise.vault.*` — 个人云盘、会议记录、股票池、微信
- `gangtise.alternative.*` — 经济指标（EDB）、题材（概念）指数画像与成分股
- `gangtise.indicator.*` — 证券级数据指标（EDE）：搜索指标码、截面、时序

Python 封装接受与 CLI 参数相同的入参，只是用 `snake_case` 代替 `--kebab-case`。例如 CLI 的 `--start-date` 对应 Python 的 `start_date`。

## 许可证

MIT
