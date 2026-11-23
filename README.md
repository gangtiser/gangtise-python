# gangtise-openapi

[Gangtise OpenAPI](https://openapi.gangtise.com) 的 Python SDK。把 164 个投研数据接口封装成带完整类型签名的 Python 方法，表格类结果直接返回 pandas DataFrame。与 npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.53.0 功能对齐。

- **覆盖面**：观点（含海外媒体与投资人观点）、研报、公告、纪要与会议、行情 K 线与资金流向、指数成分权重、财务报表与估值、证券级数据指标（EDE）、债券、公募基金、AI 生成内容、专家情报与管理层情绪、个人云盘、股票池与个股笔记、微信群消息与群文件、联网搜索、PDF 解析。
- **同步与异步**两套接口，方法与参数一一对应。
- **自动处理分页与拆分**：分页列表自动翻页；全市场 K 线按工作日自动分片；多只证券自动合批。
- **计费保护**：按条计费的大批量拉取、不可逆的删除操作都要显式确认；按次计费与单次可能花费较多的接口在超时、5xx 后不自动重发（仍会自动重试的计费接口见「计费与确认」）。
- **结果完整性**：数据不完整时在结果上标 `partial` 并告警，不会把被截断的结果当作完整结果返回。
- **本地校验**：日期写法、参数取值、空列表等问题在发请求前就报错，不花积分。

## 更新日志

最近 5 个版本（完整记录见 [`CHANGELOG.md`](https://github.com/gangtiser/gangtise-python/blob/main/CHANGELOG.md)）：

### 0.5.9 - 2026-11-23
- 与 CLI **v0.53.0** 对齐，无新增接口。
- ⚠️ **代理只读新增的环境变量 `GANGTISE_PROXY`**，不再跟随 `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY` 与系统代理设置：这些设置常是为别的流量准备的，跟随它们会改变请求的出口地址。原先靠它们访问接口的，把 `GANGTISE_PROXY` 设成同一地址。
- 请求没有送到接口时（连不上、代理要求认证或不应答等），异常附一条说明该查什么（`e.__notes__`，Python 3.11+）。
- 登录失败时，同时等这次登录的其他请求不再各自重新登录；另一个进程已登录成功的，沿用它的 token。
- 修复并发时旧 token 覆盖新 token、同步客户端偶发 `AssertionError`；`repr(client.config)` 不再显示密钥与 token。

### 0.5.8 - 2026-11-22
- 与 CLI **v0.52.2** 对齐，无新增接口。
- ⚠️ **服务端口径变化**（SDK 发出的请求不变，旧版本同样受影响）：三大报表与十大股东不传 `period` / `fiscal_year` / 日期时返回**全部历史报告期**，不再是最新一期——要最新一期传 `period="latest"`；按年份或日期取直接传，不必再配 `period`；多期结果不按报告期排序，按 `endDate` 排好再用。三大报表的 `field` 写了不存在的字段名整条报 `100005`，不再补 null。
- **美股三张表一次只取一个财年**：跨多个财年时每种报告期与报表类型的组合只返回其中一年、不报错，SDK 发 `UserWarning`；多年数据按 `fiscal_year` 逐年查。
- `insight.report_image_list` 的 `start_time` / `end_time` 现在按研报发布时间筛选。
- 文档：港股 / 美股利润表与现金流量表只给 `period="latest"` 时可能多一行最近一季的单季值（`period` 为空），要累计数取 `period` 非空那行；港股非 12 月财年公司的 `fiscal_year` 按期末所在自然年算；单季报表的 `period` 标签是单季值，别与累计表按标签合并。

### 0.5.7 - 2026-11-14
- 与 CLI **v0.52.1** 对齐，无新增接口。
- **修复**：`file` / `output` 的配置目录检查按磁盘自身的大小写规则判断，区分大小写的磁盘上不再误拒只差大小写的路径；配置目录尚未创建时，经另一种写法（如 macOS 的 `/System/Volumes/Data/…`）到达同一目录的路径同样拒收。
- 文档：三大报表与十大股东按年份或日期取，要同时给 `latest` 以外的 `period`，只给一边（包括 `period="latest"`）都返回最新一期；`insight.report_image_list` 的 `start_time` / `end_time` 目前不起筛选作用。

### 0.5.6 - 2026-11-14
- 与 CLI **v0.52.0** 对齐，新增 3 个接口，共 **164 个**。
- **新增**：`insight.overseas_opinion_list`（海外观点，0.1 积分/条，最多取前 10000 条）/ `overseas_opinion_detail`（全文与译文，10 积分/条，超时不自动重发）；`reference.overseas_account_search`（海外观点账号 ID，免费）。
- 免费查询（三大报表、主营业务、十大股东、`reference` 搜索、EDB / 指标 / 研报图表搜索、股票池成分与云盘目录）成功响应却没有数据体时抛 `ApiError`，不再当作空结果返回。
- `fund.etf_pcf_components` 补码：排除同名的另一只证券要有日 K 覆盖到相应那天的证据，排除不了的行留 null（0.5.5 可能填成另一市场那只）。
- 发请求前本地检查：下载的 `output` 不能是目录；`tool.file_parse` 要求文件带 `%PDF-` 文件头；`file` / `output` 不能指向 SDK 的配置目录（存 token）。
- `fundamental.main_business` 的 `period` 此前不起作用（请求字段写错，服务端忽略），现在按所选报告期筛选。
- 文档：帕米尔纪要的 `categoryList` / `marketList` 只在按类别 / 市场筛选时完整；三大报表的 `fiscal_year` 与 `period` 要一起传；A 股报表 `period` 取 `annual` 等值、年份放 `fiscal_year`（此前写的 `"2025annual"` 服务端拒收）。

### 0.5.5 - 2026-11-07
- 与 CLI **v0.51.0** 对齐，新增 3 个接口，共 **161 个**。
- **新增**：`ai.expert_intel_list`（AI 专家情报，20 积分/条，自动翻页、额度保护，超时不自动重发）；`reference.index_weight`（指数成分股权重，免费；只有每月最后一个交易日有数，其他日期返回空结果并告警）；`vault.wechat_message_download`（群消息里的文档 / 图片 / 音频 / 视频文件，免费，按原字节保存）。
- `vault.wechat_message_list` 的 `category`：文档类取值是 `document`（0.5.4 文档写的 `documents` 会报 `100005`），新增 `audio` / `video`。
- `fund.etf_pcf_components` 补码：A / H 同名而价格定不了的行，改用该行的 `pctChange` 与日 K 的收盘价 + 涨跌幅核对，能定的不再留 null。
- **修复**（下载）：服务端文件名自带的扩展名原样保留（0.5.4 会把 `config.ini` 存成 `config.ini.txt`）；Python 3.13 上 `filename*` 解不出时改用普通 `filename`（0.5.4 存成 `<前缀>-<id>`）。

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
| `GANGTISE_PROXY` | 所在网络须经 HTTP 代理出网时设置，如 `http://proxy.example.com:8080`，带账号写成 `http://用户名:密码@主机:端口`（特殊字符按 URL 编码）。接口请求与文件下载都经它转发；只收 `http://` / `https://`，写法不对时在发请求前报 `ConfigError`，报错不显示取值 |
| `GANGTISE_TIMEOUT_MS` | 单次请求的超时（整数毫秒，1000–3600000，默认 30000）。同步 AI 生成类接口与 `ai.stock_summary_list` 另有 120 秒下限，`tool.file_parse` 与 `vault.drive_upload` 两个上传接口为 300 秒 |
| `GANGTISE_PAGE_CONCURRENCY` | 自动翻页与分片的并发数，默认 5，最大 32 |
| `GANGTISE_VERBOSE` | 设为 `1` 时输出每个请求的耗时日志 |
| `GANGTISE_TOKEN_CACHE_PATH` / `GANGTISE_TITLE_CACHE_PATH` | token 缓存与下载文件名缓存的位置，默认在 `~/.config/gangtise/` |

SDK **只读 `GANGTISE_PROXY`，不读 `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY`，也不读 macOS / Windows 的系统代理设置**：这些设置常是为别的流量设的，跟随它们会改变请求的出口地址（登记了出口 IP 的账号，出口一变就报 `999016`）。与 npm CLI 一致。证书相关的 `SSL_CERT_FILE` / `SSL_CERT_DIR` 照常生效。客户端在创建时读取配置：之后才设的 `GANGTISE_PROXY` 不会生效，要调 `gangtise.reset()`（或 `gangtise.configure(..., replace=True)`、新建客户端）。

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

- **按条计费的列表**（研报、公告、观点（含海外观点）、路演 / 调研 / 策略会 / 论坛、个股线索、专家情报、管理层情绪、热点话题等）不传 `size` 时，SDK 先拿到总条数，按 `total × 单价` 估算全量，**超过 1000 积分就报 `ValidationError`，不再往下拉**，报错里给出估算值。只要一部分就传 `size=N`；确认要全量再传 `confirm=True`。显式传的 `size` 按 `min(size, total)` 同样估算。
- **`fundamental.earning_forecast`** 按日期区间估算（工作日数 × 3 条 × 0.5 积分），超过 1000 积分同样需要 `confirm=True`。
- **不可逆的操作**——`vault.stock_pool_delete`、`vault.stock_note_delete`、`vault.drive_delete_file`、`vault.drive_delete_folder`——必须传 `confirm=True`，否则在发请求前报错。
- **不自动重发**：以下接口在超时、断连、5xx 这类结果不确定的失败后不会自动重发，避免重复扣费：
  - 按次 / 按页计费的接口（AI 生成、管理层情绪明细、题材、联网搜索、PDF 解析、全部基金接口与 10 个债券接口等）；
  - 单次可能计费超过 3000 积分的 `ai.stock_summary_list`、`fundamental.earning_forecast`；
  - 另外 14 个按量计费接口：`ai.hot_topic`、`ai.expert_intel_list`、`insight.highlight_list`、观点正文（`opinion_detail` / `foreign_opinion_detail` / `overseas_opinion_detail`，以及 `opinion_list` / `foreign_opinion_list` 传 `with_content=True`）、三个 30 积分的文档下载（`insight.summary_download` / `foreign_report_download`、`vault.my_conference_download`）、三个债券评级接口（`bond.rating_overview` / `rating_change` / `issuer_rating_change`）。

  这类失败后请先到平台核实是否已扣费，再决定是否重新调用。只有 `999999` 的 `hint` 会给出这条提示；其他 5xx（包括网关返回的 HTML 错误页、夹在 5xx 里的业务码）带的是通用提示，超时、断连抛出的是网络异常、没有 `hint`（见「错误处理」），同样要先核实。
- **仍会自动重试**：其余 30 个计费接口（21 个按条计费的列表、8 个文档下载与按指标计费的 `alternative.edb_data`）沿用默认重试：遇到 5xx、响应超时、请求发出后断连或 `999999` 时重试至多 2 次，服务端若其实已执行，每次重试都会再计费。单页最贵的是 `ai.security_clue_list`（至多 2500 积分），其次是两个管理层情绪列表与四个日程列表（至多 500），`alternative.edb_data` 一次至多 300。

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

另有一类告警只提示、不标 `partial`：SDK 只能从返回的形态推断、不能确证缺了什么，结果原样返回。例如序列首行晚于 `start_date`（上市较晚或超出账号可回溯窗口），美股三张报表跨多个财年时每种报告期只回了一年。

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
    print(type(e).__name__, e, *getattr(e, "__notes__", ()))
```

请求没有送到接口时（连不上、连接超时、代理拒绝或不应答），httpx 异常上附一条中文说明该查什么，放在 `__notes__` 里：Python 3.11+ 未捕获时随 traceback 打印，自己捕获时要读 `e.__notes__`，如上面示例的最后一行（`str(e)` 里没有它；Python 3.10 没有这条说明）。没设代理时提示检查网络与 `GANGTISE_BASE_URL`，环境里设了 `HTTPS_PROXY` 这类变量时点名它；设了 `GANGTISE_PROXY` 时说明是连不上代理、代理要求认证、代理没有接通到接口地址、代理没有应答，还是该端口没有按 HTTP 代理应答。代理要求认证（407）时 `ApiError.hint` 写明怎么带账号；下载失败的这条说明写在 `DownloadError` 的消息里。

## 示例

每个公开方法都配有可独立运行的同步、异步示例脚本，便于自测：

```bash
uv run python sample/sync/quote_day_kline.py
uv run python sample/async/quote_day_kline.py
```

返回 DataFrame 的示例直接打印；文本或 dict / list 响应写成 Markdown 文件放在 `sample_outputs/`；下载类示例把文件写入 `sample_downloads/`。会修改账号数据的示例（股票池、个股笔记与云盘的写操作）默认不发请求，需先在脚本开头填好 ID 或文件路径。运行说明见 [`sample/README.md`](sample/README.md)，全部方法的参数说明见 [`sample/API_PARAMETERS.md`](sample/API_PARAMETERS.md)。

## 接口一览

13 个领域、164 个上游接口：

| 领域 | 内容 |
| :-- | :-- |
| `gangtise.auth` | 登录、鉴权状态 |
| `gangtise.lookup` | 本地查表（券商机构、会议机构） |
| `gangtise.reference` | 证券搜索（GTS 代码）、机构 / 公众号 / 海外观点账号 ID 搜索、常量分类与取值、题材与板块搜索、板块成分股、指数成分股权重 |
| `gangtise.insight` | 观点（国内首席、海外机构、独立分析师与海外媒体 / 投资人；摘要列表与按 ID 取正文）、研报与研报图表、公告、纪要与帕米尔专家纪要、日程、会议线索、财报日历、投资者问答 |
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
