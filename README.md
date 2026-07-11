# gangtise-openapi

[Gangtise OpenAPI](https://openapi.gangtise.com) 的 Python SDK。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.27.0 功能对齐，覆盖 90 个上游接口，并提供本地鉴权状态辅助工具。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

### 0.1.16 - 2026-07-11
- **安全**：签名 URL 不再泄露进异常信息——此前预签名下载失败的 `DownloadError` 会带完整 URL（含 `X-Amz-Signature` 查询串与 `user:password@` 认证段），终端/CI/错误采集系统都会记录；现只保留 `scheme://host[:port]/path`（userinfo、query、fragment 全部剥离，IPv6 主机自动补回方括号）。
- **数据完整性**：自动命名下载不再互相覆盖——两个 `output=None` 的并发下载解析到同名文件时，此前后完成者会静默覆盖前者；现改用 `O_CREAT|O_EXCL` 原子占名提交，输家自动改用下一个 `-1..-99` 后缀，最终移动失败时清理占位文件。全文件系统可用（不依赖硬链接）；显式 `output=` 保持文档化的覆盖语义。
- 签名 URL 拉取遇瞬态网络错误现会重试（默认策略、每次尝试独立 10× 硬截止）——重放签名 URL 恒安全，**计费上游端点绝不重发**；签名 URL 的 HTTP ≥400 仍立即失败（签名会过期，重放 403 无意义）。
- MIME→扩展名映射补齐图片类（png/jpeg/gif/webp/svg，与 TS 一致）：`report_image_download` 自动命名现落地为 `report-image-<id>.jpg` 而非无扩展名。
- no-replay 端点的 999999 提示不再写「请稍后重试」（SDK 未自动重试、请求可能已执行计费），改为提示先核实结果/扣费再决定是否手动重试。
- 测试套件在 `-W error::UserWarning` 下零警告通过（分页 fixture 统一为真实 `{total, list}` 形状），真实协议漂移告警不再被噪音掩盖。无端点/API 表面变更，仍对齐 CLI v0.27.0、90 接口。

### 0.1.15 - 2026-07-11
- 对齐 CLI v0.24.0–v0.27.0。**计费安全（重要）**：16 个按次计费端点（7 个 AI 同步生成、`earnings_review`/`viewpoint_debate` 的 get-id、`hot_topic`、`knowledge_batch`、`concept_info`/`concept_securities`、`summary`/`foreign_report`/`my_conference` 三个下载）改为 **no-replay 重试策略**——5xx/响应超时/999999 不再自动重放（实测平台按次计费且缓存命中不豁免，同参数重放每次都扣分）；仅连接期错误（请求未发出）、429 限流和 token 自愈仍重试。
- **EDE 指标三端点对 999999 不再重试**——服务端用 HTTP 500 + 999999 表示「查询无数据」（节假日/未来日期/未覆盖标的），此前每次空查询白烧 3 个请求 + ~4 秒；错误提示改为指向检查查询条件而非「稍后重试」。
- **7 个 AI 同步生成端点内置 120s 超时下限**（`one_pager`/`investment_logic`/`peer_comparison`/`theme_tracking`/`research_outline`/`management_discuss_*`×2）——生成耗时长不再撞 30s 默认超时；显式设更大 timeout 仍生效（取 max）。
- **新增接口 ×4**（86→90）：`insight.qa_list` 投资者问答（按证券提取互动平台/电话会议/调研纪要的提问与回答，11 类问题类型过滤，自动翻页单页上限 500，0.1 积分/条）；`insight.report_image_list` / `report_image_download` 研报图表（按关键词搜研报图片返回 chunkId+元数据，list 免费、下载原图 JPEG 0.1 积分/张）；`reference.official_account_search` 公众号 ID 搜索（返回 accountId 喂 `official_account_list`；免费）。
- 429 尊重 `Retry-After`（秒或 HTTP-date，优先于指数退避，60s 封顶；JSON 与下载路径都生效）。
- 本地校验（实测服务端对超限值静默截断、对拼错分类静默忽略/返回空）：`top`/`limit` 上限——reference 六个搜索 ≤10、`report_image_list`/`knowledge_batch` ≤20、`edb_search` ≤200、`indicator.search` ≤100；category 白名单——`securities_search`/`institution_search`/`official_account_search`；错误码 100003 补中文提示。
- 可靠性：AI 异步轮询容忍瞬态错误（5xx/网络抖动只消耗一次尝试并继续等待，不再作废整段等待）；全市场分片硬错后熔断（剩余分片不再派发、计入 `failedShards`，省配额）、shape 破损分片计入 `failedShards`、撞行数上限的分片输出 `truncatedShards` 具体日期窗口（可定向缩窗补拉）；分页端点首页形状漂移发 `UserWarning`（不再完全静默退化单页）；自动命名 100 个重名耗尽时抛 `DownloadError`（不再静默覆盖第一个文件）；签名 URL 下载加整体硬截止（10× 单请求超时，慢滴速传输不再无限续命）；`GANGTISE_PAGE_CONCURRENCY` 防御性解析（非法/非正数回退默认 5、上限 32）；EDE 矩阵中与 `date`/`security`/`name` 同名的指标列自动加后缀（不再覆盖元数据列）。

### 0.1.14 - 2026-07-07
- **域层过滤参数类型化**：`security`/`industry`/`rating` 等过滤参数由 `Any` 收窄为 `str | int | Sequence[str | int]`（`FilterValue` 别名），单值或列表均可——IDE 补全 + mypy 拦误用；int（如 `industry=1`、`fiscal_year=2025`）与 str 都保持有效（与接口一致）。无端点/API 表面变更，仍对齐 CLI v0.23.0、86 接口。
- **矩阵端点 DataFrame 构建 2-5x 提速**：列式 `{fieldList, list}` 响应（财报、EDE 指标等）直接按列矩阵构建，不再转成逐行 dict 再转回；输出逐值 + dtype 完全一致。
- 分页 `from`/`size` 拒绝 `bool`（`int` 子类）抛 `ValidationError`，与行情 `limit` 校验一致。
- 每个请求带 `User-Agent: gangtise-openapi-python/<version>`（同步 + 异步），便于服务端区分 Python SDK 与 npm CLI。
- 包成熟度 classifier 升至 `Development Status :: 4 - Beta`；新增 pytest-cov 覆盖率、CI 补测 Python 3.11/3.12。

### 0.1.13 - 2026-07-06
- 对齐 CLI v0.23.0。**默认接口域名迁移** `open.gangtise.com` → `openapi.gangtise.com`（新旧多接口实测等价；设 `GANGTISE_BASE_URL=https://open.gangtise.com` 可固定回旧域名）。
- 新增 `quote.fund_flow`（A 股个股日资金流向，沪深京；小/中/大/特大单流入流出及主力净流入；免费）：`security` 传具体代码或 `aShares` 拉全市场——全市场按日自动分片并发合并、须同时传 `start_date`/`end_date`（缺日期抛 `ValidationError`）；单只证券无翻页，返回行数撞上 `limit`（默认 6000、上限 10000）标 `partial` 并告警。同步+异步。
- 新增 `reference.institution_search`（机构 ID 搜索，5 类机构 `domesticBroker`/`foreignInstitution`/`leadInstitution`/`opinionInstitution`/`foreignOpinionInstitution`，结果自带 `usageScopes`，覆盖各接口 broker/institution 入参；免费）；`vault.my_conference_list` 新增 `source`（录制来源 1=企微会议助理 2=会议服务微信群）。
- `vault.wechat_chatroom_list` 接口改版为 `{total, list}`：改为按 total 并发翻页（移除已无端点使用的串行翻页机制）。
- 无翻页行情端点（`fund_flow` 单只 / `minute_kline` / 显式多标的 `day_kline`·`-hk`·`-us`·`index_day_kline`）返回行数撞上 `limit` 时标 `partial`（`raw` 可见）并发 `UserWarning`，避免静默截断；全市场分片合并结果 `total` 改为合并后行数、撞每片上限也标 `partial`，并保留首个非空 `fieldList`（尾部空分片不再清空列）。
- 下载端点若返回 `302` 跳转到预签名/对象存储 URL，现会跟随取回真正的文件（此前可能把空跳转体写盘；`200`+JSON `{url}` 变体本就已支持）；跨域跳转自动丢弃 `Authorization`，bearer 不外泄到存储域。补齐 CLI v0.22.0 遗留的下载行为。
- **所有分页端点行为变更**：服务端 `total` 虚高（实际返回行数更少）或触及 `MAX_PAGES`（1000）安全上限截断时，现标 `partial`（`raw` 可见）并发 `UserWarning`——此前两种情况均静默。
- 行情端点 `limit` 改为本地校验：超出 `1..10000` 或非整数（如 `1.5`、`True`、`"10"`）在发请求前即抛 `ValidationError`（此前可能打到服务端或抛出原始 `TypeError`）。

### 0.1.12 - 2026-07-02
- 对齐 CLI HEAD 对抗审查修复（含行为变更）：`insight.*` 纯日期串 `YYYY-MM-DD` 改按**本地午夜**锚定（此前 UTC 午夜，非 UTC 用户查询窗口偏一天）；`fundamental.earning_forecast` 仅传 `end_date` 时缺省起点改为锚定该日期前一年（此前锚定今天）；`normalize_token` 大小写不敏感剥 `bearer ` 前缀，避免 `Bearer bearer ...`。
- 下载更稳：自动命名遇同名加 `-1..-99` 后缀防批量覆盖、超长名截到 ≤200 UTF-8 字节且保留扩展名、`Content-Disposition` 的 RFC 5987 `filename*=UTF-8''` 大小写不敏感百分号解码（中文名正确落地）；鉴权重试复用他处已刷新的 token；异步清理 `.part` 改同步 `finally`，取消时也不漏删。
- 分页更稳：`MAX_PAGES` 上限改为生成扇出请求时即刻生效（损坏的 `total` 不再撑爆内存/挂死）；空或短首页不再重复请求同一偏移；异步畸形/空扇出页标 `partial`。
- 异步门面：不再跨 `asyncio.run()` 复用旧事件循环的 `httpx.AsyncClient`（消除 “Event loop is closed”）；`reset()`/`configure(replace=True)` 会关闭缓存的异步客户端。
- 发布 CI：`uv sync --locked`、发版前校验 README/CHANGELOG 含该 tag、PyPI 发布 action 钉到 commit SHA。

## 安装

```bash
pip3 install gangtise-openapi        # 或 pip
```

需要 Python 3.10+。

### 更新到最新版

```bash
pip3 install --upgrade gangtise-openapi
```

（刚发版时若提示找不到新版本，是 PyPI/pip 缓存滞后，加 `--no-cache-dir` 强制刷新。）

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

SDK 覆盖 10 个领域下的 90 个上游接口：

- `gangtise.auth.*` — 登录、状态
- `gangtise.lookup.*` — 本地查表（券商机构、会议机构）
- `gangtise.reference.*` — 证券搜索（GTS 代码）、机构 ID 搜索、公众号 ID 搜索、常量分类与常量值（行业/城市/公告分类/区域）、题材 ID 搜索、板块 ID 搜索与成分股
- `gangtise.insight.*` — 观点、研报、研报图表、公告、日程、投资者问答
- `gangtise.quote.*` — K 线、实时行情、A 股资金流向
- `gangtise.fundamental.*` — 财务报表、估值、股东、盈利预测
- `gangtise.ai.*` — AI 生成的洞察（一页通、同业对比、业绩点评等）
- `gangtise.vault.*` — 个人云盘、会议记录、股票池、微信
- `gangtise.alternative.*` — 经济指标（EDB）、题材（概念）指数画像与成分股
- `gangtise.indicator.*` — 证券级数据指标（EDE）：搜索指标码、截面、时序

Python 封装接受与 CLI 参数相同的入参，只是用 `snake_case` 代替 `--kebab-case`。例如 CLI 的 `--start-date` 对应 Python 的 `start_date`。

## 许可证

MIT
