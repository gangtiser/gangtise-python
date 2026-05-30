# API Parameter Reference

本文档按当前 Python SDK wrapper 自动整理，覆盖 76 个公开 SDK 方法（对应 75 个上游 OpenAPI endpoint，另含 `auth.status` 本地状态方法）。同步与异步方法参数一致；异步调用路径为 `gangtise.async_.<domain>.<method>(...)`。

运行示例前请配置：

```bash
export GANGTISE_ACCESS_KEY=ak_xxx
export GANGTISE_SECRET_KEY=sk_xxx
```

所有表格中的 `raw` 参数默认不在示例中传入；设置为 `True` 时返回服务端原始 `data`。`Any` 类型参数通常支持单值或列表，SDK 会按接口要求转换为列表字段。

## Method Index

| Domain | Method | Sync sample | Async sample |
| --- | --- | --- | --- |
| `auth` | `login` | [auth_login.py](sync/auth_login.py) | [auth_login.py](async/auth_login.py) |
| `auth` | `status` | [auth_status.py](sync/auth_status.py) | [auth_status.py](async/auth_status.py) |
| `lookup` | `research_areas` | [lookup_research_areas.py](sync/lookup_research_areas.py) | [lookup_research_areas.py](async/lookup_research_areas.py) |
| `lookup` | `broker_orgs` | [lookup_broker_orgs.py](sync/lookup_broker_orgs.py) | [lookup_broker_orgs.py](async/lookup_broker_orgs.py) |
| `lookup` | `meeting_orgs` | [lookup_meeting_orgs.py](sync/lookup_meeting_orgs.py) | [lookup_meeting_orgs.py](async/lookup_meeting_orgs.py) |
| `lookup` | `industries` | [lookup_industries.py](sync/lookup_industries.py) | [lookup_industries.py](async/lookup_industries.py) |
| `lookup` | `regions` | [lookup_regions.py](sync/lookup_regions.py) | [lookup_regions.py](async/lookup_regions.py) |
| `lookup` | `announcement_categories` | [lookup_announcement_categories.py](sync/lookup_announcement_categories.py) | [lookup_announcement_categories.py](async/lookup_announcement_categories.py) |
| `lookup` | `industry_codes` | [lookup_industry_codes.py](sync/lookup_industry_codes.py) | [lookup_industry_codes.py](async/lookup_industry_codes.py) |
| `lookup` | `theme_ids` | [lookup_theme_ids.py](sync/lookup_theme_ids.py) | [lookup_theme_ids.py](async/lookup_theme_ids.py) |
| `reference` | `securities_search` | [reference_securities_search.py](sync/reference_securities_search.py) | [reference_securities_search.py](async/reference_securities_search.py) |
| `quote` | `day_kline` | [quote_day_kline.py](sync/quote_day_kline.py) | [quote_day_kline.py](async/quote_day_kline.py) |
| `quote` | `day_kline_hk` | [quote_day_kline_hk.py](sync/quote_day_kline_hk.py) | [quote_day_kline_hk.py](async/quote_day_kline_hk.py) |
| `quote` | `day_kline_us` | [quote_day_kline_us.py](sync/quote_day_kline_us.py) | [quote_day_kline_us.py](async/quote_day_kline_us.py) |
| `quote` | `index_day_kline` | [quote_index_day_kline.py](sync/quote_index_day_kline.py) | [quote_index_day_kline.py](async/quote_index_day_kline.py) |
| `quote` | `minute_kline` | [quote_minute_kline.py](sync/quote_minute_kline.py) | [quote_minute_kline.py](async/quote_minute_kline.py) |
| `quote` | `realtime` | [quote_realtime.py](sync/quote_realtime.py) | [quote_realtime.py](async/quote_realtime.py) |
| `insight` | `opinion_list` | [insight_opinion_list.py](sync/insight_opinion_list.py) | [insight_opinion_list.py](async/insight_opinion_list.py) |
| `insight` | `summary_list` | [insight_summary_list.py](sync/insight_summary_list.py) | [insight_summary_list.py](async/insight_summary_list.py) |
| `insight` | `roadshow_list` | [insight_roadshow_list.py](sync/insight_roadshow_list.py) | [insight_roadshow_list.py](async/insight_roadshow_list.py) |
| `insight` | `site_visit_list` | [insight_site_visit_list.py](sync/insight_site_visit_list.py) | [insight_site_visit_list.py](async/insight_site_visit_list.py) |
| `insight` | `strategy_list` | [insight_strategy_list.py](sync/insight_strategy_list.py) | [insight_strategy_list.py](async/insight_strategy_list.py) |
| `insight` | `forum_list` | [insight_forum_list.py](sync/insight_forum_list.py) | [insight_forum_list.py](async/insight_forum_list.py) |
| `insight` | `research_list` | [insight_research_list.py](sync/insight_research_list.py) | [insight_research_list.py](async/insight_research_list.py) |
| `insight` | `foreign_report_list` | [insight_foreign_report_list.py](sync/insight_foreign_report_list.py) | [insight_foreign_report_list.py](async/insight_foreign_report_list.py) |
| `insight` | `announcement_list` | [insight_announcement_list.py](sync/insight_announcement_list.py) | [insight_announcement_list.py](async/insight_announcement_list.py) |
| `insight` | `announcement_hk_list` | [insight_announcement_hk_list.py](sync/insight_announcement_hk_list.py) | [insight_announcement_hk_list.py](async/insight_announcement_hk_list.py) |
| `insight` | `foreign_opinion_list` | [insight_foreign_opinion_list.py](sync/insight_foreign_opinion_list.py) | [insight_foreign_opinion_list.py](async/insight_foreign_opinion_list.py) |
| `insight` | `independent_opinion_list` | [insight_independent_opinion_list.py](sync/insight_independent_opinion_list.py) | [insight_independent_opinion_list.py](async/insight_independent_opinion_list.py) |
| `insight` | `summary_download` | [insight_summary_download.py](sync/insight_summary_download.py) | [insight_summary_download.py](async/insight_summary_download.py) |
| `insight` | `research_download` | [insight_research_download.py](sync/insight_research_download.py) | [insight_research_download.py](async/insight_research_download.py) |
| `insight` | `foreign_report_download` | [insight_foreign_report_download.py](sync/insight_foreign_report_download.py) | [insight_foreign_report_download.py](async/insight_foreign_report_download.py) |
| `insight` | `announcement_download` | [insight_announcement_download.py](sync/insight_announcement_download.py) | [insight_announcement_download.py](async/insight_announcement_download.py) |
| `insight` | `announcement_hk_download` | [insight_announcement_hk_download.py](sync/insight_announcement_hk_download.py) | [insight_announcement_hk_download.py](async/insight_announcement_hk_download.py) |
| `insight` | `independent_opinion_download` | [insight_independent_opinion_download.py](sync/insight_independent_opinion_download.py) | [insight_independent_opinion_download.py](async/insight_independent_opinion_download.py) |
| `fundamental` | `income_statement` | [fundamental_income_statement.py](sync/fundamental_income_statement.py) | [fundamental_income_statement.py](async/fundamental_income_statement.py) |
| `fundamental` | `income_statement_quarterly` | [fundamental_income_statement_quarterly.py](sync/fundamental_income_statement_quarterly.py) | [fundamental_income_statement_quarterly.py](async/fundamental_income_statement_quarterly.py) |
| `fundamental` | `balance_sheet` | [fundamental_balance_sheet.py](sync/fundamental_balance_sheet.py) | [fundamental_balance_sheet.py](async/fundamental_balance_sheet.py) |
| `fundamental` | `cash_flow` | [fundamental_cash_flow.py](sync/fundamental_cash_flow.py) | [fundamental_cash_flow.py](async/fundamental_cash_flow.py) |
| `fundamental` | `cash_flow_quarterly` | [fundamental_cash_flow_quarterly.py](sync/fundamental_cash_flow_quarterly.py) | [fundamental_cash_flow_quarterly.py](async/fundamental_cash_flow_quarterly.py) |
| `fundamental` | `income_statement_hk` | [fundamental_income_statement_hk.py](sync/fundamental_income_statement_hk.py) | [fundamental_income_statement_hk.py](async/fundamental_income_statement_hk.py) |
| `fundamental` | `balance_sheet_hk` | [fundamental_balance_sheet_hk.py](sync/fundamental_balance_sheet_hk.py) | [fundamental_balance_sheet_hk.py](async/fundamental_balance_sheet_hk.py) |
| `fundamental` | `cash_flow_hk` | [fundamental_cash_flow_hk.py](sync/fundamental_cash_flow_hk.py) | [fundamental_cash_flow_hk.py](async/fundamental_cash_flow_hk.py) |
| `fundamental` | `main_business` | [fundamental_main_business.py](sync/fundamental_main_business.py) | [fundamental_main_business.py](async/fundamental_main_business.py) |
| `fundamental` | `valuation_analysis` | [fundamental_valuation_analysis.py](sync/fundamental_valuation_analysis.py) | [fundamental_valuation_analysis.py](async/fundamental_valuation_analysis.py) |
| `fundamental` | `top_holders` | [fundamental_top_holders.py](sync/fundamental_top_holders.py) | [fundamental_top_holders.py](async/fundamental_top_holders.py) |
| `fundamental` | `earning_forecast` | [fundamental_earning_forecast.py](sync/fundamental_earning_forecast.py) | [fundamental_earning_forecast.py](async/fundamental_earning_forecast.py) |
| `ai` | `knowledge_batch` | [ai_knowledge_batch.py](sync/ai_knowledge_batch.py) | [ai_knowledge_batch.py](async/ai_knowledge_batch.py) |
| `ai` | `security_clue_list` | [ai_security_clue_list.py](sync/ai_security_clue_list.py) | [ai_security_clue_list.py](async/ai_security_clue_list.py) |
| `ai` | `one_pager` | [ai_one_pager.py](sync/ai_one_pager.py) | [ai_one_pager.py](async/ai_one_pager.py) |
| `ai` | `investment_logic` | [ai_investment_logic.py](sync/ai_investment_logic.py) | [ai_investment_logic.py](async/ai_investment_logic.py) |
| `ai` | `peer_comparison` | [ai_peer_comparison.py](sync/ai_peer_comparison.py) | [ai_peer_comparison.py](async/ai_peer_comparison.py) |
| `ai` | `research_outline` | [ai_research_outline.py](sync/ai_research_outline.py) | [ai_research_outline.py](async/ai_research_outline.py) |
| `ai` | `theme_tracking` | [ai_theme_tracking.py](sync/ai_theme_tracking.py) | [ai_theme_tracking.py](async/ai_theme_tracking.py) |
| `ai` | `hot_topic` | [ai_hot_topic.py](sync/ai_hot_topic.py) | [ai_hot_topic.py](async/ai_hot_topic.py) |
| `ai` | `management_discuss_announcement` | [ai_management_discuss_announcement.py](sync/ai_management_discuss_announcement.py) | [ai_management_discuss_announcement.py](async/ai_management_discuss_announcement.py) |
| `ai` | `management_discuss_earnings_call` | [ai_management_discuss_earnings_call.py](sync/ai_management_discuss_earnings_call.py) | [ai_management_discuss_earnings_call.py](async/ai_management_discuss_earnings_call.py) |
| `ai` | `earnings_review` | [ai_earnings_review.py](sync/ai_earnings_review.py) | [ai_earnings_review.py](async/ai_earnings_review.py) |
| `ai` | `earnings_review_check` | [ai_earnings_review_check.py](sync/ai_earnings_review_check.py) | [ai_earnings_review_check.py](async/ai_earnings_review_check.py) |
| `ai` | `viewpoint_debate` | [ai_viewpoint_debate.py](sync/ai_viewpoint_debate.py) | [ai_viewpoint_debate.py](async/ai_viewpoint_debate.py) |
| `ai` | `viewpoint_debate_check` | [ai_viewpoint_debate_check.py](sync/ai_viewpoint_debate_check.py) | [ai_viewpoint_debate_check.py](async/ai_viewpoint_debate_check.py) |
| `ai` | `knowledge_resource_download` | [ai_knowledge_resource_download.py](sync/ai_knowledge_resource_download.py) | [ai_knowledge_resource_download.py](async/ai_knowledge_resource_download.py) |
| `vault` | `drive_list` | [vault_drive_list.py](sync/vault_drive_list.py) | [vault_drive_list.py](async/vault_drive_list.py) |
| `vault` | `record_list` | [vault_record_list.py](sync/vault_record_list.py) | [vault_record_list.py](async/vault_record_list.py) |
| `vault` | `my_conference_list` | [vault_my_conference_list.py](sync/vault_my_conference_list.py) | [vault_my_conference_list.py](async/vault_my_conference_list.py) |
| `vault` | `wechat_message_list` | [vault_wechat_message_list.py](sync/vault_wechat_message_list.py) | [vault_wechat_message_list.py](async/vault_wechat_message_list.py) |
| `vault` | `wechat_chatroom_list` | [vault_wechat_chatroom_list.py](sync/vault_wechat_chatroom_list.py) | [vault_wechat_chatroom_list.py](async/vault_wechat_chatroom_list.py) |
| `vault` | `stock_pool_list` | [vault_stock_pool_list.py](sync/vault_stock_pool_list.py) | [vault_stock_pool_list.py](async/vault_stock_pool_list.py) |
| `vault` | `stock_pool_stocks` | [vault_stock_pool_stocks.py](sync/vault_stock_pool_stocks.py) | [vault_stock_pool_stocks.py](async/vault_stock_pool_stocks.py) |
| `vault` | `drive_download` | [vault_drive_download.py](sync/vault_drive_download.py) | [vault_drive_download.py](async/vault_drive_download.py) |
| `vault` | `record_download` | [vault_record_download.py](sync/vault_record_download.py) | [vault_record_download.py](async/vault_record_download.py) |
| `vault` | `my_conference_download` | [vault_my_conference_download.py](sync/vault_my_conference_download.py) | [vault_my_conference_download.py](async/vault_my_conference_download.py) |
| `alternative` | `edb_search` | [alternative_edb_search.py](sync/alternative_edb_search.py) | [alternative_edb_search.py](async/alternative_edb_search.py) |
| `alternative` | `edb_data` | [alternative_edb_data.py](sync/alternative_edb_data.py) | [alternative_edb_data.py](async/alternative_edb_data.py) |
| `alternative` | `concept_info` | [alternative_concept_info.py](sync/alternative_concept_info.py) | [alternative_concept_info.py](async/alternative_concept_info.py) |
| `alternative` | `concept_securities` | [alternative_concept_securities.py](sync/alternative_concept_securities.py) | [alternative_concept_securities.py](async/alternative_concept_securities.py) |

## Authentication (`gangtise.auth`)

### `auth.login`

- Endpoint: `auth.login` `POST /application/auth/oauth/open/loginV2` - Get access token
- Sync sample: `sample/sync/auth_login.py`
- Async sample: `sample/async/auth_login.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| - | - | - | - | - | 无参数。 |

### `auth.status`

- Endpoint: 本地方法；读取当前 token/cache 状态，不发起 HTTP API 请求。
- Sync sample: `sample/sync/auth_status.py`
- Async sample: `sample/async/auth_status.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| - | - | - | - | - | 无参数。 |


## Local lookup tables (`gangtise.lookup`)

### `lookup.research_areas`

- Endpoint: `lookup.research-areas.list` `GET /guide/research-area-local` - List research areas from local docs
- Sync sample: `sample/sync/lookup_research_areas.py`
- Async sample: `sample/async/lookup_research_areas.py`
- Return annotation: `pd.DataFrame | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `lookup.broker_orgs`

- Endpoint: `lookup.broker-orgs.list` `GET /guide/broker-orgs-local` - List broker orgs from local docs
- Sync sample: `sample/sync/lookup_broker_orgs.py`
- Async sample: `sample/async/lookup_broker_orgs.py`
- Return annotation: `pd.DataFrame | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `lookup.meeting_orgs`

- Endpoint: `lookup.meeting-orgs.list` `GET /guide/meeting-orgs-local` - List meeting orgs from local docs
- Sync sample: `sample/sync/lookup_meeting_orgs.py`
- Async sample: `sample/async/lookup_meeting_orgs.py`
- Return annotation: `pd.DataFrame | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `lookup.industries`

- Endpoint: `lookup.industries.list` `GET /guide/industries-local` - List industries from local docs
- Sync sample: `sample/sync/lookup_industries.py`
- Async sample: `sample/async/lookup_industries.py`
- Return annotation: `pd.DataFrame | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `lookup.regions`

- Endpoint: `lookup.regions.list` `GET /guide/regions-local` - List regions from local docs
- Sync sample: `sample/sync/lookup_regions.py`
- Async sample: `sample/async/lookup_regions.py`
- Return annotation: `pd.DataFrame | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `lookup.announcement_categories`

- Endpoint: `lookup.announcement-categories.list` `GET /guide/announcement-categories-local` - List announcement categories from local docs
- Sync sample: `sample/sync/lookup_announcement_categories.py`
- Async sample: `sample/async/lookup_announcement_categories.py`
- Return annotation: `pd.DataFrame | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `lookup.industry_codes`

- Endpoint: `lookup.industry-codes.list` `GET /guide/industry-codes-local` - List Shenwan industry codes from local docs
- Sync sample: `sample/sync/lookup_industry_codes.py`
- Async sample: `sample/async/lookup_industry_codes.py`
- Return annotation: `pd.DataFrame | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `lookup.theme_ids`

- Endpoint: `lookup.theme-ids.list` `GET /guide/theme-ids-local` - List theme IDs from local docs
- Sync sample: `sample/sync/lookup_theme_ids.py`
- Async sample: `sample/async/lookup_theme_ids.py`
- Return annotation: `pd.DataFrame | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |


## Reference data (`gangtise.reference`)

### `reference.securities_search`

- Endpoint: `reference.securities-search` `POST /application/open-reference/securities/search` - Search GTS codes (securities)
- Sync sample: `sample/sync/reference_securities_search.py`
- Async sample: `sample/async/reference_securities_search.py`
- Return annotation: `pd.DataFrame | dict[str, Any] | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"平安银行"` | 搜索关键词。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `top` | `int` | 否 | `10` | `3` | 每个查询返回的最大候选数。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |


## Market quotes (`gangtise.quote`)

### `quote.day_kline`

- Endpoint: `quote.day-kline` `POST /application/open-quote/kline/daily` - Query A-share historical daily kline (SH/SZ/BJ)
- Sync sample: `sample/sync/quote_day_kline.py`
- Async sample: `sample/async/quote_day_kline.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"AAPL.O"` | 美股证券代码或代码列表，例如 AAPL.O；部分行情接口也支持 all。 |
| `start_date` | `str | dt.date | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | dt.date | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `limit` | `int | None` | 否 | `None` | `10` | 返回条数上限。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.day_kline_hk`

- Endpoint: `quote.day-kline-hk` `POST /application/open-quote/kline-hk/daily` - Query HK stock historical daily kline (HK)
- Sync sample: `sample/sync/quote_day_kline_hk.py`
- Async sample: `sample/async/quote_day_kline_hk.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `start_date` | `str | dt.date | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | dt.date | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `limit` | `int | None` | 否 | `None` | `10` | 返回条数上限。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.day_kline_us`

- Endpoint: `quote.day-kline-us` `POST /application/open-quote/kline-us/daily` - Query US stock historical daily kline (NYSE/NASDAQ/AMEX)
- Sync sample: `sample/sync/quote_day_kline_us.py`
- Async sample: `sample/async/quote_day_kline_us.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `start_date` | `str | dt.date | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | dt.date | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `limit` | `int | None` | 否 | `None` | `10` | 返回条数上限。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.index_day_kline`

- Endpoint: `quote.index-day-kline` `POST /application/open-quote/index/kline/daily` - Query SH/SZ/BJ index daily kline
- Sync sample: `sample/sync/quote_index_day_kline.py`
- Async sample: `sample/async/quote_index_day_kline.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `start_date` | `str | dt.date | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | dt.date | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `limit` | `int | None` | 否 | `None` | `10` | 返回条数上限。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.minute_kline`

- Endpoint: `quote.minute-kline` `POST /application/open-quote/kline/minute` - Query A-share minute kline (SH/SZ/BJ)
- Sync sample: `sample/sync/quote_minute_kline.py`
- Async sample: `sample/async/quote_minute_kline.py`
- Return annotation: `pd.DataFrame | dict[str, Any] | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security` | `str` | 是 | - | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `limit` | `int | None` | 否 | `None` | `10` | 返回条数上限。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.realtime`

- Endpoint: `quote.realtime` `POST /application/open-quote/quote/realtime` - Query realtime quote snapshot (A-share / HK / US)
- Sync sample: `sample/sync/quote_realtime.py`
- Async sample: `sample/async/quote_realtime.py`
- Return annotation: `pd.DataFrame | dict[str, Any] | list[Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |


## Research insight (`gangtise.insight`)

### `insight.opinion_list`

- Endpoint: `insight.opinion.list` `POST /application/open-insight/chief-opinion/getList` - List domestic institution chief opinions, paginated max size 50
- Sync sample: `sample/sync/insight_opinion_list.py`
- Async sample: `sample/async/insight_opinion_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `rank_type` | `int` | 否 | `1` | `0` | 排序方式代码。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `chief` | `Any` | 否 | `None` | `None` | 首席分析师过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `broker` | `Any` | 否 | `None` | `None` | 券商/机构过滤，支持单值或列表。 |
| `industry` | `Any` | 否 | `None` | `1` | 行业 ID/代码过滤，支持单值或列表。 |
| `concept` | `Any` | 否 | `None` | `None` | 概念/主题过滤，支持单值或列表。 |
| `llm_tag` | `Any` | 否 | `None` | `None` | LLM 标签过滤，支持单值或列表。 |
| `source` | `Any` | 否 | `None` | `"research"` | 来源过滤，支持单值或列表；ai.security_clue_list 中请求字段为 source。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.summary_list`

- Endpoint: `insight.summary.list` `POST /application/open-insight/summary/v2/getList` - List summaries, paginated max size 50
- Sync sample: `sample/sync/insight_summary_list.py`
- Async sample: `sample/async/insight_summary_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `0` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `0` | 排序方式代码。 |
| `source` | `Any` | 否 | `None` | `"research"` | 来源过滤，支持单值或列表；ai.security_clue_list 中请求字段为 source。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `market` | `Any` | 否 | `None` | `"SH"` | 市场过滤，例如 SH、SZ、HK、US。 |
| `participant_role` | `Any` | 否 | `None` | `None` | 参与方角色过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.roadshow_list`

- Endpoint: `insight.roadshow.list` `POST /application/open-insight/schedule/roadshow/getList` - List roadshows, paginated max size 50
- Sync sample: `sample/sync/insight_roadshow_list.py`
- Async sample: `sample/async/insight_roadshow_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `market` | `Any` | 否 | `None` | `"SH"` | 市场过滤，例如 SH、SZ、HK、US。 |
| `participant_role` | `Any` | 否 | `None` | `None` | 参与方角色过滤，支持单值或列表。 |
| `broker_type` | `Any` | 否 | `None` | `None` | 券商类型过滤，支持单值或列表。 |
| `object_` | `Any` | 否 | `None` | `"company"` | 对象类型过滤；Python 参数名 object_ 会映射为 object。 |
| `permission` | `Any` | 否 | `None` | `1` | 权限/可见性过滤。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.site_visit_list`

- Endpoint: `insight.site-visit.list` `POST /application/open-insight/schedule/site-visit/getList` - List site visits, paginated max size 50
- Sync sample: `sample/sync/insight_site_visit_list.py`
- Async sample: `sample/async/insight_site_visit_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `market` | `Any` | 否 | `None` | `"SH"` | 市场过滤，例如 SH、SZ、HK、US。 |
| `participant_role` | `Any` | 否 | `None` | `None` | 参与方角色过滤，支持单值或列表。 |
| `broker_type` | `Any` | 否 | `None` | `None` | 券商类型过滤，支持单值或列表。 |
| `object_` | `Any` | 否 | `None` | `"company"` | 对象类型过滤；Python 参数名 object_ 会映射为 object。 |
| `permission` | `Any` | 否 | `None` | `1` | 权限/可见性过滤。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.strategy_list`

- Endpoint: `insight.strategy.list` `POST /application/open-insight/schedule/strategy-meeting/getList` - List strategy meetings, paginated max size 50
- Sync sample: `sample/sync/insight_strategy_list.py`
- Async sample: `sample/async/insight_strategy_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `market` | `Any` | 否 | `None` | `"SH"` | 市场过滤，例如 SH、SZ、HK、US。 |
| `participant_role` | `Any` | 否 | `None` | `None` | 参与方角色过滤，支持单值或列表。 |
| `broker_type` | `Any` | 否 | `None` | `None` | 券商类型过滤，支持单值或列表。 |
| `object_` | `Any` | 否 | `None` | `"company"` | 对象类型过滤；Python 参数名 object_ 会映射为 object。 |
| `permission` | `Any` | 否 | `None` | `1` | 权限/可见性过滤。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.forum_list`

- Endpoint: `insight.forum.list` `POST /application/open-insight/schedule/forum/getList` - List forums, paginated max size 50
- Sync sample: `sample/sync/insight_forum_list.py`
- Async sample: `sample/async/insight_forum_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `market` | `Any` | 否 | `None` | `"SH"` | 市场过滤，例如 SH、SZ、HK、US。 |
| `participant_role` | `Any` | 否 | `None` | `None` | 参与方角色过滤，支持单值或列表。 |
| `broker_type` | `Any` | 否 | `None` | `None` | 券商类型过滤，支持单值或列表。 |
| `object_` | `Any` | 否 | `None` | `"company"` | 对象类型过滤；Python 参数名 object_ 会映射为 object。 |
| `permission` | `Any` | 否 | `None` | `1` | 权限/可见性过滤。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.research_list`

- Endpoint: `insight.research.list` `POST /application/open-insight/broker-report/getList` - List broker research reports, paginated max size 50
- Sync sample: `sample/sync/insight_research_list.py`
- Async sample: `sample/async/insight_research_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `0` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `0` | 排序方式代码。 |
| `broker` | `Any` | 否 | `None` | `None` | 券商/机构过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `industry` | `Any` | 否 | `None` | `1` | 行业 ID/代码过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `llm_tag` | `Any` | 否 | `None` | `None` | LLM 标签过滤，支持单值或列表。 |
| `rating` | `Any` | 否 | `None` | `None` | 评级过滤，支持单值或列表。 |
| `rating_change` | `Any` | 否 | `None` | `None` | 评级变动过滤，支持单值或列表。 |
| `min_pages` | `int | None` | 否 | `None` | `5` | 研报最小页数过滤。 |
| `max_pages` | `int | None` | 否 | `None` | `50` | 研报最大页数过滤。 |
| `source` | `Any` | 否 | `None` | `"research"` | 来源过滤，支持单值或列表；ai.security_clue_list 中请求字段为 source。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.foreign_report_list`

- Endpoint: `insight.foreign-report.list` `POST /application/open-insight/foreign-report/getList` - List foreign reports, paginated max size 50
- Sync sample: `sample/sync/insight_foreign_report_list.py`
- Async sample: `sample/async/insight_foreign_report_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `0` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `0` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `region` | `Any` | 否 | `None` | `"US"` | 区域过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `industry` | `Any` | 否 | `None` | `1` | 行业 ID/代码过滤，支持单值或列表。 |
| `broker` | `Any` | 否 | `None` | `None` | 券商/机构过滤，支持单值或列表。 |
| `llm_tag` | `Any` | 否 | `None` | `None` | LLM 标签过滤，支持单值或列表。 |
| `rating` | `Any` | 否 | `None` | `None` | 评级过滤，支持单值或列表。 |
| `rating_change` | `Any` | 否 | `None` | `None` | 评级变动过滤，支持单值或列表。 |
| `min_pages` | `int | None` | 否 | `None` | `5` | 研报最小页数过滤。 |
| `max_pages` | `int | None` | 否 | `None` | `50` | 研报最大页数过滤。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.announcement_list`

- Endpoint: `insight.announcement.list` `POST /application/open-insight/announcement/getList` - List A-share announcements, paginated max size 50
- Sync sample: `sample/sync/insight_announcement_list.py`
- Async sample: `sample/async/insight_announcement_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `int | str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `int | str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `0` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `0` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `announcement_type` | `Any` | 否 | `None` | `None` | 公告类型过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.announcement_hk_list`

- Endpoint: `insight.announcement-hk.list` `POST /application/open-insight/announcement-hk/getList` - List HK announcements, paginated max size 50
- Sync sample: `sample/sync/insight_announcement_hk_list.py`
- Async sample: `sample/async/insight_announcement_hk_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `0` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `0` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `announcement_type` | `Any` | 否 | `None` | `None` | 公告类型过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.foreign_opinion_list`

- Endpoint: `insight.foreign-opinion.list` `POST /application/open-insight/foreign-opinion/getList` - List foreign institution opinions, paginated max size 50
- Sync sample: `sample/sync/insight_foreign_opinion_list.py`
- Async sample: `sample/async/insight_foreign_opinion_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `rank_type` | `int` | 否 | `1` | `0` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `region` | `Any` | 否 | `None` | `"US"` | 区域过滤，支持单值或列表。 |
| `industry` | `Any` | 否 | `None` | `1` | 行业 ID/代码过滤，支持单值或列表。 |
| `broker` | `Any` | 否 | `None` | `None` | 券商/机构过滤，支持单值或列表。 |
| `rating` | `Any` | 否 | `None` | `None` | 评级过滤，支持单值或列表。 |
| `rating_change` | `Any` | 否 | `None` | `None` | 评级变动过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.independent_opinion_list`

- Endpoint: `insight.independent-opinion.list` `POST /application/open-insight/independent-opinion/getList` - List foreign independent analyst opinions, paginated max size 50
- Sync sample: `sample/sync/insight_independent_opinion_list.py`
- Async sample: `sample/async/insight_independent_opinion_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `rank_type` | `int` | 否 | `1` | `0` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `industry` | `Any` | 否 | `None` | `1` | 行业 ID/代码过滤，支持单值或列表。 |
| `rating` | `Any` | 否 | `None` | `None` | 评级过滤，支持单值或列表。 |
| `rating_change` | `Any` | 否 | `None` | `None` | 评级变动过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.summary_download`

- Endpoint: `insight.summary.download` `GET /application/open-insight/summary/v2/download/file` - Download summary file
- Sync sample: `sample/sync/insight_summary_download.py`
- Async sample: `sample/async/insight_summary_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `summary_id` | `str` | 是 | - | `"<summaryId>"` | 纪要 ID，通常来自 insight.summary_list 返回结果。 |
| `file_type` | `int | None` | 否 | `None` | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |

### `insight.research_download`

- Endpoint: `insight.research.download` `GET /application/open-insight/broker-report/download/file` - Download broker research report
- Sync sample: `sample/sync/insight_research_download.py`
- Async sample: `sample/async/insight_research_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `report_id` | `str` | 是 | - | `"<reportId>"` | 研报 ID，通常来自 research/foreign_report 列表接口。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |

### `insight.foreign_report_download`

- Endpoint: `insight.foreign-report.download` `GET /application/open-insight/foreign-report/download/file` - Download foreign report
- Sync sample: `sample/sync/insight_foreign_report_download.py`
- Async sample: `sample/async/insight_foreign_report_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `report_id` | `str` | 是 | - | `"<reportId>"` | 研报 ID，通常来自 research/foreign_report 列表接口。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |

### `insight.announcement_download`

- Endpoint: `insight.announcement.download` `GET /application/open-insight/announcement/download/file` - Download A-share announcement file
- Sync sample: `sample/sync/insight_announcement_download.py`
- Async sample: `sample/async/insight_announcement_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `announcement_id` | `str` | 是 | - | `"<announcementId>"` | 公告 ID，通常来自 announcement 列表接口。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |

### `insight.announcement_hk_download`

- Endpoint: `insight.announcement-hk.download` `GET /application/open-insight/announcement-hk/download/file` - Download HK announcement file
- Sync sample: `sample/sync/insight_announcement_hk_download.py`
- Async sample: `sample/async/insight_announcement_hk_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `announcement_id` | `str` | 是 | - | `"<announcementId>"` | 公告 ID，通常来自 announcement 列表接口。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |

### `insight.independent_opinion_download`

- Endpoint: `insight.independent-opinion.download` `GET /application/open-insight/independent-opinion/download/file` - Download foreign independent opinion file
- Sync sample: `sample/sync/insight_independent_opinion_download.py`
- Async sample: `sample/async/insight_independent_opinion_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `independent_opinion_id` | `str` | 是 | - | `"<independentOpinionId>"` | 独立观点 ID，通常来自 independent_opinion_list。 |
| `file_type` | `int` | 是 | - | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |


## Fundamental data (`gangtise.fundamental`)

### `fundamental.income_statement`

- Endpoint: `fundamental.income-statement` `POST /application/open-fundamental/financial-report/income-statement/accumulated` - Query A-share income statement (accumulated)
- Sync sample: `sample/sync/fundamental_income_statement.py`
- Async sample: `sample/async/fundamental_income_statement.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报告类型过滤，支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.income_statement_quarterly`

- Endpoint: `fundamental.income-statement-quarterly` `POST /application/open-fundamental/financial-report/income-statement/quarterly` - Query A-share income statement (quarterly)
- Sync sample: `sample/sync/fundamental_income_statement_quarterly.py`
- Async sample: `sample/async/fundamental_income_statement_quarterly.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报告类型过滤，支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.balance_sheet`

- Endpoint: `fundamental.balance-sheet` `POST /application/open-fundamental/financial-report/balance-sheet/accumulated` - Query A-share balance sheet (accumulated)
- Sync sample: `sample/sync/fundamental_balance_sheet.py`
- Async sample: `sample/async/fundamental_balance_sheet.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报告类型过滤，支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.cash_flow`

- Endpoint: `fundamental.cash-flow` `POST /application/open-fundamental/financial-report/cash-flow-statement/accumulated` - Query A-share cash flow statement (accumulated)
- Sync sample: `sample/sync/fundamental_cash_flow.py`
- Async sample: `sample/async/fundamental_cash_flow.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报告类型过滤，支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.cash_flow_quarterly`

- Endpoint: `fundamental.cash-flow-quarterly` `POST /application/open-fundamental/financial-report/cash-flow-statement/quarterly` - Query A-share cash flow statement (quarterly)
- Sync sample: `sample/sync/fundamental_cash_flow_quarterly.py`
- Async sample: `sample/async/fundamental_cash_flow_quarterly.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报告类型过滤，支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.income_statement_hk`

- Endpoint: `fundamental.income-statement-hk` `POST /application/open-fundamental/financial-report/income-statement/hk` - Query HK income statement (China GAAP)
- Sync sample: `sample/sync/fundamental_income_statement_hk.py`
- Async sample: `sample/async/fundamental_income_statement_hk.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报告类型过滤，支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.balance_sheet_hk`

- Endpoint: `fundamental.balance-sheet-hk` `POST /application/open-fundamental/financial-report/balance-sheet/hk` - Query HK balance sheet (China GAAP)
- Sync sample: `sample/sync/fundamental_balance_sheet_hk.py`
- Async sample: `sample/async/fundamental_balance_sheet_hk.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报告类型过滤，支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.cash_flow_hk`

- Endpoint: `fundamental.cash-flow-hk` `POST /application/open-fundamental/financial-report/cash-flow-statement/hk` - Query HK cash flow statement (China GAAP)
- Sync sample: `sample/sync/fundamental_cash_flow_hk.py`
- Async sample: `sample/async/fundamental_cash_flow_hk.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报告类型过滤，支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.main_business`

- Endpoint: `fundamental.main-business` `POST /application/open-fundamental/main-business` - Query main business composition
- Sync sample: `sample/sync/fundamental_main_business.py`
- Async sample: `sample/async/fundamental_main_business.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `breakdown` | `str` | 否 | `'product'` | `"product"` | 主营构成维度，例如 product 或 industry。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.valuation_analysis`

- Endpoint: `fundamental.valuation-analysis` `POST /application/open-fundamental/valuation-analysis` - Query valuation analysis
- Sync sample: `sample/sync/fundamental_valuation_analysis.py`
- Async sample: `sample/async/fundamental_valuation_analysis.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `indicator` | `str` | 是 | - | `"pe_ttm"` | 估值指标名，例如 pe_ttm。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `limit` | `int | None` | 否 | `None` | `10` | 返回条数上限。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `skip_null` | `bool` | 否 | `False` | `True` | valuation_analysis 是否过滤 value/percentileRank 为空的行。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.top_holders`

- Endpoint: `fundamental.top-holders` `POST /application/open-fundamental/capital-structure/top-holders` - Query top holders (top10 / top10 float)
- Sync sample: `sample/sync/fundamental_top_holders.py`
- Async sample: `sample/async/fundamental_top_holders.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `holder_type` | `str` | 是 | - | `"top10"` | 股东类型，例如 top10 或 top10Float。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.earning_forecast`

- Endpoint: `fundamental.earning-forecast` `POST /application/open-fundamental/earning-forecast` - Query earning forecast (consensus estimates)
- Sync sample: `sample/sync/fundamental_earning_forecast.py`
- Async sample: `sample/async/fundamental_earning_forecast.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `consensus` | `Any` | 否 | `None` | `None` | 一致预期类型过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |


## AI outputs (`gangtise.ai`)

### `ai.knowledge_batch`

- Endpoint: `ai.knowledge-batch` `POST /application/open-data/ai/search/knowledge/batch` - Batch knowledge search
- Sync sample: `sample/sync/ai_knowledge_batch.py`
- Async sample: `sample/async/ai_knowledge_batch.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `query` | `Any` | 是 | - | `"贵州茅台"` | 知识库检索问题，支持字符串或列表。 |
| `top` | `int` | 否 | `10` | `3` | 每个查询返回的最大候选数。 |
| `resource_type` | `Any` | 否 | `None` | `1` | 知识资源类型代码。 |
| `knowledge_name` | `Any` | 否 | `None` | `None` | 知识库名称过滤，支持单值或列表。 |
| `start_time` | `int | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `int | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.security_clue_list`

- Endpoint: `ai.security-clue.list` `POST /application/open-ai/security-clue/getList` - List security clues, paginated max size 500
- Sync sample: `sample/sync/ai_security_clue_list.py`
- Async sample: `sample/async/ai_security_clue_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `start_time` | `str` | 是 | - | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str` | 是 | - | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `query_mode` | `str` | 是 | - | `"bySecurity"` | 线索查询模式，例如 bySecurity。 |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `gts_code` | `Any` | 否 | `None` | `"000001.SZ"` | GTS 证券代码或代码列表。 |
| `source` | `Any` | 否 | `None` | `"research"` | 来源过滤，支持单值或列表；ai.security_clue_list 中请求字段为 source。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.one_pager`

- Endpoint: `ai.one-pager` `POST /application/open-ai/agent/one-pager` - Generate one pager
- Sync sample: `sample/sync/ai_one_pager.py`
- Async sample: `sample/async/ai_one_pager.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.investment_logic`

- Endpoint: `ai.investment-logic` `POST /application/open-ai/agent/investment-logic` - Generate investment logic
- Sync sample: `sample/sync/ai_investment_logic.py`
- Async sample: `sample/async/ai_investment_logic.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.peer_comparison`

- Endpoint: `ai.peer-comparison` `POST /application/open-ai/agent/peer-comparison` - Generate peer comparison
- Sync sample: `sample/sync/ai_peer_comparison.py`
- Async sample: `sample/async/ai_peer_comparison.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.research_outline`

- Endpoint: `ai.research-outline` `POST /application/open-ai/agent/research-outline` - Get company research outline
- Sync sample: `sample/sync/ai_research_outline.py`
- Async sample: `sample/async/ai_research_outline.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.theme_tracking`

- Endpoint: `ai.theme-tracking` `POST /application/open-ai/agent/theme-tracking` - Get theme tracking daily report
- Sync sample: `sample/sync/ai_theme_tracking.py`
- Async sample: `sample/async/ai_theme_tracking.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `theme_id` | `str` | 是 | - | `"121000342"` | 主题 ID，可通过 lookup.theme_ids 查询。 |
| `date` | `str` | 是 | - | `"2026-05-28"` | 业务日期，格式通常为 YYYY-MM-DD。 |
| `type_` | `Any` | 否 | `None` | `"news"` | 类型过滤；Python 参数名 type_ 会映射为 type。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.hot_topic`

- Endpoint: `ai.hot-topic` `POST /application/open-ai/hot-topic/getList` - List hot topic reports, paginated max size 20
- Sync sample: `sample/sync/ai_hot_topic.py`
- Async sample: `sample/async/ai_hot_topic.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_date` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `with_related_securities` | `bool` | 否 | `True` | `True` | 热点主题是否返回关联证券。 |
| `with_close_reading` | `bool` | 否 | `True` | `True` | 热点主题是否返回精读内容。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.management_discuss_announcement`

- Endpoint: `ai.management-discuss-announcement` `POST /application/open-ai/management-discuss/from-announcement` - Management discussion from financial reports (half-year/annual)
- Sync sample: `sample/sync/ai_management_discuss_announcement.py`
- Async sample: `sample/async/ai_management_discuss_announcement.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `report_date` | `str` | 是 | - | `"2025-12-31"` | 报告期日期，例如 2025-12-31。 |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `dimension` | `str` | 是 | - | `"all"` | 管理层讨论维度，例如 all 或 businessOperation。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.management_discuss_earnings_call`

- Endpoint: `ai.management-discuss-earnings-call` `POST /application/open-ai/management-discuss/from-earningsCall` - Management discussion from earnings calls
- Sync sample: `sample/sync/ai_management_discuss_earnings_call.py`
- Async sample: `sample/async/ai_management_discuss_earnings_call.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `report_date` | `str` | 是 | - | `"2025-12-31"` | 报告期日期，例如 2025-12-31。 |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `dimension` | `str` | 是 | - | `"all"` | 管理层讨论维度，例如 all 或 businessOperation。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.earnings_review`

- Endpoint: `ai.earnings-review.get-id` `POST /application/open-ai/agent/earnings-review-getid` - Get earnings review ID<br>`ai.earnings-review.get-content` `POST /application/open-ai/agent/earnings-review-getcontent` - Get earnings review content
- Sync sample: `sample/sync/ai_earnings_review.py`
- Async sample: `sample/async/ai_earnings_review.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `period` | `str` | 是 | - | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `wait` | `bool` | 否 | `True` | `False` | 异步生成类接口是否阻塞轮询到内容完成。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.earnings_review_check`

- Endpoint: `ai.earnings-review.get-content` `POST /application/open-ai/agent/earnings-review-getcontent` - Get earnings review content
- Sync sample: `sample/sync/ai_earnings_review_check.py`
- Async sample: `sample/async/ai_earnings_review_check.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `data_id` | `str` | 是 | - | `"<dataId>"` | 异步生成任务 ID，由 *_review 或 *_debate wait=False 返回。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.viewpoint_debate`

- Endpoint: `ai.viewpoint-debate.get-id` `POST /application/open-ai/agent/viewpoint-debate-getid` - Get viewpoint debate ID<br>`ai.viewpoint-debate.get-content` `POST /application/open-ai/agent/viewpoint-debate-getcontent` - Get viewpoint debate content
- Sync sample: `sample/sync/ai_viewpoint_debate.py`
- Async sample: `sample/async/ai_viewpoint_debate.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `viewpoint` | `str` | 是 | - | `"白酒行业估值修复具备持续性"` | 待辩论的投资观点文本，建议不超过 1000 字。 |
| `wait` | `bool` | 否 | `True` | `False` | 异步生成类接口是否阻塞轮询到内容完成。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.viewpoint_debate_check`

- Endpoint: `ai.viewpoint-debate.get-content` `POST /application/open-ai/agent/viewpoint-debate-getcontent` - Get viewpoint debate content
- Sync sample: `sample/sync/ai_viewpoint_debate_check.py`
- Async sample: `sample/async/ai_viewpoint_debate_check.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `data_id` | `str` | 是 | - | `"<dataId>"` | 异步生成任务 ID，由 *_review 或 *_debate wait=False 返回。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.knowledge_resource_download`

- Endpoint: `ai.knowledge-resource.download` `GET /application/open-data/ai/resource/download` - Download knowledge resource
- Sync sample: `sample/sync/ai_knowledge_resource_download.py`
- Async sample: `sample/async/ai_knowledge_resource_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `resource_type` | `int` | 是 | - | `1` | 知识资源类型代码。 |
| `source_id` | `str` | 是 | - | `"<sourceId>"` | 知识资源源 ID。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |


## User vault (`gangtise.vault`)

### `vault.drive_list`

- Endpoint: `vault.drive.list` `POST /application/open-vault/drive/getList` - List vault drive files, paginated max size 50
- Sync sample: `sample/sync/vault_drive_list.py`
- Async sample: `sample/async/vault_drive_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `file_type` | `Any` | 否 | `None` | `1` | 文件类型代码；下载接口常用 1。 |
| `space_type` | `Any` | 否 | `None` | `None` | 空间类型过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.record_list`

- Endpoint: `vault.record.list` `POST /application/open-vault/record/getList` - List voice recording transcriptions, paginated max size 50
- Sync sample: `sample/sync/vault_record_list.py`
- Async sample: `sample/async/vault_record_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `space_type` | `Any` | 否 | `None` | `None` | 空间类型过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.my_conference_list`

- Endpoint: `vault.my-conference.list` `POST /application/open-vault/my-conference/getList` - List my conferences, paginated max size 50
- Sync sample: `sample/sync/vault_my_conference_list.py`
- Async sample: `sample/async/vault_my_conference_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.wechat_message_list`

- Endpoint: `vault.wechat-message.list` `POST /application/open-vault/wechatgroupmsg/list` - List WeChat group messages, paginated max size 50
- Sync sample: `sample/sync/vault_wechat_message_list.py`
- Async sample: `sample/async/vault_wechat_message_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int | None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str | None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str | None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str | None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `wechat_group_id` | `Any` | 否 | `None` | `None` | 微信群 ID，支持单值或列表。 |
| `industry` | `Any` | 否 | `None` | `1` | 行业 ID/代码过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，具体取值参考 lookup 接口。 |
| `tag` | `Any` | 否 | `None` | `None` | 标签过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.wechat_chatroom_list`

- Endpoint: `vault.wechat-chatroom.list` `POST /application/open-vault/wechatgroupmsg/chatroomId` - List WeChat group chatroom IDs
- Sync sample: `sample/sync/vault_wechat_chatroom_list.py`
- Async sample: `sample/async/vault_wechat_chatroom_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int` | 否 | `20` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `room_name` | `Any` | 否 | `None` | `"投研"` | 微信群名称或名称列表；请求时会拼成逗号分隔字符串。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.stock_pool_list`

- Endpoint: `vault.stock-pool.list` `POST /application/open-vault/stock-pool/getPoolList` - List user stock pool IDs and names
- Sync sample: `sample/sync/vault_stock_pool_list.py`
- Async sample: `sample/async/vault_stock_pool_list.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.stock_pool_stocks`

- Endpoint: `vault.stock-pool.stocks` `POST /application/open-vault/stock-pool/getStockList` - List securities in stock pool(s)
- Sync sample: `sample/sync/vault_stock_pool_stocks.py`
- Async sample: `sample/async/vault_stock_pool_stocks.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `pool_id` | `Any` | 否 | `'all'` | `"all"` | 股票池 ID 或 ID 列表；默认 all。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.drive_download`

- Endpoint: `vault.drive.download` `GET /application/open-vault/drive/download/file` - Download vault drive file
- Sync sample: `sample/sync/vault_drive_download.py`
- Async sample: `sample/async/vault_drive_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `file_id` | `str` | 是 | - | `"<fileId>"` | 网盘文件 ID，通常来自 vault.drive_list。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |

### `vault.record_download`

- Endpoint: `vault.record.download` `GET /application/open-vault/record/download/file` - Download voice recording transcription file
- Sync sample: `sample/sync/vault_record_download.py`
- Async sample: `sample/async/vault_record_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `str` | 是 | - | `"<recordId>"` | 录音记录 ID，通常来自 vault.record_list。 |
| `content_type` | `str` | 是 | - | `"summary"` | 下载内容类型，例如 original 或 summary。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |

### `vault.my_conference_download`

- Endpoint: `vault.my-conference.download` `GET /application/open-vault/my-conference/download/file` - Download my conference resource
- Sync sample: `sample/sync/vault_my_conference_download.py`
- Async sample: `sample/async/vault_my_conference_download.py`
- Return annotation: `Path`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `conference_id` | `str` | 是 | - | `"<conferenceId>"` | 会议 ID，通常来自 vault.my_conference_list。 |
| `content_type` | `str` | 是 | - | `"summary"` | 下载内容类型，例如 original 或 summary。 |
| `output` | `str | Path | None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |


## Alternative data (`gangtise.alternative`)

### `alternative.edb_search`

- Endpoint: `alternative.edb-search` `POST /application/open-alternative/EDB/search` - Search industry indicator list by keyword
- Sync sample: `sample/sync/alternative_edb_search.py`
- Async sample: `sample/async/alternative_edb_search.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"平安银行"` | 搜索关键词。 |
| `limit` | `int` | 否 | `100` | `10` | 返回条数上限。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `alternative.edb_data`

- Endpoint: `alternative.edb-data` `POST /application/open-alternative/EDB/getData` - Get industry indicator time-series data by indicator ID list
- Sync sample: `sample/sync/alternative_edb_data.py`
- Async sample: `sample/async/alternative_edb_data.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `indicator_id` | `Any` | 是 | - | `"<indicatorId>"` | EDB 指标 ID 或 ID 列表。 |
| `start_date` | `str` | 是 | - | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str` | 是 | - | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `alternative.concept_info`

- Endpoint: `alternative.concept-info` `POST /application/open-alternative/concept/info` - Query latest concept (theme index) profile by conceptId
- Sync sample: `sample/sync/alternative_concept_info.py`
- Async sample: `sample/async/alternative_concept_info.py`
- Return annotation: `dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `concept_id` | `str` | 是 | - | `"121000130"` | 题材（概念）指数 ID；与 `ai.theme_tracking` 共用题材 ID 体系，可用 lookup.theme_ids 按名查询（机器人=121000130）。 |
| `raw` | `bool` | 否 | `False` | `False` | 该接口返回最新截面画像对象，始终为 dict（定义/投资逻辑/行业空间/竞争格局/keyEvents），不支持历史回溯。 |

### `alternative.concept_securities`

- Endpoint: `alternative.concept-securities` `POST /application/open-alternative/concept/securities` - Query concept (theme index) constituent securities, grouped
- Sync sample: `sample/sync/alternative_concept_securities.py`
- Async sample: `sample/async/alternative_concept_securities.py`
- Return annotation: `pd.DataFrame | dict[str, Any]`

| Parameter | Type | Required | Default | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `concept_id` | `str` | 是 | - | `"121000130"` | 题材（概念）指数 ID；见 lookup.theme_ids（机器人=121000130）。 |
| `raw` | `bool` | 否 | `False` | `False` | 默认返回扁平化 DataFrame（每行一只成分股，列含 groupName/securityCode/securityName/isKey/inclusionReason）；True 返回嵌套分组 dict。 |
