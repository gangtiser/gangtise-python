# API 参数说明

本文档按 SDK 的方法签名整理，覆盖 152 个公开方法，对应 153 个上游接口（观点列表的 `with_content=`、题材的 `full=` 用开关在两个接口间切换），另有 2 个本地查表方法与 `auth.status` 本地状态方法。同步与异步方法参数一致；异步调用路径为 `gangtise.async_.<领域>.<方法>(...)`。

运行示例前请配置：

```bash
export GANGTISE_ACCESS_KEY=ak_xxx
export GANGTISE_SECRET_KEY=sk_xxx
```

所有表格中的 `raw` 参数默认不在示例中传入；设置为 `True` 时返回服务端原始 `data`。`confirm` 参数是 SDK 的「确认」开关（对应 CLI 的 `--yes`）：不可逆的删除类方法必须传 `confirm=True`；按条计费的分页列表省略 `size` 且按 `total × 单价` 估算超过 1000 积分时，不传就报 `ValidationError`（为得知 `total` 会先取一页，单页超过 50 积分时只取 1 条，这部分照常计费）；`fundamental.earning_forecast` 按日期区间估算超过 1000 积分时，不传就在发请求前报错。`Any` 类型参数通常支持单值或列表（任意序列均可，含 pandas `Series` / numpy 数组；集合、字典、迭代器与 bytes 会报错），SDK 会按接口要求转换为列表字段（去首尾空格、去重）；**显式传空列表（或空白字符串）会在发请求前报 `ValidationError`**——要不过滤就别传该参数（唯一例外：`vault.stock_pool_stocks(pool_id=[])` 表示全部股票池）。

## 方法索引

| 领域 | 方法 | 同步示例 | 异步示例 |
| --- | --- | --- | --- |
| `auth` | `login` | [auth_login.py](sync/auth_login.py) | [auth_login.py](async/auth_login.py) |
| `auth` | `status` | [auth_status.py](sync/auth_status.py) | [auth_status.py](async/auth_status.py) |
| `lookup` | `broker_orgs` | [lookup_broker_orgs.py](sync/lookup_broker_orgs.py) | [lookup_broker_orgs.py](async/lookup_broker_orgs.py) |
| `lookup` | `meeting_orgs` | [lookup_meeting_orgs.py](sync/lookup_meeting_orgs.py) | [lookup_meeting_orgs.py](async/lookup_meeting_orgs.py) |
| `reference` | `securities_search` | [reference_securities_search.py](sync/reference_securities_search.py) | [reference_securities_search.py](async/reference_securities_search.py) |
| `reference` | `chiefs_search` | [reference_chiefs_search.py](sync/reference_chiefs_search.py) | [reference_chiefs_search.py](async/reference_chiefs_search.py) |
| `reference` | `institution_search` | [reference_institution_search.py](sync/reference_institution_search.py) | [reference_institution_search.py](async/reference_institution_search.py) |
| `reference` | `official_account_search` | [reference_official_account_search.py](sync/reference_official_account_search.py) | [reference_official_account_search.py](async/reference_official_account_search.py) |
| `reference` | `constant_category` | [reference_constant_category.py](sync/reference_constant_category.py) | [reference_constant_category.py](async/reference_constant_category.py) |
| `reference` | `constant_list` | [reference_constant_list.py](sync/reference_constant_list.py) | [reference_constant_list.py](async/reference_constant_list.py) |
| `reference` | `concept_search` | [reference_concept_search.py](sync/reference_concept_search.py) | [reference_concept_search.py](async/reference_concept_search.py) |
| `reference` | `sector_search` | [reference_sector_search.py](sync/reference_sector_search.py) | [reference_sector_search.py](async/reference_sector_search.py) |
| `reference` | `sector_constituents` | [reference_sector_constituents.py](sync/reference_sector_constituents.py) | [reference_sector_constituents.py](async/reference_sector_constituents.py) |
| `quote` | `day_kline` | [quote_day_kline.py](sync/quote_day_kline.py) | [quote_day_kline.py](async/quote_day_kline.py) |
| `quote` | `day_kline_hk` | [quote_day_kline_hk.py](sync/quote_day_kline_hk.py) | [quote_day_kline_hk.py](async/quote_day_kline_hk.py) |
| `quote` | `day_kline_us` | [quote_day_kline_us.py](sync/quote_day_kline_us.py) | [quote_day_kline_us.py](async/quote_day_kline_us.py) |
| `quote` | `index_day_kline` | [quote_index_day_kline.py](sync/quote_index_day_kline.py) | [quote_index_day_kline.py](async/quote_index_day_kline.py) |
| `quote` | `minute_kline` | [quote_minute_kline.py](sync/quote_minute_kline.py) | [quote_minute_kline.py](async/quote_minute_kline.py) |
| `quote` | `realtime` | [quote_realtime.py](sync/quote_realtime.py) | [quote_realtime.py](async/quote_realtime.py) |
| `quote` | `fund_flow` | [quote_fund_flow.py](sync/quote_fund_flow.py) | [quote_fund_flow.py](async/quote_fund_flow.py) |
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
| `insight` | `announcement_us_list` | [insight_announcement_us_list.py](sync/insight_announcement_us_list.py) | [insight_announcement_us_list.py](async/insight_announcement_us_list.py) |
| `insight` | `foreign_opinion_list` | [insight_foreign_opinion_list.py](sync/insight_foreign_opinion_list.py) | [insight_foreign_opinion_list.py](async/insight_foreign_opinion_list.py) |
| `insight` | `independent_opinion_list` | [insight_independent_opinion_list.py](sync/insight_independent_opinion_list.py) | [insight_independent_opinion_list.py](async/insight_independent_opinion_list.py) |
| `insight` | `official_account_list` | [insight_official_account_list.py](sync/insight_official_account_list.py) | [insight_official_account_list.py](async/insight_official_account_list.py) |
| `insight` | `summary_download` | [insight_summary_download.py](sync/insight_summary_download.py) | [insight_summary_download.py](async/insight_summary_download.py) |
| `insight` | `research_download` | [insight_research_download.py](sync/insight_research_download.py) | [insight_research_download.py](async/insight_research_download.py) |
| `insight` | `foreign_report_download` | [insight_foreign_report_download.py](sync/insight_foreign_report_download.py) | [insight_foreign_report_download.py](async/insight_foreign_report_download.py) |
| `insight` | `announcement_download` | [insight_announcement_download.py](sync/insight_announcement_download.py) | [insight_announcement_download.py](async/insight_announcement_download.py) |
| `insight` | `announcement_hk_download` | [insight_announcement_hk_download.py](sync/insight_announcement_hk_download.py) | [insight_announcement_hk_download.py](async/insight_announcement_hk_download.py) |
| `insight` | `announcement_us_download` | [insight_announcement_us_download.py](sync/insight_announcement_us_download.py) | [insight_announcement_us_download.py](async/insight_announcement_us_download.py) |
| `insight` | `independent_opinion_download` | [insight_independent_opinion_download.py](sync/insight_independent_opinion_download.py) | [insight_independent_opinion_download.py](async/insight_independent_opinion_download.py) |
| `insight` | `official_account_download` | [insight_official_account_download.py](sync/insight_official_account_download.py) | [insight_official_account_download.py](async/insight_official_account_download.py) |
| `insight` | `qa_list` | [insight_qa_list.py](sync/insight_qa_list.py) | [insight_qa_list.py](async/insight_qa_list.py) |
| `insight` | `report_image_list` | [insight_report_image_list.py](sync/insight_report_image_list.py) | [insight_report_image_list.py](async/insight_report_image_list.py) |
| `insight` | `report_image_download` | [insight_report_image_download.py](sync/insight_report_image_download.py) | [insight_report_image_download.py](async/insight_report_image_download.py) |
| `insight` | `opinion_detail` | [insight_opinion_detail.py](sync/insight_opinion_detail.py) | [insight_opinion_detail.py](async/insight_opinion_detail.py) |
| `insight` | `foreign_opinion_detail` | [insight_foreign_opinion_detail.py](sync/insight_foreign_opinion_detail.py) | [insight_foreign_opinion_detail.py](async/insight_foreign_opinion_detail.py) |
| `insight` | `highlight_list` | [insight_highlight_list.py](sync/insight_highlight_list.py) | [insight_highlight_list.py](async/insight_highlight_list.py) |
| `fundamental` | `income_statement` | [fundamental_income_statement.py](sync/fundamental_income_statement.py) | [fundamental_income_statement.py](async/fundamental_income_statement.py) |
| `fundamental` | `income_statement_quarterly` | [fundamental_income_statement_quarterly.py](sync/fundamental_income_statement_quarterly.py) | [fundamental_income_statement_quarterly.py](async/fundamental_income_statement_quarterly.py) |
| `fundamental` | `balance_sheet` | [fundamental_balance_sheet.py](sync/fundamental_balance_sheet.py) | [fundamental_balance_sheet.py](async/fundamental_balance_sheet.py) |
| `fundamental` | `cash_flow` | [fundamental_cash_flow.py](sync/fundamental_cash_flow.py) | [fundamental_cash_flow.py](async/fundamental_cash_flow.py) |
| `fundamental` | `cash_flow_quarterly` | [fundamental_cash_flow_quarterly.py](sync/fundamental_cash_flow_quarterly.py) | [fundamental_cash_flow_quarterly.py](async/fundamental_cash_flow_quarterly.py) |
| `fundamental` | `income_statement_hk` | [fundamental_income_statement_hk.py](sync/fundamental_income_statement_hk.py) | [fundamental_income_statement_hk.py](async/fundamental_income_statement_hk.py) |
| `fundamental` | `balance_sheet_hk` | [fundamental_balance_sheet_hk.py](sync/fundamental_balance_sheet_hk.py) | [fundamental_balance_sheet_hk.py](async/fundamental_balance_sheet_hk.py) |
| `fundamental` | `cash_flow_hk` | [fundamental_cash_flow_hk.py](sync/fundamental_cash_flow_hk.py) | [fundamental_cash_flow_hk.py](async/fundamental_cash_flow_hk.py) |
| `fundamental` | `income_statement_us` | [fundamental_income_statement_us.py](sync/fundamental_income_statement_us.py) | [fundamental_income_statement_us.py](async/fundamental_income_statement_us.py) |
| `fundamental` | `balance_sheet_us` | [fundamental_balance_sheet_us.py](sync/fundamental_balance_sheet_us.py) | [fundamental_balance_sheet_us.py](async/fundamental_balance_sheet_us.py) |
| `fundamental` | `cash_flow_us` | [fundamental_cash_flow_us.py](sync/fundamental_cash_flow_us.py) | [fundamental_cash_flow_us.py](async/fundamental_cash_flow_us.py) |
| `fundamental` | `main_business` | [fundamental_main_business.py](sync/fundamental_main_business.py) | [fundamental_main_business.py](async/fundamental_main_business.py) |
| `fundamental` | `valuation_analysis` | [fundamental_valuation_analysis.py](sync/fundamental_valuation_analysis.py) | [fundamental_valuation_analysis.py](async/fundamental_valuation_analysis.py) |
| `fundamental` | `top_holders` | [fundamental_top_holders.py](sync/fundamental_top_holders.py) | [fundamental_top_holders.py](async/fundamental_top_holders.py) |
| `fundamental` | `earning_forecast` | [fundamental_earning_forecast.py](sync/fundamental_earning_forecast.py) | [fundamental_earning_forecast.py](async/fundamental_earning_forecast.py) |
| `ai` | `knowledge_batch` | [ai_knowledge_batch.py](sync/ai_knowledge_batch.py) | [ai_knowledge_batch.py](async/ai_knowledge_batch.py) |
| `ai` | `security_clue_list` | [ai_security_clue_list.py](sync/ai_security_clue_list.py) | [ai_security_clue_list.py](async/ai_security_clue_list.py) |
| `ai` | `stock_summary_list` | [ai_stock_summary_list.py](sync/ai_stock_summary_list.py) | [ai_stock_summary_list.py](async/ai_stock_summary_list.py) |
| `ai` | `one_pager` | [ai_one_pager.py](sync/ai_one_pager.py) | [ai_one_pager.py](async/ai_one_pager.py) |
| `ai` | `investment_logic` | [ai_investment_logic.py](sync/ai_investment_logic.py) | [ai_investment_logic.py](async/ai_investment_logic.py) |
| `ai` | `peer_comparison` | [ai_peer_comparison.py](sync/ai_peer_comparison.py) | [ai_peer_comparison.py](async/ai_peer_comparison.py) |
| `ai` | `research_outline` | [ai_research_outline.py](sync/ai_research_outline.py) | [ai_research_outline.py](async/ai_research_outline.py) |
| `ai` | `theme_tracking` | [ai_theme_tracking.py](sync/ai_theme_tracking.py) | [ai_theme_tracking.py](async/ai_theme_tracking.py) |
| `ai` | `hot_topic` | [ai_hot_topic.py](sync/ai_hot_topic.py) | [ai_hot_topic.py](async/ai_hot_topic.py) |
| `ai` | `management_discuss_announcement` | [ai_management_discuss_announcement.py](sync/ai_management_discuss_announcement.py) | [ai_management_discuss_announcement.py](async/ai_management_discuss_announcement.py) |
| `ai` | `management_discuss_earnings_call` | [ai_management_discuss_earnings_call.py](sync/ai_management_discuss_earnings_call.py) | [ai_management_discuss_earnings_call.py](async/ai_management_discuss_earnings_call.py) |
| `ai` | `management_sentiment_indicator` | [ai_management_sentiment_indicator.py](sync/ai_management_sentiment_indicator.py) | [ai_management_sentiment_indicator.py](async/ai_management_sentiment_indicator.py) |
| `ai` | `management_sentiment_conclusion` | [ai_management_sentiment_conclusion.py](sync/ai_management_sentiment_conclusion.py) | [ai_management_sentiment_conclusion.py](async/ai_management_sentiment_conclusion.py) |
| `ai` | `management_sentiment_detail` | [ai_management_sentiment_detail.py](sync/ai_management_sentiment_detail.py) | [ai_management_sentiment_detail.py](async/ai_management_sentiment_detail.py) |
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
| `vault` | `stock_pool_create` | [vault_stock_pool_create.py](sync/vault_stock_pool_create.py) | [vault_stock_pool_create.py](async/vault_stock_pool_create.py) |
| `vault` | `stock_pool_rename` | [vault_stock_pool_rename.py](sync/vault_stock_pool_rename.py) | [vault_stock_pool_rename.py](async/vault_stock_pool_rename.py) |
| `vault` | `stock_pool_add_stock` | [vault_stock_pool_add_stock.py](sync/vault_stock_pool_add_stock.py) | [vault_stock_pool_add_stock.py](async/vault_stock_pool_add_stock.py) |
| `vault` | `stock_pool_remove_stock` | [vault_stock_pool_remove_stock.py](sync/vault_stock_pool_remove_stock.py) | [vault_stock_pool_remove_stock.py](async/vault_stock_pool_remove_stock.py) |
| `vault` | `stock_pool_delete` | [vault_stock_pool_delete.py](sync/vault_stock_pool_delete.py) | [vault_stock_pool_delete.py](async/vault_stock_pool_delete.py) |
| `vault` | `drive_folder_list` | [vault_drive_folder_list.py](sync/vault_drive_folder_list.py) | [vault_drive_folder_list.py](async/vault_drive_folder_list.py) |
| `vault` | `drive_upload` | [vault_drive_upload.py](sync/vault_drive_upload.py) | [vault_drive_upload.py](async/vault_drive_upload.py) |
| `vault` | `drive_create_folder` | [vault_drive_create_folder.py](sync/vault_drive_create_folder.py) | [vault_drive_create_folder.py](async/vault_drive_create_folder.py) |
| `vault` | `drive_rename` | [vault_drive_rename.py](sync/vault_drive_rename.py) | [vault_drive_rename.py](async/vault_drive_rename.py) |
| `vault` | `drive_move_file` | [vault_drive_move_file.py](sync/vault_drive_move_file.py) | [vault_drive_move_file.py](async/vault_drive_move_file.py) |
| `vault` | `drive_move_folder` | [vault_drive_move_folder.py](sync/vault_drive_move_folder.py) | [vault_drive_move_folder.py](async/vault_drive_move_folder.py) |
| `vault` | `drive_copy` | [vault_drive_copy.py](sync/vault_drive_copy.py) | [vault_drive_copy.py](async/vault_drive_copy.py) |
| `vault` | `drive_delete_file` | [vault_drive_delete_file.py](sync/vault_drive_delete_file.py) | [vault_drive_delete_file.py](async/vault_drive_delete_file.py) |
| `vault` | `drive_delete_folder` | [vault_drive_delete_folder.py](sync/vault_drive_delete_folder.py) | [vault_drive_delete_folder.py](async/vault_drive_delete_folder.py) |
| `alternative` | `edb_search` | [alternative_edb_search.py](sync/alternative_edb_search.py) | [alternative_edb_search.py](async/alternative_edb_search.py) |
| `alternative` | `edb_data` | [alternative_edb_data.py](sync/alternative_edb_data.py) | [alternative_edb_data.py](async/alternative_edb_data.py) |
| `alternative` | `concept_info` | [alternative_concept_info.py](sync/alternative_concept_info.py) | [alternative_concept_info.py](async/alternative_concept_info.py) |
| `alternative` | `concept_securities` | [alternative_concept_securities.py](sync/alternative_concept_securities.py) | [alternative_concept_securities.py](async/alternative_concept_securities.py) |
| `insight` | `pamirs_summary_list` | [insight_pamirs_summary_list.py](sync/insight_pamirs_summary_list.py) | [insight_pamirs_summary_list.py](async/insight_pamirs_summary_list.py) |
| `insight` | `pamirs_summary_download` | [insight_pamirs_summary_download.py](sync/insight_pamirs_summary_download.py) | [insight_pamirs_summary_download.py](async/insight_pamirs_summary_download.py) |
| `insight` | `performance_calendar_list` | [insight_performance_calendar_list.py](sync/insight_performance_calendar_list.py) | [insight_performance_calendar_list.py](async/insight_performance_calendar_list.py) |
| `insight` | `performance_calendar_download` | [insight_performance_calendar_download.py](sync/insight_performance_calendar_download.py) | [insight_performance_calendar_download.py](async/insight_performance_calendar_download.py) |
| `indicator` | `search` | [indicator_search.py](sync/indicator_search.py) | [indicator_search.py](async/indicator_search.py) |
| `indicator` | `cross_section` | [indicator_cross_section.py](sync/indicator_cross_section.py) | [indicator_cross_section.py](async/indicator_cross_section.py) |
| `indicator` | `time_series` | [indicator_time_series.py](sync/indicator_time_series.py) | [indicator_time_series.py](async/indicator_time_series.py) |
| `indicator` | `screener` | [indicator_screener.py](sync/indicator_screener.py) | [indicator_screener.py](async/indicator_screener.py) |
| `bond` | `basic_info` | [bond_basic_info.py](sync/bond_basic_info.py) | [bond_basic_info.py](async/bond_basic_info.py) |
| `bond` | `issuer_info` | [bond_issuer_info.py](sync/bond_issuer_info.py) | [bond_issuer_info.py](async/bond_issuer_info.py) |
| `bond` | `daily_quote` | [bond_daily_quote.py](sync/bond_daily_quote.py) | [bond_daily_quote.py](async/bond_daily_quote.py) |
| `bond` | `valuation` | [bond_valuation.py](sync/bond_valuation.py) | [bond_valuation.py](async/bond_valuation.py) |
| `bond` | `cash_flow` | [bond_cash_flow.py](sync/bond_cash_flow.py) | [bond_cash_flow.py](async/bond_cash_flow.py) |
| `bond` | `announcement` | [bond_announcement.py](sync/bond_announcement.py) | [bond_announcement.py](async/bond_announcement.py) |
| `bond` | `issuance_detail` | [bond_issuance_detail.py](sync/bond_issuance_detail.py) | [bond_issuance_detail.py](async/bond_issuance_detail.py) |
| `bond` | `rating_overview` | [bond_rating_overview.py](sync/bond_rating_overview.py) | [bond_rating_overview.py](async/bond_rating_overview.py) |
| `bond` | `rating_change` | [bond_rating_change.py](sync/bond_rating_change.py) | [bond_rating_change.py](async/bond_rating_change.py) |
| `bond` | `issuer_rating_change` | [bond_issuer_rating_change.py](sync/bond_issuer_rating_change.py) | [bond_issuer_rating_change.py](async/bond_issuer_rating_change.py) |
| `bond` | `issuance_plan` | [bond_issuance_plan.py](sync/bond_issuance_plan.py) | [bond_issuance_plan.py](async/bond_issuance_plan.py) |
| `bond` | `exercise_notice` | [bond_exercise_notice.py](sync/bond_exercise_notice.py) | [bond_exercise_notice.py](async/bond_exercise_notice.py) |
| `bond` | `default_list` | [bond_default_list.py](sync/bond_default_list.py) | [bond_default_list.py](async/bond_default_list.py) |
| `fund` | `basic_info` | [fund_basic_info.py](sync/fund_basic_info.py) | [fund_basic_info.py](async/fund_basic_info.py) |
| `fund` | `nav` | [fund_nav.py](sync/fund_nav.py) | [fund_nav.py](async/fund_nav.py) |
| `fund` | `fee_rate` | [fund_fee_rate.py](sync/fund_fee_rate.py) | [fund_fee_rate.py](async/fund_fee_rate.py) |
| `fund` | `manager_info` | [fund_manager_info.py](sync/fund_manager_info.py) | [fund_manager_info.py](async/fund_manager_info.py) |
| `fund` | `manager_history` | [fund_manager_history.py](sync/fund_manager_history.py) | [fund_manager_history.py](async/fund_manager_history.py) |
| `fund` | `asset_size` | [fund_asset_size.py](sync/fund_asset_size.py) | [fund_asset_size.py](async/fund_asset_size.py) |
| `fund` | `holder_structure` | [fund_holder_structure.py](sync/fund_holder_structure.py) | [fund_holder_structure.py](async/fund_holder_structure.py) |
| `fund` | `top10_holders` | [fund_top10_holders.py](sync/fund_top10_holders.py) | [fund_top10_holders.py](async/fund_top10_holders.py) |
| `fund` | `asset_allocation` | [fund_asset_allocation.py](sync/fund_asset_allocation.py) | [fund_asset_allocation.py](async/fund_asset_allocation.py) |
| `fund` | `stock_portfolio` | [fund_stock_portfolio.py](sync/fund_stock_portfolio.py) | [fund_stock_portfolio.py](async/fund_stock_portfolio.py) |
| `fund` | `industry_allocation` | [fund_industry_allocation.py](sync/fund_industry_allocation.py) | [fund_industry_allocation.py](async/fund_industry_allocation.py) |
| `fund` | `bond_portfolio` | [fund_bond_portfolio.py](sync/fund_bond_portfolio.py) | [fund_bond_portfolio.py](async/fund_bond_portfolio.py) |
| `fund` | `bond_type_allocation` | [fund_bond_type_allocation.py](sync/fund_bond_type_allocation.py) | [fund_bond_type_allocation.py](async/fund_bond_type_allocation.py) |
| `fund` | `fund_portfolio` | [fund_fund_portfolio.py](sync/fund_fund_portfolio.py) | [fund_fund_portfolio.py](async/fund_fund_portfolio.py) |
| `fund` | `fund_type_allocation` | [fund_fund_type_allocation.py](sync/fund_fund_type_allocation.py) | [fund_fund_type_allocation.py](async/fund_fund_type_allocation.py) |
| `fund` | `etf_pcf_header` | [fund_etf_pcf_header.py](sync/fund_etf_pcf_header.py) | [fund_etf_pcf_header.py](async/fund_etf_pcf_header.py) |
| `fund` | `etf_pcf_components` | [fund_etf_pcf_components.py](sync/fund_etf_pcf_components.py) | [fund_etf_pcf_components.py](async/fund_etf_pcf_components.py) |
| `fund` | `etf_share_change` | [fund_etf_share_change.py](sync/fund_etf_share_change.py) | [fund_etf_share_change.py](async/fund_etf_share_change.py) |
| `tool` | `file_parse` | [tool_file_parse.py](sync/tool_file_parse.py) | [tool_file_parse.py](async/tool_file_parse.py) |
| `tool` | `file_parse_check` | [tool_file_parse_check.py](sync/tool_file_parse_check.py) | [tool_file_parse_check.py](async/tool_file_parse_check.py) |
| `tool` | `web_search` | [tool_web_search.py](sync/tool_web_search.py) | [tool_web_search.py](async/tool_web_search.py) |

## 登录与鉴权（`gangtise.auth`）

### `auth.login`

- 接口：`auth.login` `POST /application/auth/oauth/open/loginV2`
- 同步示例：`sample/sync/auth_login.py`
- 异步示例：`sample/async/auth_login.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| - | - | - | - | - | 无参数。返回 `{authorization, cache, source}`：设了 `GANGTISE_TOKEN` 时 `source="env-token"`（不联网、`cache` 为 None）；否则用 AK/SK 真登录一次（`source="login"`，不复用缓存——换了凭证后缓存里可能还是上一个账号）。 |

### `auth.status`

- 接口：本地方法；读取当前 token/cache 状态，不发起 HTTP API 请求。
- 同步示例：`sample/sync/auth_status.py`
- 异步示例：`sample/async/auth_status.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| - | - | - | - | - | 无参数。 |

## 本地查表（`gangtise.lookup`）

### `lookup.broker_orgs`

- 接口：`lookup.broker-orgs.list` `GET /guide/broker-orgs-local`
- 同步示例：`sample/sync/lookup_broker_orgs.py`
- 异步示例：`sample/async/lookup_broker_orgs.py`
- 返回类型：`pd.DataFrame | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `lookup.meeting_orgs`

- 接口：`lookup.meeting-orgs.list` `GET /guide/meeting-orgs-local`
- 同步示例：`sample/sync/lookup_meeting_orgs.py`
- 异步示例：`sample/async/lookup_meeting_orgs.py`
- 返回类型：`pd.DataFrame | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

## 参考数据（`gangtise.reference`）

### `reference.securities_search`

- 接口：`reference.securities-search` `POST /application/open-reference/securities/search`
- 同步示例：`sample/sync/reference_securities_search.py`
- 异步示例：`sample/async/reference_securities_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"平安银行"` | 搜索关键词。 |
| `category` | `Any` | 否 | `None` | `"stock"` | 分类过滤，支持单值或列表，取值 stock / dr / index / fund / bond。bond 覆盖交易所可转债、国债、地方债、金融债与银行间债券（.SH / .SZ / .IB），代码用于 `gangtise.bond`。🔴 可转债在任何分类下都可能出现（按公司简称查 stock 时同名可转债常排第一），取第一条 category 等于所查类别的行，别直接取第一行。 |
| `top` | `int` | 否 | `10` | `3` | 每个查询返回的最大候选数。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `reference.chiefs_search`

- 接口：`reference.chiefs-search` `POST /application/open-reference/chiefs/search`
- 同步示例：`sample/sync/reference_chiefs_search.py`
- 异步示例：`sample/async/reference_chiefs_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"电子"` | 搜索关键词，支持 首席姓名 / 机构 / 团队。 |
| `top` | `int` | 否 | `10` | `5` | 最大返回数，默认 10，上限 10。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `reference.institution_search`

- 接口：`reference.institution-search` `POST /application/open-reference/institutions/search`
- 同步示例：`sample/sync/reference_institution_search.py`
- 异步示例：`sample/async/reference_institution_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"招商"` | 搜索关键词，机构名 / 简称。 |
| `category` | `Any` | 否 | `None` | `["domesticBroker", "opinionInstitution"]` | 机构类型，支持单值或列表，省略=全部；枚举：`domesticBroker` / `foreignInstitution` / `leadInstitution` / `opinionInstitution` / `foreignOpinionInstitution`。 |
| `top` | `int` | 否 | `10` | `5` | 最大返回数，默认 10，上限 10。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `reference.official_account_search`

- 接口：`reference.official-account-search` `POST /application/open-reference/officialAccount/search`
- 同步示例：`sample/sync/reference_official_account_search.py`
- 异步示例：`sample/async/reference_official_account_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"中信证券"` | 公众号名称 / 所属机构 / 关键字。 |
| `category` | `Any` | 否 | `None` | `["broker", "media"]` | 分类，支持单值或列表；枚举：`listedCompany` / `broker` / `government` / `media`。部分公众号不属四类（category 为 null），传 category 会漏掉它们，要全量就别传。 |
| `top` | `int` | 否 | `10` | `5` | 最大返回数，默认 10，上限 10；结果按 matchScore 降序。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `reference.constant_category`

- 接口：`reference.constant-category` `GET /application/open-reference/constants/category`
- 同步示例：`sample/sync/reference_constant_category.py`
- 异步示例：`sample/async/reference_constant_category.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `reference.constant_list`

- 接口：`reference.constant-list` `POST /application/open-reference/constants/getList`
- 同步示例：`sample/sync/reference_constant_list.py`
- 异步示例：`sample/async/reference_constant_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `category` | `str` | 是 | - | `"citicIndustry"` | 分类编码，取值见 reference.constant_category，如 citicIndustry=中信一级行业 / swIndustry=申万一级行业 / gangtiseIndustry=Gangtise行业 / domesticCity=国内城市 / aShareAnnouncementCategory=A股公告分类（树形）/ hkShareAnnouncementCategory=港股公告分类（树形）/ regionCategory=区域分类。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。树形分类的 children 层级需 raw=True 自行递归。 |

### `reference.concept_search`

- 接口：`reference.concept-search` `POST /application/open-reference/concepts/search`
- 同步示例：`sample/sync/reference_concept_search.py`
- 异步示例：`sample/async/reference_concept_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"机器人"` | 搜索关键词，支持中文名/拼音/首字母（如 jqr）/分组名。结果的 conceptId 供 alternative.concept_info / concept_securities 与 ai.theme_tracking 共用（机器人=121000130）。 |
| `top` | `int` | 否 | `10` | `5` | 返回的最大候选数，上限 10。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `reference.sector_search`

- 接口：`reference.sector-search` `POST /application/open-reference/sectors/search`
- 同步示例：`sample/sync/reference_sector_search.py`
- 异步示例：`sample/async/reference_sector_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str \| None` | 否 | `None` | `"半导体"` | 搜索关键词，支持名称/拼音；可省略。结果的 sectorId 供 reference.sector_constituents 使用；同名板块可能出现在多个层级，用 hierarchy 字段区分。 |
| `top` | `int` | 否 | `10` | `10` | 返回的最大候选数，上限 10。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `reference.sector_constituents`

- 接口：`reference.sector-constituents` `POST /application/open-reference/sectors/constituents`
- 同步示例：`sample/sync/reference_sector_constituents.py`
- 异步示例：`sample/async/reference_sector_constituents.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `sector_id` | `str` | 是 | - | `"2000000014"` | 板块 ID，必须来自 reference.sector_search（题材 conceptId 与板块 sectorId 是两套 ID，不通用；2000000014=申万一级行业指数）。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

## 行情（`gangtise.quote`）

### `quote.day_kline`

- 接口：`quote.day-kline` `POST /application/open-quote/kline/daily`
- 同步示例：`sample/sync/quote_day_kline.py`
- 异步示例：`sample/async/quote_day_kline.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"AAPL.O"` | 证券代码或代码列表：A 股 .SH/.SZ/.BJ、港股 .HK、美股 .O/.N/.A、沪深 ETF、交易所/概念（.GT）/行业（.CI/.SWI）指数、全球指数，可混传；重复代码自动去掉。或单独传一个市场关键字 `aShares` / `hkStocks` / `usStocks`（只覆盖个股；不收 `all`；须同时传 start_date 与 end_date，按工作日自动分片：A 股 / 美股 1 个工作日一片、港股 2 个）。多只证券且「证券数 × 工作日数」达到 limit 时按行数上限分组请求、按传入顺序合并。 |
| `start_date` | `str \| dt.date \| None` | 否 | `None` | `"2026-05-01"` | 开始日期 YYYY-MM-DD；省略默认结束日往前 1 年（全市场关键字必填）。首行比它晚 14 天以上时发 warning（上市较晚或越过账号回溯窗口）。 |
| `end_date` | `str \| dt.date \| None` | 否 | `None` | `"2026-05-28"` | 结束日期 YYYY-MM-DD；省略默认最新交易日（全市场关键字必填）。 |
| `limit` | `int \| None` | 否 | `None` | `10` | 单次请求行数上限，默认 6000、最大 10000；全市场分片未传时按 10000，多只证券分组未传时每组按 10000。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。多只证券或全市场关键字时自动在最前补 securityCode / tradeDate 并发 warning；单只不补。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（含 partial / failedShards / outOfWindowShards / droppedColumns / truncatedSecurities 等标记）；False 时转换为 pandas.DataFrame。 |

### `quote.day_kline_hk`

- 接口：`quote.day-kline-hk` `POST /application/open-quote/kline-hk/daily`
- 同步示例：`sample/sync/quote_day_kline_hk.py`
- 异步示例：`sample/async/quote_day_kline_hk.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 已弃用，改用 day_kline。港股代码（.HK）或代码列表，重复代码自动去掉；或单独传 `all`=全港股（须同时传 start_date 与 end_date，按 2 个工作日一片自动分片）。本接口不校验代码，传错返回空结果。 |
| `start_date` | `str \| dt.date \| None` | 否 | `None` | `"2026-05-01"` | 开始日期 YYYY-MM-DD；省略默认结束日往前 1 年（`all` 必填）。 |
| `end_date` | `str \| dt.date \| None` | 否 | `None` | `"2026-05-28"` | 结束日期 YYYY-MM-DD；省略默认最新交易日（`all` 必填）。 |
| `limit` | `int \| None` | 否 | `None` | `10` | 单次请求行数上限，默认 6000、最大 10000。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；多只证券或 `all` 时自动在最前补 securityCode / tradeDate 并发 warning。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.day_kline_us`

- 接口：`quote.day-kline-us` `POST /application/open-quote/kline-us/daily`
- 同步示例：`sample/sync/quote_day_kline_us.py`
- 异步示例：`sample/async/quote_day_kline_us.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 已弃用，改用 day_kline。美股代码（.O/.N/.A）或代码列表，重复代码自动去掉；或单独传 `all`=全美股（须同时传 start_date 与 end_date，按 1 个工作日一片自动分片）。本接口不校验代码，传错返回空结果。 |
| `start_date` | `str \| dt.date \| None` | 否 | `None` | `"2026-05-01"` | 开始日期 YYYY-MM-DD；省略默认结束日往前 1 年（`all` 必填）。 |
| `end_date` | `str \| dt.date \| None` | 否 | `None` | `"2026-05-28"` | 结束日期 YYYY-MM-DD；省略默认最新交易日（`all` 必填）。 |
| `limit` | `int \| None` | 否 | `None` | `10` | 单次请求行数上限，默认 6000、最大 10000。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；多只证券或 `all` 时自动在最前补 securityCode / tradeDate 并发 warning。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.index_day_kline`

- 接口：`quote.index-day-kline` `POST /application/open-quote/index/kline/daily`
- 同步示例：`sample/sync/quote_index_day_kline.py`
- 异步示例：`sample/async/quote_index_day_kline.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 已弃用，改用 day_kline 传同样的代码。沪深京指数代码或代码列表（如 000001.SH / 399001.SZ），重复代码自动去掉。**没有全市场关键字**：接口对 `all` 返回空结果、不报错，SDK 在发请求前抛 ValidationError；全部指数目前没有一次拿全的写法。返回字段同 day_kline、不含指数名称（名称用 reference.securities_search(category="index") 的 gtsName）。 |
| `start_date` | `str \| dt.date \| None` | 否 | `None` | `"2026-05-01"` | 开始日期 YYYY-MM-DD；省略默认结束日往前 1 年。 |
| `end_date` | `str \| dt.date \| None` | 否 | `None` | `"2026-05-28"` | 结束日期 YYYY-MM-DD；省略默认最新交易日。 |
| `limit` | `int \| None` | 否 | `None` | `10` | 单次请求行数上限，默认 6000、最大 10000。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；多只指数时自动在最前补 securityCode / tradeDate 并发 warning。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.minute_kline`

- 接口：`quote.minute-kline` `POST /application/open-quote/kline/minute`
- 同步示例：`sample/sync/quote_minute_kline.py`
- 异步示例：`sample/async/quote_minute_kline.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 证券代码或代码列表（重复代码自动去掉）。接口本身一次只收一只，传列表时 SDK 逐只并发请求再按传入顺序合并；某只填满 limit 会标 partial + truncatedSecurities。支持沪深 A 股、ETF（512800.SH）、各类指数与全球指数（SPX.SPI / N225.NKI / HSI.HI）；无全市场关键词。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间 yyyy-MM-dd HH:mm:ss（只写日期亦可）。分钟数据窗口远短于日 K 且随日期滚动：整段在窗外返回空表且不报错（SDK 发 warning）；首行比它晚 14 天以上时发 warning。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间 yyyy-MM-dd HH:mm:ss（只写日期亦可）。 |
| `limit` | `int \| None` | 否 | `None` | `10` | 单次请求行数上限，默认 6000、最大 10000；无翻页，撞上限标 partial 并告警。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；多只证券时自动在最前补 securityCode / tradeTime 并发 warning；单只不补。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.realtime`

- 接口：`quote.realtime` `POST /application/open-quote/quote/realtime`
- 同步示例：`sample/sync/quote_realtime.py`
- 异步示例：`sample/async/quote_realtime.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"000001.SZ"` | 证券代码或代码列表（重复代码自动去掉），可混传个股 / ETF / 各类指数 / 全球指数；或单独传市场关键字 `aShares` / `hkStocks` / `usStocks`（只覆盖个股，不收 `all`）。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。多只证券或市场关键字时自动在最前补 securityCode 并发 warning；单只不补。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `quote.fund_flow`

- 接口：`quote.fund-flow` `POST /application/open-quote/fund-flow/daily`
- 同步示例：`sample/sync/quote_fund_flow.py`
- 异步示例：`sample/async/quote_fund_flow.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"600519.SH"` | A 股代码（.SH/.SZ/.BJ）或代码列表（重复代码自动去掉）；`"aShares"`=全市场（按 1 个工作日一片自动分片，须同时传日期区间）。多只代码且「证券数 × 工作日数」达到 limit 时 SDK 分组请求、按传入顺序合并。 |
| `start_date` | `str \| date` | 否 | `None` | `"2026-05-01"` | 开始日期 YYYY-MM-DD；省略默认结束日往前 1 年（`aShares` 全市场必填）。首行比它晚 14 天以上时发 warning。 |
| `end_date` | `str \| date` | 否 | `None` | `"2026-05-28"` | 结束日期 YYYY-MM-DD；省略默认最新交易日（`aShares` 全市场必填）。 |
| `limit` | `int` | 否 | `None` | `6000` | 单只证券单次返回条数上限，默认 6000、最大 10000；撞上限标 `partial` 并告警。 |
| `field` | `Any` | 否 | `None` | `["mainNetInflow", "largeInflow"]` | 返回字段名或字段名列表；None 表示使用服务端默认字段。securityCode / tradeDate 由服务端自动附带，SDK 不另补。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

## 投研资讯（`gangtise.insight`）

### `insight.opinion_list`

- 接口：`insight.opinion.list` `POST /application/open-insight/chief-opinion/v2/getList`<br>`insight.opinion.list-with-content` `POST /application/open-insight/chief-opinion/getList`
- 同步示例：`sample/sync/insight_opinion_list.py`
- 异步示例：`sample/async/insight_opinion_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `rank_type` | `int` | 否 | `1` | `1` | 排序方式代码。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域：行业用中信码 1008001xx、方向用 gangtiseIndustry 码 122000xxx；申万码在本接口返 0。支持单值或列表。 |
| `chief` | `Any` | 否 | `None` | `None` | 首席分析师过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `broker` | `Any` | 否 | `None` | `None` | 券商/机构过滤，支持单值或列表。 |
| `industry` | `Any` | 否 | `None` | `100800101` | 行业 ID：中信码 1008001xx；申万码 104xx0000 也生效，但两套码的行业成分不同、结果集不一致，同一批查询别混用。支持单值或列表。 |
| `concept` | `Any` | 否 | `None` | `None` | 概念/主题过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"earningsReview"` | 观点类别：earningsReview=业绩点评 / abnormalReview=异动点评 / researchUpdate=调研/访谈更新 / tradingDesk=交易台 / industryAnalysis=行业分析；支持单值或列表，多个值取并集，非法值报 100005。with_content=True 时不可用（本地报错）。 |
| `llm_tag` | `Any` | 否 | `None` | `"strongRcmd"` | 投研业务标签（28 项）：推荐 strongRcmd / undervalued / highElasticity / highDividend / reversal / bottom / beatExpect / expectGap / oversold / targetPrice / certainty；业绩侧 highGrowth / withProfitForecast / withGuidance / marginalImprovement；产业链 priceHike / tightSupplyDemand / capacityRelease / newOrder / orderSurge / keyCustomer / soleSupplier / coreSupplier / industryEntry；壁垒 leader / moat / scarcity / breakthrough。支持单值或列表，多个值取并集，非法值报 100005。「业绩点评」「头部券商」「新财富团队」改用 category / broker_tag。with_content=True 时只收 strongRcmd / earningsReview / topBroker / newFortune。 |
| `broker_tag` | `Any` | 否 | `None` | `"topBroker"` | 机构标签：topBroker=头部券商 / newFortune=新财富团队；支持单值或列表，非法值报 100005。with_content=True 时不可用（本地报错）。 |
| `source` | `Any` | 否 | `None` | `"realTime"` | 来源：realTime=实时 / openSource=开放来源；支持单值或列表。 |
| `with_content` | `bool` | 否 | `False` | `False` | True=走旧版 v1 列表直接带正文（30 积分/条，超时 / 5xx 不自动重发），返回旧版结构：标题与正文在 contentList.title / contentList.content（对象，不是数组），没有顶层 title / brief，也没有 categoryList / brokerTagList；不收 category / broker_tag。默认 False 只含 200 字摘要 brief（1 积分/条），正文改用 insight.opinion_detail 按 ID 取。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（默认 1 积分/条，with_content=True 为 30 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.summary_list`

- 接口：`insight.summary.list` `POST /application/open-insight/summary/v2/getList`
- 同步示例：`sample/sync/insight_summary_list.py`
- 异步示例：`sample/async/insight_summary_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `1` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `1` | 排序方式代码。 |
| `source` | `Any` | 否 | `None` | `"research"` | 来源过滤，支持单值或列表；ai.security_clue_list 中请求字段为 source。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"companyAnalysis"` | 纪要分类，例如 companyAnalysis / industryAnalysis / earningsCall；支持单值或列表。 |
| `market` | `Any` | 否 | `None` | `"aShares"` | 市场过滤，取值 aShares / hkStocks / usStocks；交易所后缀（SH/SZ 等）会被拒为 100005。 |
| `participant_role` | `Any` | 否 | `None` | `None` | 参与方角色过滤，支持单值或列表。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.roadshow_list`

- 接口：`insight.roadshow.list` `POST /application/open-insight/schedule/roadshow/getList`
- 同步示例：`sample/sync/insight_roadshow_list.py`
- 异步示例：`sample/async/insight_roadshow_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `category` | `Any` | 否 | `None` | `"earningsCall"` | 路演类型：earningsCall / strategyMeeting / fundRoadshow 等；支持单值或列表。 |
| `market` | `Any` | 否 | `None` | `"aShares"` | 市场过滤，取值 aShares / hkStocks / usStocks；交易所后缀（SH/SZ 等）会被拒为 100005。 |
| `participant_role` | `Any` | 否 | `None` | `None` | 参与方角色过滤，支持单值或列表。 |
| `broker_type` | `Any` | 否 | `None` | `None` | 券商类型过滤，支持单值或列表。 |
| `permission` | `Any` | 否 | `None` | `1` | 权限/可见性过滤。 |
| `location` | `Any` | 否 | `None` | `"156440000"` | 举办地点，domesticCity 码（`reference.constant_list(category="domesticCity")`，如上海 `156310000`）；支持单值或列表。传城市名（`"上海"`）返回 999999 系统内部错误，不是参数错误。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（10 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.site_visit_list`

- 接口：`insight.site-visit.list` `POST /application/open-insight/schedule/site-visit/getList`
- 同步示例：`sample/sync/insight_site_visit_list.py`
- 异步示例：`sample/async/insight_site_visit_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `category` | `Any` | 否 | `None` | `"single"` | 调研形式：single=单场 / series=系列；支持单值或列表。 |
| `market` | `Any` | 否 | `None` | `"aShares"` | 市场过滤，取值 aShares / hkStocks / usStocks；交易所后缀（SH/SZ 等）会被拒为 100005。 |
| `object_` | `Any` | 否 | `None` | `"company"` | 对象类型过滤；Python 参数名 object_ 会映射为 object。 |
| `permission` | `Any` | 否 | `None` | `1` | 权限/可见性过滤。 |
| `location` | `Any` | 否 | `None` | `"156440000"` | 举办地点，domesticCity 码（`reference.constant_list(category="domesticCity")`，如上海 `156310000`）；支持单值或列表。传城市名（`"上海"`）返回 999999 系统内部错误，不是参数错误。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（10 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.strategy_list`

- 接口：`insight.strategy.list` `POST /application/open-insight/schedule/strategy-meeting/getList`
- 同步示例：`sample/sync/insight_strategy_list.py`
- 异步示例：`sample/async/insight_strategy_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `location` | `Any` | 否 | `None` | `"156440000"` | 举办地点，domesticCity 码（`reference.constant_list(category="domesticCity")`，如上海 `156310000`）；支持单值或列表。传城市名（`"上海"`）返回 999999 系统内部错误，不是参数错误。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（10 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.forum_list`

- 接口：`insight.forum.list` `POST /application/open-insight/schedule/forum/getList`
- 同步示例：`sample/sync/insight_forum_list.py`
- 异步示例：`sample/async/insight_forum_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `location` | `Any` | 否 | `None` | `"156440000"` | 举办地点，domesticCity 码（`reference.constant_list(category="domesticCity")`，如上海 `156310000`）；支持单值或列表。传城市名（`"上海"`）返回 999999 系统内部错误，不是参数错误。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（10 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.research_list`

- 接口：`insight.research.list` `POST /application/open-insight/broker-report/getList`
- 同步示例：`sample/sync/insight_research_list.py`
- 异步示例：`sample/async/insight_research_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `1` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `1` | 排序方式代码。 |
| `broker` | `Any` | 否 | `None` | `None` | 券商/机构过滤，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `industry` | `Any` | 否 | `None` | `104110000` | 申万行业 ID（104xx0000 形态），支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"strategy"` | 研报分类，例如 strategy / macro；支持单值或列表。 |
| `llm_tag` | `Any` | 否 | `None` | `None` | LLM 标签过滤，支持单值或列表。 |
| `rating` | `Any` | 否 | `None` | `None` | 评级过滤，支持单值或列表。 |
| `rating_change` | `Any` | 否 | `None` | `None` | 评级变动过滤，支持单值或列表。 |
| `min_pages` | `int \| None` | 否 | `None` | `5` | 研报最小页数过滤。 |
| `max_pages` | `int \| None` | 否 | `None` | `50` | 研报最大页数过滤。 |
| `source` | `Any` | 否 | `None` | `"research"` | 来源过滤，支持单值或列表；ai.security_clue_list 中请求字段为 source。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.foreign_report_list`

- 接口：`insight.foreign-report.list` `POST /application/open-insight/foreign-report/getList`
- 同步示例：`sample/sync/insight_foreign_report_list.py`
- 异步示例：`sample/async/insight_foreign_report_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `1` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `1` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `region` | `Any` | 否 | `None` | `"us"` | 区域代码，本接口接受 regionCategory 的全部取值（含大写写法）；支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"strategy"` | 研报分类，例如 strategy / macro；支持单值或列表。 |
| `industry` | `Any` | 否 | `None` | `104110000` | 申万行业 ID（104xx0000 形态），支持单值或列表。 |
| `broker` | `Any` | 否 | `None` | `None` | 券商/机构过滤，支持单值或列表。 |
| `llm_tag` | `Any` | 否 | `None` | `None` | LLM 标签过滤，支持单值或列表。 |
| `rating` | `Any` | 否 | `None` | `None` | 评级过滤，支持单值或列表。 |
| `rating_change` | `Any` | 否 | `None` | `None` | 评级变动过滤，支持单值或列表。 |
| `min_pages` | `int \| None` | 否 | `None` | `5` | 研报最小页数过滤。 |
| `max_pages` | `int \| None` | 否 | `None` | `50` | 研报最大页数过滤。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.announcement_list`

- 接口：`insight.announcement.list` `POST /application/open-insight/announcement/getList`
- 同步示例：`sample/sync/insight_announcement_list.py`
- 异步示例：`sample/async/insight_announcement_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `int \| str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间：日期 / 日期时间字符串或 10/13 位时间戳，按北京时间换算成 13 位毫秒发出（与运行机器时区无关）。 |
| `end_time` | `int \| str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间，换算同 start_time；**只写日期时按当日 23:59:59 换算**，与 start_time 写同一天即查这一整天。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `1` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `1` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `category` | `Any` | 否 | `None` | `"103910200"` | 公告分类 ID，用 reference.constant_list(category="aShareAnnouncementCategory") 查；支持单值或列表。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.announcement_hk_list`

- 接口：`insight.announcement-hk.list` `POST /application/open-insight/announcement-hk/getList`
- 同步示例：`sample/sync/insight_announcement_hk_list.py`
- 异步示例：`sample/async/insight_announcement_hk_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `1` | 搜索类型代码。 |
| `rank_type` | `int` | 否 | `1` | `1` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `category` | `Any` | 否 | `None` | `"103910200"` | 公告分类 ID，用 reference.constant_list(category="hkShareAnnouncementCategory") 查；支持单值或列表。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.announcement_us_list`

- 接口：`insight.announcement-us.list` `POST /application/open-insight/announcement-us/getList`
- 同步示例：`sample/sync/insight_announcement_us_list.py`
- 异步示例：`sample/async/insight_announcement_us_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；省略则按 endpoint 最大页大小 50 自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"earnings"` | 搜索关键词。 |
| `search_type` | `int` | 否 | `1` | `2` | 搜索方式：1=标题（默认） 2=全文。 |
| `rank_type` | `int` | 否 | `1` | `2` | 排序方式：1=综合（默认） 2=时间倒序。 |
| `security` | `Any` | 否 | `None` | `"TSLA.O"` | 美股代码或代码列表，例如 TSLA.O。 |
| `category` | `Any` | 否 | `None` | `None` | 美股公告类型 ID，支持单值或列表，见 reference.constant_list(category="usShareAnnouncementCategory")。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.foreign_opinion_list`

- 接口：`insight.foreign-opinion.list` `POST /application/open-insight/foreign-opinion/v2/getList`<br>`insight.foreign-opinion.list-with-content` `POST /application/open-insight/foreign-opinion/getList`
- 同步示例：`sample/sync/insight_foreign_opinion_list.py`
- 异步示例：`sample/async/insight_foreign_opinion_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `rank_type` | `int` | 否 | `1` | `1` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `region` | `Any` | 否 | `None` | `"us"` | 区域代码，**小写**：cn / cnHk / cnTw / us / jp / uk；其余 regionCategory 取值在本接口报 100005。 |
| `industry` | `Any` | 否 | `None` | `104110000` | 申万行业 ID（104xx0000 形态）；中信码在本接口报 100005。支持单值或列表。 |
| `broker` | `Any` | 否 | `None` | `None` | 券商/机构过滤，支持单值或列表。 |
| `rating` | `Any` | 否 | `None` | `None` | 评级过滤，支持单值或列表。 |
| `rating_change` | `Any` | 否 | `None` | `None` | 评级变动过滤，支持单值或列表。 |
| `with_content` | `bool` | 否 | `False` | `False` | True=走旧版 v1 列表直接带原文与译文（30 积分/条，超时 / 5xx 不自动重发），content / contentTranslate 在顶层、不含 brief。默认 False 只含摘要 brief / briefTranslate（1 积分/条），正文改用 insight.foreign_opinion_detail 按 ID 取。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（默认 1 积分/条，with_content=True 为 30 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.independent_opinion_list`

- 接口：`insight.independent-opinion.list` `POST /application/open-insight/independent-opinion/getList`
- 同步示例：`sample/sync/insight_independent_opinion_list.py`
- 异步示例：`sample/async/insight_independent_opinion_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `rank_type` | `int` | 否 | `1` | `1` | 排序方式代码。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `industry` | `Any` | 否 | `None` | `104110000` | 申万行业 ID（104xx0000 形态）；中信码在本接口报 100005。支持单值或列表。 |
| `rating` | `Any` | 否 | `None` | `None` | 评级过滤，支持单值或列表。 |
| `rating_change` | `Any` | 否 | `None` | `None` | 评级变动过滤，支持单值或列表。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.official_account_list`

- 接口：`insight.official-account.list` `POST /application/open-insight/officialAccount/getList`
- 同步示例：`sample/sync/insight_official_account_list.py`
- 异步示例：`sample/async/insight_official_account_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；省略则按 endpoint 最大页大小 50 自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"泡泡玛特"` | 搜索关键词；需用数据中的具体词，不能用整句白话。 |
| `search_type` | `int` | 否 | `1` | `2` | 搜索方式：1=标题（默认） 2=全文。 |
| `rank_type` | `int` | 否 | `1` | `2` | 排序方式：1=综合（默认） 2=时间倒序。 |
| `account_id` | `Any` | 否 | `None` | `None` | 公众号 ID 过滤，取自列表返回的 accountId 列，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"report"` | 文章类型，支持单值或列表，枚举：news/law/report/view/data/event/meeting/notice/recruit/investEdu/brand/notes/other。 |
| `industry` | `Any` | 否 | `None` | `104110000` | 行业 ID，申万码与中信码均可；支持单值或列表。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.summary_download`

- 接口：`insight.summary.download` `GET /application/open-insight/summary/v2/download/file`
- 同步示例：`sample/sync/insight_summary_download.py`
- 异步示例：`sample/async/insight_summary_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `summary_id` | `str` | 是 | - | `"<summaryId>"` | 纪要 ID，通常来自 insight.summary_list 返回结果。 |
| `file_type` | `int \| None` | 否 | `None` | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `insight.research_download`

- 接口：`insight.research.download` `GET /application/open-insight/broker-report/download/file`
- 同步示例：`sample/sync/insight_research_download.py`
- 异步示例：`sample/async/insight_research_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `report_id` | `str` | 是 | - | `"<reportId>"` | 研报 ID，通常来自 research/foreign_report 列表接口。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `insight.foreign_report_download`

- 接口：`insight.foreign-report.download` `GET /application/open-insight/foreign-report/download/file`
- 同步示例：`sample/sync/insight_foreign_report_download.py`
- 异步示例：`sample/async/insight_foreign_report_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `report_id` | `str` | 是 | - | `"<reportId>"` | 研报 ID，通常来自 research/foreign_report 列表接口。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `insight.announcement_download`

- 接口：`insight.announcement.download` `GET /application/open-insight/announcement/download/file`
- 同步示例：`sample/sync/insight_announcement_download.py`
- 异步示例：`sample/async/insight_announcement_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `announcement_id` | `str` | 是 | - | `"<announcementId>"` | 公告 ID，通常来自 announcement 列表接口。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `insight.announcement_hk_download`

- 接口：`insight.announcement-hk.download` `GET /application/open-insight/announcement-hk/download/file`
- 同步示例：`sample/sync/insight_announcement_hk_download.py`
- 异步示例：`sample/async/insight_announcement_hk_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `announcement_id` | `str` | 是 | - | `"<announcementId>"` | 公告 ID，通常来自 announcement 列表接口。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型：1=原文（默认） 2=Markdown。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `insight.announcement_us_download`

- 接口：`insight.announcement-us.download` `GET /application/open-insight/announcement-us/download/file`
- 同步示例：`sample/sync/insight_announcement_us_download.py`
- 异步示例：`sample/async/insight_announcement_us_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `announcement_id` | `str` | 是 | - | `"<announcementId>"` | 美股公告 ID，通常来自 insight.announcement_us_list 返回的 announcementId 列。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型：1=原文 PDF（默认） 2=Markdown。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `insight.independent_opinion_download`

- 接口：`insight.independent-opinion.download` `GET /application/open-insight/independent-opinion/download/file`
- 同步示例：`sample/sync/insight_independent_opinion_download.py`
- 异步示例：`sample/async/insight_independent_opinion_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `independent_opinion_id` | `str` | 是 | - | `"<independentOpinionId>"` | 独立观点 ID，通常来自 independent_opinion_list。 |
| `file_type` | `int` | 是 | - | `1` | 文件类型代码；下载接口常用 1。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 🔴 本方法**不支持** `True`（发请求前报 `ValidationError`）：其 list 按 1 积分/条计费，回查 200 条要 200 积分只为一个文件名。先调 `independent_opinion_list()` 让标题进缓存，下载自动命中（免费）。参数保留只为签名兼容。 |

### `insight.official_account_download`

- 接口：`insight.official-account.download` `GET /application/open-insight/officialAccount/download/file`
- 同步示例：`sample/sync/insight_official_account_download.py`
- 异步示例：`sample/async/insight_official_account_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `article_id` | `str` | 是 | - | `"<articleId>"` | 文章 ID，通常来自 official_account_list 返回的 articleId 列。 |
| `file_type` | `int` | 否 | `1` | `1` | 文件类型：1=txt（默认） 2=HTML。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.txt")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `insight.qa_list`

- 接口：`insight.qa.list` `POST /application/open-insight/Q&A-data/getList`
- 同步示例：`sample/sync/insight_qa_list.py`
- 异步示例：`sample/async/insight_qa_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"601012.SH"` | 证券代码，按单只证券提取投资者问答。 |
| `from_` | `int` | 否 | `0` | `0` | 起始偏移。 |
| `size` | `int \| None` | 否 | `None` | `20` | 返回条数；省略=拉全量（自动翻页，单页上限 500）。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-01-01"` | 开始时间，`yyyy-MM-dd` 或 `yyyy-MM-dd HH:mm:ss`（字符串直传）。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-07-01"` | 结束时间，格式同上。 |
| `source` | `Any` | 否 | `None` | `["conference", "interactive"]` | 问题来源，支持单值或列表；枚举：`conference` 电话会议 / `interactive` 互动平台 / `survey` 调研纪要。 |
| `question_category` | `Any` | 否 | `None` | `["productAndBusiness"]` | 问题类型（11 类），支持单值或列表；拼错服务端报 100003：`productAndBusiness` / `capacityAndProjects` / `ordersAndCustomers` / `financialData` / `materialEvents` / `capitalOperations` / `shareholdersAndDividends` / `corporateGovernance` / `marketAndValuation` / `macroAndIndustry` / `risksAndOthers`。 |
| `answer_important` | `Any` | 否 | `None` | `1` | 答案是否涉及重要信息：`1`=是 `0`=否；可多选，省略=不筛。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.report_image_list`

- 接口：`insight.report-image.list` `POST /application/open-insight/report-image/getList`
- 同步示例：`sample/sync/insight_report_image_list.py`
- 异步示例：`sample/async/insight_report_image_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"AI"` | 搜索关键词，如 `AI`、`新能源汽车`。 |
| `top` | `int` | 否 | `10` | `20` | 最大返回数，默认 10，上限 20（超限本地报错；服务端会静默截断）。 |
| `source_id` | `str \| None` | 否 | `None` | `"<研报ID>"` | 限定到某篇研报（可从研报列表或知识库取）。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-01-01"` | 限定图片所属研报发布时间，`yyyy-MM-dd HH:mm:ss`（`yyyy-MM-dd` 自动补全）。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-07-01 23:59:59"` | 结束时间，格式同上。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `insight.report_image_download`

- 接口：`insight.report-image.download` `GET /application/open-insight/report-image/download/file`
- 同步示例：`sample/sync/insight_report_image_download.py`
- 异步示例：`sample/async/insight_report_image_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `chunk_id` | `str` | 是 | - | `"<chunkId>"` | 图片唯一标识，取自 report_image_list 返回的 chunkId 列。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/img.jpg")` | 下载保存路径；None 时按服务端文件名或 `report-image-<chunkId>` 自动命名。 |

### `insight.opinion_detail`

- 接口：`insight.opinion.detail` `POST /application/open-insight/chief-opinion/getDetail`
- 同步示例：`sample/sync/insight_opinion_detail.py`
- 异步示例：`sample/async/insight_opinion_detail.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `chief_opinion_id` | `Any` | 是 | - | `"<chiefOpinionId>"` | 国内首席观点 ID（取自 insight.opinion_list 返回的 chiefOpinionId），支持单值或列表。返回字段同列表行，另加 content（正文全文）。 |
| `raw` | `bool` | 否 | `False` | `False` | True 返回 dict：`{total, list, missingIds?, unfetchedIds?, unfetchedError?, partial?}`；False 返回 list 的 DataFrame（缺失 / 未取到的 ID 只在 dict 与 UserWarning 里）。 |

**说明**：去重后按 20 个一批依次请求，30 积分/条（按返回条数计），超时 / 5xx 不自动重发。没有有效正文的 ID 不报错、直接跳过——列在 `missingIds` 并标 `partial` + UserWarning；某一批失败或返回异常时已取到的正文保留，没取到的 ID 在 `unfetchedIds`、原因在 `unfetchedError`（message / code / traceId），只对这些 ID 重跑即可；第一批就失败且一条正文都没拿到时直接抛出原错误。

### `insight.foreign_opinion_detail`

- 接口：`insight.foreign-opinion.detail` `POST /application/open-insight/foreign-opinion/getDetail`
- 同步示例：`sample/sync/insight_foreign_opinion_detail.py`
- 异步示例：`sample/async/insight_foreign_opinion_detail.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `foreign_opinion_id` | `Any` | 是 | - | `"<foreignOpinionId>"` | 海外机构观点 ID（取自 insight.foreign_opinion_list 返回的 foreignOpinionId），支持单值或列表。返回字段同列表行，另加 content（原文）/ contentTranslate（中文译文）。 |
| `raw` | `bool` | 否 | `False` | `False` | True 返回 dict：`{total, list, missingIds?, unfetchedIds?, unfetchedError?, partial?}`；False 返回 list 的 DataFrame（缺失 / 未取到的 ID 只在 dict 与 UserWarning 里）。 |

**说明**：去重后按 20 个一批依次请求，30 积分/条（按返回条数计），超时 / 5xx 不自动重发。没有有效正文的 ID 不报错、直接跳过——列在 `missingIds` 并标 `partial` + UserWarning；某一批失败或返回异常时已取到的正文保留，没取到的 ID 在 `unfetchedIds`、原因在 `unfetchedError`（message / code / traceId），只对这些 ID 重跑即可；第一批就失败且一条正文都没拿到时直接抛出原错误。

### `insight.highlight_list`

- 接口：`insight.highlight.list` `POST /application/open-insight/summary/highlight/getList`
- 同步示例：`sample/sync/insight_highlight_list.py`
- 异步示例：`sample/async/insight_highlight_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。from_ + 条数不能超过 10000，from_ ≥ 10000 本地拒绝。 |
| `size` | `int \| None` | 否 | `None` | `10` | 条数；单页上限 50，超出自动翻页。🔴 5 积分/条，务必带 size。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-09-01 00:00:00"` | 开始时间：yyyy-MM-dd HH:mm:ss，也接受 yyyy-MM-dd；可查历史前溯 3 个月（试用账号 1 个月），超出报 110003。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-09-07 23:59:59"` | 结束时间，格式同 start_time。 |
| `security` | `Any` | 否 | `None` | `"09992.HK"` | 证券代码，大小写敏感、精确匹配（A 股 601702.SH、港股 5 位数字 09992.HK、美股 AAPL.O）；支持单值或列表。 |
| `research_area` | `Any` | 否 | `None` | `"100800101"` | 研究方向：中信行业码 1008001xx 或 Gangtise 方向码 122000xxx；**不认申万码**。支持单值或列表。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（5 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分（约 200 条）本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

**返回字段**：highlightId / title（会议名称）/ publishTime / content（**HTML 片段**，<p> 包裹、小标题 <strong>）/ securityList / researchAreaList。固定按发布时间倒序；要点可能不关联任何证券（securityList 为 []）。

## 基本面（`gangtise.fundamental`）

### `fundamental.income_statement`

- 接口：`fundamental.income-statement` `POST /application/open-fundamental/financial-report/income-statement/accumulated`
- 同步示例：`sample/sync/fundamental_income_statement.py`
- 异步示例：`sample/async/fundamental_income_statement.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。⚠️ 返回的是最新版本数值：重述过的报告期在 `consolidated` 下也是重述后数值，`announcementDate` 是该数值所属公告的日期，`earliestAnncDate` 是该期首次公告日。做时点回测别把这些数值按 `earliestAnncDate` 回填（会用到当时还没公布的重述值）；数值从 `announcementDate` 起可得，首次披露的原始数不在返回里。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.income_statement_quarterly`

- 接口：`fundamental.income-statement-quarterly` `POST /application/open-fundamental/financial-report/income-statement/quarterly`
- 同步示例：`sample/sync/fundamental_income_statement_quarterly.py`
- 异步示例：`sample/async/fundamental_income_statement_quarterly.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。⚠️ 返回的是最新版本数值：重述过的报告期在 `consolidated` 下也是重述后数值，`announcementDate` 是该数值所属公告的日期，`earliestAnncDate` 是该期首次公告日。做时点回测别把这些数值按 `earliestAnncDate` 回填（会用到当时还没公布的重述值）；数值从 `announcementDate` 起可得，首次披露的原始数不在返回里。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.balance_sheet`

- 接口：`fundamental.balance-sheet` `POST /application/open-fundamental/financial-report/balance-sheet/accumulated`
- 同步示例：`sample/sync/fundamental_balance_sheet.py`
- 异步示例：`sample/async/fundamental_balance_sheet.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。⚠️ 返回的是最新版本数值：重述过的报告期在 `consolidated` 下也是重述后数值，`announcementDate` 是该数值所属公告的日期，`earliestAnncDate` 是该期首次公告日。做时点回测别把这些数值按 `earliestAnncDate` 回填（会用到当时还没公布的重述值）；数值从 `announcementDate` 起可得，首次披露的原始数不在返回里。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.cash_flow`

- 接口：`fundamental.cash-flow` `POST /application/open-fundamental/financial-report/cash-flow-statement/accumulated`
- 同步示例：`sample/sync/fundamental_cash_flow.py`
- 异步示例：`sample/async/fundamental_cash_flow.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。⚠️ 返回的是最新版本数值：重述过的报告期在 `consolidated` 下也是重述后数值，`announcementDate` 是该数值所属公告的日期，`earliestAnncDate` 是该期首次公告日。做时点回测别把这些数值按 `earliestAnncDate` 回填（会用到当时还没公布的重述值）；数值从 `announcementDate` 起可得，首次披露的原始数不在返回里。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.cash_flow_quarterly`

- 接口：`fundamental.cash-flow-quarterly` `POST /application/open-fundamental/financial-report/cash-flow-statement/quarterly`
- 同步示例：`sample/sync/fundamental_cash_flow_quarterly.py`
- 异步示例：`sample/async/fundamental_cash_flow_quarterly.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。⚠️ 返回的是最新版本数值：重述过的报告期在 `consolidated` 下也是重述后数值，`announcementDate` 是该数值所属公告的日期，`earliestAnncDate` 是该期首次公告日。做时点回测别把这些数值按 `earliestAnncDate` 回填（会用到当时还没公布的重述值）；数值从 `announcementDate` 起可得，首次披露的原始数不在返回里。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.income_statement_hk`

- 接口：`fundamental.income-statement-hk` `POST /application/open-fundamental/financial-report/income-statement/hk`
- 同步示例：`sample/sync/fundamental_income_statement_hk.py`
- 异步示例：`sample/async/fundamental_income_statement_hk.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.balance_sheet_hk`

- 接口：`fundamental.balance-sheet-hk` `POST /application/open-fundamental/financial-report/balance-sheet/hk`
- 同步示例：`sample/sync/fundamental_balance_sheet_hk.py`
- 异步示例：`sample/async/fundamental_balance_sheet_hk.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.cash_flow_hk`

- 接口：`fundamental.cash-flow-hk` `POST /application/open-fundamental/financial-report/cash-flow-statement/hk`
- 同步示例：`sample/sync/fundamental_cash_flow_hk.py`
- 异步示例：`sample/async/fundamental_cash_flow_hk.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.income_statement_us`

- 接口：`fundamental.income-statement-us` `POST /application/open-fundamental/financial-report/income-statement/us`
- 同步示例：`sample/sync/fundamental_income_statement_us.py`
- 异步示例：`sample/async/fundamental_income_statement_us.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"AAPL.O"` | 单个美股代码，例如 AAPL.O、TSLA.O。 |
| `start_date` | `str \| None` | 否 | `None` | `"2024-01-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"annual"` | 美股报告期：q1/h1/q3/nsd/annual/latest，支持单值或列表。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.balance_sheet_us`

- 接口：`fundamental.balance-sheet-us` `POST /application/open-fundamental/financial-report/balance-sheet/us`
- 同步示例：`sample/sync/fundamental_balance_sheet_us.py`
- 异步示例：`sample/async/fundamental_balance_sheet_us.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"AAPL.O"` | 单个美股代码，例如 AAPL.O、TSLA.O。 |
| `start_date` | `str \| None` | 否 | `None` | `"2024-01-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"annual"` | 美股报告期：q1/h1/q3/nsd/annual/latest，支持单值或列表。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.cash_flow_us`

- 接口：`fundamental.cash-flow-us` `POST /application/open-fundamental/financial-report/cash-flow-statement/us`
- 同步示例：`sample/sync/fundamental_cash_flow_us.py`
- 异步示例：`sample/async/fundamental_cash_flow_us.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"AAPL.O"` | 单个美股代码，例如 AAPL.O、TSLA.O。 |
| `start_date` | `str \| None` | 否 | `None` | `"2024-01-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"annual"` | 美股报告期：q1/h1/q3/nsd/annual/latest，支持单值或列表。 |
| `report_type` | `Any` | 否 | `None` | `None` | 报表类型：`consolidated` 合并（默认）/ `consolidatedRestated` 合并（调整）/ `standalone` 母公司 / `standaloneRestated` 母公司（调整）；支持单值或列表。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.main_business`

- 接口：`fundamental.main-business` `POST /application/open-fundamental/main-business`
- 同步示例：`sample/sync/fundamental_main_business.py`
- 异步示例：`sample/async/fundamental_main_business.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `breakdown` | `str` | 否 | `'product'` | `"product"` | 主营构成维度，例如 product 或 industry。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或字段名列表；None 表示使用服务端默认字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.valuation_analysis`

- 接口：`fundamental.valuation-analysis` `POST /application/open-fundamental/valuation-analysis`
- 同步示例：`sample/sync/fundamental_valuation_analysis.py`
- 异步示例：`sample/async/fundamental_valuation_analysis.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"600519.SH"` | 单个 A 股证券代码（港股 / 美股报 120001）。 |
| `indicator` | `str` | 是 | - | `"peTtm"` | 估值指标：peTtm / pbMrq / peg / psTtm / pcfTtm / em。 |
| `start_date` | `str \| None` | 否 | `None` | `"2025-01-01"` | 开始日期 YYYY-MM-DD。早于账号回溯下界时接口从下界起返回、不报错；首行晚于 start_date 时发 UserWarning（上市较晚或撞了权限窗口）。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期 YYYY-MM-DD。 |
| `limit` | `int \| None` | 否 | `None` | `600` | 返回行数上限，省略时按接口默认 2000 显式发送（正整数，否则本地抛 ValidationError）。🔴 序列按自然日逐日一行（含周末），超出时接口**保留最近的行、丢掉区间开头**；行数撞满即标 partial + UserWarning（首行恰好就是 start_date 时不标）。取 N 年设 limit ≥ 366 × N。 |
| `field` | `Any` | 否 | `None` | `["value", "percentileRank"]` | 返回字段，至少含一个数值列（value / percentileRank / average / median / upper1Std / lower1Std）：只传 tradeDate 时接口返回 0 行不报错（SDK 发 UserWarning）；不存在的名字（含 securityCode）整条报 100005 并点名。tradeDate 总在第一列返回，SDK 发请求前去掉它并去重（只传 tradeDate 一项时照常发）。 |
| `skip_null` | `bool` | 否 | `False` | `True` | 丢弃 value 或 percentileRank 为空的行；field 没点名这两列时 SDK 补取、过滤后删掉，输出列仍由 field 决定。raw=True 时不生效。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（撞满 limit 时带 partial: True）；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.top_holders`

- 接口：`fundamental.top-holders` `POST /application/open-fundamental/capital-structure/top-holders`
- 同步示例：`sample/sync/fundamental_top_holders.py`
- 异步示例：`sample/async/fundamental_top_holders.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `holder_type` | `str` | 是 | - | `"top10"` | 股东类型，例如 top10 或 top10Float。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `fiscal_year` | `Any` | 否 | `None` | `2025` | 财年过滤，支持单值或列表。 |
| `period` | `Any` | 否 | `None` | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `fundamental.earning_forecast`

- 接口：`fundamental.earning-forecast` `POST /application/open-fundamental/earning-forecast`
- 同步示例：`sample/sync/fundamental_earning_forecast.py`
- 异步示例：`sample/async/fundamental_earning_forecast.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"600519.SH"` | 单个 A 股证券代码（港股 / 美股报 120001）。 |
| `start_date` | `str \| None` | 否 | `None` | `"2025-01-01"` | 开始日期 YYYY-MM-DD；省略时取 end_date 前一年。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期 YYYY-MM-DD；省略时取**北京时间**当天（与机器时区无关）。 |
| `consensus` | `Any` | 否 | `None` | `["netIncome", "eps"]` | 一致预期指标，支持单值或列表：netIncome / netIncomeYoy / eps / pe / bps / pb / peg / roe / ps（roe 单位是 %）。 |
| `latest` | `bool` | 否 | `True` | `True` | 仅保留最近一次更新的预测；传 False 返回区间内每一次更新。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费 0.5 积分/条，行数随区间增长：发请求前按「工作日数 × 3 条 × 0.5」估算，超过 1000 积分（约两年半）抛 ValidationError、不发请求；缩短区间，或 confirm=True 确认发送。超时 / 5xx 不自动重试。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

## AI 生成内容（`gangtise.ai`）

### `ai.knowledge_batch`

- 接口：`ai.knowledge-batch` `POST /application/open-data/ai/search/knowledge/batch`
- 同步示例：`sample/sync/ai_knowledge_batch.py`
- 异步示例：`sample/async/ai_knowledge_batch.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `query` | `Any` | 是 | - | `"贵州茅台"` | 知识库检索问题，支持字符串或列表（最多 5 个，由接口校验）；**每个 query 整段送出**，句中逗号不会被拆成两个查询。 |
| `top` | `int` | 否 | `10` | `3` | 每个查询返回的最大候选数。 |
| `resource_type` | `Any` | 否 | `None` | `10` | 资源类型：10=券商研报 / 11=外资研报 / 20=内部报告 / 40=首席观点 / 50=公司公告 / 51=港股公告 / 60=会议平台纪要 / 70=调研纪要公告 / 80=网络资源纪要 / 90=产业公众号；支持单值或列表。 |
| `knowledge_name` | `Any` | 否 | `None` | `"system_knowledge_doc"` | 知识库：system_knowledge_doc=系统知识库 / tenant_knowledge_doc=机构知识库；支持单值或列表。 |
| `start_time` | `int \| str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间：日期 / 日期时间字符串或 10/13 位时间戳，按北京时间换算成 13 位毫秒发出。 |
| `end_time` | `int \| str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间，换算同 start_time；**只写日期时按当日 23:59:59 换算**，与 start_time 写同一天即查这一整天。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.security_clue_list`

- 接口：`ai.security-clue.list` `POST /application/open-ai/security-clue/getList`
- 同步示例：`sample/sync/ai_security_clue_list.py`
- 异步示例：`sample/async/ai_security_clue_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `start_time` | `str` | 是 | - | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str` | 是 | - | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `query_mode` | `str` | 是 | - | `"bySecurity"` | 线索查询模式：bySecurity=按证券（gts_code 传股票代码，如 600519.SH），byIndustry=按行业（gts_code 传申万行业码，如 821035.SWI）。 |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `gts_code` | `Any` | 否 | `None` | `["000001.SZ"]` | 股票代码（bySecurity，如 600519.SH）或申万行业码（byIndustry，如 821035.SWI）。**服务端要求非空**，缺省报 410120。支持单值或列表。 |
| `source` | `Any` | 否 | `None` | `"researchReport"` | 来源：researchReport / conference / announcement / view，支持单值或列表；其他取值本地报错（接口对错值不报错，会返回不按来源过滤的全部结果并照常计费）。请求字段为 source。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（5 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.stock_summary_list`

- 接口：`ai.stock-summary.list` `POST /application/open-ai/stock-summary/getList`
- 同步示例：`sample/sync/ai_stock_summary_list.py`
- 异步示例：`sample/async/ai_stock_summary_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"600519.SH"` | 证券代码或代码列表（仅 A 股 / 港股），本接口 2026-08-14 起不再支持市场关键词；留空抛 ValidationError 以防全市场积分误耗。**单次最多 6000 只**（接口上限，本地同值拦截并提示分批）。1 积分/条，无看点的证券不在返回里、不计费，返回行数少于提交数是正常的。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.one_pager`

- 接口：`ai.one-pager` `POST /application/open-ai/agent/one-pager`
- 同步示例：`sample/sync/ai_one_pager.py`
- 异步示例：`sample/async/ai_one_pager.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.investment_logic`

- 接口：`ai.investment-logic` `POST /application/open-ai/agent/investment-logic`
- 同步示例：`sample/sync/ai_investment_logic.py`
- 异步示例：`sample/async/ai_investment_logic.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.peer_comparison`

- 接口：`ai.peer-comparison` `POST /application/open-ai/agent/peer-comparison`
- 同步示例：`sample/sync/ai_peer_comparison.py`
- 异步示例：`sample/async/ai_peer_comparison.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.research_outline`

- 接口：`ai.research-outline` `POST /application/open-ai/agent/research-outline`
- 同步示例：`sample/sync/ai_research_outline.py`
- 异步示例：`sample/async/ai_research_outline.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.theme_tracking`

- 接口：`ai.theme-tracking` `POST /application/open-ai/agent/theme-tracking`
- 同步示例：`sample/sync/ai_theme_tracking.py`
- 异步示例：`sample/async/ai_theme_tracking.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `theme_id` | `str` | 是 | - | `"121000342"` | 主题 ID，可通过 reference.concept_search 按关键词查询。 |
| `date` | `str` | 是 | - | `"2026-05-28"` | 业务日期，格式通常为 YYYY-MM-DD。 |
| `type_` | `Any` | 否 | `None` | `"news"` | 类型过滤；Python 参数名 type_ 会映射为 type。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.hot_topic`

- 接口：`ai.hot-topic` `POST /application/open-ai/hot-topic/getList`
- 同步示例：`sample/sync/ai_hot_topic.py`
- 异步示例：`sample/async/ai_hot_topic.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `category` | `Any` | 否 | `None` | `"morningBriefing"` | 报告类型：morningBriefing=早报 / noonBriefing=午报 / afternoonFlash=盘中快报 / eveningBriefing=晚报；支持单值或列表，省略=全部；其他取值本地报错。计费 10 积分/篇（一篇=一整份报告）。 |
| `with_related_securities` | `bool` | 否 | `True` | `True` | 热点主题是否返回关联证券。 |
| `with_close_reading` | `bool` | 否 | `True` | `True` | 热点主题是否返回精读内容。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（10 积分/篇）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.management_discuss_announcement`

- 接口：`ai.management-discuss-announcement` `POST /application/open-ai/management-discuss/from-announcement`
- 同步示例：`sample/sync/ai_management_discuss_announcement.py`
- 异步示例：`sample/async/ai_management_discuss_announcement.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `report_date` | `str` | 是 | - | `"2025-12-31"` | 报告期日期，例如 2025-12-31。 |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `dimension` | `str` | 是 | - | `"all"` | 管理层讨论维度，例如 all 或 businessOperation。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.management_discuss_earnings_call`

- 接口：`ai.management-discuss-earnings-call` `POST /application/open-ai/management-discuss/from-earningsCall`
- 同步示例：`sample/sync/ai_management_discuss_earnings_call.py`
- 异步示例：`sample/async/ai_management_discuss_earnings_call.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `report_date` | `str` | 是 | - | `"2025-12-31"` | 报告期日期，例如 2025-12-31。 |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `dimension` | `str` | 是 | - | `"all"` | 管理层讨论维度，例如 all 或 businessOperation。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.management_sentiment_indicator`

- 接口：`ai.management-sentiment-indicator` `POST /application/open-ai/management-sentiment/company/indicator`
- 同步示例：`sample/sync/ai_management_sentiment_indicator.py`
- 异步示例：`sample/async/ai_management_sentiment_indicator.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

管理层在业绩会问答里的三维情绪评分：正面回应程度 `sentimentResponsiveness`、回复乐观度 `sentimentPolarity`、回复确定度 `sentimentConviction`（0–5），有效问答数 `qaCount`，回避 / 风险 / 低确定度占比（百分数，`7.14` 即 7.14%），按问题类型拆分的 `questionCategoryList`。一行 = 一只证券 × 一场会议，按发布时间倒序；`source.sourceId` 传给 `management_sentiment_detail`。`publishTime` 是北京时间，与 `start_time` / `end_time` 的筛选同一口径。

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 返回条数；单页上限 100，超出自动翻页。🔴 5 积分/条，务必带 size。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-08-01"` | 发布时间起（北京时间）：YYYY-MM-DD、YYYY-MM-DD HH:mm:ss 或 10 / 13 位时间戳；写时刻须带秒（HH:mm 报 110001）。范围正式账号前溯 1 年、试用 6 个月，早于范围报 110003。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-10-23"` | 发布时间止（北京时间），写法同 start_time；只写日期时含当天整天。 |
| `security` | `Any` | 否 | `None` | `"300285.SZ"` | 证券代码或列表，只收具体代码（市场关键词报 120001），任一代码非法整批报 120001；**不传 = 全部证券**。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（5 积分/条）的额度确认：省略 size 时按 total × 单价估算（先取 1 条拿到 total）、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.management_sentiment_conclusion`

- 接口：`ai.management-sentiment-conclusion` `POST /application/open-ai/management-sentiment/company/conclusion`
- 同步示例：`sample/sync/ai_management_sentiment_conclusion.py`
- 异步示例：`sample/async/ai_management_sentiment_conclusion.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

每场业绩会的情绪结论文本 `sentimentSummary`、三维信号文本 `sentimentSignal`（不含分数）与较上一场同一事项的问答对照 `qaSentimentContrast`，对比基准见 `previousSource`；没有可比的上一场时 `qaSentimentContrast` 为 `[]`、`previousSource` 为 `null`。行粒度与参数同 `management_sentiment_indicator`；`publishTime`（含 `previousSource.publishTime`）是北京时间。

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 返回条数；单页上限 100，超出自动翻页。🔴 5 积分/条，务必带 size。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-08-01"` | 发布时间起（北京时间）：YYYY-MM-DD、YYYY-MM-DD HH:mm:ss 或 10 / 13 位时间戳；写时刻须带秒（HH:mm 报 110001）。范围正式账号前溯 1 年、试用 6 个月，早于范围报 110003。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-10-23"` | 发布时间止（北京时间），写法同 start_time；只写日期时含当天整天。 |
| `security` | `Any` | 否 | `None` | `"300285.SZ"` | 证券代码或列表，只收具体代码（市场关键词报 120001），任一代码非法整批报 120001；**不传 = 全部证券**。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（5 积分/条）的额度确认：省略 size 时按 total × 单价估算（先取 1 条拿到 total）、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.management_sentiment_detail`

- 接口：`ai.management-sentiment-detail` `POST /application/open-ai/management-sentiment/company/detail`
- 同步示例：`sample/sync/ai_management_sentiment_detail.py`
- 异步示例：`sample/async/ai_management_sentiment_detail.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

一场业绩会的全部问答（一次返回、不分页），每条给三维档位 `qaResponsiveness` / `qaPolarity` / `qaConviction`（只取 `5.0` / `2.5` / `0.0`）与依据（`*Quote` 回答原文节选、`*Reason` 判断理由）。计费 10 积分/次，超时 / 5xx 不自动重发。

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `source_id` | `str` | 是 | - | `"554030"` | 取自 management_sentiment_indicator / management_sentiment_conclusion 返回行的 source.sourceId。写错不报错、返回空结果。 |
| `source_type` | `str` | 否 | `"conference"` | `"conference"` | 取自同一行的 source.sourceType；目前只有 conference（电话会议）。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.earnings_review`

- 接口：`ai.earnings-review.get-id` `POST /application/open-ai/agent/earnings-review-getid`<br>`ai.earnings-review.get-content` `POST /application/open-ai/agent/earnings-review-getcontent`
- 同步示例：`sample/sync/ai_earnings_review.py`
- 异步示例：`sample/async/ai_earnings_review.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security_code` | `str` | 是 | - | `"000001.SZ"` | 单个证券代码，例如 000001.SZ、600519.SH、00700.HK。 |
| `period` | `str` | 是 | - | `"2025annual"` | 报告期/财报期；AI 财报点评常用 2025annual、2026q1。 |
| `wait` | `bool` | 否 | `True` | `False` | 异步生成类接口是否阻塞轮询到内容完成。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.earnings_review_check`

- 接口：`ai.earnings-review.get-content` `POST /application/open-ai/agent/earnings-review-getcontent`
- 同步示例：`sample/sync/ai_earnings_review_check.py`
- 异步示例：`sample/async/ai_earnings_review_check.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `data_id` | `str` | 是 | - | `"<dataId>"` | 异步生成任务 ID，由 *_review 或 *_debate wait=False 返回。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.viewpoint_debate`

- 接口：`ai.viewpoint-debate.get-id` `POST /application/open-ai/agent/viewpoint-debate-getid`<br>`ai.viewpoint-debate.get-content` `POST /application/open-ai/agent/viewpoint-debate-getcontent`
- 同步示例：`sample/sync/ai_viewpoint_debate.py`
- 异步示例：`sample/async/ai_viewpoint_debate.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `viewpoint` | `str` | 是 | - | `"白酒行业估值修复具备持续性"` | 待辩论的投资观点文本，建议不超过 1000 字。 |
| `wait` | `bool` | 否 | `True` | `False` | 异步生成类接口是否阻塞轮询到内容完成。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.viewpoint_debate_check`

- 接口：`ai.viewpoint-debate.get-content` `POST /application/open-ai/agent/viewpoint-debate-getcontent`
- 同步示例：`sample/sync/ai_viewpoint_debate_check.py`
- 异步示例：`sample/async/ai_viewpoint_debate_check.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `data_id` | `str` | 是 | - | `"<dataId>"` | 异步生成任务 ID，由 *_review 或 *_debate wait=False 返回。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `ai.knowledge_resource_download`

- 接口：`ai.knowledge-resource.download` `GET /application/open-data/ai/resource/download`
- 同步示例：`sample/sync/ai_knowledge_resource_download.py`
- 异步示例：`sample/async/ai_knowledge_resource_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `resource_type` | `int` | 是 | - | `1` | 知识资源类型代码。 |
| `source_id` | `str` | 是 | - | `"<sourceId>"` | 知识资源源 ID。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |

## 个人云盘与股票池（`gangtise.vault`）

### `vault.drive_list`

- 接口：`vault.drive.list` `POST /application/open-vault/drive/getList`
- 同步示例：`sample/sync/vault_drive_list.py`
- 异步示例：`sample/async/vault_drive_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `file_type` | `Any` | 否 | `None` | `1` | 文件类型代码；下载接口常用 1。 |
| `space_type` | `Any` | 否 | `None` | `None` | 空间类型过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.record_list`

- 接口：`vault.record.list` `POST /application/open-vault/record/getList`
- 同步示例：`sample/sync/vault_record_list.py`
- 异步示例：`sample/async/vault_record_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `category` | `Any` | 否 | `None` | `"upload"` | 录音来源：upload / link / mobile / gtNote / pc / share；支持单值或列表。 |
| `space_type` | `Any` | 否 | `None` | `None` | 空间类型过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.my_conference_list`

- 接口：`vault.my-conference.list` `POST /application/open-vault/my-conference/getList`
- 同步示例：`sample/sync/vault_my_conference_list.py`
- 异步示例：`sample/async/vault_my_conference_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `research_area` | `Any` | 否 | `None` | `None` | 研究领域 ID，支持单值或列表。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `institution` | `Any` | 否 | `None` | `None` | 机构过滤，支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"earningsCall"` | 会议分类，例如 earningsCall / strategyMeeting；支持单值或列表。 |
| `source` | `Any` | 否 | `None` | `[1, 2]` | 录制来源（数字，支持单值或列表）：1=企微会议助理 2=会议服务微信群。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费 0.1 积分/条：省略 size 时按 total × 单价估算，超过 1000 积分拒绝；传 size 取一部分，或 confirm=True 确认全量。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.wechat_message_list`

- 接口：`vault.wechat-message.list` `POST /application/open-vault/wechatgroupmsg/list`
- 同步示例：`sample/sync/vault_wechat_message_list.py`
- 异步示例：`sample/async/vault_wechat_message_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 分页大小；部分接口会按 endpoint 最大页大小自动分页。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-05-01"` | 开始时间过滤；多数列表接口接受日期或时间字符串。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-05-28"` | 结束时间过滤；多数列表接口接受日期或时间字符串。 |
| `keyword` | `str \| None` | 否 | `None` | `"平安银行"` | 搜索关键词。 |
| `security` | `Any` | 否 | `None` | `"000001.SZ"` | 证券代码或代码列表，例如 000001.SZ；部分行情接口也支持 all。 |
| `wechat_group_id` | `Any` | 否 | `None` | `None` | 微信群 ID，支持单值或列表。 |
| `industry` | `Any` | 否 | `None` | `100800101` | 中信行业 ID（1008001xx 形态）；申万码与未知值在本接口报 100005。支持单值或列表。 |
| `category` | `Any` | 否 | `None` | `"text"` | 消息类型：text / image / documents / url；支持单值或列表。 |
| `tag` | `Any` | 否 | `None` | `None` | 标签过滤，支持单值或列表。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.wechat_chatroom_list`

- 接口：`vault.wechat-chatroom.list` `POST /application/open-vault/wechatgroupmsg/chatroomId`
- 同步示例：`sample/sync/vault_wechat_chatroom_list.py`
- 异步示例：`sample/async/vault_wechat_chatroom_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 分页起始偏移量；Python 参数名 from_ 会映射为请求字段 from。 |
| `size` | `int \| None` | 否 | `None` | `5` | 省略则拉取全部群（接口返回 {total, list}，按 total 并发翻页，单页上限 50）；传 N 仅取前 N 条。 |
| `room_name` | `Any` | 否 | `None` | `"投研"` | 微信群名称或名称列表；请求时会拼成逗号分隔字符串。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.stock_pool_list`

- 接口：`vault.stock-pool.list` `POST /application/open-vault/stock-pool/getPoolList`
- 同步示例：`sample/sync/vault_stock_pool_list.py`
- 异步示例：`sample/async/vault_stock_pool_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.stock_pool_stocks`

- 接口：`vault.stock-pool.stocks` `POST /application/open-vault/stock-pool/getStockList`
- 同步示例：`sample/sync/vault_stock_pool_stocks.py`
- 异步示例：`sample/async/vault_stock_pool_stocks.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `pool_id` | `Any` | 否 | `'all'` | `"all"` | 股票池 ID 或 ID 列表；默认 all。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `vault.drive_download`

- 接口：`vault.drive.download` `GET /application/open-vault/drive/download/file`
- 同步示例：`sample/sync/vault_drive_download.py`
- 异步示例：`sample/async/vault_drive_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `file_id` | `str` | 是 | - | `"<fileId>"` | 网盘文件 ID，通常来自 vault.drive_list。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `vault.record_download`

- 接口：`vault.record.download` `GET /application/open-vault/record/download/file`
- 同步示例：`sample/sync/vault_record_download.py`
- 异步示例：`sample/async/vault_record_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `str` | 是 | - | `"<recordId>"` | 录音记录 ID，通常来自 vault.record_list。 |
| `content_type` | `str` | 是 | - | `"summary"` | 下载内容：original=原始文件 / asr=语音识别 / summary=AI 速记；其他取值本地拒绝、不发请求（接口对错值报 130003「没有文件可供下载」，易误读成没附件）。「与我分享」类录音无法下载原始文件。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `vault.my_conference_download`

- 接口：`vault.my-conference.download` `GET /application/open-vault/my-conference/download/file`
- 同步示例：`sample/sync/vault_my_conference_download.py`
- 异步示例：`sample/async/vault_my_conference_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `conference_id` | `str` | 是 | - | `"<conferenceId>"` | 会议 ID，通常来自 vault.my_conference_list。 |
| `content_type` | `str` | 是 | - | `"summary"` | 下载内容：asr=语音识别 / summary=AI 速记（没有 original）；其他取值本地拒绝、不发请求（接口对错值报 130003「没有文件可供下载」）。30 积分/篇，超时不自动重发。 |
| `output` | `str \| Path \| None` | 否 | `None` | `Path("sample_downloads/file.pdf")` | 下载保存路径；None 时根据标题、响应头或 fallback 文件名生成。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `vault.stock_pool_create`

- 接口：`vault.stock-pool.create` `POST /application/open-vault/stock-pool/createPool`
- 同步示例：`sample/sync/vault_stock_pool_create.py`
- 异步示例：`sample/async/vault_stock_pool_create.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `name` | `str` | 是 | - | `"核心池"` | 新池名：≤10 个字符（中文算 1，超出 230007）；不可与已有池重名（230006，整串精确比较，首尾空格不去、大小写不归一）；每账号最多 30 个池（230003）。超时 / 5xx 不自动重发，超时后先 stock_pool_list 确认。 |
| `raw` | `bool` | 否 | `False` | `False` | 写操作总是返回服务端原始 data（{poolId, poolName}）；raw 仅为签名统一。 |

### `vault.stock_pool_rename`

- 接口：`vault.stock-pool.rename` `POST /application/open-vault/stock-pool/updatePool`
- 同步示例：`sample/sync/vault_stock_pool_rename.py`
- 异步示例：`sample/async/vault_stock_pool_rename.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `pool_id` | `str` | 是 | - | `"<poolId>"` | 股票池 ID，取自 vault.stock_pool_list。 |
| `name` | `str` | 是 | - | `"新池名"` | 新池名，规则同 stock_pool_create（≤10 个字符、不可重名）；改成该池当前的名字算成功。 |
| `raw` | `bool` | 否 | `False` | `False` | 写操作总是返回服务端原始 data（{poolId, poolName}）；raw 仅为签名统一。 |

### `vault.stock_pool_add_stock`

- 接口：`vault.stock-pool.add-stock` `POST /application/open-vault/stock-pool/addStock`
- 同步示例：`sample/sync/vault_stock_pool_add_stock.py`
- 异步示例：`sample/async/vault_stock_pool_add_stock.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `pool_id` | `str` | 是 | - | `"<poolId>"` | 目标股票池 ID，取自 vault.stock_pool_list。 |
| `security` | `Any` | 是 | - | `["600519.SH", "00700.HK", "AAPL.O"]` | 证券代码，支持单值或列表；须带市场后缀且大小写敏感（600519 / 600519.sh / 700.HK 进 failList）；单池上限 10000 只。failList 非空时告警并标 partial=True。 |
| `raw` | `bool` | 否 | `False` | `False` | 写操作总是返回服务端原始 data（{successList, failList}）；raw 仅为签名统一。 |

### `vault.stock_pool_remove_stock`

- 接口：`vault.stock-pool.remove-stock` `POST /application/open-vault/stock-pool/deleteStock`
- 同步示例：`sample/sync/vault_stock_pool_remove_stock.py`
- 异步示例：`sample/async/vault_stock_pool_remove_stock.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `pool_id` | `str` | 是 | - | `"<poolId>"` | 目标股票池 ID，取自 vault.stock_pool_list。 |
| `security` | `Any` | 是 | - | `"600519.SH"` | 证券代码，支持单值或列表；规则同 stock_pool_add_stock。移出本就不在池内的证券算成功。 |
| `raw` | `bool` | 否 | `False` | `False` | 写操作总是返回服务端原始 data（{successList, failList}）；raw 仅为签名统一。 |

### `vault.stock_pool_delete`

- 接口：`vault.stock-pool.delete` `POST /application/open-vault/stock-pool/deletePool`
- 同步示例：`sample/sync/vault_stock_pool_delete.py`
- 异步示例：`sample/async/vault_stock_pool_delete.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `pool_id` | `Any` | 是 | - | `["<poolId>"]` | 要删除的股票池 ID，支持单值或列表；删不存在的池算成功。 |
| `confirm` | `bool` | 否 | `False` | `True` | 必须为 True：删池会移除池内全部证券的关注关系且不可恢复；False 时在发请求前抛 ValidationError。 |
| `raw` | `bool` | 否 | `False` | `False` | 写操作总是返回服务端原始 data（{successList, failList}）；raw 仅为签名统一。 |

### `vault.drive_folder_list`

- 接口：`vault.drive.folder-list` `POST /application/open-vault/drive/getFolderList`
- 同步示例：`sample/sync/vault_drive_folder_list.py`
- 异步示例：`sample/async/vault_drive_folder_list.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `space_type` | `int` | 否 | `1` | `1` | 空间：1=我的云盘，2=租户云盘（本地校验）。 |
| `parent_id` | `str \| None` | 否 | `None` | `"root"` | 该空间里的文件夹 ID；不传或 "root" 即根目录；属于另一空间报 100003。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（{folderTotal, folderList, fileTotal, fileList}，只含直接下级）；raw 仅为签名统一。 |

### `vault.drive_upload`

- 接口：`vault.drive.upload` `POST /application/open-vault/drive/uploadFile`
- 同步示例：`sample/sync/vault_drive_upload.py`
- 异步示例：`sample/async/vault_drive_upload.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `file` | `str \| Path` | 是 | - | `Path("sample_downloads/example.pdf")` | 本地文件路径；本地先拦不存在 / 非文件 / 空文件 / >100MB。试用账号每天累计 ≤500MB（超出 230008）。 |
| `space_type` | `int` | 否 | `1` | `1` | 目标空间：1=我的云盘，2=租户云盘（对整个租户可见）。 |
| `folder_id` | `str \| None` | 否 | `None` | `"root"` | 目标文件夹 ID；不传或 "root" 即根目录；属于另一空间报 100003。 |
| `title` | `str \| None` | 否 | `None` | `"示例文档.pdf"` | 云盘里的名称，不传用本地文件名；≤200 个字符，按 UTF-16 计（emoji 算 2），本地先拦（服务端 230004）。云盘允许同名，重复上传会多一份，且不自动重发。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（{fileId, title, folderId, spaceType, fileSize}）；raw 仅为签名统一。 |

### `vault.drive_create_folder`

- 接口：`vault.drive.create-folder` `POST /application/open-vault/drive/createFolder`
- 同步示例：`sample/sync/vault_drive_create_folder.py`
- 异步示例：`sample/async/vault_drive_create_folder.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `name` | `str` | 是 | - | `"2026Q3"` | 文件夹名，≤200 个字符（超出 230004）；允许同名，重复执行会多建一个，且不自动重发。 |
| `space_type` | `int` | 否 | `1` | `1` | 空间：1=我的云盘，2=租户云盘。 |
| `parent_id` | `str \| None` | 否 | `None` | `"root"` | 父文件夹 ID；不传或 "root" 即根目录；属于另一空间报 100003。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（{folderId, parentId, folderName, spaceType, createTime}）；raw 仅为签名统一。 |

### `vault.drive_rename`

- 接口：`vault.drive.rename` `POST /application/open-vault/drive/rename`
- 同步示例：`sample/sync/vault_drive_rename.py`
- 异步示例：`sample/async/vault_drive_rename.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `type_` | `str` | 是 | - | `"file"` | id_ 指的是什么：file / folder（本地校验）；映射为请求字段 type。 |
| `id_` | `str` | 是 | - | `"<fileId>"` | 文件或文件夹 ID；映射为请求字段 id。 |
| `name` | `str` | 是 | - | `"新名称.pdf"` | 新名称，≤200 个字符（超出 230004）。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（{id, name}）；raw 仅为签名统一。 |

### `vault.drive_move_file`

- 接口：`vault.drive.move-file` `POST /application/open-vault/drive/moveFile`
- 同步示例：`sample/sync/vault_drive_move_file.py`
- 异步示例：`sample/async/vault_drive_move_file.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `file_id` | `Any` | 是 | - | `["<fileId>"]` | 文件 ID，支持单值或列表；另一空间的文件进 failList（「空间不一致」），failList 非空时告警并标 partial=True。 |
| `target_folder_id` | `str` | 是 | - | `"root"` | 同一空间里的目标文件夹 ID，或 "root"。跨空间用 drive_copy。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（{successList, failList}）；raw 仅为签名统一。 |

### `vault.drive_move_folder`

- 接口：`vault.drive.move-folder` `POST /application/open-vault/drive/moveFolder`
- 同步示例：`sample/sync/vault_drive_move_folder.py`
- 异步示例：`sample/async/vault_drive_move_folder.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `folder_id` | `str` | 是 | - | `"<folderId>"` | 要移动的文件夹 ID。 |
| `target_parent_id` | `str` | 是 | - | `"root"` | 同一空间里的目标父文件夹 ID，或 "root"；移到另一空间、自身或其子文件夹报 230005。跨空间用 drive_copy。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（{folderId, parentId}）；raw 仅为签名统一。 |

### `vault.drive_copy`

- 接口：`vault.drive.copy` `POST /application/open-vault/drive/copy`
- 同步示例：`sample/sync/vault_drive_copy.py`
- 异步示例：`sample/async/vault_drive_copy.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `file_id` | `Any` | 否 | `None` | `["<fileId>"]` | 复制文件：源文件 ID，支持单值或列表，与 target_folder_id 成对传（源保留）；单条失败进 failList，非空时告警并标 partial=True。与 folder_id + target_parent_id 二选一，混传、只传一半或都不传本地拒绝。重复复制会多一份，且不自动重发。 |
| `target_folder_id` | `str \| None` | 否 | `None` | `"root"` | 复制文件：另一空间里的目标文件夹 ID，"root" 即另一空间的根目录；同空间复制报 100003。 |
| `folder_id` | `str \| None` | 否 | `None` | `"<folderId>"` | 复制文件夹：源文件夹 ID，与 target_parent_id 成对传，连同其中的子文件夹与文件一起复制。 |
| `target_parent_id` | `str \| None` | 否 | `None` | `"root"` | 复制文件夹：另一空间里的目标父文件夹 ID，"root" 即另一空间的根目录；同空间复制报 100003。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（复制文件 {successList[]{fileId, newFileId}, failList}；复制文件夹 {folderId, newFolderId}）；raw 仅为签名统一。 |

### `vault.drive_delete_file`

- 接口：`vault.drive.delete-file` `POST /application/open-vault/drive/deleteFile`
- 同步示例：`sample/sync/vault_drive_delete_file.py`
- 异步示例：`sample/async/vault_drive_delete_file.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `file_id` | `Any` | 是 | - | `["<fileId>"]` | 要删除的文件 ID，支持单值或列表；单条失败（如「文件不存在」）进 failList，非空时告警并标 partial=True。 |
| `confirm` | `bool` | 否 | `False` | `True` | 必须为 True：删除不可恢复；False 时在发请求前抛 ValidationError。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（{successList, failList}）；raw 仅为签名统一。 |

### `vault.drive_delete_folder`

- 接口：`vault.drive.delete-folder` `POST /application/open-vault/drive/deleteFolder`
- 同步示例：`sample/sync/vault_drive_delete_folder.py`
- 异步示例：`sample/async/vault_drive_delete_folder.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `folder_id` | `str` | 是 | - | `"<folderId>"` | 要删除的文件夹 ID；连同其中全部子文件夹与文件一起删除。 |
| `confirm` | `bool` | 否 | `False` | `True` | 必须为 True：删除不可恢复；False 时在发请求前抛 ValidationError。 |
| `raw` | `bool` | 否 | `False` | `False` | 总是返回原始 data（{folderId}）；raw 仅为签名统一。 |

## 另类数据（`gangtise.alternative`）

### `alternative.edb_search`

- 接口：`alternative.edb-search` `POST /application/open-alternative/EDB/search`
- 同步示例：`sample/sync/alternative_edb_search.py`
- 异步示例：`sample/async/alternative_edb_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"平安银行"` | 搜索关键词。 |
| `limit` | `int` | 否 | `100` | `10` | 返回条数上限。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `alternative.edb_data`

- 接口：`alternative.edb-data` `POST /application/open-alternative/EDB/getData`
- 同步示例：`sample/sync/alternative_edb_data.py`
- 异步示例：`sample/async/alternative_edb_data.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `indicator_id` | `Any` | 是 | - | `"<indicatorId>"` | EDB 指标 ID 或 ID 列表，最多 10 个（接口校验）。计费 30 积分/指标。 |
| `start_date` | `str` | 是 | - | `"2026-05-01"` | 开始日期，格式通常为 YYYY-MM-DD。 |
| `end_date` | `str` | 是 | - | `"2026-05-28"` | 结束日期，格式通常为 YYYY-MM-DD。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `alternative.concept_info`

- 接口：`alternative.concept-info` `POST /application/open-alternative/concept/v2/info`<br>`alternative.concept-info-full` `POST /application/open-alternative/concept/info`
- 同步示例：`sample/sync/alternative_concept_info.py`
- 异步示例：`sample/async/alternative_concept_info.py`
- 返回类型：`dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `concept_id` | `str` | 是 | - | `"121000130"` | 题材（概念）指数 ID；与 `ai.theme_tracking` 共用题材 ID 体系，可用 reference.concept_search 按名查询（机器人=121000130）。 |
| `full` | `bool` | 否 | `False` | `False` | 默认走 v2 接口（50 积分/次），不含催化事件 keyEvents；True=走旧版接口（500 积分/次），只多一列 keyEvents。 |
| `raw` | `bool` | 否 | `False` | `False` | 该接口返回最新截面画像对象，始终为 dict（定义/投资逻辑/行业空间/竞争格局；full=True 另有 keyEvents），不支持历史回溯。 |

### `alternative.concept_securities`

- 接口：`alternative.concept-securities` `POST /application/open-alternative/concept/v2/securities`<br>`alternative.concept-securities-full` `POST /application/open-alternative/concept/securities`
- 同步示例：`sample/sync/alternative_concept_securities.py`
- 异步示例：`sample/async/alternative_concept_securities.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `concept_id` | `str` | 是 | - | `"121000130"` | 题材（概念）指数 ID；见 reference.concept_search（机器人=121000130）。 |
| `full` | `bool` | 否 | `False` | `False` | 默认走 v2 接口（50 积分/次），不含 isKey / inclusionReason；True=走旧版接口（500 积分/次），每只成分股多这两列。 |
| `raw` | `bool` | 否 | `False` | `False` | 默认返回扁平化 DataFrame（每行一只成分股，列 groupName/securityCode/securityName；full=True 另有 isKey/inclusionReason）；True 返回嵌套分组 dict。 |

### `insight.pamirs_summary_list`

- 接口：`insight.pamirs-summary.list` `POST /application/open-insight/pamirs-summary/getList`
- 同步示例：`sample/sync/insight_pamirs_summary_list.py`
- 异步示例：`sample/async/insight_pamirs_summary_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 起始偏移。 |
| `size` | `int \| None` | 否 | `None` | `5` | 返回条数；省略则自动翻页拉全量（单页上限 50）。 |
| `start_time` | `str \| None` | 否 | `None` | `"2026-01-01"` | 起始时间，YYYY-MM-DD[ HH:mm:ss] 或 10/13 位时间戳。 |
| `end_time` | `str \| None` | 否 | `None` | `"2026-08-01"` | 结束时间，同上。 |
| `keyword` | `str \| None` | 否 | `None` | `"PCB"` | 搜索词。 |
| `search_type` | `int` | 否 | `1` | `2` | 1=标题（默认） 2=全文。**本地白名单**：范围外的值会让 keyword 一并失效、返回未过滤的结果集，故在本地拦下。 |
| `rank_type` | `int` | 否 | `1` | `2` | 1=综合（默认） 2=时间倒序。同样本地白名单。 |
| `research_area` | `Any` | 否 | `None` | `"100800119"` | 行业码：中信（1008001xx）与申万（104xx0000）都认；方向码 122000xxx 在本端点返 0。 |
| `security` | `Any` | 否 | `None` | `"600519.SH"` | 证券代码或列表。 |
| `category` | `Any` | 否 | `None` | `"companyAnalysis"` | companyAnalysis / industryAnalysis，本地白名单。 |
| `market` | `Any` | 否 | `None` | `"aShares"` | aShares / hkStocks / usChinaConcept / usStocks，本地白名单。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data。 |

**注意**：这是独立的专家纪要库，需单独购买（未开通报 `999004`），筛选项是 `summary_list` 的真子集（没有 source / institution / participant_role）。已知返回口径：`conceptList` / `categoryList` / `marketList` 三个标签字段稀疏、不保证完整，是否有值随记录和查法而变——不带筛选时常整条为空，用 category 或 market 过滤时回填率明显更高。按这几个维度分组要靠过滤参数取，别拉全量再本地分组；某条为空也不说明它没有该属性。

### `insight.pamirs_summary_download`

- 接口：`insight.pamirs-summary.download` `GET /application/open-insight/pamirs-summary/download/file`
- 同步示例：`sample/sync/insight_pamirs_summary_download.py`
- 异步示例：`sample/async/insight_pamirs_summary_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `summary_id` | `str` | 是 | - | `"12345"` | 纪要唯一标识，取自列表的 summaryId。 |
| `file_type` | `int \| None` | 否 | `None` | `2` | 1=原文（默认） 2=HTML。本地白名单，其他值直接报错。 |
| `output` | `str \| Path \| None` | 否 | `None` | `"out.pdf"` | 显式落盘路径；省略则按标题 / 服务端文件名命名。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

### `insight.performance_calendar_list`

- 接口：`insight.performance-calendar.list` `POST /application/open-insight/schedule/performance-calendar/getList`
- 同步示例：`sample/sync/insight_performance_calendar_list.py`
- 异步示例：`sample/async/insight_performance_calendar_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `from_` | `int` | 否 | `0` | `0` | 起始偏移。 |
| `size` | `int \| None` | 否 | `None` | `5` | 返回条数；省略则自动翻页。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-07-01"` | 起始日 YYYY-MM-DD，过滤 publishDate。**这是唯一按 `*_date` 而非 `*_time` 筛选的 insight 列表。** |
| `end_date` | `str \| None` | 否 | `None` | `"2026-07-31"` | 结束日 YYYY-MM-DD。 |
| `security` | `Any` | 否 | `None` | `"600519.SH"` | 证券代码或列表。 |
| `market` | `Any` | 否 | `None` | `"aShares"` | aShares / hkStocks / usChinaConcept / usStocks，本地白名单。 |
| `category` | `Any` | 否 | `None` | `"performanceForecast"` | performanceForecast / performanceExpress / performanceAnnouncement，本地白名单。 |
| `confirm` | `bool` | 否 | `False` | `False` | 按条计费（0.1 积分/条）的额度确认：省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分本地拒绝（ValidationError）；True=确认全量拉取。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（含 partial 标记）。 |

**必须给一个约束**：本接口数据量很大（含未来排期），省略 size 等于按分页上限拉满（1000 页 × 50 = 5 万条，按 0.1 积分/条约 5000 积分）。完整日期区间 / security / 显式 size 三者至少给一个，否则本地报 `ValidationError` 且不发请求。只给 security 时另加 1000 行隐式上限，撞上且仍有剩余会标 `partial` 并发 warning。

### `insight.performance_calendar_download`

- 接口：`insight.performance-calendar.download` `GET /application/open-insight/schedule/performance-calendar/download/file`
- 同步示例：`sample/sync/insight_performance_calendar_download.py`
- 异步示例：`sample/async/insight_performance_calendar_download.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `performance_report_id` | `str` | 是 | - | `"12345"` | 报告唯一标识，取自列表的 performanceReportId。 |
| `output` | `str \| Path \| None` | 否 | `None` | `"out.pdf"` | 显式落盘路径；省略则用 title-cache 里的真实标题命名。 |
| `resolve_title` | `bool` | 否 | `False` | `False` | 标题缓存未命中时是否回查 list 接口取文件名（额外 4 次请求，这些 list 多数按条计费）；关闭时用服务端 Content-Disposition 文件名或 `<前缀>-<id>`。给了 output 时忽略。 |

**计费**：A股 1 积分 / 港美股 2 积分；仅 `hasAttachment: true` 的记录可下。

## 数据指标 EDE（`gangtise.indicator`）

### `indicator.search`

- 接口：`indicator.search` `POST /application/open-indicator/EDE/search`
- 同步示例：`sample/sync/indicator_search.py`
- 异步示例：`sample/async/indicator_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any] | list[Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `keyword` | `str` | 是 | - | `"收盘价"` | 指标词，如 收盘价 / 成交量 / 营业收入（不是自然语言问题）。 |
| `limit` | `int` | 否 | `50` | `20` | 最大返回数，默认 50，上限 100。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时尽量转换为 pandas.DataFrame。 |

### `indicator.cross_section`

- 接口：`indicator.cross-section` `POST /application/open-indicator/EDE/cross-section`
- 同步示例：`sample/sync/indicator_cross_section.py`
- 异步示例：`sample/async/indicator_cross_section.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `str` | 是 | - | `"2025-06-30"` | 数据日期，格式 YYYY-MM-DD。作为**每个指标各自的 tradeDate** 下发（服务端 2026-08-01 起废弃根级 date）。 |
| `indicator` | `Any` | 是 | - | `"qte_close"` | 指标码或列表，例如 qte_close；用 indicator.search 查询。缺失在本地报 ValidationError（服务端只会回 100001）。 |
| `security` | `Any` | 是 | - | `"600519.SH"` | 证券代码或代码列表，也接受板块 ID（reference.sector_search 的 10 位 sectorId，与代码混传取并集；服务端展开成**全部成分股**）。🔴 单次上限 30000 单元格（证券数 × 指标数），超出报 100006、不返回部分结果，按乘积拆批。 |
| `currency` | `str \| None` | 否 | `None` | `"CNY"` | 币种：DFT/CNY/HKD/USD/EUR/GBP/JPY/TWD/MOP/AUD（默认 DFT）。 |
| `scale` | `str \| None` | 否 | `None` | `"8"` | 数量级：0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）。只作用于支持该参数的指标，价格类与金额类可以混查。 |
| `indicator_param` | `dict[str, dict[str, Any]] \| None` | 否 | `None` | `{"qte_close": {"adjustType": "2"}}` | 单指标参数映射（按 indicatorCode 索引）。参数名以 search 的 parameterList 为准（复权是 **adjustType**，2=前复权 3=后复权；写错名报 100003 并点名）。键名以 Date 结尾的值与 date 同样校验，年在前三种写法统一成 YYYY-MM-DD、年在后本地拒绝。⚠️ 注入的 tradeDate 会被拒，**当且仅当该指标的 parameterList 里没有 tradeDate**。四种情形：① 有 tradeDate → 不用管；② 无 tradeDate 有 reportDate（`is_*` 那族、`finc_roe_avg_avg`）→ 传 reportDate，SDK 自动不再注入；③ 无 tradeDate 但有别的参数（currency / scale / fiscalYear …）→ 传那些参数**再加** `"tradeDate": None`，如 `{"pty_shr_reg": {"currency": "CNY", "tradeDate": None}}`；④ parameterList 为空 → 传 `{}`。tradeDate 与 reportDate 都必填的（如 div_cash_yld）两个都显式给。fiscalYear 等必填参数漏传报 100001 并点名。**键必须是 `indicator` 里列出的 code**，未绑定的 code 本地报错。 |
| `key_by` | `str` | 否 | `"name"` | `"code"` | 列头来源：name=服务端给的指标显示名；code=你传进去的 indicatorCode。服务端按自己的顺序返回列，位置索引不可靠；name 模式还需再查一次 search 才能把显示名映射回 code。非法值发请求前抛 ValidationError。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时摊平为每行一证券、指标名作列的宽表 DataFrame。 |

### `indicator.time_series`

- 接口：`indicator.time-series` `POST /application/open-indicator/EDE/time-series`
- 同步示例：`sample/sync/indicator_time_series.py`
- 异步示例：`sample/async/indicator_time_series.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `start_date` | `str` | 是 | - | `"2025-01-01"` | 起始日期，格式 YYYY-MM-DD。 |
| `end_date` | `str` | 是 | - | `"2025-06-30"` | 结束日期，格式 YYYY-MM-DD。 |
| `indicator` | `Any` | 是 | - | `"qte_close"` | 指标码或列表；用 indicator.search 查询。缺失在本地报 ValidationError。 |
| `security` | `Any` | 是 | - | `"600519.SH"` | 证券代码或代码列表，也接受板块 ID（仅单指标时；服务端展开成全部成分股，此时列头按证券出）。🔴 单次上限 30000 单元格（序列数 × 日期数），超出报 100006、不返回部分结果，缩短区间或拆证券分批取。 |
| `calendar_type` | `str \| None` | 否 | `None` | `"TD"` | 日历：ND=自然日 TD=交易日 WD=工作日，服务端默认 ND。**省略时 SDK 自动选**：用免费的 indicator.search 读各指标 parameterList（每个指标码一次，并发 ≤ 5），全部声明 tradeDate 且都不声明 reportDate / fiscalYear 才发 TD，否则不发（报告期类指标在 TD 轴上会整行全 null）。显式传了原样发送、不查询。 |
| `currency` | `str \| None` | 否 | `None` | `"CNY"` | 币种：DFT/CNY/HKD/USD/EUR/GBP/JPY/TWD/MOP/AUD（默认 DFT）。 |
| `scale` | `str \| None` | 否 | `None` | `"0"` | 数量级：0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）。只作用于支持该参数的指标。 |
| `indicator_param` | `dict[str, dict[str, Any]] \| None` | 否 | `None` | `{"qte_close": {"adjustType": "2"}}` | 单指标参数映射（按 indicatorCode 索引），规则同 cross_section（参数名以 parameterList 为准、写错报 100003；*Date 键的值校验并统一成 YYYY-MM-DD；必填参数漏传报 100001）。区间由 start_date / end_date 统管，不要再传 tradeDate。**键必须是 `indicator` 里列出的 code**，未绑定的 code 本地报错。 |
| `key_by` | `str` | 否 | `"name"` | `"code"` | 列头来源：name=服务端给的显示名；code=你传进去的代码（多指标 × 单证券为 indicatorCode，单指标 × 多证券为 securityCode）。服务端按自己的顺序返回列，位置索引不可靠。非法值发请求前抛 ValidationError。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时摊平为每行一日期的宽表 DataFrame。 |

### `indicator.screener`

- 接口：`indicator.screener` `POST /application/open-indicator/screener`
- 同步示例：`sample/sync/indicator_screener.py`
- 异步示例：`sample/async/indicator_screener.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `str` | 是 | - | `"2026-08-07"` | 数据日期 YYYY-MM-DD，作为每个变量的 tradeDate 下发（已带 tradeDate / reportDate 的不覆盖）。绝大多数指标必填 tradeDate，漏传服务端报 100001，因此必填。 |
| `expression` | `str` | 是 | - | `"F1 >= 500 && F2 <= 30"` | 筛选表达式，支持 `&&` / `\|\|` / 括号，以及 contains / notcontains 文本匹配（仅 dataType 为 string 的指标）。只能引用已绑定的变量，否则本地报 ValidationError。 |
| `indicator` | `dict[str, str]` | 是 | - | `{"F1": "qte_mkt_cptl", "F2": "finc_pe_ttm"}` | 变量 → 指标码绑定；变量名必须是 F + 正整数。同一指标可绑到两个变量取不同参数。 |
| `security` | `Any` | 是 | - | `"600519.SH"` | 证券代码或代码列表，也接受板块 ID（reference.sector_search 的 sectorId，服务端展开成全部成分股）。 |
| `indicator_param` | `dict[str, dict[str, Any]] \| None` | 否 | `None` | `{"F1": {"scale": "8"}}` | 单指标参数，**按变量索引**（不是按 code）——只有变量能区分同一指标的两次绑定。引用未绑定变量本地报错。tradeDate 注入的四种情形、*Date 键的日期校验、必填参数漏传报 100001 都同 `cross_section`，只是键写变量名，如 `{"F1": {"currency": "CNY", "tradeDate": None}}`。 |
| `key_by` | `str` | 否 | `"name"` | `"code"` | 列头来源：name=显示名（默认）；code=indicatorCode。同一 code 绑到两个变量时两列都会带上 (F1)/(F2) 后缀。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data；False 时摊平为每行一只命中证券的宽表 DataFrame。 |

**结果校验**：响应里每列携带的 `field` 是唯一能把该列追溯回筛选条件的东西，SDK 会校验它命名的是请求过的变量、带该变量对应的 code、且不重复——不符即抛 `ApiError`。某个变量整列缺失时按表达式的布尔结构判定：还有分支可求值就标 `partial` + 发 warning，没有任何分支可求值则抛 `ApiError`（这些行无法被证明满足它们声称的条件）。空结果是正常答案，但也可能是报告期类指标的日期不在报告期末（全为 null、无一通过）或指标不覆盖这些证券——对照 search 的 parameterList 与 scopeList 核对。

## 债券（`gangtise.bond`）

整族通用：**全部计费，0.4 积分起**——多数按次（与返回行数无关），`rating_overview` 按条、`rating_change` 按有数据的债券只数、`issuer_rating_change` 按发行人计。**超时 / 5xx 不自动重试**（整族 no-replay，避免重复扣费），偶发失败自行重跑。`security` 只收**标准债券代码**（`019742.SH` / `123456.SZ` / `220205.IB`），简称或拼音整批报 `120001`，只有简称时先用 `reference.securities_search(keyword=<简称>)` 换代码；列表发送前去重，有只数上限的按去重后计。`field` 写了不支持的字段名整批报 `100003`（`default_list` 报 `100005`），不会静默丢列。返回是列式的（`fieldList` + 数组行），默认转 DataFrame。条件合法但全部无数据时抛 `ApiError`（`130001`）。

### `bond.basic_info`

- 接口：`bond.basic-info` `POST /application/open-fundamental/bond/basic-info`
- 同步示例：`sample/sync/bond_basic_info.py`
- 异步示例：`sample/async/bond_basic_info.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"019742.SH"` | 标准债券代码或代码列表（如 019742.SH / 123456.SZ / 220205.IB），不收简称与拼音；去重后单次最多 10000 只，超出本地拒绝。库中无资料的代码仍占一行、除 securityCode 外全为 null。 |
| `field` | `Any` | 否 | `None` | `["securityName", "couponRate"]` | 返回字段名或列表；None 返回全部字段。写错字段名整批报 100003。默认列 securityCode 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.issuer_info`

- 接口：`bond.issuer-info` `POST /application/open-fundamental/bond/issuer-info`
- 同步示例：`sample/sync/bond_issuer_info.py`
- 异步示例：`sample/async/bond_issuer_info.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 否 | `None` | `"136236.SH"` | 标准债券代码或列表，查其发行人；与 issuer 二选一，同传或都不传本地拒绝。 |
| `issuer` | `Any` | 否 | `None` | `"国家电网有限公司"` | 发行人全称或简称（单值或列表），模糊匹配、一个名称只返回最匹配的一家，匹配不到不产生行；与 security 二选一。 |
| `field` | `Any` | 否 | `None` | `["issuerName", "swIndustry", "latestIssuerRating", "ratingAgency"]` | 返回字段名或列表；None 返回全部字段。swIndustry 为申万、nationalIndustry 为国民经济行业分类；latestIssuerRating 括号部分可能缺省且混合境内外口径，需一并取 ratingAgency。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.daily_quote`

- 接口：`bond.daily-quote` `POST /application/open-quote/bond/daily-quote-exchange-cfets`
- 同步示例：`sample/sync/bond_daily_quote.py`
- 异步示例：`sample/async/bond_daily_quote.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"019742.SH"` | 标准债券代码或列表，不限只数。 |
| `start_date` | `str` | 是 | - | `"2026-09-15"` | 交易日区间开始，YYYY-MM-DD。历史范围正式账号前溯 5 年、试用 3 年；早于可回溯下界时整批报 110003（即使 end_date 在窗口内）。数据还可能比账号窗口短：早于数据起点整段报 130001，跨过数据起点时从有数据的那天起返回、不报错（首行比 start_date 晚超过 14 天时发 UserWarning，只看整批最早的首行）——取长序列时按 securityCode 逐只核对首行日期。 |
| `end_date` | `str` | 是 | - | `"2026-09-19"` | 交易日区间结束，YYYY-MM-DD。 |
| `field` | `Any` | 否 | `None` | `["cleanClose", "ytmClose", "modifiedDuration"]` | 返回字段名或列表；None 返回全部字段。默认列 securityCode + tradeDate 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.valuation`

- 接口：`bond.valuation` `POST /application/open-fundamental/bond/valuation-shclearing`
- 同步示例：`sample/sync/bond_valuation.py`
- 异步示例：`sample/async/bond_valuation.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"019742.SH"` | 标准债券代码或列表。 |
| `start_date` | `str` | 是 | - | `"2026-09-15"` | 估值日区间开始，YYYY-MM-DD。历史范围正式账号前溯 5 年、试用 3 年；早于可回溯下界时整批报 110003。数据还可能比账号窗口短：早于数据起点整段报 130001，跨过数据起点时从有数据的那天起返回、不报错（首行比 start_date 晚超过 14 天时发 UserWarning，只看整批最早的首行）——取长序列时按 securityCode 逐只核对首行日期。 |
| `end_date` | `str` | 是 | - | `"2026-09-19"` | 估值日区间结束，YYYY-MM-DD。 |
| `confidence_level` | `str \| None` | 否 | `None` | `"不推荐"` | 估值可信度：推荐 / 不推荐，其他值本地拒绝。不传时服务端默认只返回「推荐」的估值，要看全部需两个值分别查。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。默认列 securityCode + tradeDate + confidenceLevel 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.cash_flow`

- 接口：`bond.cash-flow` `POST /application/open-fundamental/bond/cash-flow`
- 同步示例：`sample/sync/bond_cash_flow.py`
- 异步示例：`sample/async/bond_cash_flow.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"019742.SH"` | 标准债券代码或列表。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-01-01"` | 兑付日区间开始，YYYY-MM-DD；省略返回全部历史。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-12-31"` | 兑付日区间结束，YYYY-MM-DD；省略返回全部历史。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。默认列 securityCode + paymentDate 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.announcement`

- 接口：`bond.announcement` `POST /application/open-fundamental/bond/announcement`
- 同步示例：`sample/sync/bond_announcement.py`
- 异步示例：`sample/async/bond_announcement.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 否 | `None` | `"019742.SH"` | 标准债券代码或列表；与 start_date/end_date 二选一，同传或都不传本地拒绝。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-09-18"` | 公告日区间开始，YYYY-MM-DD；与 security 二选一。按日期查询时有代码的行都带市场后缀，部分行（如不对应已上市证券的公告）securityCode 为空。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-09-19"` | 公告日区间结束，YYYY-MM-DD；与 security 二选一。 |
| `page_no` | `int` | 否 | `1` | `2` | 页码，从 1 开始。响应无 total、SDK 不自动翻页：逐页递增，返回空结果即停；条件下一条都没有时任何页码都抛 ApiError(130001)。 |
| `page_size` | `int` | 否 | `50` | `200` | 每页条数 1-200，超出本地拒绝。按次计费、每页扣一次，批量翻页传 200 调用次数只有默认的四分之一。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。默认列 announcementDate + securityCode 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.issuance_detail`

- 接口：`bond.issuance-detail` `POST /application/open-fundamental/bond/issuance-detail`
- 同步示例：`sample/sync/bond_issuance_detail.py`
- 异步示例：`sample/async/bond_issuance_detail.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"019742.SH"` | 标准债券代码或列表。 |
| `start_date` | `str \| None` | 否 | `None` | `"2024-01-01"` | 发行公告日区间开始，YYYY-MM-DD；省略返回全部历史。 |
| `end_date` | `str \| None` | 否 | `None` | `"2024-12-31"` | 发行公告日区间结束，YYYY-MM-DD；省略返回全部历史。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。默认列 securityCode + issueBatchNo 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.rating_overview`

- 接口：`bond.rating-overview` `POST /application/open-fundamental/bond/rating-overview`
- 同步示例：`sample/sync/bond_rating_overview.py`
- 异步示例：`sample/async/bond_rating_overview.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"136236.SH"` | 标准债券代码或列表；去重后单次最多 10 只，超出本地拒绝。按条计费 0.4 积分/条（除代码外全为 null 的行不计）；评级值可能带 sf / pi 小写后缀。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.rating_change`

- 接口：`bond.rating-change` `POST /application/open-fundamental/bond/rating-change`
- 同步示例：`sample/sync/bond_rating_change.py`
- 异步示例：`sample/async/bond_rating_change.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"149478.SZ"` | 标准债券代码或列表；去重后单次最多 10 只，超出本地拒绝。按有数据的债券只数计费 0.4 积分/只。 |
| `start_date` | `str \| None` | 否 | `None` | `"2023-01-01"` | 评级变动公告日区间开始，YYYY-MM-DD；省略返回全部历史。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-09-20"` | 评级变动公告日区间结束，YYYY-MM-DD；省略返回全部历史。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。默认列 securityCode + announcementDate 恒在最前；首次评级的 previousRating 为 null。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.issuer_rating_change`

- 接口：`bond.issuer-rating-change` `POST /application/open-fundamental/bond/issuer-rating-change`
- 同步示例：`sample/sync/bond_issuer_rating_change.py`
- 异步示例：`sample/async/bond_issuer_rating_change.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 否 | `None` | `"136236.SH"` | 标准债券代码或列表，查其发行人；与 issuer 二选一，同传或都不传本地拒绝。 |
| `issuer` | `Any` | 否 | `None` | `"国家电网有限公司"` | 发行人全称或简称（单值或列表），模糊匹配；与 security 二选一。命中的发行人总数超过 10 个时服务端报 100006；按发行人计费 0.4 积分/个。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-01-01"` | 公告日区间开始，YYYY-MM-DD；省略返回全部历史。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-09-20"` | 公告日区间结束，YYYY-MM-DD；省略返回全部历史。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。默认列 issuerName + announcementDate 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.issuance_plan`

- 接口：`bond.issuance-plan` `POST /application/open-fundamental/bond/issuance-plan`
- 同步示例：`sample/sync/bond_issuance_plan.py`
- 异步示例：`sample/async/bond_issuance_plan.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `start_date` | `str` | 是 | - | `"2026-09-01"` | 发行日区间开始，YYYY-MM-DD（只按日期查，不收债券码）。历史范围正式账号前溯 5 年、试用 3 年；早于可回溯下界时整批报 110003。 |
| `end_date` | `str` | 是 | - | `"2026-09-30"` | 发行日区间结束，YYYY-MM-DD。区间内无发行计划时报 130001。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。默认列 issueDate 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.exercise_notice`

- 接口：`bond.exercise-notice` `POST /application/open-fundamental/bond/exercise-notice`
- 同步示例：`sample/sync/bond_exercise_notice.py`
- 异步示例：`sample/async/bond_exercise_notice.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `Any` | 是 | - | `"136236.SH"` | 标准债券代码或列表。国债这类品种本身没有行权数据，返回 130001 属正常。 |
| `start_date` | `str \| None` | 否 | `None` | `None` | 行权日区间开始，YYYY-MM-DD；省略返回全部历史。 |
| `end_date` | `str \| None` | 否 | `None` | `None` | 行权日区间结束，YYYY-MM-DD；省略返回全部历史。 |
| `field` | `Any` | 否 | `None` | `None` | 返回字段名或列表；None 返回全部字段。默认列 securityCode + exerciseDate 恒在最前。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

### `bond.default_list`

- 接口：`bond.default-list` `POST /application/open-fundamental/bond/default-list`
- 同步示例：`sample/sync/bond_default_list.py`
- 异步示例：`sample/async/bond_default_list.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

违约债券：代码、简称、违约日期、违约金额（亿元）、发行人、违约原因，0.4 积分/次。🔴 按违约日期区间、`security`、`issuer` **三选一**，同传或都不传本地拒绝。默认列 securityCode + defaultDate 恒在最前，按违约日期降序；条件下没有记录时抛 ApiError（130001）。

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `start_date` | `str \| None` | 否 | `None` | `"2025-01-01"` | 违约日期区间开始，YYYY-MM-DD；须与 end_date 同时给，区间不超过 1 个自然年（超出报 110002）。 |
| `end_date` | `str \| None` | 否 | `None` | `"2025-12-31"` | 违约日期区间结束，YYYY-MM-DD。 |
| `security` | `Any` | 否 | `None` | `"169687.SH"` | 标准债券代码或列表，不限只数；没有违约记录的代码不产生行。 |
| `issuer` | `str \| None` | 否 | `None` | `"上海世茂股份有限公司"` | **一个**发行人，用全称：传简称也会返回结果，但只返回最匹配的一家，核对返回的 issuerName。传多个或用逗号拼接本地报错。 |
| `field` | `Any` | 否 | `None` | `["securityName", "defaultAmount", "issuerName"]` | 返回字段名或列表；None 返回全部字段。🔴 写错报 100005（其余 bond 方法为 100003）。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（列式 fieldList + list）；False 时转换为 pandas.DataFrame。 |

## 公募基金（`gangtise.fund`）

### `fund.basic_info`

- 接口：`fund.basic-info` `POST /application/open-fundamental/fund/basic-info`
- 同步示例：`sample/sync/fund_basic_info.py`
- 异步示例：`sample/async/fund_basic_info.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `field` | `str \| Sequence[str] \| None` | 否 | `None` | `["fundName", "exchange", "isIndexFund", "trackIndexName"]` | 返回字段名，单值或列表；None 返回全部，fundCode 始终返回。字段名写错整批报 100003 并指名（本地不校验）。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.nav`

- 接口：`fund.nav` `POST /application/open-quote/fund/nav`
- 同步示例：`sample/sync/fund_nav.py`
- 异步示例：`sample/async/fund_nav.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-09-01"` | 交易日区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-09-29"` | 交易日区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.fee_rate`

- 接口：`fund.fee-rate` `POST /application/open-fundamental/fund/fee-rate`
- 同步示例：`sample/sync/fund_fee_rate.py`
- 异步示例：`sample/async/fund_fee_rate.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `fee_type` | `str \| Sequence[str] \| None` | 否 | `None` | `["managementFee", "custodianFee"]` | 费率类型：purchaseFee 申购 / redemptionFee 赎回 / managementFee 管理 / custodianFee 托管 / saleFee 销售服务；单值或列表，None 返回全部。写错报 100003（本地不校验）。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.manager_info`

- 接口：`fund.manager-info` `POST /application/open-fundamental/fund/manager-info`
- 同步示例：`sample/sync/fund_manager_info.py`
- 异步示例：`sample/async/fund_manager_info.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `manager` | `str \| Sequence[str]` | 是 | - | `"张坤"` | 基金经理姓名（不是基金代码），按姓名精确匹配，同名经理全部返回（用 currentCompany 区分）；单值或列表（多人请传列表，名字原样发送），重复值去掉；空值本地报 ValidationError、不发请求。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.manager_history`

- 接口：`fund.manager-history` `POST /application/open-fundamental/fund/manager-history`
- 同步示例：`sample/sync/fund_manager_history.py`
- 异步示例：`sample/async/fund_manager_history.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.asset_size`

- 接口：`fund.asset-size` `POST /application/open-fundamental/fund/asset-size`
- 同步示例：`sample/sync/fund_asset_size.py`
- 异步示例：`sample/async/fund_asset_size.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.holder_structure`

- 接口：`fund.holder-structure` `POST /application/open-fundamental/fund/holder-structure`
- 同步示例：`sample/sync/fund_holder_structure.py`
- 异步示例：`sample/async/fund_holder_structure.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.top10_holders`

- 接口：`fund.top10-holders` `POST /application/open-fundamental/fund/top10-holders`
- 同步示例：`sample/sync/fund_top10_holders.py`
- 异步示例：`sample/async/fund_top10_holders.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"510300.SH"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2025-12-31"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2025-12-31"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.asset_allocation`

- 接口：`fund.asset-allocation` `POST /application/open-fundamental/fund/asset-allocation`
- 同步示例：`sample/sync/fund_asset_allocation.py`
- 异步示例：`sample/async/fund_asset_allocation.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `asset_level` | `str \| Sequence[str] \| None` | 否 | `None` | `"level1"` | 资产分类层级：level1 一级 / level2 二级；单值或列表，None 两级都返回（一二级混在一起别直接加总）。写错报 100003（本地不校验）。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.stock_portfolio`

- 接口：`fund.stock-portfolio` `POST /application/open-fundamental/fund/stock-portfolio`
- 同步示例：`sample/sync/fund_stock_portfolio.py`
- 异步示例：`sample/async/fund_stock_portfolio.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `position_type` | `str \| None` | 否 | `None` | `"all"` | 持仓口径：top 重仓（各季度披露，服务端默认）/ all 全部持股（仅中报、年报披露，一三季度查 all 得空）。写错报 100003（本地不校验）。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.industry_allocation`

- 接口：`fund.industry-allocation` `POST /application/open-fundamental/fund/industry-allocation`
- 同步示例：`sample/sync/fund_industry_allocation.py`
- 异步示例：`sample/async/fund_industry_allocation.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `industry_standard` | `str \| None` | 否 | `None` | `"citicIndustry"` | 行业分类：swIndustry 申万一级（服务端默认）/ citicIndustry 中信一级。写错报 100003（本地不校验）。 |
| `position_type` | `str \| None` | 否 | `None` | `"all"` | 持仓口径：top 重仓（各季度披露，服务端默认）/ all 全部持股（仅中报、年报披露，一三季度查 all 得空）。写错报 100003（本地不校验）。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.bond_portfolio`

- 接口：`fund.bond-portfolio` `POST /application/open-fundamental/fund/bond-portfolio`
- 同步示例：`sample/sync/fund_bond_portfolio.py`
- 异步示例：`sample/async/fund_bond_portfolio.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.bond_type_allocation`

- 接口：`fund.bond-type-allocation` `POST /application/open-fundamental/fund/bond-type-allocation`
- 同步示例：`sample/sync/fund_bond_type_allocation.py`
- 异步示例：`sample/async/fund_bond_type_allocation.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005827.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.fund_portfolio`

- 接口：`fund.fund-portfolio` `POST /application/open-fundamental/fund/fund-portfolio`
- 同步示例：`sample/sync/fund_fund_portfolio.py`
- 异步示例：`sample/async/fund_fund_portfolio.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005220.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-06-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.fund_type_allocation`

- 接口：`fund.fund-type-allocation` `POST /application/open-fundamental/fund/fund-type-allocation`
- 同步示例：`sample/sync/fund_fund_type_allocation.py`
- 异步示例：`sample/async/fund_fund_type_allocation.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"005220.OF"` | 基金交易代码，后缀大写：场外 .OF、场内 .SH / .SZ；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2025-09-30"` | 报告期（季末日）区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2025-09-30"` | 报告期（季末日）区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.etf_pcf_header`

- 接口：`fund.etf-pcf-header` `POST /application/open-fundamental/fund/etf-pcf-header`
- 同步示例：`sample/sync/fund_etf_pcf_header.py`
- 异步示例：`sample/async/fund_etf_pcf_header.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"510300.SH"` | ETF 交易代码，后缀大写（.SH / .SZ）；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

### `fund.etf_pcf_components`

- 接口：`fund.etf-pcf-components` `POST /application/open-fundamental/fund/etf-pcf-components`
- 同步示例：`sample/sync/fund_etf_pcf_components.py`
- 异步示例：`sample/async/fund_etf_pcf_components.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"510300.SH"` | ETF 交易代码，后缀大写（.SH / .SZ）；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `component_code` | `bool` | 否 | `True` | `False` | 接口只返回成分名称；True 时由 SDK 按名称匹配补上带市场后缀的 `componentCode`（用该行 `close` 核对行情，A+H 同名两行据此分开；匹配不到的为 null，并发 UserWarning 列出），额外请求都免费（证券列表 3 次、少量搜索、一两次实时行情，必要时一次日 K）。False 不发这些请求，返回接口原样的行。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total；`componentCode` 同样已补上）；False 时转换为 pandas.DataFrame。 |

### `fund.etf_share_change`

- 接口：`fund.etf-share-change` `POST /application/open-fundamental/fund/etf-share-change`
- 同步示例：`sample/sync/fund_etf_share_change.py`
- 异步示例：`sample/async/fund_etf_share_change.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `security` | `str \| Sequence[str]` | 是 | - | `"510300.SH"` | ETF 交易代码，后缀大写（.SH / .SZ）；单值或列表（多只请传列表，字符串不拆分），重复值去掉；空值本地报 ValidationError、不发请求。代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。 |
| `start_date` | `str \| None` | 否 | `None` | `"2026-09-01"` | 交易日区间起点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；两端都不传 = 账号可回溯窗口（正式 5 年 / 试用 3 年）内全部；早于窗口下界整批报 110003。 |
| `end_date` | `str \| None` | 否 | `None` | `"2026-09-30"` | 交易日区间终点，YYYY-MM-DD（YYYY/MM/DD、YYYYMMDD 也收）；只传 end_date = 从账号窗口下界到该日；起 > 止报 110002。 |
| `raw` | `bool` | 否 | `False` | `False` | 返回原始 API data（{list}，无 total）；False 时转换为 pandas.DataFrame。 |

## 文件解析与联网搜索（`gangtise.tool`）

### `tool.file_parse`

- 接口：`tool.file-parse.submit` `POST /application/open-tool/file-parse/submit`
- 同步示例：`sample/sync/tool_file_parse.py`
- 异步示例：`sample/async/tool_file_parse.py`
- 返回类型：`str`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `file` | `str \| Path` | 是 | - | `"report.pdf"` | 本地 PDF 路径。上传前本地校验后缀 / 非空 / ≤100MB。 |

**计费**：0.8 积分/页，**提交时一次性扣费**；取结果免费。该端点标 `no-replay`（不重放，避免重复扣费）且超时下限 300 秒（100MB 上传不会被默认 30 秒超时掐断）。返回 `task_id`，交给 `tool.file_parse_check` 取结果。

### `tool.file_parse_check`

- 接口：`tool.file-parse.result` `POST /application/open-tool/file-parse/result`
- 同步示例：`sample/sync/tool_file_parse_check.py`
- 异步示例：`sample/async/tool_file_parse_check.py`
- 返回类型：`Path`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `task_id` | `str` | 是 | - | `"1782345678901234567"` | `tool.file_parse` 返回的任务号。 |
| `output` | `str \| Path \| None` | 否 | `None` | `"out.zip"` | 显式落盘路径；省略则按服务端文件名 / `file-parse-<taskId>` 命名。 |
| `wait` | `bool` | 否 | `False` | `True` | True=按与 AI 异步接口相同的退避预算（约 316 秒）轮询到就绪；False 时未就绪直接抛 ApiError（码 140001 / 旧 410110）。 |

**返回**：ZIP 路径，包内是 `file.md` 与 `images/`。取结果免费，所以未就绪时重复调用不产生费用；`140002` 是终态失败，不会消耗整个轮询预算。

### `tool.web_search`

- 接口：`tool.web-search` `POST /application/open-tool/web-search/search`
- 同步示例：`sample/sync/tool_web_search.py`
- 异步示例：`sample/async/tool_web_search.py`
- 返回类型：`pd.DataFrame | dict[str, Any]`

| 参数 | 类型 | 必填 | 默认值 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `query` | `str` | 是 | - | `"减持新规"` | 检索词，1-200 字符，原样发送（服务端不做意图推断或改写）。 |
| `size` | `int \| None` | 否 | `None` | `10` | 1-20，默认 10；include_content=True 时上限 5、省略默认取 5（显式传大于 5 本地报错）。去重与过滤之后的条数，不足不补。 |
| `freshness` | `str \| None` | 否 | `None` | `"week"` | 时效：day / week / month / none（默认不过滤）；按 publishTime 过滤，publishTime 为 null 的结果在 day/week/month 下被滤掉。 |
| `min_tier` | `str \| None` | 否 | `None` | `"T1"` | 最低信源等级：T0 / T1 / T2 / T3（T3=不过滤）。 |
| `site` | `str \| list[str] \| None` | 否 | `None` | `["csrc.gov.cn", "sse.com.cn"]` | 注册域或子域，最多 10 个（按去重后计），相互之间为或关系，子域按后缀匹配。 |
| `include_content` | `bool` | 否 | `False` | `True` | True=返回网页正文 content（Markdown；个别页面取不到时为 null）。 |
| `max_content_chars` | `int \| None` | 否 | `None` | `6000` | 每条正文上限 1000-20000（默认 8000），仅 include_content 时生效，超出截断并置 contentTruncated。 |
| `raw` | `bool` | 否 | `False` | `False` | True 返回 `{query, total, hints, list}`（total=0 时 hints 给出放宽建议）；False 返回 list 的 DataFrame。 |

**说明**：1 积分/次，与返回条数、是否带正文无关；零结果与报错不扣，超时 / 5xx 不自动重发。⚠️ 排序是「信源等级 tier 升序 → publishTime 降序 → 相关性」，**首条不等于最相关**。
