# gangtise-openapi

[Gangtise OpenAPI](https://openapi.gangtise.com) 的 Python SDK。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.38.0 功能对齐，覆盖 97 个上游接口，并提供本地鉴权状态辅助工具。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

### 0.4.0 - 2026-09-07
- 对齐 CLI **v0.38.0**。**无新增接口**，仍 97 个上游接口。**次版本号**：本版会拒掉上一版会转发的入参、会对上一版当成功渲染的响应报错，另有两处同样的调用行为有变。
- **新拒收的入参**：① 日期 / 时间 / 时间戳参数**末尾带换行**（从文件或管道读入的值请先 `.strip()`）；② `indicator_param` 的键必须是 `indicator` 里列出的 code——拼错的 code 此前会作为一个未被查询的指标的参数组发出，参数（以及不要日期的标记 `{"<code>": {}}`）等于没设；③ `ai.stock_summary_list` 单次超过 5000 只——接口文档写 6000，更大的批次服务端返回空列表且不报错，读起来就是「所有证券都没有看点」，请自行分批。
- **新拒收的响应形状**（此前都会给出一个看着合理的结果）：① `fieldList` 有重复列名——按位置拍平时后一列会覆盖前一列，两个 `close` 会塌成一个；② 数组行没有 `fieldList`——没有列名就无从按位置读；③ 行情端点返回的载荷里没有 `list`——七个行情端点在任何情况下都返 `{total, list}`（空区间、非法代码在内），所以 `null` 或裸对象是坏响应而不是空响应，现在报 `ApiError` 并带上响应的 `traceId`。
- 🔴 **`ai.knowledge_batch` 与 A 股 `insight.announcement_list` 的 `start_time` / `end_time` 改按北京时间（UTC+8）锚定**。这两个接口收 13 位毫秒、由 SDK 代为换算，锚点现在是固定的，不再取运行机器的时区，`"2026-08-01"` 在哪台机器上都是同一时刻。要别的锚点就显式传偏移（`"2026-08-01T00:00:00-04:00"`）或时间戳。本地夏令时跳过的墙钟时刻现在也能转换（UTC+8 没有这个空档）。
- 🔴 **下载默认不再为了文件名去查 list 接口**。标题缓存未命中时，取一个友好文件名要向 list 接口发 4 次请求，而这些接口多数按条计费，比下载本身还贵。现改为按次开关 `resolve_title=True`；不开就用服务端自己的 `Content-Disposition` 文件名，再退到 `<前缀>-<id>`。**先 `*_list()` 再 `*_download()` 的常规用法不受影响**：缓存命中，不会多发请求。
- **新增：一次可传多只证券**。`quote.minute_kline` 现在收列表（接口本身一次只吃一只，SDK 并发发出后按传入顺序合并）；`quote.day_kline` 在「证券数 × 区间交易日数」超过 `limit` 时自动改为逐只请求——一次请求按顺序填满行数上限，尾部证券会整只从结果里消失。两者都要求各只的列布局一致，填满 `limit` 的证券记入 `truncatedSecurities` 并标 `partial`。
- **新增：完整性信号**。① `missingFields`——传了接口不认的 `field=` 时，该列会被连名带值丢弃（HTTP 200、不报错），现在标 `partial` + `missingFields` 并告警；只判「请求了但没回」，不依赖字段白名单。② 全市场 K 线分片按列名对齐后再合并，行宽与自身 `fieldList` 不符、无法对齐、或 `total > 0` 却零行的分片记入 `failedShards`。③ 分片 / 后续页 / 逐只请求自带的 `partial` 会传导到合并结果并告警（默认返回的 DataFrame 带不走这些标记）。④ 从末页起步的全量拉取现在同样探测 `total` 是否被服务端封顶。⑤ 单个异常分片不再中断其余分片的取数。
- **修复**：下载改用端点声明的超时下限，不再直接读客户端默认超时。
- **文档**：ETF 与 20 个全球指数可直接传代码（`512800.SH` / `SPX.SPI` / `N225.NKI` / `HSI.HI`），**市场关键词只覆盖个股**，ETF 与指数需逐个列出；全球指数哪些列为 `null` 按接口而异（`realtime` 是 `volume` / `amount` / `amplitude`，`minute_kline` 是 `volume` / `amount`，`day_kline` 只有 `amount`），时间为交易所当地时间，ETF 带 `adjustFactor` 且 `volume` 单位是「份」。`quote.realtime` 的 `tradeStatus` 仅 A 股 / 港股个股有值，`turnoverRate` / `volumeRatio` **不返回**（换手率改用 EDE 指标 `qte_turn`），美股 `amount` 为 `null`。`fundamental.earning_forecast` 的 `roe` **单位是百分比**。`insight.foreign_opinion_list` 的 `region` 取值、海外观点两个接口的 `industry` 码系、以及 `vault.wechat_message_list` 的 `industry` 码系均按接口现行为写明。

### 0.3.1 - 2026-08-18
- 对齐 CLI **v0.35.0–v0.36.0**。**无新增接口**，仍 97 个上游接口。**补丁号：0.3.0 能跑的调用一个都不受影响**——日期校验只放宽（原先收的写法照收、归一后仍是它自己），探针那条是把 0.3.0 本该有的行为修回来。返回数据上唯一的变化：`ai.hot_topic` 全量拉取此前被静默截断的情况，现在会明说（`totalCapped` / `partial` + 告警）；请求层面该次全量拉取会多发一个 `from = total` 探针（无论 `total` 是否真的被封顶）。
- **日期写法放宽到三种「年在前」格式。** `start_date` / `end_date` / `date` / `report_date` 现接受 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYYMMDD`，统一归一成 `YYYY-MM-DD` 再发出；`start_time` / `end_time` 同理，只归一日期那一半（`"2026/07/01 09:30:00"` → `"2026-07-01 09:30:00"`，时间部分与 Unix 时间戳原样透传）。上一版只收 `YYYY-MM-DD`，见「关于日期格式」。
- **「年在后」写法仍在本地拒绝**（`01-07-2026`、`07/01/2026`）。平台接口一律按美式「月在前」解析它们——这是平台的解析约定，本身工作正常；但同一串数字按国际习惯是另一天，差半年、HTTP 200、行数看着也正常。SDK 无从判断调用方想要哪一种读法，故只转发无歧义的写法，并在报错里给出可照抄的格式。
- **`total` 封顶探测恢复覆盖 `ai.hot_topic`。** 0.3.0 把它排除在外，依据是「该端点按次计费，探一次要花钱」——这个前提不成立：按平台的计费规则，它是按篇计费（50/篇，一「篇」= 一整份报告），而按篇/按条计费的接口查不到内容不计费——`total` 诚实时探针正好返回空，所以那次探测本来就是免费的。（计费是平台侧的规则，SDK 无法自行测量。）排除的实际效果只是让它失去截断检测：全量拉取被服务端 `total` 封顶时看起来仍是完整的。现与其他分页端点一致，探到数据会标 `totalCapped` / `partial` 并告警。
- **文档订正**：`indicator.screener` 的「不要查询日期」写法（`indicator_param={"F1": {}}`）此前在内部注释里被描述成不存在，实际从 0.3.0 起就可用——四份 docstring 与本条对齐。CLI 加入了同语义的写法——v0.35.0 是截面的 `--indicator-param "<指标code>:"`，v0.36.0 是条件选股的 `--indicator-param "<变量名>:"`（与本 SDK 一样按变量键控），两边现在能力一致。

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
  >
  > **年在前的 `2026/07/01` 与 `20260701` 已于 0.3.1 放开并归一**，本条只对年在后的写法仍然成立——详见下文「关于日期格式」一节。
- **破坏性：时间参数只收 10/13 位时间戳或 `YYYY-MM-DD[ HH:mm[:ss]]`**（空格或 `T` 分隔）。`start_time`/`end_time` 按字段校验后**原样透传**——透传型 list 端点对年在后格式的误读方式与日期端点完全一致。这些字段拒绝 `.SSS` 毫秒尾与时区尾（服务端按自己时区解析该字符串，SDK 不转换就无权替它假设偏移）。校验**与客户端时区无关**：本地时区跳过的墙钟时刻（DST 缺口）照常转发，合法性只由服务端时区决定。
- **破坏性：`ai.knowledge_batch(start_time=…)` 改收 `int | str`** 并统一转 13 位毫秒（与 A 股 `insight.announcement_list` 一致）；此前只收裸 `int` 且不做任何校验。私有 helper `domains.insight._to_unix_ms` 并入共享的 `domains._common._to_timestamp13`。
- **新增 `ApiError.trace_id`**，并在 `str(err)` 里渲染成 `[trace 830965044897325056]`——这是 Gangtise 侧唯一能回溯一次失败的抓手，报障请带上。两个转换端点额外接受带时区的 ISO 串（`2026-01-01T00:00:00+08:00` / `Z` / `+0800`），这是有意比 CLI 放宽：转成毫秒时显式偏移无歧义，且 `dt.datetime.now(tz).isoformat()` 是 Python 常见写法。
- **错误码表按三层结构重写**（`999xxx` 服务统一层 / `1xxxxx` 业务通用层 / `2xxxxx` 接口专有层），61 条覆盖全部 41 个公开码 + 实测仍在线的旧码。两代都列是有意的：实测 2026-07-22 迁移是部分的——业务层已发新码（JSON **数字**、带 `errorType`），而 token 过滤器仍发 `0000001007`/`0000001008`/`900002`。提示文案改为只给下一步动作、不再复述服务端 msg，且引用 SDK 的方法/参数名而非 CLI 选项。**`900002` 释义纠错**：旧表写「请求缺少 uid」，服务端实际用它表示「请求类型有误」（HTTP 405），据旧文案排查会走错方向。补上 `410001`/`410106` 两个 EDE 旧码的提示——它们是 `indicator` 取数最常见的两个报错（漏传 `indicator`/`security`、漏传必填 `indicator_param`），此前完全没有提示。
- **异步轮询认新码 `140001`/`140002`**（生成中 / 终态失败）。服务端目前仍发旧码，此为预置——但漏了代价很大：不认「生成中」的轮询会在首次尝试就中止，把已扣的 50 积分作废。终态失败的报错现在带上服务端的 code/msg/`traceId`，并提示重新提交会再次计费且结果不会变（此前只有一句 `Content generation failed (terminal). Do not retry.`）。
- **`999011`/`140002` 任何 HTTP 状态都不重试**（优先于 429 与 5xx 规则）：凭证错不会自己好；异步 `*-check` 端点无 retry 声明，`140002@500` 此前会被默认策略白重试 2 次才轮到异步层判定终态。**token 自愈补 `999002`**（`0000001008` 的新码），服务端切换后不再静默失效。
- **HTTP 200 包裹的错误信封保留 `Retry-After`**（Gangtise 也用这种形态）：此前该路径丢掉服务端的退避窗口、退化成盲目指数退避；主 JSON、异步、下载三条路径都已接线。
- **修复毫秒转换的量级判断**：旧规则是 `> 1e12`，而 13 位的 `1000000000000` 恰好等于 1e12，会落进秒分支再乘 1000。改按位数判断后无边界可错。**转换端点拒绝 DST 缺口时刻**（美国春季 `02:30`、Lord Howe 的 30 分钟缺口 `02:15`）——这类墙钟时刻没有忠实的时间戳，`datetime.timestamp()` 会静默映到缺口另一侧、查到的是另一个小时。所有形状校验改用 `re.ASCII`（Python 的 `\d` 匹配全角数字且 `int()` 认全角，全角日期此前能过检查再原样发给读不懂它的服务端）；年份 `0000` 改为拒绝而非从转换路径漏出裸 `ValueError`。

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

## 关于日期格式

**三种「年在前」写法都收，统一归一成 `YYYY-MM-DD` 再发出：**

| 你传的 | 发出去的 |
| :-- | :-- |
| `"2026-07-01"` | `2026-07-01` |
| `"2026/07/01"` | `2026-07-01` |
| `"20260701"` | `2026-07-01` |

`start_time` / `end_time` 同理，只归一日期部分：`"2026/07/01 09:30:00"` → `"2026-07-01 09:30:00"`（秒可省，空格或 `T` 分隔）；10/13 位 Unix 时间戳原样透传。

⚠️ **末尾带换行的写法会被拒绝**（`"2026-07-01\n"`）——从文件或管道读进来的值先 `.strip()`。

⚠️ **`ai.knowledge_batch` 与 A 股 `insight.announcement_list` 例外**：这两个接口收 13 位毫秒，由 SDK 代为换算，**锚点固定为北京时间（UTC+8）**，与运行机器的时区无关。要别的锚点就显式传偏移（`"2026-08-01T00:00:00-04:00"`）或直接传时间戳。

**「年在后」的写法会在发请求前拒绝**，因为它对不同人意思不同：

| 写法 | 美式读法 | 国际习惯读法 | 平台实际按 |
| :-- | :-- | :-- | :-- |
| `01-07-2026` | 1 月 7 日 | 7 月 1 日 | **1 月 7 日**（美式） |
| `07-01-2026` | 7 月 1 日 | 1 月 7 日 | **7 月 1 日**（美式） |

平台接口本身能解析年在后的写法，**一律按美式「月在前」**。所以若按国际习惯用 `"01-07-2026"` 表示「7 月 1 日」，拿到的是 1 月 7 日的数据——请求返回正常、行数看着也正常，**不会有任何报错提示**。SDK 在发请求前就拒掉这类写法（不发请求、不计费，`ValidationError` 里直接给出可用格式），所以经 SDK 调用不会踩到这个坑。

⚠️ **绕过 SDK 直接调 HTTP 接口时，请统一使用 `YYYY-MM-DD`。**

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
