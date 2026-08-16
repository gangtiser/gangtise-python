# gangtise-openapi

[Gangtise OpenAPI](https://openapi.gangtise.com) 的 Python SDK。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.34.1 功能对齐，覆盖 97 个上游接口，并提供本地鉴权状态辅助工具。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

### 0.3.0 - 2026-08-15
- 对齐 CLI **v0.28.3–v0.34.1**（9 个版本）。新增条件选股、帕米尔专家纪要、财报日历、PDF 解析四组接口，**97 个上游接口**（此前 90）。**次版本号：本版会拒掉上一版会转发的入参，也会对上一版当成功渲染的响应报错。**
- 🔴 **修复：`indicator.cross_section` / `time_series` 此前对线上 API 完全不可用。** 服务端 2026-08-01 重构了 EDE 契约，而 SDK 仍在发旧 body（`securityCodeList` + 根级 `date`）、读旧响应（两个平行 name/code 数组 + 未转置矩阵），旧 body 一律被回 `100001 缺少必填参数`。现已对齐：`universe`、每指标各自的 `tradeDate`、结构化 `indicatorList`、截面 `values` 转置为 `[证券][指标]`、截面输出不再有 `date` 列。
- 🔴 **复权参数名是 `adjustType`，不是 `adjustmentType`**——服务端对错参数名静默忽略并退回不复权，数看着正常实则错（茅台 2024-01-02：`adjustType=3` → 13609.6168 真后复权，错名 → 1685.01 不复权）。文档、示例、参数表全线改正。
- ⚠️ **报告期类指标（`is_*` 等）自 2026-08-14 起拒收 `tradeDate`**，须用 `indicator_param` 传 `reportDate`。哪个指标吃哪个日期**不能按 code 前缀推断**（170 指标抽样：7 个 `finc_*`、3 个 `div_*` 要 `reportDate`，而 8 个 `is_*`、4 个 `cf_*` 要 `tradeDate`；`div_cash_yld` 两个都要），新增按服务端**消息内容**匹配的提示层，直接给出该改的写法并指向 `indicator.search` 的 `parameterList`。
- 🔴 **修复：`quote.day_kline` 拉不了全市场。** 服务端 2026-08-14 停止支持 `"all"`，改为 `aShares` / `hkStocks` / `usStocks` 且**必须单独传**——两种错法服务端都回 `120001「证券代码无效」`，提示指向本来没问题的代码，照着排查会一路走偏，故本地先拦并给出该用哪个关键字。分片改为按市场取粒度（A/美股 1 天、港股 2 天）；`index_day_kline` 从 30 天改 **15 天**（531 行/交易日 × 30 天窗口约 11.7K，必然撞 10000 上限并静默截断）；关键字改为按小写比对并归一化后再下发（`fund-flow` 是唯一服务端不折叠大小写的端点，这一步是它能收 `ashares` 的唯一原因）。
- 🔴 **`quote.fund_flow` 不再把「关键字 + 代码」静默降级成单只**（服务端在该端点上是静默丢弃关键字、只返代码那几行）；**`ai.stock_summary_list` 拒收市场关键字**（服务端已移除全市场批量，且该接口按 3 积分/条计费，拦在发请求前）。
- 🔴 **列式响应行长与 `fieldList` 不符改为硬失败。** 此前短行补 `None`、长行丢值，而按位置拍平会把值贴到错误的字段上：`quote.realtime` 传 `field=["securityCode","close","turnoverRate"]`（realtime 根本没有 `close`）只回 2 个值，换手率 28.5573 被贴成 `close`，读起来就是「茅台收盘价 28.56」（真实价 1297.41）——不报错、数字看着合理、却完全是另一个指标。
- 🔴 **`search_type` / `rank_type` / `file_type` 改为本地白名单。** 传了范围外的枚举值时，可观察到的结果是：该筛选条件不生效、返回**未过滤的结果集**、HTTP 200——与传一个服务端不认识的字段表现一致。最坏的一例是非法 `search_type` 会连 `keyword` 一起失效，`summary_list(keyword=…)` 返回的不再是这个关键词的结果，而是**整库量级**（实测相差三个数量级），自动化流程里几乎不可能发现。守卫挂在 `_request_body` 与端点表上，新增的 wrapper / 下载端点自动覆盖。
- **分页新增 `total` 封顶探测。** `insight.opinion*` 三个端点的 `total` 恒为 10000 而实际记录远不止，于是全量拉取正好取满就停、`collected == total`，所有完整性检查都通过——一次自以为完整的截断导出，而该端点按 30 积分/条计费。现全量拉取后探一行 `from = total`，探到数据就标 `partial` + `totalCapped` 并告警（判据不写死 10000；`total` 诚实时探针返回空且按条计费下不产生费用）。分页首包异形、`total` 跨页漂移同样标 `partial`。
- **矩阵护栏**：身份轴（证券代码 / 日期 / 指标 code）一律不许强转（`None` 曾变成字面量 `"null"` 标签，凭空造出的身份比缺数据更危险）；行数与每行单元格数双向校验；时序响应同时出现多证券与多指标改为硬失败（该形态无法归属，且请求/响应差集为空，没有别的守卫会注意到）；`securityNameList` 长度不符**只丢名称、保住数值**（名称是标题不是身份，与其他必须致命的守卫有意不对称）；板块 ID 一律优先按证券轴出列；服务端未能解析的 code 标 `partial` + `omittedIndicators` / `omittedSecurities`。
- **形状错误不再丢 trace**：`unwrap_envelope` 剥掉信封时会把 `traceId` 一并丢掉，而形状守卫恰好都在 transport 之外——报障时最需要的那个 id 拿不到。现解包后的载荷带着信封的 id（dict 子类，序列化/比较/建表与普通 dict 无差），`ApiError.trace_id` 回落到它；EDE 双层信封会把**外层** id 传下去（内层本身没有）。
- **示例 93 → 100（每侧）**，`sample/API_PARAMETERS.md` 补 7 个方法段；三大报表补充 **`earliestAnncDate`** 的用法说明（做 point-in-time 对齐要用它——实测存在个股把 `announcementDate` 四个季度全填成年报披露日）。
- **查证后未改**：CLI v0.34.1 的两条 title-cache 并发缺陷在 Python 不成立（`flush` 全程持锁、`_load` 只在构造时跑一次），已补两条回归测试钉住这个性质，而不是假定它成立。

### 0.2.1 - 2026-07-24
- 对齐 CLI v0.28.1–v0.28.2。indicator `cross_section`/`time_series` 新增 `key_by`（`name` 默认 / `code` 用 `indicatorCode`·`securityCode` 做列头——列头就是你传进去的 code，实测服务端按自己的顺序返回列，位置索引不可靠、显示名还要再查一次 `search` 才能映射回 code）；EDE `999999` 无数据提示收窄到取数端点，`search` 回落通用提示。
- **修复：指标无显示名时不再落成名为 `None` 的列。** 服务端确实会发 null 显示名（实测 `qte_open` 回 `indicatorNameList: [None, "日收盘价"]`），此前被字符串化成 `"None"` 当列头；现回退用 `indicatorCode`，`securityNameList` 的 null 也保持 null 而非文本 `"None"`。
- **修复：sdist 不再夹带 `sample/README.md`**（`include` 的 `README.md` 未锚定，把它一起打了进去，而它引用的示例脚本与 `API_PARAMETERS.md` 并不在包里）。
- `sample/API_PARAMETERS.md` 与四个 indicator 示例补上 `key_by`；live 测试新增 3 个 indicator 用例，钉住「服务端重排列序下 `indicatorCodeList` 仍与 `values` 行序平行」这个只能线上验的假设。**补丁号：`key_by` 默认 `name`。**

### 0.2.0 - 2026-07-22
- 对齐 CLI v0.28.0（2026-07-17 错误码三层重排 + 日期严格校验 + 重试策略修正）。**无新增接口**，仍 90 个上游接口。**次版本号而非补丁号：本版会拒掉上一版会转发的入参。**
- **破坏性：日期参数只收 `YYYY-MM-DD`。** `start_date`/`end_date`/`date`/`report_date` 其余写法在发请求前抛 `ValidationError`，包括服务端本能正确处理的 `2026/07/01`、`20260701`——统一成一种入参形态，好过按端点逐一探针维护白名单。真正要堵的是另一类：实测（2026-07-22，`insight.research.list` 同窗口比 `total`）年在后的写法**按分隔符不同被解析成不同的日期**——`07/01/2026`(斜杠) 读成 `2026-01-07`、`07-01-2026`(横杠) 读成 `2026-07-01`，同样三个数字差半年、都 HTTP 200、响应不回显实际采用的日期（用 `25/12/2026` 可解析而 `12/25/2026` 报错交叉验证）。客户端无从判断调用方想要哪个读法，故只转发无歧义写法。

  > 该解析差异已于 2026-08-14 由服务端统一（2026-08-16 复测：三种「7月1日」写法同一个结果）。**本地守卫仍保留**：统一为「月在前」之后，欧洲习惯的 `01-07-2026` 仍会被读成 1 月 7 日而非 7 月 1 日，差半年且无提示。
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

SDK 覆盖 11 个领域下的 97 个上游接口：

- `gangtise.auth.*` — 登录、状态
- `gangtise.lookup.*` — 本地查表（券商机构、会议机构）
- `gangtise.reference.*` — 证券搜索（GTS 代码）、机构 ID 搜索、公众号 ID 搜索、常量分类与常量值（行业/城市/公告分类/区域）、题材 ID 搜索、板块 ID 搜索与成分股
- `gangtise.insight.*` — 观点、研报、研报图表、公告、日程、财报日历、帕米尔专家纪要、投资者问答
- `gangtise.quote.*` — K 线、实时行情、A 股资金流向
- `gangtise.fundamental.*` — 财务报表、估值、股东、盈利预测
- `gangtise.ai.*` — AI 生成的洞察（一页通、同业对比、业绩点评等）
- `gangtise.vault.*` — 个人云盘、会议记录、股票池、微信
- `gangtise.alternative.*` — 经济指标（EDB）、题材（概念）指数画像与成分股
- `gangtise.indicator.*` — 证券级数据指标（EDE）：搜索指标码、截面、时序、条件选股
- `gangtise.tool.*` — PDF 解析（异步：提交 → 取结果 ZIP）

Python 封装接受与 CLI 参数相同的入参，只是用 `snake_case` 代替 `--kebab-case`。例如 CLI 的 `--start-date` 对应 Python 的 `start_date`。

## 许可证

MIT
