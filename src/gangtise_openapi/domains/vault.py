# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# strings that intentionally use fullwidth punctuation.)
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._download import download_to_path, download_to_path_async
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import _as_list, _extract_rows, _strip_none


class Vault:
    """`gangtise.vault.*` — personal drive, recordings, conferences, WeChat, stock pools."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def drive_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        file_type: Any = None,
        space_type: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询个人网盘文件列表（vault.drive.list）。

        space_type 取值: 1=我的文件, 2=租户文件; 支持单值或列表。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "fileTypeList": _as_list(file_type),
                "spaceTypeList": _as_list(space_type),
            }
        )
        result = self._client._call("vault.drive.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="vault.drive.list",
            id_field="fileId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def record_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        category: Any = None,
        space_type: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询录音转写记录列表（vault.record.list）。

        category 录音来源: upload/link/mobile/gtNote/pc/share;
        space_type 取值: 1=我的记录, 2=租户记录; 均支持单值或列表。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "categoryList": _as_list(category),
                "spaceTypeList": _as_list(space_type),
            }
        )
        result = self._client._call("vault.record.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="vault.record.list",
            id_field="recordId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def my_conference_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        security: Any = None,
        institution: Any = None,
        category: Any = None,
        source: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询我的会议列表（vault.my-conference.list）。

        source 录制来源（数字，可单值或列表）: 1=企微会议助理 2=会议服务微信群。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area),
                "securityList": _as_list(security),
                "institutionList": _as_list(institution),
                "categoryList": _as_list(category),
                "sourceList": _as_list(source),
            }
        )
        result = self._client._call("vault.my-conference.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="vault.my-conference.list",
            id_field="conferenceId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def wechat_message_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        security: Any = None,
        wechat_group_id: Any = None,
        industry: Any = None,
        category: Any = None,
        tag: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询微信群消息列表（vault.wechat-message.list）。

        category 消息类型: text/image/documents/url; tag 标签: roadShow=路演,
        research=调研, strategyMeeting=策略会, meetingSummary=会议纪要,
        industryComment=行业点评, companyComment=公司点评, earningsReview=业绩点评。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "securityList": _as_list(security),
                "wechatGroupIdList": _as_list(wechat_group_id),
                "industryIdList": _as_list(industry),
                "categoryList": _as_list(category),
                "tagList": _as_list(tag),
            }
        )
        result = self._client._call("vault.wechat-message.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    def wechat_chatroom_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        room_name: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询微信群 chatroomId 列表（vault.wechat-chatroom.list）。

        room_name 支持单值或列表; 请求时会拼成逗号分隔字符串。
        省略 size 拉取全部群（接口返回 {total, list}，按 total 并发翻页，
        单页上限 50）；传 size=N 仅取前 N 条。
        """
        names = _as_list(room_name) or []
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "roomName": ",".join(names) if names else None,
            }
        )
        result = self._client._call("vault.wechat-chatroom.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    def stock_pool_list(self, *, raw: bool = False) -> pd.DataFrame | dict[str, Any]:
        """查询用户股票池 ID 与名称列表（vault.stock-pool.list）。"""
        result = self._client._call("vault.stock-pool.list", body={})
        if raw:
            return result  # type: ignore[no-any-return]
        # TS returns {poolList: [...]}; treat poolList as the row collection.
        rows: list[Any] = []
        if isinstance(result, dict):
            pool_list = result.get("poolList") or result.get("list") or []
            if isinstance(pool_list, list):
                rows = pool_list
        elif isinstance(result, list):
            rows = result
        return to_dataframe(rows, schema=None)

    def stock_pool_stocks(
        self,
        *,
        pool_id: Any = "all",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询股票池内的证券列表（vault.stock-pool.stocks）。

        pool_id 默认 "all" 表示全部股票池; 真实 ID 见 stock_pool_list。
        """
        body = {"poolIdList": _as_list(pool_id)}
        result = self._client._call("vault.stock-pool.stocks", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- download endpoints ----

    def drive_download(
        self,
        *,
        file_id: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载网盘文件（vault.drive.download）。

        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="vault.drive.download",
            query={"fileId": file_id},
            output=output,
            fallback_name=f"file-{file_id}",
            title_lookup=("vault.drive.list", "fileId", file_id),
        )

    def record_download(
        self,
        *,
        record_id: str,
        content_type: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载录音转写文件（vault.record.download）。

        content_type 取值: original=原始音频, asr=语音转写, summary=纪要。
        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="vault.record.download",
            query={"recordId": record_id, "contentType": content_type},
            output=output,
            fallback_name=f"record-{record_id}-{content_type}",
            title_lookup=("vault.record.list", "recordId", record_id),
        )

    def my_conference_download(
        self,
        *,
        conference_id: str,
        content_type: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载会议资源文件（vault.my-conference.download）。

        content_type 取值: asr=语音转写, summary=纪要。
        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="vault.my-conference.download",
            query={"conferenceId": conference_id, "contentType": content_type},
            output=output,
            fallback_name=f"conference-{conference_id}-{content_type}",
            title_lookup=("vault.my-conference.list", "conferenceId", conference_id),
        )


class AsyncVault:
    """Async mirror of `Vault`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def drive_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        file_type: Any = None,
        space_type: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询个人网盘文件列表（vault.drive.list）。

        space_type 取值: 1=我的文件, 2=租户文件; 支持单值或列表。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "fileTypeList": _as_list(file_type),
                "spaceTypeList": _as_list(space_type),
            }
        )
        result = await self._client._call("vault.drive.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="vault.drive.list",
            id_field="fileId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def record_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        category: Any = None,
        space_type: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询录音转写记录列表（vault.record.list）。

        category 录音来源: upload/link/mobile/gtNote/pc/share;
        space_type 取值: 1=我的记录, 2=租户记录; 均支持单值或列表。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "categoryList": _as_list(category),
                "spaceTypeList": _as_list(space_type),
            }
        )
        result = await self._client._call("vault.record.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="vault.record.list",
            id_field="recordId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def my_conference_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        security: Any = None,
        institution: Any = None,
        category: Any = None,
        source: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询我的会议列表（vault.my-conference.list）。

        source 录制来源（数字，可单值或列表）: 1=企微会议助理 2=会议服务微信群。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area),
                "securityList": _as_list(security),
                "institutionList": _as_list(institution),
                "categoryList": _as_list(category),
                "sourceList": _as_list(source),
            }
        )
        result = await self._client._call("vault.my-conference.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="vault.my-conference.list",
            id_field="conferenceId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def wechat_message_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        security: Any = None,
        wechat_group_id: Any = None,
        industry: Any = None,
        category: Any = None,
        tag: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询微信群消息列表（vault.wechat-message.list）。

        category 消息类型: text/image/documents/url; tag 标签: roadShow=路演,
        research=调研, strategyMeeting=策略会, meetingSummary=会议纪要,
        industryComment=行业点评, companyComment=公司点评, earningsReview=业绩点评。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "securityList": _as_list(security),
                "wechatGroupIdList": _as_list(wechat_group_id),
                "industryIdList": _as_list(industry),
                "categoryList": _as_list(category),
                "tagList": _as_list(tag),
            }
        )
        result = await self._client._call("vault.wechat-message.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def wechat_chatroom_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        room_name: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询微信群 chatroomId 列表（vault.wechat-chatroom.list）。

        room_name 支持单值或列表; 请求时会拼成逗号分隔字符串。
        省略 size 拉取全部群（接口返回 {total, list}，按 total 并发翻页，
        单页上限 50）；传 size=N 仅取前 N 条。
        """
        names = _as_list(room_name) or []
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "roomName": ",".join(names) if names else None,
            }
        )
        result = await self._client._call("vault.wechat-chatroom.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def stock_pool_list(self, *, raw: bool = False) -> pd.DataFrame | dict[str, Any]:
        """查询用户股票池 ID 与名称列表（vault.stock-pool.list）。"""
        result = await self._client._call("vault.stock-pool.list", body={})
        if raw:
            return result  # type: ignore[no-any-return]
        rows: list[Any] = []
        if isinstance(result, dict):
            pool_list = result.get("poolList") or result.get("list") or []
            if isinstance(pool_list, list):
                rows = pool_list
        elif isinstance(result, list):
            rows = result
        return to_dataframe(rows, schema=None)

    async def stock_pool_stocks(
        self,
        *,
        pool_id: Any = "all",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询股票池内的证券列表（vault.stock-pool.stocks）。

        pool_id 默认 "all" 表示全部股票池; 真实 ID 见 stock_pool_list。
        """
        body = {"poolIdList": _as_list(pool_id)}
        result = await self._client._call("vault.stock-pool.stocks", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def drive_download(
        self,
        *,
        file_id: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载网盘文件（vault.drive.download）。

        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="vault.drive.download",
            query={"fileId": file_id},
            output=output,
            fallback_name=f"file-{file_id}",
            title_lookup=("vault.drive.list", "fileId", file_id),
        )

    async def record_download(
        self,
        *,
        record_id: str,
        content_type: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载录音转写文件（vault.record.download）。

        content_type 取值: original=原始音频, asr=语音转写, summary=纪要。
        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="vault.record.download",
            query={"recordId": record_id, "contentType": content_type},
            output=output,
            fallback_name=f"record-{record_id}-{content_type}",
            title_lookup=("vault.record.list", "recordId", record_id),
        )

    async def my_conference_download(
        self,
        *,
        conference_id: str,
        content_type: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载会议资源文件（vault.my-conference.download）。

        content_type 取值: asr=语音转写, summary=纪要。
        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="vault.my-conference.download",
            query={"conferenceId": conference_id, "contentType": content_type},
            output=output,
            fallback_name=f"conference-{conference_id}-{content_type}",
            title_lookup=("vault.my-conference.list", "conferenceId", conference_id),
        )
