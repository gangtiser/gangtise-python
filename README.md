# gangtise-openapi

[Gangtise OpenAPI](https://openapi.gangtise.com) 的 Python SDK。把 161 个投研数据接口封装成带完整类型签名的 Python 方法，表格类结果直接返回 pandas DataFrame。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.51.0 功能对齐。

- **覆盖面**：观点、研报、公告、纪要与会议、行情 K 线与资金流向、指数成分权重、财务报表与估值、证券级数据指标（EDE）、债券、公募基金、AI 生成内容、专家情报与管理层情绪、个人云盘、股票池与个股笔记、微信群消息与群文件、联网搜索、PDF 解析。
- **同步与异步**两套接口，方法与参数一一对应。
- **自动处理分页与拆分**：分页列表自动翻页；全市场 K 线按工作日自动分片；多只证券自动合批。
- **计费保护**：按条计费的大批量拉取、不可逆的删除操作都要显式确认；按次计费与单次可能花费较多的接口在超时、5xx 后不自动重发（仍会自动重试的计费接口见「计费与确认」）。
- **结果完整性**：数据不完整时在结果上标 `partial` 并告警，不会把被截断的结果当作完整结果返回。
- **本地校验**：日期写法、参数取值、空列表等问题在发请求前就报错，不花积分。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

### 0.5.5 - 2026-11-07
- 与 CLI **v0.51.0** 对齐，新增 3 个接口，共 **161 个**。
- **新增**：`ai.expert_intel_list`（AI 专家情报，20 积分/条，自动翻页、额度保护，超时不自动重发）；`reference.index_weight`（指数成分股权重，免费；只有每月最后一个交易日有数，其他日期返回空结果并告警）；`vault.wechat_message_download`（群消息里的文档 / 图片 / 音频 / 视频文件，免费，按原字节保存）。
- `vault.wechat_message_list` 的 `category`：文档类取值是 `document`（0.5.4 文档写的 `documents` 会报 `100005`），新增 `audio` / `video`。
- `fund.etf_pcf_components` 补码：A / H 同名而价格定不了的行，改用该行的 `pctChange` 与日 K 的收盘价 + 涨跌幅核对，能定的不再留 null。
- **修复**（下载）：服务端文件名自带的扩展名原样保留（0.5.4 会把 `config.ini` 存成 `config.ini.txt`）；Python 3.13 上 `filename*` 解不出时改用普通 `filename`（0.5.4 存成 `<前缀>-<id>`）。

### 0.5.4 - 2026-11-02
- 与 CLI **v0.50.0** 对齐，新增 5 个接口，共 **158 个**。
- **新增**：个股投资笔记 `vault.stock_note_list` / `stock_note_add` / `stock_note_update` / `stock_note_delete`（全部免费，只操作本人笔记；删除须 `confirm=True`，新增超时不自动重发）；`quote.sector_fund_flow`（板块日资金流向，免费）。
- `vault.stock_pool_list` / `stock_pool_stocks` 新增 `space_type`（`2` 查所属租户的股票池）；路演 / 调研 / 策略会 / 论坛列表新增 `publish_start_time` / `publish_end_time`（按收录时间筛选）。
- `indicator.time_series` 不传 `calendar_type` 时不再先查 `indicator.search`、也不再自动发 `TD`，由服务端选日期轴（纯交易日类序列结果不变）；空结果的告警先指向日期轴。⚠️ **服务端口径变化（0.5.3 同样受影响）**：不传 `calendarType` 时服务端按指标定日期轴（行情类交易日、报告期类报告期、混查取并集），报告期类不再返回逐日 null 行，区间里没有报告期末时返回空结果；一致预期类（`frcst_*`）要逐日序列请传 `calendar_type="ND"`。
- `fund.etf_pcf_components` 补码：同名证券在两个市场都有时，实时价对得上还要另一市场那只的近期收盘价对不上才采用；没补上代码的行里有一行可能在两个市场（含价格同时对得上 A / H 的行）时，不按其余行推断 ETF 的市场，这类行为 null。含 A / H 同名成分的 ETF 每次都会查日 K（免费；此前只在有行与实时价对不上时才查）。

### 0.5.3 - 2026-10-28
- 与 CLI **v0.49.0** 对齐，无新增接口。
- 🔴 **`fund.etf_pcf_components`**：接口只返回成分名称，SDK 按名称匹配、用收盘价核对，补上带市场后缀的 `componentCode`（如 `600519.SH`，A+H 同名两行据此分开）；匹配不到的为 null，并发 `UserWarning` 列出。额外请求都免费，`component_code=False` 关闭。
- ⚠️ **服务端口径变化**：管理层情绪的 `publishTime` 现为北京时间（按 0.5.2 说明「先加 8 小时」的处理要去掉）；`fund.holder_structure` 的 `holderCount` 现为整数（去千分位逗号的处理要去掉）。
- 文档：`ai.security_clue_list` 的 `gts_code` 按 `query_mode` 传股票代码或申万行业码。

### 0.5.2 - 2026-10-25
- 与 CLI **v0.48.0** 对齐，新增 4 个接口，共 **153 个**。
- **新增**：`ai.management_sentiment_indicator` / `management_sentiment_conclusion`（管理层情绪评分与结论，5 积分/条，自动翻页、额度保护）、`ai.management_sentiment_detail`（逐条问答评分，10 积分/次）；`bond.default_list`（违约债券）。⚠️ 管理层情绪返回的 `publishTime` 比北京时间早 8 小时。
- 🔴 **`insight.opinion_list` 的 `llm_tag` 换为 28 项投研业务标签**，新增 `category`（观点类别）与 `broker_tag`（机构标签）。「业绩点评」「头部券商」「新财富团队」改传 `category="earningsReview"`、`broker_tag="topBroker"` / `"newFortune"`，继续传给 `llm_tag` 服务端报 `100005`。`with_content=True` 不收两个新参数（本地报错）。
- **计费按平台最新价目**：AI 生成多数 10 积分/次（业绩点评、观点辩论 20），热点话题 10/篇，个股看点 1/条，路演等四个日程列表 10/条，独立观点列表 1/条，纪要 / 外资研报 / 我的会议下载 30/篇，公告与财报日历下载 1–2/篇；`alternative.edb_data` 30 积分/指标。额度保护按新单价估算。
- `reference.securities_search` 新增 `category="bond"`；`bond.daily_quote` / `bond.valuation` 首行比 `start_date` 晚超过 14 天时告警。
- **修复**：路演 / 调研 / 策略会 / 论坛列表的翻页去重此前按 `id` 认行、实际不生效，现按各自的行 ID 去重并标 `partial`。
- 文档：四个日程列表的 `location` 传 domesticCity 码可用（传城市名报 `999999`）；A 股财务报表返回的是含重述的最新版本数值，做时点回测别按 `earliestAnncDate` 回填。

### 0.5.1 - 2026-10-07
- 与 CLI **v0.45.0** 对齐，无新增接口。
- `vault.drive_copy` 可复制整个文件夹：传 `folder_id` + `target_parent_id`，连同子文件夹与文件复制到另一空间，返回 `{folderId, newFolderId}`；复制文件的写法（`file_id` + `target_folder_id`）不变，两组参数二选一，混传或只传一半在本地报错。
- 下载：响应同时给出编码文件名（`filename*`，通常为 UTF-8）与普通文件名时，用编码的那个，并按它声明的字符集解码。
- 接口地址用明文 `http://` 且不是本机地址时告警一次：AK / SK 与 token 会明文传输。
- 文档：`bond.daily_quote` / `bond.valuation` 的数据可能比账号窗口短，**取长序列时核对首行日期**；`bond.announcement` 按日期查询时有代码的行都带后缀；只知道基金名称时怎么换代码。

## 安装

```bash
pip install gangtise-openapi
```

需要 Python 3.10+。升级到最新版：

```bash
pip install --upgrade gangtise-openapi
```

刚发版时若提示找不到新版本，多为 PyPI / pip 缓存滞后，加 `--no-cache-dir` 即可。

## 配置

最少只需两个环境变量：

```bash
export GANGTISE_ACCESS_KEY=ak_xxx
export GANGTISE_SECRET_KEY=sk_xxx
```

| 环境变量 | 说明 |
| :-- | :-- |
| `GANGTISE_ACCESS_KEY` / `GANGTISE_SECRET_KEY` | 账号凭证，SDK 用它们登录换取 token |
| `GANGTISE_TOKEN` | 直接使用已有 token，优先于 AK/SK；失效时若同时配了 AK/SK 会自动重新登录 |
| `GANGTISE_BASE_URL` | 接口地址，默认 `https://openapi.gangtise.com`。用明文 `http://` 且不是本机地址时告警一次（凭证会明文传输） |
| `GANGTISE_TIMEOUT_MS` | 单次请求的超时（整数毫秒，1000–3600000，默认 30000）。同步 AI 生成类接口与 `ai.stock_summary_list` 另有 120 秒下限，`tool.file_parse` 与 `vault.drive_upload` 两个上传接口为 300 秒 |
| `GANGTISE_PAGE_CONCURRENCY` | 自动翻页与分片的并发数，默认 5，最大 32 |
| `GANGTISE_VERBOSE` | 设为 `1` 时输出每个请求的耗时日志 |
| `GANGTISE_TOKEN_CACHE_PATH` / `GANGTISE_TITLE_CACHE_PATH` | token 缓存与下载文件名缓存的位置，默认在 `~/.config/gangtise/` |

环境变量设成空字符串按未设置处理。token 缓存与 npm CLI 共用同一个文件，并记录签发它的凭证：换了 `GANGTISE_ACCESS_KEY` 后不会沿用上一个账号的 token。

也可以在代码里配置：

```python
from gangtise_openapi import gangtise

gangtise.configure(access_key="ak_xxx", secret_key="sk_xxx", timeout=60)
```

或者自己创建客户端，配合各领域的类使用：

```python
from gangtise_openapi import GangtiseClient
from gangtise_openapi.domains import Quote

with GangtiseClient(access_key="ak_xxx", secret_key="sk_xxx") as client:
    df = Quote(client).day_kline(security="600519.SH", start_date="2026-09-01", end_date="2026-09-30")
```

## 快速开始

```python
from gangtise_openapi import gangtise

# 表格类接口返回 pandas DataFrame
df = gangtise.quote.day_kline(security="600519.SH", start_date="2026-09-01", end_date="2026-09-30")

# 全市场：用市场关键字，SDK 自动按工作日分片后合并
market = gangtise.quote.day_kline(security="aShares", start_date="2026-09-28", end_date="2026-09-30")

# 公募基金净值
nav = gangtise.fund.nav(security="510300.SH", start_date="2026-09-01", end_date="2026-09-30")

# 按条计费的列表：用 size 控制取多少条
opinions = gangtise.insight.opinion_list(keyword="机器人", size=20)

# raw=True 返回接口原始数据（dict / list），包括完整性标记
raw = gangtise.insight.research_list(keyword="光伏", size=50, raw=True)
```

异步写法相同，入口是 `gangtise.async_`：

```python
import asyncio

from gangtise_openapi import gangtise


async def main():
    df = await gangtise.async_.quote.day_kline(security="600519.SH")


asyncio.run(main())
```

多个值请传列表（`security=["600519.SH", "000858.SZ"]`）；字符串是一个值，不会按逗号拆分。列表里的重复值与首尾空格会自动去掉；显式传空列表会报错——要不过滤就别传该参数。

## 计费与确认

- **按条计费的列表**（研报、公告、观点、路演 / 调研 / 策略会 / 论坛、个股线索、专家情报、管理层情绪、热点话题等）不传 `size` 时，SDK 先拿到总条数，按 `total × 单价` 估算全量，**超过 1000 积分就报 `ValidationError`，不再往下拉**，报错里给出估算值。只要一部分就传 `size=N`；确认要全量再传 `confirm=True`。显式传的 `size` 按 `min(size, total)` 同样估算。
- **`fundamental.earning_forecast`** 按日期区间估算（工作日数 × 3 条 × 0.5 积分），超过 1000 积分同样需要 `confirm=True`。
- **不可逆的操作**——`vault.stock_pool_delete`、`vault.stock_note_delete`、`vault.drive_delete_file`、`vault.drive_delete_folder`——必须传 `confirm=True`，否则在发请求前报错。
- **不自动重发**：以下接口在超时、断连、5xx 这类结果不确定的失败后不会自动重发，避免重复扣费：
  - 按次 / 按页计费的接口（AI 生成、管理层情绪明细、题材、联网搜索、PDF 解析、全部基金接口与 10 个债券接口等）；
  - 单次可能计费超过 3000 积分的 `ai.stock_summary_list`、`fundamental.earning_forecast`；
  - 另外 13 个按量计费接口：`ai.hot_topic`、`ai.expert_intel_list`、`insight.highlight_list`、观点正文（`opinion_detail` / `foreign_opinion_detail`，以及 `opinion_list` / `foreign_opinion_list` 传 `with_content=True`）、三个 30 积分的文档下载（`insight.summary_download` / `foreign_report_download`、`vault.my_conference_download`）、三个债券评级接口（`bond.rating_overview` / `rating_change` / `issuer_rating_change`）。

  这类失败后请先到平台核实是否已扣费，再决定是否重新调用。只有 `999999` 的 `hint` 会给出这条提示；其他 5xx（包括网关返回的 HTML 错误页、夹在 5xx 里的业务码）带的是通用提示，超时、断连抛出的是网络异常、没有 `hint`（见「错误处理」），同样要先核实。
- **仍会自动重试**：其余 29 个计费接口（20 个按条计费的列表、8 个文档下载与按指标计费的 `alternative.edb_data`）沿用默认重试：遇到 5xx、响应超时、请求发出后断连或 `999999` 时重试至多 2 次，服务端若其实已执行，每次重试都会再计费。单页最贵的是 `ai.security_clue_list`（至多 2500 积分），其次是两个管理层情绪列表与四个日程列表（至多 500），`alternative.edb_data` 一次至多 300。

`confirm=True` 对应 CLI 的 `--yes`，只认真正的 `True`。

## 结果完整性

结果不完整时，SDK 会发出 `UserWarning` 说明原因，并在原始结果（`raw=True`）上标 `partial: True` 和对应的标记。默认返回的 DataFrame 带不走这些标记，需要据此做判断时请用 `raw=True`，或把告警转成异常（`warnings.simplefilter("error", UserWarning)`）。

| 标记 | 含义 |
| :-- | :-- |
| `duplicateRows` / `changedRows` | 翻页时有行重复出现（重复了几行就缺了几行）/ 翻页期间有行内容变化 |
| `totalCapped` | 服务端返回的 `total` 是封顶值，实际条数更多 |
| `failedShards` / `truncatedShards` / `droppedColumns` | 全市场 K 线有分片失败 / 撞满行数上限 / 有列只在部分分片出现 |
| `outOfWindowShards` | 早于账号可回溯窗口的分片被跳过（不算不完整，仅列出日期） |
| `truncatedSecurities` | 多只证券合并时，某只证券撞满了 `limit` |
| `missingFields` | `field=` 里有接口不认识的字段名，该列没有返回 |
| `failedPages` | 分页列表有页没取到（列出这些页的 `from` / `size`，可只补这几页） |
| `omittedIndicators` / `omittedSecurities` | 指标矩阵：服务端不认识的指标或证券代码从结果里消失了（多为拼写或市场后缀错误） |
| `missingIds` / `unfetchedIds` / `unfetchedError` | 观点正文：部分 ID 没有正文 / 后面的批次失败，这些 ID 未取到，失败原因在 `unfetchedError` |
| `failList` | 股票池、个股笔记与云盘的批量写操作：请求成功但其中部分条目失败（列表非空即标 `partial`） |

## 关于日期格式

**三种「年在前」写法都收，统一成 `YYYY-MM-DD` 再发出：**

| 你传的 | 发出去的 |
| :-- | :-- |
| `"2026-07-01"` | `2026-07-01` |
| `"2026/07/01"` | `2026-07-01` |
| `"20260701"` | `2026-07-01` |

`start_time` / `end_time`（以及日程列表的 `publish_start_time` / `publish_end_time`）同理，只规范日期部分：`"2026/07/01 09:30:00"` → `"2026-07-01 09:30:00"`（秒可省，空格或 `T` 分隔；例外是 `ai.management_sentiment_indicator` / `management_sentiment_conclusion`，写时刻须带秒，`HH:mm` 报 `110001`）；10 / 13 位 Unix 时间戳原样透传。末尾带换行的值会被拒绝，从文件或管道读入的值请先 `.strip()`。

`ai.knowledge_batch` 与 A 股 `insight.announcement_list` 的时间参数由 SDK 换算成毫秒，**按北京时间（UTC+8）解释**，与运行机器的时区无关；`end_time` 只写日期时表示当日 23:59:59。要用别的时区就显式写偏移（`"2026-08-01T00:00:00-04:00"`）或直接传时间戳。

**「年在后」的写法会在发请求前拒绝**，因为它对不同的人意思不同：

| 写法 | 美式读法 | 国际习惯读法 | 平台实际按 |
| :-- | :-- | :-- | :-- |
| `01-07-2026` | 1 月 7 日 | 7 月 1 日 | **1 月 7 日**（美式） |
| `07-01-2026` | 7 月 1 日 | 1 月 7 日 | **7 月 1 日**（美式） |

平台接口能解析年在后的写法，但一律按美式「月在前」。若按国际习惯用 `"01-07-2026"` 表示 7 月 1 日，拿到的会是 1 月 7 日的数据——请求正常返回、行数看着也正常，**不会有任何报错**。SDK 在本地拒收这类写法（不发请求、不计费），报错里给出可用的格式。绕过 SDK 直接调用 HTTP 接口时，请统一使用 `YYYY-MM-DD`。

## 错误处理

SDK 自己的异常都继承自 `gangtise_openapi.GangtiseError`：

| 异常 | 何时抛出 |
| :-- | :-- |
| `ValidationError` | 多数是参数在本地校验不通过，此时没有发请求、不计费。也有两类在请求之后抛出、可能已经计费：按条计费列表的额度保护（见「计费与确认」，要先取一页——单页超过 50 积分时只取 1 条——才知道总条数，报错里写明取了几条），以及返回结构校验不通过（如列数与 `fieldList` 不符、列名重复，属于上游异常，请报障）。**不能只凭异常类型判断是否已发请求或计费** |
| `ConfigError` | 缺少凭证或配置不合法 |
| `ApiError` | 接口返回错误。`code` 是平台错误码，`hint` 是中文处置建议，`trace_id` 是报障时需要提供的追踪号 |
| `DownloadError` | 下载失败 |

超时、断连、响应解压失败这类网络错误，自动重试用尽（或该接口不自动重发）后会原样抛出 httpx 的异常（`httpx.ReadTimeout`、`httpx.ConnectError` 等，都是 `httpx.HTTPError` 的子类），**不继承 `GangtiseError`**；单次请求超过总时长上限时同样抛 `httpx.ReadTimeout`。下载接口例外：下载阶段的网络错误与超时都包成 `DownloadError`。要一并处理，请同时捕获两类：

```python
import httpx

from gangtise_openapi import ApiError, GangtiseError, gangtise

try:
    gangtise.quote.day_kline(security="600519.SH", start_date="2010-01-01", end_date="2010-01-31")
except ApiError as e:
    print(e.code, e.hint, e.trace_id)
except (GangtiseError, httpx.HTTPError) as e:
    print(type(e).__name__, e)
```

## 示例

每个公开方法都配有可独立运行的同步、异步示例脚本，便于自测：

```bash
uv run python sample/sync/quote_day_kline.py
uv run python sample/async/quote_day_kline.py
```

返回 DataFrame 的示例直接打印；文本或 dict / list 响应写成 Markdown 文件放在 `sample_outputs/`；下载类示例把文件写入 `sample_downloads/`。会修改账号数据的示例（股票池、个股笔记与云盘的写操作）默认不发请求，需先在脚本开头填好 ID 或文件路径。运行说明见 [`sample/README.md`](sample/README.md)，全部方法的参数说明见 [`sample/API_PARAMETERS.md`](sample/API_PARAMETERS.md)。

## 接口一览

13 个领域、161 个上游接口：

| 领域 | 内容 |
| :-- | :-- |
| `gangtise.auth` | 登录、鉴权状态 |
| `gangtise.lookup` | 本地查表（券商机构、会议机构） |
| `gangtise.reference` | 证券搜索（GTS 代码）、机构 / 公众号 ID 搜索、常量分类与取值、题材与板块搜索、板块成分股、指数成分股权重 |
| `gangtise.insight` | 观点（摘要列表与按 ID 取正文）、研报与研报图表、公告、纪要与帕米尔专家纪要、日程、会议线索、财报日历、投资者问答 |
| `gangtise.quote` | 日 / 分钟 K 线、实时行情、A 股个股与板块资金流向 |
| `gangtise.fundamental` | 三大报表、主营业务、估值分析、十大股东、盈利预测 |
| `gangtise.bond` | 债券资料、发行人、日行情、估值、现金流、公告、发行、评级、利率债发行计划、行权、违约 |
| `gangtise.fund` | 公募基金资料、净值、费率、基金经理、规模、持有人、资产配置与持仓、ETF 申赎清单与份额 |
| `gangtise.ai` | 一页通、投资逻辑、同业对比、业绩点评、主题跟踪、热点话题、个股看点、专家情报、管理层讨论与管理层情绪、知识库搜索等 |
| `gangtise.vault` | 个人云盘（列表、下载、上传、建文件夹、移动、复制、删除）、录音与会议记录、股票池（个人与租户池查询、增删改）、个股投资笔记、微信群消息与群文件下载 |
| `gangtise.alternative` | 经济指标（EDB）、题材画像与成分股 |
| `gangtise.indicator` | 证券级数据指标（EDE）：指标搜索、截面、时序、条件选股 |
| `gangtise.tool` | PDF 解析（提交后取结果 ZIP）、联网搜索 |

参数与 CLI 一一对应，只是写成 `snake_case`：CLI 的 `--start-date` 对应 `start_date`，`--yes` 对应 `confirm=True`。

## 许可证

MIT
