# gangtise-openapi

[Gangtise OpenAPI](https://openapi.gangtise.com) 的 Python SDK。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.28.0 功能对齐，覆盖 90 个上游接口，并提供本地鉴权状态辅助工具。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

### 0.2.0 - 2026-07-22
- 对齐 CLI v0.28.0（2026-07-17 错误码三层重排 + 日期严格校验 + 重试策略修正）。**无新增接口**，仍 90 个上游接口。**次版本号而非补丁号：本版会拒掉上一版会转发的入参。**
- **破坏性：日期参数只收 `YYYY-MM-DD`。** `start_date`/`end_date`/`date`/`report_date` 其余写法在发请求前抛 `ValidationError`，包括服务端本能正确处理的 `2026/07/01`、`20260701`——统一成一种入参形态，好过按端点逐一探针维护白名单。真正要堵的是另一类：实测（2026-07-22，`insight.research.list` 同窗口比 `total`）服务端**按分隔符翻转日月且静默接受**——`07/01/2026`(斜杠) 读成 `2026-01-07`（total 246534）、`07-01-2026`(横杠) 读成 `2026-07-01`（total 24092），同样三个数字差半年、都 HTTP 200、响应不回显实际采用的日期（用 `25/12/2026` 可解析而 `12/25/2026` 报错交叉验证）。客户端无从判断用户想要哪个读法，故只转发无歧义写法。
- **破坏性：时间参数只收 10/13 位时间戳或 `YYYY-MM-DD[ HH:mm[:ss]]`**（空格或 `T` 分隔）。`start_time`/`end_time` 按字段校验后**原样透传**——透传型 list 端点对年在后格式的误读方式与日期端点完全一致。这些字段拒绝 `.SSS` 毫秒尾与时区尾（服务端按自己时区解析该字符串，SDK 不转换就无权替它假设偏移）。校验**与客户端时区无关**：本地时区跳过的墙钟时刻（DST 缺口）照常转发，合法性只由服务端时区决定。
- **破坏性：`ai.knowledge_batch(start_time=…)` 改收 `int | str`** 并统一转 13 位毫秒（与 A 股 `insight.announcement_list` 一致）；此前只收裸 `int` 且不做任何校验。私有 helper `domains.insight._to_unix_ms` 并入共享的 `domains._common._to_timestamp13`。
- **新增 `ApiError.trace_id`**，并在 `str(err)` 里渲染成 `[trace 830965044897325056]`——这是 Gangtise 侧唯一能回溯一次失败的抓手，报障请带上。两个转换端点额外接受带时区的 ISO 串（`2026-01-01T00:00:00+08:00` / `Z` / `+0800`），这是有意比 CLI 放宽：转成毫秒时显式偏移无歧义，且 `dt.datetime.now(tz).isoformat()` 是 Python 常见写法。
- **错误码表按三层结构重写**（`999xxx` 服务统一层 / `1xxxxx` 业务通用层 / `2xxxxx` 接口专有层），61 条覆盖全部 41 个公开码 + 实测仍在线的旧码。两代都列是有意的：实测 2026-07-22 迁移是部分的——业务层已发新码（JSON **数字**、带 `errorType`），而 token 过滤器仍发 `0000001007`/`0000001008`/`900002`。提示文案改为只给下一步动作、不再复述服务端 msg，且引用 SDK 的方法/参数名而非 CLI 选项。**`900002` 释义纠错**：旧表写「请求缺少 uid」，服务端实际用它表示「请求类型有误」（HTTP 405），据旧文案排查会走错方向。补上 `410001`/`410106` 两个 EDE 旧码的提示——它们是 `indicator` 取数最常见的两个报错（漏传 `indicator`/`security`、漏传必填 `indicator_param`），此前完全没有提示。
- **异步轮询认新码 `140001`/`140002`**（生成中 / 终态失败）。服务端目前仍发旧码，此为预置——但漏了代价很大：不认「生成中」的轮询会在首次尝试就中止，把已扣的 50 积分作废。终态失败的报错现在带上服务端的 code/msg/`traceId`，并提示重新提交会再次计费且结果不会变（此前只有一句 `Content generation failed (terminal). Do not retry.`）。
- **`999011`/`140002` 任何 HTTP 状态都不重试**（优先于 429 与 5xx 规则）：凭证错不会自己好；异步 `*-check` 端点无 retry 声明，`140002@500` 此前会被默认策略白重试 2 次才轮到异步层判定终态。**token 自愈补 `999002`**（`0000001008` 的新码），服务端切换后不再静默失效。
- **HTTP 200 包裹的错误信封保留 `Retry-After`**（Gangtise 也用这种形态）：此前该路径丢掉服务端的退避窗口、退化成盲目指数退避；主 JSON、异步、下载三条路径都已接线。
- **修复毫秒转换的量级判断**：旧规则是 `> 1e12`，而 13 位的 `1000000000000` 恰好等于 1e12，会落进秒分支再乘 1000。改按位数判断后无边界可错。**转换端点拒绝 DST 缺口时刻**（美国春季 `02:30`、Lord Howe 的 30 分钟缺口 `02:15`）——这类墙钟时刻没有忠实的时间戳，`datetime.timestamp()` 会静默映到缺口另一侧、查到的是另一个小时。所有形状校验改用 `re.ASCII`（Python 的 `\d` 匹配全角数字且 `int()` 认全角，全角日期此前能过检查再原样发给读不懂它的服务端）；年份 `0000` 改为拒绝而非从转换路径漏出裸 `ValueError`。

### 0.1.18 - 2026-07-12
- **自动命名下载在不支持硬链接的文件系统上不再丢文件**：v0.1.17 的 `os.link` 仅对硬编码 errno 白名单回退 O_EXCL 占位，漏了 macOS exFAT/SMB 的 `ENOTSUP`（与白名单里的 `EOPNOTSUPP` 是不同值）和 Windows FAT 的 `EINVAL`——完成的 `.part` 被删、下载报成写失败（no-replay 计费端点手动重试还再扣费）。现任何 `os.link` 失败都回退占位（`ENOSPC`/`EROFS` 等真故障会在占位的 `os.open` 处照常抛出）。
- **302 跳转目标回 200+JSON 不再被当文件写盘**：跳转目标返回 `application/json` 业务错误 envelope 时，此前把 JSON 字节存成 `report.pdf` 并报成功（计费 + 损坏文件）；现跟随后的拉取与直连下载路径同样做 envelope 校验——失败 envelope 抛 `ApiError`、`{url}` 元数据续接，对齐 TS `client.ts`。
- **跳转那一跳的 CDN 瞬态 429/5xx 改为重试**：跟随 URL 此前只重试网络错误，一次性 `503`/`429`（签名仍有效）会立即失败；现可重试状态按默认策略重试（尊重 `Retry-After`），`403/404` 仍快速失败（签名过期重放无意义），计费上游永不重发。
- **同源 302 保留 bearer**：手工跳转此前对任何 `Location` 都不带 `Authorization`，同源跳到另一鉴权路径的 302 会 401/403；现仅当 `Location` 停在 API 同源（scheme+host+port 精确匹配）时转发 bearer，跨源 CDN 永不可见。恢复 v0.1.16 / TS 一致。
- **`_require_fetchable_url` 真正 fail-closed**：此前用 stdlib `urlsplit` 校验（比 httpx 宽松），含控制符、畸形点分 IPv4 或 IDNA 主机、超长、前导空格的 URL 能过闸，随后 `httpx.URL` 抛 `httpx.InvalidURL`（非 `httpx.HTTPError`）逃出 except 阶梯；现用 `httpx.URL` 本体 + 精确 strip 校验，畸形 URL 抛脱敏后的 `DownloadError`。
- **`.part` 清理失败不再把成功下载报成失败**（独立 Codex 审查发现）：`os.link` 提交完整文件后，`finally` 的 `.part` unlink 是承重步骤，一旦失败（杀软锁、只读挂载）裸 `OSError` 会绕过 `except OSError` 报假失败（并诱发 no-replay 重扣）；现清理改为尽力而为。
- **任何从跟随目标冒出的错误都不再重放计费上游，`{url}` 链加跳数上限**（对上述修复的第二、三轮复核）：把跟随目标的 JSON envelope 抛成 `ApiError` 后，从**已成功的上游之后**冒出的错误仍可能驱动 `download_to_path` 外层循环重发上游。现此类错误打标记、短路**每一条**外层重放：**鉴权** envelope（`0000001008`/`8000014`/`8000015`）的刷 token 路径，以及可重试 `999999` 的默认策略重试路径（正是让默认重试端点 `insight.report-image.download`（0.1 积分/张）被重扣三次的那条）。直连（非跟随）路径的鉴权自愈与 `999999` 重试不变。自引用/环形 `{url}` 链现以有上限的 `DownloadError`（最多 5 跳）失败，不再递归到 `RecursionError` + 请求风暴；同源 bearer 转发每跳重新判断（第二个同源跳不再丢 bearer）；`_redact_url` 改为复用 `httpx.URL` 的判定，非 ASCII/畸形 authority（坏 IDNA、非法点分 IPv4 如 `1.2.3.999`）折叠为 `redacted-url` 而非回显。
- **跟随目标错误改用计费安全提示、占位回退扛住 close 故障、同源精确区分显式 `:0`**（第四轮复核）：(1) 打标记的跟随目标错误仍带通用 `.hint`——`999999` 的「请稍后重试」、鉴权码的「会自动重新登录重试」——都会诱导用户手动重发、重扣已执行的上游（且此处并不会真的自动重登），现改为专用提示，明确「计费上游已执行、勿盲目重试」。(2) 无硬链接占位提交里，对 `O_EXCL` 占位 fd 的 `os.close()` 未加保护：close 期 `OSError`（如本版重点覆盖的 SMB/exFAT 上的 `EIO`）会在改名前中断，完整 `.part` 被外层 `finally` 删除、只剩 0 字节文件；现 close 改为尽力而为（fd 仅用于占名，承重的改名照常落盘）。(3) `_same_origin` 用 `port or default` 把显式 `:0` 折成默认端口，令 `https://api.test:0` 与 `https://api.test` 判为同源；现改用 `port if not None else default`，scheme+host+port 真正精确匹配。无端点/API 表面变更，仍对齐 CLI v0.27.0、90 接口。

### 0.1.17 - 2026-07-12
- **计费安全（重要）**：下载端点 302 跳转 CDN 后 CDN 失败，不再重放计费上游端点——此前上游让 httpx 内联跟随跳转，CDN 那一跳失败会被误判为**上游**的连接期错误，对 no-replay（按篇计费）端点触发重发；现上游停在 3xx、把 Location 交给签名 URL 拉取器（其重试循环只重放不计费的 CDN URL）。跟随后的 URL 也补上了此前绕过的 10× 传输硬截止。
- **签名 URL 脱敏改为 fail-closed**：`_redact_url` 此前只留 `scheme://host/path`，但裸 `alice:SECRET@host/p` 会被解析成 scheme=`alice`，旧的 netloc 路径会泄露 `alice://SECRET@…`；非法端口还会以未包装的 `httpx.InvalidURL` 带出原值。现非绝对 http(s)+有 host+合法端口一律折叠为 `redacted-url`，签名 URL 拉取前先校验，畸形 URL 抛脱敏后的 `DownloadError`。
- **自动命名下载恢复原子可见 + 后缀正确**：v0.1.16 的 `O_CREAT|O_EXCL` 占名会先创建 0 字节最终文件再 rename（崩溃可能留下看似成功的空文件），且 `report-1.pdf` 碰撞会落成 `report-1-1.pdf` 而非 `report-2.pdf`；现改用 os.link 把完成的 `.part` 硬链接到目标（完整文件一次性出现、后缀从原始名扫描），仅在不支持硬链接的文件系统回退 O_EXCL 占位（仍非 clobber）。
- **EDE 内层 999999 补正确提示**：双层 envelope 的内层错误在 transport 之外解包，此前仍是「请稍后重试」；现与外层同用「检查查询条件」的 EDE 提示。
- **零警告固化**：`pyproject.toml` 的 `filterwarnings` 把本项目的 `UserWarning` 升级为错误，未来分片/漂移告警会让本地与 CI/release 套件失败（此前仅在个别测试临时断言）。无端点/API 表面变更，仍对齐 CLI v0.27.0、90 接口。

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
