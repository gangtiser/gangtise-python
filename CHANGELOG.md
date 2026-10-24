# 更新日志

本文件记录本项目的所有重要变更。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.5.2] - 2026-10-25

与 `gangtise-openapi-cli` **v0.48.0** 功能对齐（覆盖 v0.46.0–v0.48.0）。**新增 4 个接口，共 153 个上游接口 /
端点注册表 155 条**（此前 149 / 151）。

### 新增

- **管理层情绪**（管理层在业绩会问答里的正面回应程度、回复乐观度、回复确定度）：
  - `ai.management_sentiment_indicator`：每场会议的三维评分（0–5）、有效问答数、回避 / 风险 / 低确定度三个
    占比（百分数，`7.14` 即 7.14%）与按问题类型的拆分。
  - `ai.management_sentiment_conclusion`：情绪结论文本、三维情绪信号与较上一场会议的问答对照；没有可比的
    上一场时对照为 `[]`、`previousSource` 为 `None`。
  - 两个列表一行 = 一只证券 × 一场会议，按发布时间倒序，**5 积分/条**，自动翻页（单页 100）。不传 `security`
    即全部证券；省略 `size` 时按额度保护估算，超过 1000 积分需 `confirm=True`。`start_time` / `end_time` 写
    `YYYY-MM-DD`、`YYYY-MM-DD HH:mm:ss` 或 10 / 13 位时间戳，写时刻须带秒（`HH:mm` 报 `110001`）。数据范围
    正式账号 1 年、试用 6 个月。翻页去重按「证券 + 来源会议」联合判定。
  - `ai.management_sentiment_detail(source_id=...)`：一场会议的逐条问答评分（`5.0` / `2.5` / `0.0` 三档）与判断
    依据，`source_id` 取自列表返回的 `source.sourceId`，**10 积分/次**，超时 / 5xx 不自动重发。
  - ⚠️ **返回的 `publishTime` 比北京时间早 8 小时**（北京时间 20:30 的业绩会返回 `12:30:00`），时间筛选仍按
    北京时间。按时刻展示、与纪要对齐或按日期归档前先加 8 小时。
- **`bond.default_list` 违约债券**：债券代码、简称、违约日期、违约金额（亿元）、发行人、违约原因，**0.4 积分/次**。
  按违约日期区间（两端都给、不超过 1 个自然年）、`security` 或 `issuer` 三选一；混传、都不传或只给一端日期，
  在发请求前报 `ValidationError`。`issuer` 一次一个，传列表或用逗号拼接同样本地报错。⚠️ **用发行人全称**：传简称
  也会返回结果，但只返回最匹配的一家主体，核对返回的 `issuerName`。`field` 写错报 `100005`（其余 `bond` 方法为
  `100003`）；条件下没有记录时抛 `ApiError`（`130001`）。
- **`insight.opinion_list` 新增 `category`（观点类别）与 `broker_tag`（机构标签）**：`category` 取
  `earningsReview` 业绩点评 / `abnormalReview` 异动点评 / `researchUpdate` 调研/访谈更新 / `tradingDesk` 交易台 /
  `industryAnalysis` 行业分析，`broker_tag` 取 `topBroker` 头部券商 / `newFortune` 新财富团队。返回行同时带
  `categoryList` / `brokerTagList`（无标签时为 `[]`）。
- **`reference.securities_search(category="bond")`**：按代码或简称搜交易所可转债、国债、地方债、金融债与银行间
  债券（`.SH` / `.SZ` / `.IB`），代码用于 `gangtise.bond`；`quote`、公告等其余方法不收债券代码。

### 变更

- 🔴 **`insight.opinion_list` 的 `llm_tag` 换为 28 项投研业务标签**（推荐 / 业绩侧 / 产业链 / 壁垒四组，如
  `strongRcmd` 强烈推荐、`beatExpect` 超预期、`priceHike` 涨价、`leader` 龙头；完整取值见 docstring 与
  `sample/API_PARAMETERS.md`）。**存量调用要改**：「业绩点评」「头部券商」「新财富团队」改传
  `category="earningsReview"`、`broker_tag="topBroker"` / `broker_tag="newFortune"`，继续传给 `llm_tag` 服务端报
  `100005`。同一参数传多个值取并集（命中任一即返回）。
- `insight.opinion_list(with_content=True)` 不收 `category` / `broker_tag`：同时传在本地报 `ValidationError`、不发
  请求——旧版列表不认这两个字段，会按 30 积分/条返回未经筛选的结果。它的 `llm_tag` 只收 `strongRcmd` /
  `earningsReview` / `topBroker` / `newFortune`，返回行也没有两个新字段。既要按新标签筛、又要正文，先
  `opinion_list` 筛选，再用 `opinion_detail` 取正文。
- **计费单价按平台最新价目**，额度保护随之按新单价估算：
  - AI 生成：`one_pager` / `investment_logic` / `peer_comparison` / `research_outline` / `theme_tracking`
    10 积分/次；`earnings_review` / `viewpoint_debate` 提交 20 积分/次；`management_discuss_announcement` 5 积分/次。
  - `ai.hot_topic` 10 积分/篇；`ai.stock_summary_list` 1 积分/条（一次最多 6000 积分）。
  - 路演 / 调研 / 策略会 / 论坛列表 10 积分/条，省略 `size` 时约 100 条以上才触发 1000 积分的拦截；
    `insight.independent_opinion_list` 1 积分/条，不再先取 1 条估算。
  - 下载：纪要 / 外资研报 / 我的会议 30 积分/篇；A 股公告 1 积分/篇、港美股公告 2 积分/篇；财报日历 A 股
    1 积分/篇、港美股 2 积分/篇。
  - `alternative.edb_data` 30 积分/指标（单次最多 10 个指标，即最多 300 积分）；超时 / 5xx 仍按默认策略重试。
- `bond.daily_quote` / `bond.valuation`：返回的首行比 `start_date` 晚超过 14 天时发 `UserWarning`（债券上市较晚，
  或数据起点晚于所查区间），不标 `partial`。告警只看整批最早的首行：多只同查时有一只数据够早就不会告警，
  逐只的起点按 `securityCode` 核对。
- 列式响应的字段数与 `fieldList` 对不上时，报错改为「响应结构异常」：先去掉 `field` 重试，仍报错再报障。

### 修复

- **路演 / 调研 / 策略会 / 论坛列表的翻页去重此前不生效。** 四个列表按 `id` 认行，实际返回的行 ID 却是
  `roadshowId` / `siteVisitId` / `strategyMeetingId` / `forumId`：相邻两页重复出现的行原样保留，同时漏掉的行
  也不提示，结果看着完整。现在按各自的 ID 去掉整行重复，标 `partial` 并告警；缺的行要缩短时间范围重取。

### 文档

- 四个日程列表的 `location` 可用：传 domesticCity 码（`reference.constant_list(category="domesticCity")`，如上海
  `156310000`）；传城市名（`"上海"`）服务端返回 `999999`、不是参数错误。此前文档说任何取值都不可用，已不成立。
- A 股财务报表返回的是**最新版本数值**：重述过的报告期在 `consolidated` 下也是重述后数值，`announcementDate`
  是该数值所属公告的日期，`earliestAnncDate` 是该期首次公告日。做时点回测别把这些数值按 `earliestAnncDate`
  回填（会用到当时还没公布的重述值）；数值从 `announcementDate` 起可得，首次披露的原始数不在返回里。
- `insight.pamirs_summary_list` 的 `conceptList` / `categoryList` / `marketList` 稀疏、不保证完整，用 `category`
  或 `market` 过滤时回填率明显更高（此前说 `conceptList` 恒为空，已有非空的记录）。
- `fundamental.main_business` / `valuation_analysis` 的 `field` 写了不存在的名字（含 `securityCode`）时，服务端
  整条报 `100005` 并点名；`valuation_analysis` 只传 `tradeDate` 仍返回 0 行、不报错（SDK 发 `UserWarning`）。
- `indicator`：`parameterList` 标必填的 `fiscalYear` 漏传时报 `100001` 并点名，与其他必填参数一致（此前文档说
  漏传不报错，`999999` 的提示一并更正）。区间指标的 `changePeriod` / `yieldType` / `riskFreeRate` /
  `benchmarkCode` 与股东结构类指标的 `rank` / `shareType` 即使 `parameterList` 列了默认值也须显式传，漏传报
  `100001`。`cross_section` 返回的证券顺序不作保证，按 `security` 列对应；`time_series` 每行一个日期，多只证券
  时按列头对应，列的顺序同样不作保证。多只基金横向比较分类、复权净值与风险收益指标（夏普 / 最大回撤 /
  Alpha / 同类排名）用 `indicator.cross_section`（`security` 传基金代码）。
- 基金名称换代码：`reference.securities_search(category="fund")` 同时返回场内与场外（`.OF`）代码，同一基金的
  不同份额一起返回，按 `gtsName` 区分（此前说场外代码搜不到，已不成立）。🔴 **可转债可能出现在任何
  `category` 的结果里**——按公司简称查 `stock` 时同名可转债常排第一，只取返回行 `category` 等于所查类别的那一行；
  债券代码传给 `fund` 方法返回空结果、不报错。
- 数据范围：`ai.hot_topic` 前溯 3 个月（各档相同）；`quote.minute_kline` 最近 1 个月；
  `fundamental.earning_forecast` 前溯 1 年；`vault.my_conference_list` 前溯 1 个月。
- 常量分类新增 `interestBondSubtype`（利率债子类型），对应 `bond.issuance_plan` 的 `bondType`；`bond.basic_info`
  的 `bondType` 仍用 `bondType` 这一套码。

## [0.5.1] - 2026-10-07

与 `gangtise-openapi-cli` **v0.45.0** 功能对齐，无新增接口。

### 新增

- **`vault.drive_copy` 可复制整个文件夹**：传 `folder_id` + `target_parent_id`，连同其中的子文件夹与文件
  复制到另一空间（我的云盘 ↔ 租户云盘），返回 `{folderId, newFolderId}`。复制文件的写法
  （`file_id` + `target_folder_id`）不变。两组参数二选一：混传、只传一半或都不传，在发请求前报
  `ValidationError`。超时 / 5xx 仍不自动重发（重发会多出一份副本）。

### 变更

- **下载文件名**：响应的 `Content-Disposition` 同时给出编码文件名（`filename*`，通常为 UTF-8）与普通文件名时，
  用编码的那个。此前按出现顺序取，普通文件名在前时用的是它（通常是 ASCII 的替代名）。`filename*` 按它声明的
  字符集解码（如 `ISO-8859-1`），此前一律按 UTF-8 解码；字符集无法识别或按它解码失败时退回普通文件名，不会让已收到的下载失败。
- **明文 http 告警**：生效的接口地址（`GANGTISE_BASE_URL` 或代码里传入的 `base_url`）指向非本机地址却用
  `http://` 时，构造客户端时发一次 `UserWarning`——登录与请求里的 AK / SK / token 会明文传输。本机地址
  （`localhost`、`127.x.x.x`、`::1`）不告警。

### 文档

- `bond.daily_quote` / `bond.valuation` 的数据可能比账号的可回溯窗口短：区间早于数据起点时报 `130001`，
  跨过数据起点时从有数据的那天起返回、不报错。**按年份取长序列时核对返回的首行日期。**
- `bond.announcement` 按日期区间查询时，有代码的行都带市场后缀，可直接传给其他 `bond` 方法；部分行（如不
  对应已上市证券的公告）`securityCode` 为空。此前文档说按日期查询时不带后缀，有误。
- `gangtise.fund` 只知道基金名称时：场内基金用 `reference.securities_search(keyword=<场内简称或 6 位代码>,
  category="fund")` 换代码（基金全称常搜不到）；场外 `.OF` 代码搜不到，需要自备。
- `quote.minute_kline` 的可查历史是随日期滚动的短窗口。

## [0.5.0] - 2026-10-01

与 `gangtise-openapi-cli` **v0.44.0** 功能对齐。**新增 52 个接口，共 149 个上游接口 / 端点注册表
151 条**（此前 97 / 99）：公募基金（`fund`）与债券（`bond`）两个领域、云盘管理、股票池增删改、观点正文、会议线索、联网搜索。

**次版本号，而非补丁号**：0.4.0 会发出的几类调用，本版改为在本地拒收；另有两个接口的默认返回内容变了。
两类都列在「破坏性变更」下。

### 破坏性变更——改为在本地拒收

- **按条计费的列表不传 `size`**（研报、公告、观点、路演 / 调研 / 策略会 / 论坛、个股线索、热点话题等）
  按 `total × 单价` 估算全量，超过 **1000 积分**即拒收，`ValidationError` 里给出估算值。`total` 取自第一页；
  若一整页本身就超过 50 积分，则先只取 1 条拿到 `total`。这一页（或这 1 条）照常计费，报错里写明取了几条。显式传的 `size` 按 `min(size, total)` 同样估算。
  只要一部分就传 `size=N`，确认要全量再传 `confirm=True`。免费列表不受影响。
- **`fundamental.earning_forecast`** 按日期区间估算（工作日数 × 3 条 × 0.5 积分），超过 1000 积分时
  不传 `confirm=True` 即拒收。
- **列表参数显式传空列表或空白字符串**（如 `research_list(security=[])`、`hot_topic(category=[])`、
  `field=[]`）一律拒收，报错点名该参数。0.4.0 对此处理不一致（有的发出 `[]`，有的省略该字段，
  `hot_topic` 会展开成全部类别）；若改为省略，就等于把「按空集过滤」变成「不过滤」，在按条计费的接口上
  有风险。要不过滤就别传该参数。`vault.stock_pool_stocks(pool_id=[])` 仍表示全部股票池。
- **`quote.index_day_kline(security="all")`**：接口对它返回空结果且不报错，与「当天无数据」无法区分。
  请用 `quote.day_kline` 逐个传指数代码；指数名称用
  `reference.securities_search(keyword=<代码>, category="index")` 查询。
- **全市场 K 线关键字**（`aShares` / `hkStocks` / `usStocks` / `all`）必须同时给 `start_date` 与
  `end_date`；起始日晚于结束日报 `ValidationError`。
- **`vault.wechat_message_list` 与 `insight.highlight_list` 的 `from_ >= 10000`**：服务端只允许
  `from + size <= 10000`。
- **`indicator_param` 中键名以 `Date` 结尾的值**按 `date` 的规则校验：三种年在前的写法统一成
  `YYYY-MM-DD`，年在后的写法拒收。
- **新增本地取值校验**（0.4.0 会原样发出）：`ai.hot_topic(category=...)`、
  `ai.security_clue_list(source=..., query_mode=...)`、`vault.record_download` 的 `content_type`
  （`original` / `asr` / `summary`）与 `vault.my_conference_download` 的 `content_type`
  （`asr` / `summary`）。空白或不是文本的 `ai.knowledge_batch` 查询与 `fundamental.valuation_analysis(limit=0)`
  同样拒收。`fundamental.valuation_analysis` 的 `indicator` 只收 `peTtm` / `pbMrq` / `peg` / `psTtm` /
  `pcfTtm` / `em`（与 CLI 一致）。
- **列表参数传集合（`set`）、字典（含 `keys()` / `values()`）、迭代器或 bytes** 会报 `ValidationError`，
  报错点名该参数——集合没有顺序，迭代器只能读一次；请传列表或元组。0.4.0 对这些输入有的抛裸 `TypeError`，
  `indicator` 则把 `dict_keys([...])` 这样的文本当作指标代码发出。任意序列（如 `UserList`）以及 pandas
  `Series` / numpy 数组按列表处理，列表里的 numpy 标量按对应的 Python 值发送。
- **代码里传入的 `timeout`**（`GangtiseClient` / `AsyncGangtiseClient` 构造参数与 `gangtise.configure`）须在
  1–3600 秒之间，否则报 `ConfigError`（此前任何值都原样生效）。
- **`insight.independent_opinion_download(resolve_title=True)`**：其列表按 5 积分/条计费，为取一个文件名
  回查 200 条要 1000 积分。先调 `independent_opinion_list()` 时缓存下来的标题仍会免费使用。
- **`GANGTISE_TIMEOUT_MS`** 须为 1000–3600000 之间的整数毫秒：其他取值回退到 30000（超上限则按上限），
  并给出一次告警。

### 破坏性变更——同样的调用，结果不同

- **`insight.opinion_list` / `foreign_opinion_list` 改走 v2 列表**（1 积分/条，原 30）：每行只有 200 字摘要
  `brief`（海外观点另有 `briefTranslate`），不再带正文。正文用新增的 `opinion_detail` /
  `foreign_opinion_detail` 按 ID 取，或传 `with_content=True` 取带正文的旧版列表（30 积分/条，旧版结构）。
- **`alternative.concept_info` / `concept_securities` 改走 v2**（50 积分/次，原 500），不含 `keyEvents`
  与 `isKey` / `inclusionReason`；需要时传 `full=True`（500 积分/次）。
- **`fundamental.valuation_analysis` 省略 `limit` 时按接口默认值显式发送 `limit=2000`**，行数撞满即标
  `partial`：序列每个自然日一行，接口保留最近的行，缺的是区间**开头**。`field` 发送前去重并去掉
  `tradeDate`。**0.4.0 在 `field` 同时含 `tradeDate`（或重复字段）与不存在的字段名时，结果会整体右移
  一列，用过这类组合的请重跑。** 返回里没有 `list` 时报错。
- **`quote` 对多只证券或全市场关键字使用 `field=`** 时，自动在前面补上身份列（`securityCode`，K 线另加
  `tradeDate` / `tradeTime`），并给出告警。
- **`indicator.time_series` 不传 `calendar_type`** 时，若每个指标都声明 `tradeDate`、且都不声明
  `reportDate` / `fiscalYear`（用免费的 `indicator.search` 判定），就用交易日历（`TD`），否则用服务端默认
  的 `ND`。交易日类序列不再带全为空的周末行。
- **全市场 K 线所有分片都失败时**，即使失败只在合并阶段才暴露（分片声称有行却没给），也会报错，不再返回
  一张标 `partial` 的空表。报出的错误是首个失败，否则是窗口外分片的 `110003`。
- **`fundamental.earning_forecast` 超时或 5xx 后不再自动重发**：一次调用可能计费数千积分，重发可能重复扣费。
  `ai.stock_summary_list` 同理（另有 120 秒超时下限）。
- **A 股 `insight.announcement_list` 与 `ai.knowledge_batch` 的 `end_time` 只写日期时**按当日
  23:59:59（北京时间）换算，不再是 00:00。
- **列表参数去首尾空格并去重**：同一代码传两次，此前每行会返回两遍。
- **`auth.login()`** 在配置了 AK/SK 时总是真正登录一次，并返回 `source`（`"login"` / `"env-token"`）；
  设了 `GANGTISE_TOKEN` 时直接报告该 token，不联网。
- **缓存的 token 只给签发它的凭证使用**：缓存记录 access key 与 base URL 的指纹（`issuedFor`，与 npm CLI
  共用同一文件、互相识别）；换了 `GANGTISE_ACCESS_KEY` 后不再发送上一个账号的 token。旧版本写的缓存会多
  一次登录。
- **环境变量设成空字符串按未设置处理。**

### 新增

- **`gangtise.fund`**——18 个方法：基金资料、净值、费率、基金经理、规模、持有人结构、资产 / 股票 / 债券 /
  基金持仓与分布、ETF 申赎清单与份额变动。0.4 积分/次。代码不存在、不带后缀、后缀小写或传成股票代码，都
  **返回空结果、不报错**。各方法单位不同，见 docstring。
- **`gangtise.bond`**——12 个方法：债券资料、发行人、日行情、估值、现金流、公告、发行、评级、利率债发行计划、
  行权。列式返回自动拍平；`announcement` 需手动翻页（`page_no` / `page_size`）。
- **股票池写操作**：`vault.stock_pool_create`、`stock_pool_rename`、`stock_pool_add_stock`、
  `stock_pool_remove_stock`、`stock_pool_delete`。
- **云盘管理**（免费）：`vault.drive_folder_list`、`drive_upload`、`drive_create_folder`、
  `drive_rename`、`drive_move_file`、`drive_move_folder`、`drive_copy`、`drive_delete_file`、
  `drive_delete_folder`。
- **`insight.opinion_detail` / `foreign_opinion_detail`**——按 ID 取观点正文（30 积分/条，每次请求 20 个 ID）。
  没有正文的 ID 列在 `missingIds`；后面某批失败时，已取到的正文照常返回，其余 ID 列在 `unfetchedIds`。
- **`insight.highlight_list`**——会议线索（5 积分/条）。
- **`tool.web_search`**——联网搜索，结果带信源等级（1 积分/次）。排序依次按信源等级、发布日期、相关性。
- **`confirm=True`**（对应 CLI 的 `--yes`）：三个不可逆方法（`stock_pool_delete`、`drive_delete_file`、
  `drive_delete_folder`）必须传；超过 1000 积分额度保护的拉取也要传。只认真正的 `True`。
- 批量写操作在成功响应里夹带单条失败（`failList`）时，结果标 `partial`，并在告警里列出失败的条目。
- 新增股票池与云盘错误码（`230003`–`230008`）的处置提示；`100006`、`130002`、`140002`、`410111` 的提示
  写得更明确。

### 修复

- **翻页**：排序键不唯一的列表跨页出现的重复行会被去掉，并标 `duplicateRows` 与 `partial`——重复了几行就缺了
  几行，缩短时间范围重拉即可；翻页期间内容变化的行两版都保留，标 `changedRows`；查不到内容时返回
  `{total: 0, list: null}` 的列表按空结果处理，不再告警结构异常；被服务端偏移窗口封顶的 `total` 标
  `totalCapped`。
- **全市场 K 线**：分片按工作日计（A 股 / 美股 1 个工作日一片，港股 2 个）；早于账号可回溯窗口的分片跳过，
  列在 `outOfWindowShards`，不再中止其余分片；只在后面分片出现的列标 `droppedColumns`；失败告警写明首个错误；
  合并结果的元数据取自第一个有数据的分片（此前被后面的分片覆盖）。
- **多只证券日 K** 按行数上限尽量合并到少量请求里，不再每只证券一个请求。
- 首行比请求起点晚 14 天以上、分钟数据整段为空、估值序列晚于 `start_date` 开始，都会给出告警说明原因。
- `valuation_analysis(skip_null=True, field=[...])` 在 `field` 不含过滤所需的列时，不再把每一行都删掉。
- `indicator` 的日期写成 `2026/03/31` 时，按校验后的规范写法发送。
- 有 `fieldList`、没有行的结果保留列名：没有数据的日子 `df["close"]` 是空列，不再抛 `KeyError`。
- **鉴权**：token 被拒时，先试用其他请求或进程已经刷新好的 token，最多再登录一次；被拒的 token 无论随什么
  HTTP 状态返回，都不会再被重发。
- **请求总时长上限**：httpx 的读取超时只限制空闲时间，服务端持续缓慢返回时请求可以一直不结束。现在一次请求
  最长为有效超时的 2 倍（上传与下载为 60 倍），超出时抛 `httpx.ReadTimeout`（下载抛 `DownloadError`）。异步
  客户端覆盖整个请求过程；同步客户端在接收正文时检查。
- **下载**：先把文件写到磁盘再决定文件名，`resolve_title=True` 的回查不再让下载响应一直开着；`{url}` 形式
  的返回按链接里的扩展名命名；Markdown 文件保留 `.md`；超过总时长上限的下载不会自动重发，报错说明可能已经
  计费。
- **缓存**：损坏的 token 或标题缓存文件按空处理；写标题缓存失败不会让列表调用丢掉结果；其他进程或 npm CLI
  写入的标题会合并，不会被覆盖。
- `client._call` 在发请求前就拒绝下载类接口，以及没有带文件的上传类接口。
- 连接池不小于 `GANGTISE_PAGE_CONCURRENCY`；并发的首次调用共用同一个 HTTP 客户端。
- `ai.stock_summary_list` 单次上限 6000 只（原 5000）。
- `vault.wechat_chatroom_list` 的 `room_name` 含数字时按文本拼接，不再抛 `TypeError`。
- 登录响应缺少 `accessToken` 时报带说明的 `ApiError`，不再抛裸 `KeyError`；`Retry-After` 里不带时区的日期按 GMT
  解释，不再随本机时区偏移；配置在 `GANGTISE_TOKEN` 里带 `Bearer ` 前缀的 token 与缓存里的同一 token 视为同一个。
- 文件解析（`tool.file_parse_check`）终态失败的提示指向 `task_id`，并说明重新提交会按页再次计费。

### 行为未变，但请知悉

- **26 个计费接口在一次调用中仍可能被计费多次。** 重试策略与 CLI 一致：按次 / 按页计费的接口、单次请求可能计费超过
  3000 积分的接口，以及另外 12 个按量计费的接口（`ai.hot_topic`、会议线索、两个观点正文、两个带正文的观点列表、
  三个 50 积分/篇的下载、三个债券评级接口），在结果不确定的失败后都不会重发。其余 26 个——18 个按条计费的
  列表（研报、外资研报、A 股 / 港股 / 美股公告、纪要、财报日历、公众号、问答、会议记录、观点与海外观点摘要、独立观点、
  路演 / 调研 / 策略会 / 论坛、个股线索）与 8 个文档下载——遇到 5xx、响应超时、请求发出后断连或 `999999` 时会重试
  至多 2 次；服务端若其实已执行，每次重试都会再计费。单页最贵的是 `ai.security_clue_list`（至多 2500 积分）与四个
  日程列表（至多 1000）。
- **网络错误不包装。** 超时、断连、响应解压失败在重试用尽（或该接口不重发）后原样抛出 httpx 的异常
  （`httpx.HTTPError` 的子类），不继承 `GangtiseError`；下载阶段的这类错误包成 `DownloadError`。

## [0.4.0] - 2026-09-07

功能与 `gangtise-openapi-cli` **v0.38.0** 对齐。**无新增接口**——仍为 **网络接口 97 个 / 端点注册表 99 条**。

**升 minor 而非 patch：** 本版会拒收 0.3.1 照常转发的入参、拒收 0.3.1 照常渲染的响应形状，并且在调用本身不变的情况下，改变了两条路径发送或产出的内容。以上全部列在下方各「破坏性变更」小节中。

### 破坏性变更——拒收的入参

- **日期 / 日期时间 / 时间戳参数末尾带换行符**，现在会抛 `ValidationError`（`date="2026-07-01\n"`、`start_time="1785513600\n"`）。0.3.1 及以前，这类值会原样转发。从文件或 shell 管道读入的值请先调用 `.strip()`。
- **`indicator_param` 只能指定 `indicator` 中也列出的代码。** `cross_section` 和 `time_series` 现在遇到未绑定的代码会抛 `ValidationError`，与 `screener` 早已对未绑定变量的处理一致。此前拼错的代码会作为一个从未被查询的指标的参数组发出去，于是这些参数——以及无日期标记 `{"<code>": {}}`——都悄无声息地没有生效。
- **`ai.stock_summary_list` 单次调用最多 5000 只证券。** 接口文档写的是 6000，但更大的批次会以 HTTP 200、无报错的空列表返回，读起来像「没有任何证券有看点」。请拆分代码、分批调用。

### 破坏性变更——拒收的响应形状

以下每种情况过去都会产出一个看似合理的结果，而不是报错：

- **`fieldList` 中存在重复列名**时拒收。按位置展平时，重名列只保留最后一个值，于是两个 `close` 列被合并成了一列。
- **数组行却没有 `fieldList`** 时拒收——没有列名可供解读这些行。
- **行情接口的响应不含 `list`** 时拒收，抛出携带该响应 `traceId` 的 `ApiError`。这七个接口始终返回 `{total, list}`，空日期区间和未知证券代码也不例外，因此 `null` 或裸对象载荷属于异常响应，而不是空结果。

### 破坏性变更——同样的调用、结果不同

- **`ai.knowledge_batch` 和 A 股 `insight.announcement_list` 的 `start_time` / `end_time` 固定按北京时间（UTC+8）解释。** 这两个接口接收毫秒级 epoch 时间戳，由 SDK 代为转换；锚点现在是固定的，不再取运行机器的时区，因此 `"2026-08-01"` 在任何地方都指同一时刻。如需其他锚点，请显式带上偏移（`"2026-08-01T00:00:00-04:00"`）或直接传 epoch。被本地夏令时切换跳过的挂钟时间现在也能接受，因为 UTC+8 没有这种空档。
- **下载默认不再为取文件名而查询列表接口。** 标题缓存未命中时，解析友好文件名要对列表接口发 4 次请求，而列表接口通常按条计费——比多数下载本身还贵。现在改为逐次调用显式开启：`resolve_title=True`；不开启时，文件沿用服务端自带的 `Content-Disposition` 文件名，没有则退回 `<prefix>-<id>`。**常规的先 `*_list()` 再 `*_download()` 流程不受影响**：缓存会命中，不会多发请求。

### 新增——单次调用支持多只证券

- **`quote.minute_kline` 接受证券列表。** 该接口本身每次请求只收一只证券，因此 SDK 会并发逐只请求，并按传入顺序合并。
- **`quote.day_kline`（以及已弃用的分市场变体）会拆分单次请求装不下的批次**——当证券数 × 区间内交易日数超过 `limit` 时，逐只证券分别拉取。单次请求会按顺序填满行数上限，排在后面的证券会整个从结果中消失。

两者通用：各证券的列布局必须一致；填满 `limit` 的证券会列入 `truncatedSecurities`，并置 `partial`。

### 新增——完整性信号

- **`missingFields`。** 接口不认识的 `field=` 名称会连同其值一起被丢弃——HTTP 200、无报错，只是少了一列。现在请求的列若没有返回，会置 `partial` + `missingFields` 并发出告警。只判断「请求了但没返回」，因此不涉及任何字段白名单。
- **全市场 K 线分片在合并前按列名对齐**；若某个分片的行与其自身 `fieldList` 不匹配、无法对齐，或报告 `total > 0` 却什么都没返回，则记入 `failedShards`，不参与合并。
- **任一分片、页或逐只证券的部分自报 `partial` 时，合并结果保持 `partial` 并发出告警。** 默认返回值是 DataFrame，不携带这些标记，因此现在每条合并路径都会在经过时明确提示。
- **从最后一页内部开始的全量拉取，也会检查 `total` 是否为服务端封顶值**，此前这一步被跳过。
- **单个格式异常的分片不再阻止其他分片的拉取**；它只是一个坏窗口，而非系统性故障。

### 修复

- 下载遵循接口声明的超时下限，而不是客户端默认值。

### 文档

- **ETF 和 20 个全球指数**可用于 `quote.realtime` / `day_kline` / `minute_kline`：直接传 `512800.SH`、`SPX.SPI`、`N225.NKI`、`HSI.HI` 等代码即可。市场关键字（`aShares` / `hkStocks` / `usStocks`）**只覆盖股票**，ETF 和指数必须按代码列出。全球指数留 `null` 的字段因接口而异——`realtime` 上是 `volume` / `amount` / `amplitude`，`minute_kline` 上是 `volume` / `amount`，`day_kline` 上只有 `amount`——且其 `tradeDate` / `tradeTime` 为交易所当地时间。ETF 带有 `adjustFactor`，其 `volume` 以份为单位。
- **`quote.realtime` 字段**：`tradeStatus` 适用于 A 股和港股；`turnoverRate` 和 `volumeRatio` 不返回——换手率请用 EDE 指标 `qte_turn`。美股的 `amount` 为 `null`。
- **`fundamental.earning_forecast`：`roe` 是百分数**（`35.6` 表示 35.6%）。
- **`insight.foreign_opinion_list`**：`region` 接受 `cn` / `cnHk` / `cnTw` / `us` / `jp` / `uk`——其余 `regionCategory` 取值会以 `100005` 被拒收，尽管它们在 `foreign_report_list` 上可用。在 `foreign_opinion_list` 和 `independent_opinion_list` 上，`industry` 都只接受 swIndustry 代码。
- **`vault.wechat_message_list`**：`industry` 只接受 citicIndustry 代码；swIndustry 代码及未知取值会以 `100005` 被拒收。

## [0.3.1] - 2026-08-18

与 `gangtise-openapi-cli` **v0.35.0 → v0.36.0** 同步。**无新增接口**——仍为 **网络接口 97 个 / 端点注册表 99 条**。

**升 patch 而非 minor：** 0.3.0 上能用的一切都不变。日期护栏只放宽——此前接受的每种写法仍然接受，且仍归一为其自身——探测修复则恢复了 0.3.0 本应具备的行为。返回数据中唯一的变化：原本被悄悄截断的 `ai.hot_topic` 全量拉取，现在会如实说明（`totalCapped` / `partial` + 告警），而不再报告为完整。在请求层面，该拉取还会多发一次 `from = total` 探测，无论 total 最终是否被封顶。

### 变更——日期参数接受三种年在前写法

`start_date` / `end_date` / `date` / `report_date` 现在接受 `YYYY-MM-DD`、`YYYY/MM/DD` 和 `YYYYMMDD`，发请求前统一归一为 `YYYY-MM-DD`。`start_time` / `end_time` 仅对日期部分适用同一规则——`"2026/07/01 09:30:00"` → `"2026-07-01 09:30:00"`，时间部分（空格或 `T` 分隔，秒可省）以及 10/13 位 Unix 时间戳原样透传。0.2.0 至 0.3.0 只接受 `YYYY-MM-DD`。

选择归一而非原样转发，是为了让线上只有一种形状：平台的宽松解析并不保证在各接口组之间一致，而 `YYYY-MM-DD` 是每个接口组都实测过的写法。

**年在后的写法仍在本地拒收**（`01-07-2026`、`07/01/2026`）。平台按月在前（美式惯例）解析它们，而且始终如一。问题不在解析，而在调用方一侧：同样三个数字，有人读作 1 月 7 日，有人读作 7 月 1 日，若原样转发，一半调用方会拿到偏差六个月的数据，而响应成功、行数看似合理。SDK 无从得知本意是哪一种，因此在发请求前拒收（不往返、不计费），并在报错中给出一种可用写法。参见 README 的「关于日期格式」一节。

### 修复——`total` 封顶探测重新覆盖 `ai.hot_topic`

0.3.0 把该接口排除在拉取末尾的 `from = total` 探测之外，前提是它按次计费、探测会产生不必要的扣费。这个前提两半都错了：按平台计费规则，该接口按条计价（每篇 50，一篇指一整份报告），而按条计价的接口对无结果的查询不收费——`total` 如实时，探测返回的恰恰就是空结果。（SDK 本身无法测量计费；上面两条说法来自平台，并非本客户端验证所得。）

因此这一排除什么也没省下，反而让 `ai.hot_topic` 失去了唯一的截断检查：被服务端封顶的全量拉取看起来是完整的，`collected == total`，各项一致性检查也全部通过。现在该接口和其他所有分页接口一样执行探测，若在报告的 `total` 之后仍发现数据，则以告警标记 `totalCapped` / `partial`。

该接口的 `retry="no-replay"` 策略不变。这个标记的含义是*绝不重发服务端可能已执行过的请求*；探测是一个新请求，不是重发，两者无关。

### 文档

- `indicator.screener` 对无日期指标的豁免写法（`indicator_param={"F1": {}}` 或 `{"F1": {"tradeDate": None}}`，以**变量**为键）自 0.3.0 起就可用，但一处内部 docstring 称该接口不存在这种写法——现已与代码对齐。`parameterList` 未声明 `tradeDate` 的指标（`pty_*` / `scr_*` 静态属性系列、`div_cash_paid_ratio`、`div_cash_yr`、`pty_shr_reg`）既可通过 `cross_section` 访问，也可通过选股器访问。CLI 在 v0.35.0（截面查询上的 `--indicator-param "<code>:"`）和 v0.36.0（选股器上的 `--indicator-param "<var>:"`，同样以变量为键）中加入了相同能力；两边现已对齐。
- `_errors.py` 和 `domains/indicator.py` 中对上游行为的过时引用（这些行为在 CLI v0.35.0 / v0.36.0 中已变更）已更正。

## [0.3.0] - 2026-08-15

与 `gangtise-openapi-cli` **v0.28.3 → v0.34.1**（共九个版本）同步。新增接口：条件选股、帕米尔专家纪要库、财报日历，以及异步 PDF 解析工具——**网络接口 97 个 / 端点注册表 99 项**（此前 90 / 92）。

**升 minor 而非 patch：** 服务端于 2026-08-01 重写了 EDE 接口契约，并于 2026-08-14 下线了 `quote day-kline` 的 `"all"` 关键字；本版本还把三条「静默返回错误数据」的路径改成了显式失败。上一版会照常转发的若干入参现在会被拒收，上一版当作成功处理的若干响应现在会抛异常。

### 🔴 修复——EDE 接口在线上 API 下完全不可用

`indicator.cross_section` / `time_series` 仍在发送 2026-08-01 之前的请求体（`securityCodeList`、根级 `date`），并按 2026-08-01 之前的格式解析响应（`indicatorCodeList` / `indicatorNameList` 两个平行数组、未转置的矩阵）。服务端对旧请求体回 `100001 缺少必填参数`，因此在当前 API 下**这两个方法每次调用都失败**。新契约如下：

- **`securityCodeList` → `universe`**，两个接口均如此。
- **根级 `date` 已移除。** `date=` 现在作为每个指标自己的 `tradeDate` 发送。若某指标在 `indicator_param` 中已带 `tradeDate` / `reportDate`，则保留调用方的值。⚠️ `sDate` 刻意不算作「已带日期」：在区间类指标上它是区间起点，而必填的 `tradeDate` 是区间终点，把它当作替代会悄悄挪动区间终点（茅台 `sDate=2024-01-02`：不带 `tradeDate` 得 2,265,873,849，带 `tradeDate=2024-01-31` 得 65,687,435，两者都「成功」）。
- **`indicatorList: [{code, name, dataType}]`** 取代了两个平行数组，且**截面接口的 `values` 矩阵改为转置**，即 `[security][indicator]`。用旧代码读取新响应会得到一张完全转置的表。
- **截面输出不再有 `date` 列**——查询日期现在落在每个指标自己的参数上，各列之间可以合法地不同。
- 🔴 **前复权参数是 `adjustType`，不是 `adjustmentType`。** 服务端会静默忽略错误的参数名并回退到不复权价格，数字看起来正常，实际却是错的（茅台 2024-01-02：`adjustType=3` → 13609.6168 真后复权，拼错 → 1685.01 不复权）。文档字符串、示例和 `sample/API_PARAMETERS.md` 已全部更正。
- ⚠️ **报告期类指标（`is_*` 等）现在拒收 `tradeDate`**（服务端 2026-08-14 变更）：请传 `indicator_param={"code": {"reportDate": "…"}}`。某个指标要哪种日期**无法**从代码前缀推断——对 170 个指标的调查发现，7 个 `finc_*` 和 3 个 `div_*` 要 `reportDate`，而 8 个 `is_*` 和 4 个 `cf_*` 要 `tradeDate`，`div_cash_yld` 两者都要，还有两个 `div_*` 要 `fiscalYear`。新增一条按报错文本匹配的提示，在服务端返回那句原话时触发（无论错误码是 `100001` 还是 `100003`），并引导到 `indicator.search` 的 `parameterList`。

### 🔴 修复——`quote.day_kline` 无法拉取全市场

服务端自 2026-08-14 起，统一日 K 线接口不再接受 `["all"]`，改为 `aShares` / `hkStocks` / `usStocks`，且每个都必须**单独**传入。这两种错误都只回一个光秃秃的 `120001 "invalid security code"`，指向的却是完全正常的代码，因此 SDK 现在在本地就拒收，并指明应使用的关键字。

- **按市场分片**：`aShares` / `usStocks` 每个分片 1 天，`hkStocks` 2 天（2026-08-13 实测的单交易日行数：A 股 5543 / 美股 5919 / 港股 2810）。
- **`index_day_kline` 按 15 天分片，不再是 30 天。** 每个交易日约 531 行指数数据 × 30 天窗口内约 22 个交易日 ≈ 11.7K 行——每个分片都悄悄顶到 10000 行上限，丢失约 11% 的区间数据。
- **市场关键字按大小写不敏感匹配，并在发送前归一化。** 这一步归一化是承重的，不是为了整洁：`quote.fund-flow` 是唯一一个服务端不做大小写折叠的接口（`ashares` → `120001 非有效A股`），所以大小写变体在那里能用，全靠这一步。
- 🔴 **`quote.fund_flow` 不再静默缩窄混合请求。** 服务端会丢掉关键字，只按显式代码作答——一行、没有告警——于是「全市场外加这一只」悄悄变成了「只有这一只」。
- **`ai.stock_summary_list` 拒收市场关键字。** 服务端于 2026-08-14 移除了全市场批量查询；该接口按每只证券 3 积分计费，因此检查放在请求之前而非之后。
- `day_kline` 的文档现已注明扩大后的覆盖范围（港股 / 美股 / 交易所、概念和行业指数，可在一次请求中混合）；`day_kline_hk` / `day_kline_us` / `index_day_kline` 标记为已弃用。它们**并未**移除：`index_day_kline` 仍能一次拉取全部 531 个指数并返回 `securityName`，这两点 `day_kline` 都做不到。

### 新增
- **`indicator.screener`**——条件选股：把变量绑定到指标（`indicator={"F1": "qte_mkt_cptl"}`），再用表达式筛选（`"F1 >= 500 && F2 <= 30"`，字符串类指标还支持 `contains` / `notcontains`）。`indicator_param` 以**变量**而非代码为键，因为同一指标可以合法地以不同参数出现在两个变量下。
  - **校验返回的绑定关系。** 每一列的 `field` 是把它对应回所属筛选条件的唯一依据，响应里没有其他任何东西能发现它出错——一个把请求的 `F1` 标成 `F9` 的响应，打印出来是一张再普通不过的表。绑定不匹配、未知或重复时，现在抛 `ApiError`。
  - **缺失列按表达式的布尔结构来判定**，而不是仅看有没有 `||`。`A && B` 两边都需要；`A || B` 只需一边。没有可求值的分支 → `ApiError`（无法证明这些行满足任何条件）；仍有分支成立 → `partial` + 告警，数据保留。
- **`insight.pamirs_summary_list` / `pamirs_summary_download`**——帕米尔专家纪要库（需单独购买；未开通返回 `999004`）。它的筛选参数是 `summary_list` 的严格子集，且刻意没有照搬：服务端会静默丢弃不认识的字段，所以照搬的参数集看起来已生效，实际返回的却是未经筛选的整个库。
- **`insight.performance_calendar_list` / `performance_calendar_download`**——财报日历（业绩预告 / 快报 / 公告）。它是唯一一个按 `start_date` / `end_date` 而非 `start_time` 筛选的 insight 列表。**必须给出限定条件**：不加筛选时，省略 `size` 意味着「全部拉取」——最多 50k 行，每行 0.1 积分。只传 `security` 时会隐式加上 1000 行上限，若仍有剩余行则把结果标记为 `partial`——这正是服务端筛选失效的典型征兆。
- **`tool.file_parse` / `tool.file_parse_check`**——异步 PDF → Markdown 解析，新增 `gangtise.tool` 领域。提交是一次 multipart 上传，**在提交时按每页 0.8 积分计费**（不自动重发（`no-replay`），超时下限 300s）；获取结果 ZIP 免费，`wait=True` 时的轮询与 AI 异步接口使用相同的退避预算。
- **`EndpointDef.big_int_fields`**——声明的字段在解析前会重新加上引号，使 id 的类型不取决于服务端的序列化器（Python 能精确解析大整数，因此与 CLI 不同，这是类型稳定性护栏，而非精度修复）。
- **`EndpointDef.file_types`**——合法的 `file_type` 取值挂在接口定义上，以后新增的下载方法不会漏掉白名单。

### 变更（破坏性）
- **`indicator.cross_section` / `time_series` 必须传 `indicator` 和 `security`。** 两者名义上可选，但不传会在一次往返之后得到 `100001`。
- **列式行的长度与 `fieldList` 不一致时，现在抛异常。** 以前会补齐（偏短）或截断（偏长），导致值被贴到错误的字段上：`quote.realtime` 传 `field=["securityCode","close","turnoverRate"]`（realtime 没有 `close`）时返回 2 个值，把换手率 28.5573 放到了 `close` 下——读起来像茅台收盘价 28.56，而真实价格是 1297.41。没有报错、数字看似合理，却是完全不同的指标。适用于 `normalize_rows`、行情路径和 `alternative.edb_data`。
- **`search_type` / `rank_type` 白名单限定为 1/2，`file_type` 限定为所属接口的取值。** 服务端把越界的枚举值当作未知字段处理：丢掉该条件，以 HTTP 200 返回未经筛选的结果集。最坏的情况会连 `keyword` 一起失效：`search_type=99` 时，`summary_list(keyword=…)` 不再返回该关键字的结果，而是返回整个库——**行数多出三个数量级**，且是 HTTP 200，自动化流水线几乎不可能察觉。`research_list` 行为相同。该校验挂在 `_request_body` 上——所有方法本就必经的那个汇合点——因此也覆盖以后新增的方法。
- **`indicator.time_series` 遇到无法归属的响应时直接失败**：同时包含多只证券和多个指标的响应（该接口并不支持这种形状的请求）会悄悄丢掉其中一个维度的标识，而请求与响应的比对也看不出差异，没有别的机制能报出来。
- **矩阵的标识轴不再做强制转换。** `securityCodeList` 或 `dates` 中的 `None` 以前会变成字面标签 `"null"`，作为一个看似完全合理的标识交给调用方；`indicatorList` 中没有 `code` 的条目会塌缩成 `col0`。两者现在都抛异常——伪造的标识比缺失的数据更危险。
- **矩阵形状在两个维度上都做检查。** 行数和每行的单元格数必须与轴长度严格一致；服务端会用 `null` 补齐而不是截断，所以参差不齐的行意味着结构变化，而非数据缺失。

### 修复
- **对分页接口的 `total` 进行探测，检查是否被服务端封顶。** 三个 `insight.opinion*` 接口报告固定的 10000，而越过该偏移后仍有数据，于是全量拉取恰好停在上限处，`collected == total`，所有完整性检查都通过——一份看起来完整、实则被截断的导出，而该接口按每条 30 积分计费。无限制拉取之后，SDK 会在 `from = total` 处再读一行；如果有数据返回，就把结果标记为 `partial` + `totalCapped` 并发出告警。判定没有写死为 10000；若 `total` 如实，探测返回为空（不产生费用，因为这些接口按返回条数计费）。
- **首页格式异常时标记为 `partial`，而不只是告警。** 字符串类型的 `total` 会把全量拉取截断到第 1 页，而结果看起来是完整的——比一个明显为空的响应更糟。
- **`total` 在翻页过程中发生漂移时，结果标记为 `partial`** 并告警：拉取过程中数据发生了变动，即使计数对得上，也可能有重复或遗漏的行。
- **`securityNameList` 异常时丢弃名称，而不是给行贴错标签。** 名称按位置对应，所以对两只代码给出 `["泡泡玛特"]` 时，会把茅台那一行标成泡泡玛特。现在长度不匹配时丢弃全部名称、回退为证券代码，并发出告警——这与其他护栏刻意不对称，因为那些护栏保护的是数值，必须直接报错。
- **板块 ID 不再丢失证券轴。** 单个 `sectorId` 会在服务端展开，所以请求里的数量说明不了各列属于哪个轴；板块请求现在一律取证券轴。
- **报告服务端无法识别的代码。** 自 2026-08-07 起，真正的覆盖缺口会以 `null` 单元格返回、行列保持完整，因此轴上消失的项意味着代码拼错或市场后缀错误（`AAPL.US` 会消失，`AAPL.O` 能返回）——否则这是看不见的，因为 `key_by="code"` 根本找不到对应的键，而不是得到一个 null。标记为 `partial` + `omittedIndicators` / `omittedSecurities`。
- **形状错误不再丢失 traceId。** `unwrap_envelope` 会丢弃信封，连同其中的 `traceId`——这是 Gangtise 技术支持追查故障的唯一线索。在传输层之后抛出的失败受影响最大，而矩阵形状护栏恰恰就在那里。解包后的响应现在把信封的 id 挂在一个属性上（一个 `dict` 子类，因此序列化、比较和制表都与它所替代的普通 dict 一致），`ApiError.trace_id` 会回退取用它。双层包装的 EDE 响应会向下传递外层的 id，因为内层信封本身不带 id。
- **日期校验跟随 `date=` 到了它的新位置。** 它不再是请求体字段，所以 `_request_body` 的检查看不到它了；`cross_section` / `screener` 现在显式校验它。

### 错误提示
- `100006` 现在也涵盖单页 size 上限（50），而不只是「请求的行数过多」。
- `110003` 不再提示「缩短时间窗口」：限制来自账户的数据权限，所以完全早于权限范围的请求（`fiscal_year=2015`）无论窗口多窄都会返回同一错误码。
- `130003` 既涵盖「资源未生成」，也涵盖「记录无附件」；`130002` 去掉了「非法 `file_type` 会落到这里」的说法（已移到 `130005`）；`140002` 既涵盖 AI 生成失败，也涵盖 EDE 参数/表达式错误；`999004` 涵盖整个数据库未购买的情形，而不只是单条记录不可见。新增：`230002`（未绑定微信账号）。

### 修复（续）

- 🔴 **reportDate 提示不再断言服务端从未点名的键。** 该规则从 CLI 原样移植，是一条单一的多选正则（`不支持参数 tradeDate|缺少必填参数 reportDate`），所以只出现半句时也会触发——而半句只能证明 `tradeDate` 被拒，并没有说该改用什么。`scr_exchg_mkt` 的 `parameterList` 为空（它根本不需要日期），提示却让调用方传 `reportDate`，服务端同样会拒。现拆分为五条按顺序、须全部匹配的规则：完整句子给出断言性提示，半句给出非断言性提示，指向 `parameterList` 并附两条已知可行的路径。CLI 仍是单一多选的写法。
- 🔴 **不需要日期、或只需要 `fiscalYear` 的指标，重新可以查询了。** `_DATE_PARAM_KEYS` 会给所有尚未带 `tradeDate`/`reportDate` 的指标注入 `tradeDate`，导致一批指标（`scr_exchg_mkt` / `pty_main_bus` 这类静态属性，以及 `div_cash_paid_ratio` / `div_cash_yr`）在截面接口和条件选股中完全无法查询——服务端会因这个多余的键拒收整个请求。现在提供两种**需显式启用**的抑制标记：`indicator_param={"code": {}}`（该指标不接受任何参数），以及 `{"code": {"fiscalYear": "2025", "tradeDate": None}}`（`None` 标记某个键不需要，其他键照常发送；`None` 本身不会被发出）。需显式启用，意味着现有调用的行为都不变。
  - 判定标准是**指标的 `parameterList` 中是否有 `tradeDate`，仅此而已**——不看代码前缀，也不看「是不是静态属性」。分四种情况：有 `tradeDate`（无需处理）；没有它而有 `reportDate`（传入该参数即可，它本身就会抑制注入）；两者都没有，但有 `currency` / `scale` / `fiscalYear` 等其他参数（传入这些参数并加上 `None` 标记）；`parameterList` 为空（传 `{}`）。第三种情况最容易被误读成第四种——`pty_shr_reg` 看起来像静态属性，但带有 `currency` / `scale`，写成 `{}` 会悄悄丢掉它们。
  - 🔴 **`fiscalYear` 刻意不被视为日期选择器**，这一点经实测确定。把它加入集合，一行就能修好只需 `fiscalYear` 的那两个指标——但一次线上 `indicator.search` 扫描（免费接口，323 个指标，2026-08-15）发现 **5 个指标同时要求 `fiscalYear` 和 `tradeDate`**：`frcst_op_rev`、`frcst_op_rev_yoy`、`frcst_shnp`、`frcst_shnp_yoy`、`frcst_pe`。把它加进去会弄坏现在能正常工作的调用。CLI 也独立得出了相同结论。
  - ⚠️ `sDate` 不在该集合中，也必须不在：它是区间起点，不是选择器，把它当作选择器会悄悄挪动区间终点。
- **`zip_field_row` 把 traceId 带入错误信息——四个调用点全部覆盖。** CLI 版本接受第三个参数 `source`，其 id 会附加到错误信息中；移植时丢掉了它，导致 SDK 中唯一实际使用所携带 id 的地方没有接上。四个调用点中最需要它的是 `quote.realtime`（该护栏自己的头号示例）和 `alternative.edb_data` 的两条路径（其错误信息会让调用方提交 bug 报告）。
- **在按次计费的接口上跳过 `totalCapped` 探测。** `ai.hot-topic` 是唯一一个既分页又不自动重发（`no-replay`）的接口，在它上面「探测返回为空所以不花钱」根本不成立。这是与 CLI 的刻意差异，CLI 的探测条件没有这项排除。
- **拒收 `file_type=True`。** `bool` 是 `int` 的子类，所以 `True in (1, 2)` 能通过成员检查，并以 JSON `true` 发出——标量枚举护栏本来就拒收 bool，现在两者一致了。

### 文档与示例
- 示例：同步、异步各 93 → **100** 个（条件选股、帕米尔 ×2、财报日历 ×2、文件解析 ×2），并按新契约重写了 EDE 和 K 线示例。
- `sample/API_PARAMETERS.md`：新增 7 个方法小节，更正 `adjustType`，并在矩阵类接口上把 `indicator` / `security` 标为必填。
- 财务报表类方法的文档注明了 **`earliestAnncDate`**（服务端 2026-08-14 新增）：做时点对齐请用它，因为部分证券四个季度的 `announcementDate` 填的都是年报的发布日期（五粮液 FY2025 四次都返回 20260430，而 `earliestAnncDate` 返回 20250426 / 20250828 / 20251031 / 20260430）。无代码改动——财务报表类方法没有固定 schema，两个字段都会原样透传。

## [0.2.1] - 2026-07-24

与 `gangtise-openapi-cli` v0.28.1–v0.28.2 同步。v0.28.1 只改了文档（npm 包内置的 skill），无需移植；v0.28.2 新增 `key_by` 选项，并收窄了 EDE 无数据提示的适用范围。没有新接口（仍为网络接口 90 个 / 端点注册表 92 项）。

**升 patch 而非 minor：** `key_by` 默认为 `name`（行为不变），其余是提示的细化——上一版接受的入参，现在没有一个会被拒收。

### 新增
- **`indicator.cross_section(key_by=…)` 和 `indicator.time_series(key_by=…)`**——取值 `"name"`（默认；列以指标的显示名称为键）或 `"code"`（列以 `indicatorCode` 为键，单指标 × 多证券的时序则以 `securityCode` 为键）。`key_by="code"` 让列头就是你传入的代码；默认的 `"name"` 则让列头是服务端自己起的名字。2026-07-24 实测：**服务端按自己的顺序返回列，而不是按请求的顺序**——`indicator=["cf_finc_exp", "cf_finc_exp_qtr"]` 返回为 `["cf_finc_exp_qtr", "cf_finc_exp"]`，`security=["600519.SH", "000858.SZ"]` 返回为 `["000858.SZ", "600519.SH"]`——所以按位置索引不安全；而在 `key_by="name"` 下，你拿到的列名是「财务费用(现金流量表)」，还得再调一次 `search` 才能映射回 `cf_finc_exp`。非法取值会在发送请求前抛 `ValidationError`。

### 变更
- **EDE `999999`「无数据」提示现在只作用于取数接口**（`indicator.cross-section` / `time-series`）。`indicator.search` 共用 `no-999999` 重试策略，但只接受关键字，因此保留通用提示，而不给出与之无关的日期/范围/参数指引。提示文本现在指向真正的首要原因——日期是否与指标周期匹配（财务/MRQ = 报告期末，如 `2025-12-31`；日频估值 = 交易日）、`scopeList` 覆盖范围，以及 `parameterList` 中的必填参数。

### 修复
- **没有显示名称的指标不再落到字面名为 `None` 的列下。** 服务端确实会返回这种情况——2026-07-24 实测，`qte_open` 返回为 `indicatorNameList: [None, "日收盘价"]`——而矩阵展平逻辑在 `_build_headers` 回退到代码之前就把列表转成了字符串，于是 `"None"` 成了一个真值列头。这类列现在使用 `indicatorCode`（`qte_open`），`securityNameList` 中的 null 条目保持为 null，而不会变成文本 `"None"`。位置保持不变：这些列表与 `values` 的行一一平行。这是与 CLI 的刻意差异——CLI 有同样的 bug，并把该列命名为 `"null"`。
- **sdist 不再包含 `sample/README.md`。** `include` 模式 `README.md` 没有锚定，匹配到了它，导致源码包里带了一份示例索引，而其中提到的脚本和 `API_PARAMETERS.md` 并不在包里。四个根目录文件的模式现在都已锚定（`/README.md` 等）。

### 文档
- `sample/API_PARAMETERS.md` 和四个 `indicator` 示例脚本（同步 + 异步 × 截面 + 时序）记录并演示了 `key_by`；这些示例此前声称覆盖了每个参数。

## [0.2.0] - 2026-07-22

与 `gangtise-openapi-cli` v0.28.0 同步——包括 2026-07-17 的三层错误码改版、严格的日期/日期时间校验，以及重试策略修正。无新增接口（仍为 90 个网络接口 / 92 个端点注册表条目）。

**升 minor 而非 patch：本版会拒收上一版原样转发的入参。** 详见下文「破坏性变更」。

### 破坏性变更
- **日期参数只接受 `YYYY-MM-DD`。** `start_date` / `end_date` / `date` / `report_date` 若用其他写法，现在会在发请求前抛出 `ValidationError`——包括服务端能正确处理的 `2026/07/01` 和 `20260701`。只认一种写法，好过维护一份需要按接口分组逐一重新实测的白名单。

  原因在于那种*不*安全的写法。2026-07-22 对 `insight.research.list` 实测（同一时间窗，比较 `total`）：

  | `start_time` | `total` | 服务端解读为 |
  | --- | --- | --- |
  | `2026-01-07` | 基准 A | — |
  | `2026-07-01` | 基准 B | — |
  | `07/01/2026`（斜杠） | **与 A 一致** | 2026-01-07（`DD/MM/YYYY`） |
  | `07-01-2026`（连字符） | **与 B 一致** | 2026-07-01（`MM-DD-YYYY`） |

  同样三组数字，相差半年，两者都返回 `HTTP 200`，响应里也没有任何信息表明实际用的是哪一天。反向验证同样成立：`25/12/2026` 能解析，`12/25/2026` 却报错。SDK 无从得知调用方想要哪种解读，因此只转发无歧义的写法。
- **日期时间参数只接受 10/13 位 epoch 时间戳或 `YYYY-MM-DD[ HH:mm[:ss]]`**（分隔符可为空格或 `T`）。`start_time` / `end_time` 逐字段校验后原样转发。透传型列表接口对年在后写法的误读与日期接口完全相同。这些字段拒收末尾的 `.SSS` 和 UTC 偏移——服务端按自己的时区解析字符串，SDK 不做换算的偏移只能算猜测。有意不处理时区：*客户端*时区中被跳过的钟点（夏令时缺口）仍会转发，因为是否有效只由服务端的时区决定。
- **`ai.knowledge_batch(start_time=…)` 现接受 `int | str`**，且始终发送 13 位毫秒，与 A 股 `insight.announcement_list` 一致。此前它只接受原始 `int`，且不做校验直接转发。
- `domains.insight._to_unix_ms`（私有）已并入共用的 `domains._common._to_timestamp13`。

### 新增
- **`ApiError.trace_id`**——2026-07-17 新版信封中的服务端关联 ID，同时以 `[trace 830965044897325056]` 的形式写入 `str(err)`。这是 Gangtise 技术支持追查故障的唯一线索。
- 两个做换算的接口（`ai.knowledge_batch`、A 股 `insight.announcement_list`）额外接受**带偏移的 ISO 字符串**（`2026-01-01T00:00:00+08:00`、`Z`、`+0800`）。有意比 CLI 更宽：换算成毫秒后显式偏移不再有歧义，而 `dt.datetime.now(tz).isoformat()` 又是惯用的 Python 写法。偏移量为手工解析，因为 `fromisoformat` 直到 3.11 才支持 `Z` 和不带冒号的偏移。

### 变更
- **错误码表按 2026-07-17 的三层结构重写**（`999xxx` 服务层 / `1xxxxx` 业务通用 / `2xxxxx` 接口专属），共 61 条，覆盖全部 41 个公开错误码以及线上仍能观察到的旧码。新旧两代并列是有意为之：切换只完成了一部分——2026-07-22 实测，业务层已用新码应答（JSON **数字**，并带 `errorType`），而 token 过滤器仍在返回 `0000001007` / `0000001008` / `900002`。
- 提示现在给出下一步**操作**，而不是复述服务端的 `msg`（`资源不存在 — 资源不存在，确认 ID 有效` 读起来像结巴），并引用 SDK 的方法名/参数名，而非 CLI 参数。
- **更正 `900002` 的含义**：原表写的是「请求缺少 uid」；服务端实际用它表示「请求类型有误」（HTTP 方法错误，`HTTP 405`）。旧文本会把排查引向完全错误的方向。
- 为 `410001` / `410106` 补充提示——这是 `indicator` 最常见的两种失败（缺少 `indicator`/`security`、缺少必填的 `indicator_param`），重新编号时被漏掉，此前完全没有提示。

### 修复
- **`--wait` 式轮询不再因重新编号的异步错误码而中止。** `140001`（RESULT_GENERATING）和 `140002`（PROCESSING_FAILED）加入 `410110` / `410111` 之列。服务端目前仍返回旧的那一对，所以这是前瞻性防护——但漏掉的代价很高：不认识「生成中」码的轮询会在第一次尝试时就中止，作废一个已扣 50 积分的任务。
- **`999011` 和 `140002` 在任何 HTTP 状态下都不会被重放。** 两者优先级均高于 `429` 和 `5xx` 规则。错误的 AK/SK 不会自己变好，而异步 `*-check` 接口没有声明重试策略——于是 `140002@500` 在异步层把它判为终态*之前*，就已被默认策略重试了两次。
- **token 自愈识别 `999002`**（TOKEN_INVALID，即 `0000001008` 的新码），因此 token 过滤器切换后不会悄无声息地失效。
- **`HTTP 200` 的错误信封保留服务端的 `Retry-After`。** Gangtise 也会把错误包在 `200` 响应体里；这条路径此前丢掉了该响应头，把限流退避降级成了盲目的指数退避。同步、异步和下载路径均已接通。
- **异步任务的终态失败现在会报告服务端的原话**——错误码、`msg` 和 `traceId`——并附一条告警：重新提交生成任务会再次计费，而结论不会改变。此前只打印 `Content generation failed (terminal). Do not retry.`
- **epoch 毫秒换算不再把 13 位输入的量级判错。** 原先的量级判断是 `> 1e12`，而 `1000000000000` 恰好等于 `1e12`——于是真实的 13 位时间戳落入秒级分支，结果放大了 1000 倍。按位数判断不存在可判错的边界。
- **做换算的接口拒收夏令时缺口中的钟点。** 美国夏令时开始当天早上的 `02:30`（以及豪勋爵岛 30 分钟缺口中的 `02:15`）没有对应的真实 epoch，`datetime.timestamp()` 会悄悄把它解析到缺口另一侧——查的是与请求不同的一个小时。
- 所有格式检查均使用 `re.ASCII`。Python 的 `\d` 匹配所有 Unicode 十进制数字，`int()` 也能解析全角数字，所以用 `U+FF10..U+FF19` 写的日期能通过检查，并被原样转发给读不懂它的 API。
- 年份 `0000` 现被拒收，而不是让裸的 `ValueError` 从换算路径中漏出（它能通过日历算术检查——`0 % 400 == 0` 甚至让它成为闰年——但 `datetime` 的 `MINYEAR` 是 1）。

## [0.1.18] - 2026-07-12

下载路径的加固修复。接口与 API 表面均无变化（仍与 `gangtise-openapi-cli` v0.27.0 对齐，90 个接口）。

### 修复
- **自动命名的下载在不支持硬链接的文件系统上不再丢失文件。** v0.1.17 的 `os.link` 快速路径只对一份写死的 errno 白名单回退到 `O_CREAT|O_EXCL` 占位方式，漏掉了 macOS exFAT/SMB（`ENOTSUP`，与白名单中的 `EOPNOTSUPP` 是不同的值）和 Windows FAT（`EINVAL`）：已下载完成的 `.part` 被删除，下载被报告为写入失败——而对于不自动重发（`no-replay`）的计费接口（如 `insight.summary.download`，50/篇），手动重试会再次计费。现在任何 `os.link` 失败都回退到占位方式，这种方式处处安全：真正致命的情况（`ENOSPC`、`EROFS`）会在占位的 `os.open` 处直接再次抛出。
- **重定向目标若返回 `200` + JSON，不再被当作「文件」写入磁盘。** 下载 `302` 到一个返回 `application/json` 业务错误信封的 URL 时，JSON 字节会被保存成例如 `report.pdf`，调用却返回成功（已计费，文件损坏）。跟随后的请求现在执行与直接下载路径相同的信封检查——失败信封抛出 `ApiError`，`{url}` 元数据信封则继续链式跟随——与 TS `client.ts` 一致。
- **重定向那一跳上 CDN 的临时 `429/5xx` 会重试，而不再让整次下载失败。** 跟随 URL 的请求此前只重试网络错误；一次偶发的 `503`/`429`（签名 URL 仍有效）会立即中止，尽管重放签名 URL 不产生任何费用。可重试的 HTTP 状态现在按默认策略重试（遵循 `Retry-After`）；`403/404` 仍快速失败（过期的签名无法复活），计费的上游请求绝不重放。
- **同源重定向保留 bearer token。** 手动重定向跳转对任何被跟随的 `Location` 都不发送 `Authorization`，因此 `302` 到 API 源上另一个需认证的路径时会得到 `401/403`。现在当且仅当 `Location` 仍在 API 源上（scheme+host+port 完全一致）时才转发 bearer；跨源 CDN 仍然永远拿不到它。恢复与 v0.1.16 / TS `client.ts` 的一致性。
- **`_require_fetchable_url` 现在真正 fail-closed。** 它此前用标准库 `urlsplit` 校验，比 httpx 宽松：带控制字符的 URL、格式错误的点分四段 / IDNA 主机、超长内容或带前导空白的 URL 都能通过检查，却会在请求时让 `httpx.URL` 抛出 `httpx.InvalidURL`（不是 `httpx.HTTPError`），未经包装就逃出了下载路径的 except 链。现在直接用 `httpx.URL` 本身校验，并加上首尾空白的精确检查，抛出已脱敏的 `DownloadError`。
- **`.part` 清理失败不再掩盖成功的下载。** `os.link` 提交完整文件之后，`finally` 中对 `.part` 的 unlink 却会左右最终结果：一旦它抛错（杀毒软件锁定、只读挂载），原始 `OSError` 会越过 `except OSError` 向外传出，对已经落盘的文件报告虚假失败（并诱发 `no-replay` 接口的重复计费）。清理现在改为尽力而为。
- **被跟随目标抛出的任何错误都不再重放计费的上游，且 `{url}` 链有跳数上限。** 把被跟随目标的 JSON 信封作为 `ApiError` 抛出（见上文修复）从另一侧重新打开了重复计费的口子：来自已成功上游*之后*的错误，仍可能驱动 `download_to_path` 的外层循环重发上游请求。这类错误现在会被打上标记，并短路**所有**外层重放——既包括针对*认证*信封（`0000001008`/`8000014`/`8000015`）的 token 刷新路径，**也**包括针对可重试 `999999` 的默认策略重试路径（正是这种情况让 `insight.report-image.download`——一个 0.1 积分/张的默认重试接口——被重复计费了三次）。直接（非跟随）路径上的认证自愈和 `999999` 重试不变。自引用/循环的 `{url}` 链现在以有界的 `DownloadError` 失败（最多 5 跳），而不是递归到 `RecursionError` 并引发请求风暴；同源 bearer 转发在每一跳重新判定（第 2 个同源跳不再丢失它）；`_redact_url` 以 `httpx.URL` 的判定为准，所以非 ASCII / 格式错误的 authority（错误的 IDNA、无效的点分四段如 `1.2.3.999`）会折叠为 `redacted-url`，而不是被原样回显。
- **被跟随目标的错误现在带有计费安全的提示，占位回退能扛住关闭时的故障，同源判断把显式 `:0` 视为不同端口。** (1) 打了标记的被跟随目标错误仍沿用通用的 `.hint`——`999999` 的「请稍后重试」和认证码的「会自动重新登录重试」——两者都会诱导手动重发，从而对已执行的上游再次计费（而且这里根本不会自动重新登录）；现在给出专门的提示，说明计费的上游已经执行，不可盲目重试。(2) 在无硬链接的占位提交中，对 `O_EXCL` 预留 fd 的 `os.close()` 没有保护：关闭时的 `OSError`（如不稳定的 SMB/exFAT 挂载上的 `EIO`——恰恰是本版所针对的文件系统）会在 rename 之前中止，于是完整的 `.part` 被外层 `finally` 删除，只留下一个 0 字节文件。关闭现在改为尽力而为——这个 fd 只用于占住文件名，真正关键的 rename 仍会把完整内容落盘。(3) `_same_origin` 用 `port or default` 计算实际端口，把显式的 `:0` 折叠为默认端口，从而把 `https://api.test:0` 判为与 `https://api.test` 同源；现在改用 `port if not None else default`，实现真正精确的 scheme+host+port 匹配。

## [0.1.17] - 2026-07-12

下载路径的加固修复。接口与 API 表面均无变化（仍与 `gangtise-openapi-cli` v0.27.0 对齐，90 个接口）。

### 修复
- **302 跳转到 CDN 不再导致计费的下载接口被重放。** 上游下载请求此前让 httpx 内联自动跟随重定向；CDN 那一跳失败时，看起来就像*上游*请求的连接阶段错误——对于 `no-replay`（按篇计费）的接口，这会触发对计费接口的重发。现在上游请求停在 3xx，并把 `Location` 交给签名 URL 获取器，其重试循环只会重放不计费的 CDN URL。（这是与 TS `client.ts` 的有意分歧：后者内联跟随，存在同样的隐患。）被跟随的 URL 现在也受 10× 传输时限约束，此前它绕过了这一时限。
- **签名 URL 脱敏现在 fail-closed。** `_redact_url` 只保留 `scheme://host/path`，但裸的 `alice:SECRET@host/p` 会被解析为 scheme 是 `alice`，所以旧的基于 netloc 的路径会泄露 `alice://SECRET@…`；无效端口也会以未包装的 `httpx.InvalidURL` 逃出，并携带原始值。现在凡不是带主机和有效端口的绝对 http(s) URL，一律折叠为 `redacted-url`；签名 URL 在请求前先校验，格式错误的会抛出已脱敏的 `DownloadError`，而不会泄露。
- **自动命名的下载恢复原子发布，后缀也正确了。** v0.1.16 的 `O_CREAT|O_EXCL` 预留会在 rename 之前把最终路径建成 0 字节占位（崩溃时可能留下一个空的假「成功」文件），而且 `report-1.pdf` 冲突时生成的是 `report-1-1.pdf` 而不是 `report-2.pdf`。现在提交时把完成的 `.part` 硬链接到目标路径（完整文件一步出现；`-1..-99` 后缀从原始文件名开始扫描），仅在不支持硬链接的文件系统上回退到 O_EXCL 占位（仍不会覆盖已有文件）。
- **EDE 内层信封的 `999999` 现在给出「无数据」提示。** 双层信封的内层错误在传输层之后才解包，所以一直沿用通用的「稍后重试」提示；现在与外层错误码一样，提示检查查询时间窗。

## [0.1.16] - 2026-07-11

针对 0.1.15 的安全与下载完整性修复。接口与 API 表面均无变化（仍与 `gangtise-openapi-cli` v0.27.0 对齐，90 个接口）。

### 修复
- **签名 URL 不再泄露到异常消息中。** 预签名 URL 请求失败时，`DownloadError` 文本曾嵌入完整 URL——包括 `X-Amz-Signature` 查询参数和任何 `user:password@` authority——终端、CI 日志和错误收集器都会把它记录下来。现在消息只包含 `scheme://host[:port]/path`（去掉 userinfo、query 和 fragment；IPv6 主机重新加方括号）。
- **自动命名的下载不再互相覆盖。** 两个并发的 `output=None` 下载若标题解析为同一文件名，会在 `_unique_path` 先检查后使用的窗口内发生竞争：后一个 `replace()` 会悄悄覆盖前一个文件。自动生成的文件名现在通过原子的 `O_CREAT|O_EXCL` 预留提交——竞争失败的一方重新扫描下一个 `-1..-99` 后缀——最终移动失败时会清理其占位文件。适用于所有文件系统（不依赖硬链接）；显式 `output=` 路径保持文档所述的覆盖语义。
- **预签名 URL 请求现在会重试临时网络故障**（默认策略，每次尝试有 10× 硬时限）。重放签名 URL 始终安全——计费的上游接口绝不会被重新请求；签名 URL 返回 HTTP >= 400 时仍快速失败（签名 URL 会过期，重放 403 毫无意义）。
- **`report_image_download` 的自动命名现在带扩展名**：`image/png` / `image/jpeg` / `image/gif` / `image/webp` / `image/svg+xml` 加入了 MIME→扩展名映射（与 TS 一致），因此自动命名的图片会落盘为 `report-image-<id>.jpg`，而不是没有扩展名。
- **不自动重发接口上的 999999 不再提示「稍后重试」。** SDK 有意不重试（请求可能已经执行并计费）；提示现在改为先核实结果/计费情况，再手动重试。

## [0.1.15] - 2026-07-11

与 `gangtise-openapi-cli` v0.24.0–v0.27.0 同步：计费安全的重试策略、4 个新接口（86 → 90）、对会被静默截断的参数做本地校验，以及轮询、分片、分页和下载各方面的可靠性加固。

### 变更
- **计费安全（重要）。** 16 个按次计费的接口——7 个同步 AI 生成接口、`earnings_review`/`viewpoint_debate` 的获取 ID、`hot_topic`、`knowledge_batch`、`concept_info`/`concept_securities`，以及 `summary`/`foreign_report`/`my_conference` 的下载——现在采用**不自动重发的重试策略**：5xx / 响应超时 / API 错误码 999999 不再自动重发（平台按次计费，命中缓存也不豁免，重放即重复计费）。只有连接阶段错误（可以证明请求从未到达服务端）、429 限流和 token 自愈仍会重试。廉价的按条计费列表接口保留完整的默认重试。
- **EDE 指标接口不再重试 999999。** 服务端对无数据查询（节假日 / 未来日期 / 未覆盖的证券）返回 HTTP 500 + 错误码 999999；此前每次空查询都要白耗 3 次请求和约 4 秒。错误提示现在指向检查查询时间窗，而不是「稍后重试」。
- **7 个同步 AI 生成接口获得 120 秒的超时下限**（`one_pager`、`investment_logic`、`peer_comparison`、`theme_tracking`、`research_outline`、`management_discuss_*` ×2）——长时间生成不再撞上 30 秒的默认超时；客户端显式设置了更高的超时时仍以更高者为准（取 max）。
- **429 响应遵循 `Retry-After`**（delta-seconds 或 HTTP-date，上限 60 秒），在 JSON 和下载两条路径上都优先于指数退避。
- **对服务端会静默截断的参数做本地上限校验**（经 CLI 侧实测）：`top`/`limit`——六个 `reference` 搜索 ≤ 10，`report_image_list` / `knowledge_batch` ≤ 20，`edb_search` ≤ 200，`indicator.search` ≤ 100——以及 `securities_search` / `institution_search` / `official_account_search` 的类别白名单（拼写错误过去会伪装成「无结果」）。违反时在发出任何请求之前抛出 `ValidationError`。
- **全市场 K 线分片在遇到硬错误后中止**：剩余分片不再派发（节省配额），并记录到 `failedShards`；没有 `list` 数组的 2xx 分片现在也会连同其时间窗落入 `failedShards`。触及单分片行数上限的分片会以具体日期窗口列在 **`truncatedShards`** 中（与 `failedShards` 对应），方便调用方缩小范围重新拉取。
- **AI 异步轮询容忍临时错误**：一次 5xx / 网络抖动（在传输层自身重试之后）只消耗一次轮询机会，而不会作废整个长达数分钟的等待；终态错误（积分不足、参数错误）仍会中止。
- `GANGTISE_PAGE_CONCURRENCY` 做了防御式解析：无效值 / 非正值回退到默认的 5，且上限为 32（负值过去会悄悄降级成单个串行 worker）。

### 新增
- **4 个新接口**（端点注册表 88 → 92，含 2 张本地 lookup 表）：
  - `insight.qa_list`——按证券查询投资者问答（互动平台 / 业绩说明会 / 调研来源，11 种问题类别，自动翻页每页 500 条；0.1 积分/条）。
  - `insight.report_image_list` / `insight.report_image_download`——按关键词搜索研报图片（返回 `chunkId` + 元数据；免费），并按 `chunkId` 下载原始 JPEG（0.1 积分/张）。
  - `reference.official_account_search`——微信公众号 ID 搜索（为 `insight.official_account_list` 提供 `accountId`；免费）。
- `ERROR_HINTS` 新增错误码 `100003`（枚举参数值无效）的条目。
- 为四个新方法补充示例脚本（同步 + 异步）及 `sample/API_PARAMETERS.md` 条目。

### 修复
- EDE 矩阵中名为 `date` / `security` / `name` 的列不再覆盖元数据列——它们会像其他重复列一样加上代码后缀。
- 自动生成的下载文件名在已存在 100 个同名文件时抛出 `DownloadError`，而不是悄悄覆盖第一个文件。
- 分页接口的第一页若以意外形状返回（如 `total` 为字符串），现在会发出 `UserWarning`，而不是悄悄降级为只取一页。
- 预签名 URL 下载获得整体硬时限（请求超时的 10 倍）：空闲型读超时会在每收到一个字节时重置，因此慢速滴灌的 CDN 过去可能让下载无限期挂起。

## [0.1.14] - 2026-07-07

类型体验、性能与参数校验方面的改进——接口与 API 面均无变化（仍与 `gangtise-openapi-cli` v0.23.0 对齐，86 个接口）。

### 变更
- **领域过滤参数现已标注类型** `str | int | Sequence[str | int]`（新增的 `FilterValue` 别名），不再是 `Any`。证券代码、行业 ID、评级等——无论单值还是列表——现在都能获得 IDE 补全和 mypy 检查；整数（`industry=1`、`fiscal_year=2025`）与字符串依旧都合法，与 API 实际接受的取值一致。
- **矩阵型接口构建 DataFrame 提速 2-5 倍。** 列式 `{fieldList, list}` 响应（财务报表、EDE 指标等）直接由列矩阵构建，不再先转置成逐行 dict 再转回；输出逐字节一致（取值与 dtype 均相同）。
- **分页参数 `from` / `size` 拒收 `bool`**（`int` 的子类），抛 `ValidationError`，与行情 `limit` 的校验一致，不再被当作 `0`/`1` 透传。
- 包分类标识（classifier）升级为 `Development Status :: 4 - Beta`。

### 新增
- 每个请求（同步 + 异步）都带上 `User-Agent: gangtise-openapi-python/<version>`，便于服务端日志区分 Python SDK 与 npm CLI。

## [0.1.13] - 2026-07-06

与 `gangtise-openapi-cli` v0.23.0 同步。

### 变更
- **默认 API 主机迁移** `https://open.gangtise.com` → `https://openapi.gangtise.com`（实际各接口等价；旧主机仍可用——设置 `GANGTISE_BASE_URL=https://open.gangtise.com` 即可固定使用旧主机）。
- **`vault.wechat_chatroom_list`** 改为消费服务端新的 `{total, list}` 响应，与其他分页接口一样按 `total` 并发拉取各页。原先专用的顺序翻页路径（无 `total`、`chatRoomList`）已移除。
- **分页截断现在可见。** 当服务端报告的 `total` 高于实际返回的行数，或 `MAX_PAGES`（1000）安全上限截断了并发拉取时，所有分页接口都会把结果标记为 `partial`（`raw=True` 时可见）并发出 `UserWarning`。这两种情况此前都是静默的。
- **行情接口的 `limit` 改在本地校验。** 超出 `1..10000` 的值或非整数（`1.5`、`True`、`"10"` 等）现在会在发请求前抛 `ValidationError`，而不是发到服务端，或在范围比较时漏出原始的 `TypeError`。

### 新增
- **`quote.fund_flow`**——A 股日度资金流向（沪/深/北；小单/中单/大单/特大单的流入/流出金额与占比 + 主力净流入；免费）。可传具体的 `security`（单个或列表），或传 `aShares` 查全市场——全市场请求按天做日期分片、并发拉取后合并，且必须同时提供 `start_date` 和 `end_date`（缺少日期范围抛 `ValidationError`）。单证券请求不分页；返回行数达到所发送的 `limit`（默认 6000，最大 10000）时，结果标记为 `partial` 并告警。同步 + 异步。
- **`reference.institution_search`**——跨五个类别检索机构 ID（`domesticBroker`/`foreignInstitution`/`leadInstitution`/`opinionInstitution`/`foreignOpinionInstitution`）；结果带 `usageScopes`，覆盖现有各接口中的券商/机构类入参。免费。同步 + 异步。
- **`vault.my_conference_list`** 新增 `source` 参数（录音来源；数值 `1`=企微会议助理 `2`=会议服务微信群）→ 请求体中为 `sourceList`。

### 修复
- **非分页行情接口的静默截断防护**（`fund_flow` 单证券、`minute_kline`，以及显式传入多证券的 `day_kline`/`-hk`/`-us`/`index_day_kline`）：这些接口的 `total` 报的是实际返回行数，因此当行数等于所发送的 `limit` 时，现在会把结果标记为 `partial`（`raw=True` 时可见）并发出 `UserWarning`，而不是静默丢行。`limit` 现在默认 6000 并显式发送，确保请求上限与截断判定阈值始终一致。
- **全市场分片合并**：合并结果的 `total` 现在反映合并后的总行数（此前沿用某一个分片较小的 `total`）；任一分片触及单次请求上限时，整个结果标记为 `partial`。合并时还会保留第一个非空的 `fieldList`，末尾的空分片不会再把列清空。
- **下载会跟随预签名 URL 的重定向。** 下载接口若以 `302` 重定向到对象存储的预签名 URL，现在会跟随跳转取回实际文件（`200` + JSON `{url}` 的形式此前已支持）；httpx 在跨源跳转时会丢弃 `Authorization` bearer，因此它不会到达存储主机。至此 CLI v0.22.0 的下载行为已全部移植。

## [0.1.12] - 2026-07-02

### 变更
- **`insight.announcement_list` 的纯日期字符串改用本地午夜**（与 `"YYYY-MM-DD 00:00:00"` 锚点相同），不再用 UTC 午夜，与 TS HEAD 一致，避免 UTC 以外时区的用户在边界日上出现偏移。

### 修复
- **模块级异步门面（facade）** 不再在不同的 `asyncio.run()` 事件循环之间复用同一个 `httpx.AsyncClient`；`reset()`/`configure(replace=True)` 现在会尽可能关闭缓存的异步客户端。
- **自动命名的下载** 遇到同名时会加后缀（`report.pdf`、`report-1.pdf`），不再静默覆盖第一个文件；过长的 UTF-8 文件名会被截断，同时保留扩展名。
- **`Content-Disposition` 文件名解析** 现在不区分大小写地解码 RFC 5987 `filename*=UTF-8''...` 值，百分号编码的中文文件名落盘时已是解码后的名字。
- **下载的鉴权重试** 现在复用其他请求已刷新好的 token，不再强制重新登录，与 JSON 请求路径一致。
- **分页** 现在在生成并发请求时即执行 `MAX_PAGES` 上限；异步并发拉取中格式异常/`None` 的页标记为 `partial`；顺序翻页中出现形状丢失也标记为 `partial`；首页为空或不满一页时直接停止，不再重复请求同一偏移。
- **`fundamental.earning_forecast` 默认时间窗口** 在只提供 `end_date` 时，现在以该 `end_date` 为锚点推算 `start_date`。
- **`normalize_token`** 将 `bearer ...` / `BEARER ...` 规范化为 `Bearer ...`，不再生成 `Bearer bearer ...`。
- **异步下载清理** 在 `finally` 中同步删除 `.part-*` 文件，取消操作也无法跳过删除。

### 安全
- 发布 CI 现在用 `uv --locked` 同步依赖，发布前检查 README/CHANGELOG 是否提及该 tag，并将 PyPI 发布 action 固定到某个 commit SHA，而不是可变的 `release/v1` 分支。

## [0.1.11] - 2026-06-29

### 变更
- **`vault.wechat_chatroom_list`** 在省略 `size` 时现在拉取**全部**群聊（此前上限 20）。该接口不返回 `total`，因此客户端顺序翻页，直到出现不满一页的页（服务端每页上限 50）表示结束；传 `size=N` 可将结果限制为前 N 行。依赖隐式 20 行默认值的脚本现在会拿到所有群。移植自 CLI v0.21.0。

### 修复
- **下载文件名** 除原有的路径不安全字符集外，现在还会剔除控制字符和 NUL（`\x00`–`\x1f`），避免服务端给出的文件名破坏文件写入或夹带终端转义序列。与 TS 对齐（CLI v0.21.0）。
- **标题缓存** 加载时会丢弃半损坏的条目（`titles` 字段不是 dict 的接口条目），不再沿用下去——否则可能导致下一次记录标题的列表调用崩溃。
- **格式异常的 2xx 响应不再静默丢行**：当并发分页的某一页或某个分片 K 线响应返回 `200` 但形状不符合预期（既不是分页列表，也不是 K 线矩阵）时，结果现在标记为 `partial` 并发出告警，而不是悄悄略去这些行。这让「成功但格式异常」的路径与硬失败路径以及顺序收集器的处理保持对称。

### 安全
- **token 缓存与标题缓存** 文件现在以 `0600` 原子创建（`os.open` 指定模式 `0600`，再原子重命名），取代先写入再 `chmod` 的做法，消除了文件短暂以 umask 默认权限（通常全局可读）存在的时间窗口。移植自 CLI v0.21.0 的 token 缓存加固；标题缓存可能包含非公开的研报标题。

## [0.1.10] - 2026-06-27

### 新增
- **指标（EDE）领域**——`gangtise.indicator.*`（同步 + 异步）：`search` 按关键词查找数据指标代码；`cross_section` 返回单一日期下的多指标 × 多证券矩阵；`time_series` 返回某一日期区间内的多指标 × 单证券（或单指标 × 多证券）矩阵。线上返回的 `values` 矩阵被展平为宽表行（每个证券/每个日期一行，指标名作列），内层的双层信封会被拆开——内层失败码以 `ApiError` 抛出，而不是返回 null 载荷。`indicator_param={"qte_close": {"adjustmentType": "2"}}` 可为单个指标设置选项（如前复权）。移植自 CLI v0.19.0。
- **美股接口**（CLI v0.20.0）：`insight.announcement_us_list` / `announcement_us_download`（与港股公告方法对应，`file_type` 1=原始 PDF，2=Markdown）；`fundamental.income_statement_us` / `balance_sheet_us` / `cash_flow_us`。
- **`ai.stock_summary_list`**（个股看点）——按证券给出的精炼投研摘要；必须传 `security`（证券代码或市场关键词 `aShares` / `hkStocks`），传空值时抛 `ValidationError`，避免全市场查询导致积分暴增。
- **`reference.chiefs_search`**——按姓名/机构/团队检索首席分析师 ID。

### 变更
- **`ai.hot_topic`** 现在把 `with_related_securities` / `with_close_reading` 作为显式布尔值发送，传 `False` 即发送 `false`（此前会省略该字段，由服务端使用默认值）。与 TS 对齐（`!== false`）。
- **`insight.announcement_hk_download`** 新增 `file_type`（1=原文，为默认值；2=Markdown），与 CLI 一致。
- **缺少凭证时的报错** 现在会指明缺的是 `GANGTISE_ACCESS_KEY` 还是 `GANGTISE_SECRET_KEY`，并说明如何在 shell 中 `export`（以及 `gangtise.configure(...)`），取代原来笼统的单一提示。

### 修复
- **分页改为软失败**：当并发拉取的某一页遇到不可重试错误（限流、无权限）时，保留已拉取的页并发出 `UserWarning`，而不是抛异常丢弃全部结果。raw 载荷带 `partial=True` 和 `failedPages` 标记（`raw=True`）；默认的 DataFrame 会去掉这些键，因此在该路径上告警就是唯一信号——与现有 K 线分片的容错方式一致。同步 + 异步；CLI v0.20.0。
- **`ai.knowledge_batch`** 在 `query` 为空时抛 `ValidationError`，不再向服务端发送空的 `queries` 列表。

## [0.1.9] - 2026-06-17

### 新增
- **Insight 公众号（微信）接口**：`official_account_list` 按关键词/公众号/证券/类别（枚举）/行业分页检索产业公众号文章，支持 `search_type`（1=标题，2=全文）和 `rank_type`（1=综合，2=时间倒序）；`official_account_download` 按 `article_id` 将文章下载为 txt（默认，`file_type=1`）或 HTML（`file_type=2`）。两个方法均提供同步 + 异步版本，下载时通过标题缓存解析文件名。移植自 CLI v0.18.0。

## [0.1.8] - 2026-06-16

### 修复
- **服务端使 token 失效后自动恢复**（`0000001008`）：当服务端吊销了一个按本地过期时间看仍然有效的 token 时——例如账号在别处登录、挤掉了本会话——SDK 现在会强制重新登录并重放请求一次，覆盖 `_call` 与下载两条路径（同步 + 异步），而不是在手动重新登录之前每个请求都失败。同时补充了对应的中文错误提示。移植自 CLI v0.17.2。

## [0.1.7] - 2026-06-16

### 修复
- **并发下载临时文件冲突**：`download_to_path` / `download_to_path_async` 以前流式写入固定的 `<target>.part` 临时文件。两个并发下载若解析到同一目标文件名（同一 id 下载两次、两份标题相同的文档，或显式传了相同的 `output=`），会写入同一个文件句柄——字节交错——且各自的清理会删掉对方的文件，表现为 `DownloadError: ... No such file or directory`。临时文件现在带每次调用唯一的后缀（`.part-<uuid>`），让每次下载都具备 token / 标题缓存早已具备的隔离性。

### 变更
- **异步下载不再因文件系统元数据操作阻塞事件循环**：异步写入路径中的 `mkdir` / `replace` / `unlink` 现在通过 `anyio.to_thread.run_sync` 执行（流式写入正文本就使用 `anyio.open_file`）。
- **行提取逻辑合并**：`reference.securities_search` 和 `alternative.edb_search`（同步 + 异步）现在使用共享的 `_extract_rows` 辅助函数，取代各自定制的 `isinstance` 判断链——对这些接口返回的形状输出完全相同，还顺带获得列式矩阵的兜底处理。

## [0.1.6] - 2026-06-15

与上游 CLI v0.16.0 和 v0.17.0 同步；另修复 3 个 bug。

### 新增
- **`reference` 常量/概念/板块 API**（5 个新接口，同步 + 异步）：
  - `reference.constant_category()`——列出常量类别，以及哪些 API 参数接受这些类别（`GET /application/open-reference/constants/category`）。
  - `reference.constant_list(category=...)`——某一类别下的全部常量值（citicIndustry / swIndustry / gangtiseIndustry / domesticCity / aShareAnnouncementCategory / hkShareAnnouncementCategory / regionCategory）。API 返回的 `constants` 数组被归一化为 `list`（与 TS `normalizeRows` 对齐）；树状类别保留嵌套的 `children`——需要递归时用 `raw=True`。
  - `reference.concept_search(keyword=..., top=10)`——题材/概念 ID 检索（ID 与 `alternative.concept_*` 和 `ai.theme_tracking` 通用）。
  - `reference.sector_search(keyword=None, top=10)`——板块 ID 检索，用 `hierarchy` 区分同名板块。
  - `reference.sector_constituents(sector_id=...)`——某板块的完整成分股列表（`gtsCode`/`gtsName`）。
- **四个日程列表新增 `location` 过滤**（`insight.roadshow_list` / `site_visit_list` / `strategy_list` / `forum_list`）：城市/省份 ID 取自 `reference.constant_list(category="domesticCity")`，以 `locationList` 发送。

### 修复
- **日程过滤参数收紧**（与 TS v0.17.0 对齐）：四个日程接口现在各自只暴露其 API 规格真正支持的过滤参数。此前四者共用一套相同的宽泛签名，不支持的关键字参数（如 `strategy_list(market=...)`）会被静默发往服务端，服务端返回空行而不报错。现在不支持的关键字参数会在调用处抛 `TypeError`，与 TS `v0.17.0` 按命令划分的字段矩阵一致。各接口具体变化：
  - `roadshow_list`——移除 `object_`（路演不接受该参数）。
  - `site_visit_list`——保留 `object_`；`market` 限定为 `aShares/hkStocks/usChinaConcept`（无 `usStocks`）。
  - `strategy_list`——收窄为仅 `institution` + `location`。
  - `forum_list`——收窄为仅 `research_area` + `location`。
- **`insight.announcement_list` / `announcement_hk_list`**（与 TS v0.17.0 对齐）：移除 `announcement_type` 参数——服务端一直忽略它。
- **`ai.knowledge_batch` 的空 `resource_type`**：此前传 `resource_type=[]` 会在请求中发送 `"resourceTypes": []`；TS CLI 在列表为空时省略该字段（`.length` 判断）。已用 `_as_list(...) or None` 修复。
- **`_quote_sharding.is_all_market` 遇到混合列表**：`security=["all", "000001.SZ"]` 会错误地触发全市场分片。TS 仅在 `securityList` 恰好为 `["all"]` 时分片；已修复为 `list(security) == ["all"]`。
- **`410110`/`410111` 的错误提示文案** 与 TS `errors.ts` 对齐（提及 `*-check` 命令，终态失败码的提示中使用「终态」）。

### 移除
- **六个已由 API 覆盖的本地查询表**（与 TS v0.16.0 对齐）：`lookup.research_areas` / `industries` / `regions` / `announcement_categories` / `industry_codes` / `theme_ids` 及其内置数据文件。这些 ID 现在由 `reference.constant_list`、`reference.concept_search` 和 `reference.sector_constituents` 在线提供。仅 `lookup.broker_orgs` 和 `lookup.meeting_orgs` 仍保留在本地。端点注册表由 75 项减为 74 项。

## [0.1.5] - 2026-06-12

### 修复
- **并发下的 token 处理**：N 个并发调用方遇到过期 token 时，现在只触发一次登录（与 TS `refreshPromise` 对齐）；被拒的 `GANGTISE_TOKEN` 环境变量 token 在首次失败后即被跳过，不再让此后每次调用都永久变成三倍请求；token 缓存的临时文件现在按写入方唯一（多进程安全）；`__enter__`/`__aenter__` 复用惰性创建的 HTTP 客户端，不再泄漏旧连接池。
- **异步错误契约**：分页/分片并发拉取失败时，现在抛出原始的 `ApiError`，而不是 anyio 的 `ExceptionGroup`，因此 `except ApiError` 在同步和异步代码中行为一致。
- **K 线分片**（与 CLI 对齐）：单个分片失败不再丢弃全部已拉取的数据——成功的分片会合并，并带上 `partial: true` + `failedShards` 标记，同时发出 `UserWarning`；只有全部分片都失败时才抛异常。
- **下载路径**（与 TS 对齐）：鉴权自愈（8000014/8000015 → 刷新 → 重试一次）、瞬时错误带退避重试、预签名 `{url}` 响应现在会去取文件而不是报错、4xx JSON 信封保留业务码和中文提示、流式传输失败时清理 `.part` 临时文件，且异步版本写盘时不再阻塞事件循环。
- **门面（Facade）**：`gangtise.configure(...)` 现在会同步作用到 `gangtise.async_`（此前异步门面只会静默重读环境变量）。
- **TS 对齐细节**：`fundamental.earning_forecast` 在省略日期时注入 CLI 默认的一年日期窗口；`insight` 时间戳转换与 `toTimestamp13` 一致（秒级整数 ×1000，naive datetime 按本地时区处理）；`ERROR_HINTS` 补齐至 TS v0.15.1（410004、430004、430007、433007、10011401）。
- 缓存持久化失败（token 缓存 / 标题缓存）不再导致本已成功的请求或下载失败。
- 文档中引用了不存在的 `lookup.theme_ids_list()`——已更正为 `lookup.theme_ids()`。

### 变更
- **性能**：列式 K 线载荷直接由矩阵构建 DataFrame（快 2–3 倍，大行数时峰值内存约减半）；全市场日 K 线分片跳过纯周末窗口（回补 1 年数据时请求数减少约 29%）。
- IDE 体验：门面的领域属性现已静态标注类型（mypy / IDE 自动补全可用于 `gangtise.quote.*`），`dir()` 会列出各领域，每个公开方法都有中文 docstring，注明接口 key 与枚举值。

## [0.1.4] - 2026-05-30

### 新增
- **`alternative.concept_info`**——概念（题材指数）的最新简介：定义、投资逻辑、行业空间、竞争格局，以及 `keyEvents` 列表。按 `concept_id` 查询；以 dict 形式返回唯一一个最新截面对象（无历史）。（`POST /application/open-alternative/concept/info`）
- **`alternative.concept_securities`**——概念（题材指数，F8）的成分证券，按组划分。每只证券带 `isKey`（重点股标记）和 `inclusionReason`。默认 DataFrame 将分组展平为每只证券一行，并带 `groupName` 列；`raw=True` 返回嵌套的分组载荷。没有成分股的概念返回列相同的空 DataFrame。（`POST /application/open-alternative/concept/securities`）
- `concept_id` 与 `ai.theme_tracking` 共用同一套题材 ID 命名空间——可通过 `gangtise.lookup.theme_ids()` 按名称查找 ID（如 机器人 → `121000130`）。同步与异步方法均已添加。

### 变更
- `quote.index_day_kline` 现在会带出上游新增的 `securityName` 列（如「上证指数」）。方法无需改动——0.1.3 中上线的动态 schema 路径会透传 API 返回的所有字段。

### 性能
- **标题缓存不再无限增长。** 该缓存（用于解析下载文件名）此前会永久合并每次列表调用的标题，并在每次合并时刷新条目的 `ts`，导致 24h TTL 永远清理不掉高频接口——磁盘上已达约 58 MB / 600k+ 条标题，每次客户端初始化都要重新解析（约 900 ms），每次非 `raw` 列表调用都要整体重写（约 360 ms）。现在每个接口的标题数设有上限（`TITLE_CACHE_MAX_PER_ENDPOINT`，保留最近 10k 条），加载时裁剪超大条目，且没有带出新标题的列表调用不再把缓存标脏（不重写）。在一个真实的 58 MB 缓存上，下一次写入缩减到约 1.7 MB，客户端初始化的解析时间也按比例下降。

## [0.1.3] - 2026-05-29

### 修复
- **`quote.realtime` 和 `quote.minute_kline` 返回全为 None 的 DataFrame。** 这两个接口返回列式矩阵 `{fieldList, list:[[...]]}`，但行数据是按一份硬编码 schema 制表的，而 schema 中的字段名与 API 对不上，导致每个单元格都是 null。现在按响应中的 `fieldList` 转置每一行（共享的 `_quote_rows_and_fields` 辅助函数）。
- **`quote.day_kline` 列名已更正。** 硬编码 schema 凭空造出了 `turnover` / `changePct`，还丢掉了真实字段；A 股日 K 线并没有 `turnover` 列——真实字段是 `pctChange` 和 `adjustFactor`。
- **`reference.securities_search` 返回的列大多为 None。** schema 用的是 `code/name/market/...`，而 API 实际返回 `gtsCode/gtsName/category/matchScore/matchType`。
- 移除全部三个硬编码的行情 schema 以及字段别名重映射；行情与证券检索现在原样返回 API 的字段名（`schema=None`），与 0.1.2 中为 fundamental 接口上线的列式修复一致。

## [0.1.2] - 2026-05-29

### 修复
- **列式响应的 DataFrame 转换。** 许多数据接口（fundamental 的利润表 / 资产负债表 / 现金流量表、估值分析、主营业务）返回列式矩阵 `{fieldList, list:[[...]]}`。新增的 `normalize_rows`（移植自 TS CLI）会将其转置为具名列；此前这些接口产出的是空 DataFrame 或列名为整数的 DataFrame。
- `fundamental.valuation_analysis` 的列 schema 已更正为真实字段（`tradeDate, value, percentileRank, average, median, upper1Std, lower1Std`）。
- `GANGTISE_VERBOSE` 现在真正会输出调试日志——同步与异步传输层都挂上了 stderr handler（此前只设置了日志级别却没有 handler，日志记录被丢弃）。客户端会遵循 `Config.verbose`。
- 异步客户端在 token / 标题缓存的磁盘 I/O 上不再阻塞事件循环（通过 `anyio.to_thread` 移到线程中执行）。
- 标题缓存在加载时清理超过 TTL 的条目，限制磁盘占用的增长。
- 示例 `fundamental_valuation_analysis` 使用了无效指标（`pe_ttm` → `peTtm`）。

### 新增
- `fundamental.earning_forecast` 现在返回 DataFrame（展平后的分析师一致预期，每个更新日期 × 预测年度一行）。默认返回最新一次更新的快照；传 `latest=False` 获取完整历史，传 `raw=True` 获取嵌套载荷。
- 异步传输层现在会记录请求耗时日志，与同步路径一致。

### 变更
- 领域辅助函数（`_as_list`、`_strip_none`、`_extract_rows`）合并到 `domains/_common.py`（此前在每个领域模块中重复存在）。
- 分页结果在 `MAX_PAGES` 处被截断时会记录一条告警日志。
- 从传输层的请求函数中删去了一个未使用的 `config` 参数。

## [0.1.1] - 2026-05-28

## [0.1.0] - 2026-05-28
