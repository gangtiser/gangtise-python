# Gangtise OpenAPI 示例

本目录为每个公开 SDK 方法提供一个可独立运行的示例脚本：`sync/` 下 152 个同步示例，`async/` 下 152 个异步示例。

## 配置

运行需要联网的示例前，先配置凭证：

```bash
export GANGTISE_ACCESS_KEY=ak_xxx
export GANGTISE_SECRET_KEY=sk_xxx
```

## 运行

运行一个同步示例：

```bash
uv run python sample/sync/quote_day_kline.py
```

运行一个异步示例：

```bash
uv run python sample/async/quote_day_kline.py
```

## 输出

返回 DataFrame 的示例直接打印 DataFrame，不加其他文字。返回文本或 dict / list 的示例把结果写成 Markdown 文件，放在仓库根目录的 `sample_outputs/` 下，并打印生成的 `.md` 路径。下载类示例把文件写入 `sample_downloads/`，接口提供文件名时沿用原文件名。

## 特殊情况

- **查询生成结果的 AI 示例**（`ai_earnings_review_check`、`ai_viewpoint_debate_check`）需要对应生成示例以 `wait=False` 返回的 `data_id`，通过环境变量 `GANGTISE_SAMPLE_EARNINGS_REVIEW_DATA_ID` / `GANGTISE_SAMPLE_VIEWPOINT_DEBATE_DATA_ID` 传入。
- **写操作示例**（`vault_stock_pool_create` / `_rename` / `_add_stock` / `_remove_stock` / `_delete`，以及 `vault_drive_upload` / `_create_folder` / `_rename` / `_move_file` / `_move_folder` / `_copy` / `_delete_file` / `_delete_folder`）会修改账号数据，脚本开头的 ID / 名称常量填好之前不发任何请求。两个云盘删除与 `stock_pool_delete` 还需要 `confirm=True`——SDK 对所有不可逆操作都要求显式确认。
- **知识库资源下载**需要环境变量 `GANGTISE_SAMPLE_KNOWLEDGE_SOURCE_ID`，可选 `GANGTISE_SAMPLE_KNOWLEDGE_RESOURCE_TYPE`。
- **会花大量积分的参数**（如 `confirm=True` 拉全量、`full=True`）在示例里以注释形式展示，不直接调用。

完整的参数说明见 `sample/API_PARAMETERS.md`。
