from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._download import download_to_path, download_to_path_async
from gangtise_openapi._normalize import to_dataframe


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


def _extract_rows(result: Any) -> list[Any]:
    if isinstance(result, dict):
        rows = result.get("list", [])
        return rows if isinstance(rows, list) else []
    if isinstance(result, list):
        return result
    return []


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
        body = _strip_none({
            "from": from_,
            "size": size,
            "startTime": start_time,
            "endTime": end_time,
            "keyword": keyword,
            "fileTypeList": _as_list(file_type),
            "spaceTypeList": _as_list(space_type),
        })
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
        body = _strip_none({
            "from": from_,
            "size": size,
            "startTime": start_time,
            "endTime": end_time,
            "keyword": keyword,
            "categoryList": _as_list(category),
            "spaceTypeList": _as_list(space_type),
        })
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none({
            "from": from_,
            "size": size,
            "startTime": start_time,
            "endTime": end_time,
            "keyword": keyword,
            "researchAreaList": _as_list(research_area),
            "securityList": _as_list(security),
            "institutionList": _as_list(institution),
            "categoryList": _as_list(category),
        })
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
        body = _strip_none({
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
        })
        result = self._client._call("vault.wechat-message.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    def wechat_chatroom_list(
        self,
        *,
        from_: int = 0,
        size: int = 20,
        room_name: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        names = _as_list(room_name) or []
        body = _strip_none({
            "from": from_,
            "size": size,
            "roomName": ",".join(names) if names else None,
        })
        result = self._client._call("vault.wechat-chatroom.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    def stock_pool_list(self, *, raw: bool = False) -> pd.DataFrame | dict[str, Any]:
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
        body = _strip_none({
            "from": from_,
            "size": size,
            "startTime": start_time,
            "endTime": end_time,
            "keyword": keyword,
            "fileTypeList": _as_list(file_type),
            "spaceTypeList": _as_list(space_type),
        })
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
        body = _strip_none({
            "from": from_,
            "size": size,
            "startTime": start_time,
            "endTime": end_time,
            "keyword": keyword,
            "categoryList": _as_list(category),
            "spaceTypeList": _as_list(space_type),
        })
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none({
            "from": from_,
            "size": size,
            "startTime": start_time,
            "endTime": end_time,
            "keyword": keyword,
            "researchAreaList": _as_list(research_area),
            "securityList": _as_list(security),
            "institutionList": _as_list(institution),
            "categoryList": _as_list(category),
        })
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
        body = _strip_none({
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
        })
        result = await self._client._call("vault.wechat-message.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def wechat_chatroom_list(
        self,
        *,
        from_: int = 0,
        size: int = 20,
        room_name: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        names = _as_list(room_name) or []
        body = _strip_none({
            "from": from_,
            "size": size,
            "roomName": ",".join(names) if names else None,
        })
        result = await self._client._call("vault.wechat-chatroom.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def stock_pool_list(
        self, *, raw: bool = False
    ) -> pd.DataFrame | dict[str, Any]:
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
        return await download_to_path_async(
            client=self._client,
            endpoint_key="vault.my-conference.download",
            query={"conferenceId": conference_id, "contentType": content_type},
            output=output,
            fallback_name=f"conference-{conference_id}-{content_type}",
            title_lookup=("vault.my-conference.list", "conferenceId", conference_id),
        )
