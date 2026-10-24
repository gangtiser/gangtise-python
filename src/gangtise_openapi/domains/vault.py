# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# strings that intentionally use fullwidth punctuation.)
from __future__ import annotations

import os
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._download import download_to_path, download_to_path_async
from gangtise_openapi._errors import ValidationError
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi._transport import UploadFile
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _as_named_list,
    _extract_rows,
    _refuse_empty,
    _request_body,
    _result_to_dataframe,
    _validate_enum,
)

# Server-side cap per uploaded file (spec: <=100MB). Checked locally so a doomed
# upload fails instantly instead of after a long transfer (TS v0.41.0 driveUpload.ts).
DRIVE_UPLOAD_MAX_BYTES = 100 * 1024 * 1024
# Drive name cap (spec: 200), counted in UTF-16 code units — what the server counts
# (Java `String.length()`), so an emoji is 2. Python's `len()` counts code points.
DRIVE_NAME_MAX = 200
_DRIVE_SPACES = (1, 2)
_DRIVE_RENAME_TYPES = ("file", "folder")
# The platform's `contentType` values (TS vault.ts `contentTypeChoices`). An unknown
# value comes back as 130003 「没有文件可供下载」, which reads as "this record has no
# file" (probed by the CLI 2026-09-25), so it is refused locally (TS v0.43.0 ⑧).
_RECORD_CONTENT_TYPES = ("original", "asr", "summary")
_CONFERENCE_CONTENT_TYPES = ("asr", "summary")


def _check_choice(value: Any, *, name: str, allowed: tuple[str, ...]) -> str:
    """Whitelist for a scalar string enum kwarg, checked before any request."""
    if not isinstance(value, str) or value not in allowed:
        raise ValidationError(f"invalid {name}: {value!r} is not one of {'/'.join(allowed)}")
    return value


def _utf16_units(text: str) -> int:
    # surrogatepass: a POSIX file name with undecodable bytes arrives as lone
    # surrogates (surrogateescape); count them instead of crashing the check.
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def _read_drive_upload(
    file: str | Path, *, space_type: int, folder_id: str | None, title: str | None
) -> UploadFile:
    """Validate and load a drive upload. Every reason to reject the file is checked
    before the request goes out (TS v0.41.0 ``uploadDriveFile``)."""
    _validate_enum(space_type, name="space_type", allowed=_DRIVE_SPACES)
    # abspath, not resolve(): like Node's path.resolve it is lexical, so a symlink is
    # uploaded under ITS name rather than the target's.
    path = Path(os.path.abspath(Path(file).expanduser()))
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ValidationError(f"file not found: {file}") from error
    if not path.is_file():
        raise ValidationError(f"not a file: {file}")
    if size == 0:
        raise ValidationError(f"file is empty: {file}")
    if size > DRIVE_UPLOAD_MAX_BYTES:
        raise ValidationError(
            f"file is {size / 1024 / 1024:.1f}MB — the drive accepts at most 100MB per file"
        )
    name = title if title is not None else path.name
    units = _utf16_units(name)
    if units > DRIVE_NAME_MAX:
        raise ValidationError(
            f"file name is {units} characters — the drive accepts at most {DRIVE_NAME_MAX} "
            "(counted in UTF-16 units: an emoji counts as 2); pass a shorter title"
        )
    fields = [("spaceType", str(space_type))]
    if folder_id is not None:
        fields.append(("folderId", str(folder_id)))
    if title is not None:
        fields.append(("title", title))
    return UploadFile(filename=path.name, data=path.read_bytes(), fields=tuple(fields))


def _drive_copy_body(
    file_id: Any, target_folder_id: Any, folder_id: Any, target_parent_id: Any
) -> dict[str, Any]:
    """The endpoint takes one of two shapes keyed on ``copyType``; a mixed or half
    request would only come back as a bare 100001/100003, so it is refused before any
    request (TS v0.45.0 ``drive-copy``)."""
    files = _as_named_list(file_id, "file_id")
    by_file = files is not None or target_folder_id is not None
    by_folder = folder_id is not None or target_parent_id is not None
    if by_file and by_folder:
        raise ValidationError(
            "pass either file_id + target_folder_id (copy files) or folder_id + "
            "target_parent_id (copy a folder), not both"
        )
    if by_file and (files is None or target_folder_id is None):
        raise ValidationError("copying files needs both file_id and target_folder_id")
    if by_folder and (folder_id is None or target_parent_id is None):
        raise ValidationError("copying a folder needs both folder_id and target_parent_id")
    if not by_file and not by_folder:
        raise ValidationError(
            "pass either file_id + target_folder_id (copy files) or folder_id + "
            "target_parent_id (copy a folder)"
        )
    if by_file:
        return _request_body(
            {"copyType": "file", "fileIdList": files, "targetFolderId": target_folder_id}
        )
    return _request_body(
        {"copyType": "folder", "folderId": folder_id, "targetParentId": target_parent_id}
    )


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
        file_type: FilterValue | None = None,
        space_type: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询个人网盘文件列表（vault.drive.list）。

        space_type 取值: 1=我的文件, 2=租户文件; 支持单值或列表。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "fileTypeList": _as_list(file_type, "file_type"),
                "spaceTypeList": _as_list(space_type, "space_type"),
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
        category: FilterValue | None = None,
        space_type: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询录音转写记录列表（vault.record.list）。

        category 录音来源: upload/link/mobile/gtNote/pc/share;
        space_type 取值: 1=我的记录, 2=租户记录; 均支持单值或列表。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "categoryList": _as_list(category, "category"),
                "spaceTypeList": _as_list(space_type, "space_type"),
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
        research_area: FilterValue | None = None,
        security: FilterValue | None = None,
        institution: FilterValue | None = None,
        category: FilterValue | None = None,
        source: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询我的会议列表（vault.my-conference.list）。

        source 录制来源（数字，可单值或列表）: 1=企微会议助理 2=会议服务微信群。
        可查范围前溯 1 个月（各档相同）。
        按条计费 0.1 积分/条: 省略 size 时按 total × 单价估算，超过 1000 积分拒绝；
        传 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area, "research_area"),
                "securityList": _as_list(security, "security"),
                "institutionList": _as_list(institution, "institution"),
                "categoryList": _as_list(category, "category"),
                "sourceList": _as_list(source, "source"),
            }
        )
        result = self._client._call("vault.my-conference.list", body=body, confirm=confirm)
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
        security: FilterValue | None = None,
        wechat_group_id: FilterValue | None = None,
        industry: FilterValue | None = None,
        category: FilterValue | None = None,
        tag: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询微信群消息列表（vault.wechat-message.list）。

        category 消息类型: text/image/documents/url; tag 标签: roadShow=路演,
        research=调研, strategyMeeting=策略会, meetingSummary=会议纪要,
        industryComment=行业点评, companyComment=公司点评, earningsReview=业绩点评。
        industry 只收中信码 (1008001xx); 申万码与未知值被接口以 100005 拒绝
        (2026-09 起——此前是静默忽略并返回未过滤的全量, 那更危险)。

        按偏移量最多取到第 10000 条（from_ + 条数不能超过 10000），窗口外的行取不到
        也数不到；total 最多也只报到 10000——正好报 10000 时实际条数可能更多，按封顶
        处理（告警并标 partial + totalCapped）。要更多请缩短时间范围分段取，每段的
        total 低于 10000 才说明取全了。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "securityList": _as_list(security, "security"),
                "wechatGroupIdList": _as_list(wechat_group_id, "wechat_group_id"),
                "industryIdList": _as_named_list(industry, "industry"),
                "categoryList": _as_list(category, "category"),
                "tagList": _as_list(tag, "tag"),
            }
        )
        result = self._client._call("vault.wechat-message.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def wechat_chatroom_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        room_name: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询微信群 chatroomId 列表（vault.wechat-chatroom.list）。

        room_name 支持单值或列表; 请求时会拼成逗号分隔字符串。
        省略 size 拉取全部群（接口返回 {total, list}，按 total 并发翻页，
        单页上限 50）；传 size=N 仅取前 N 条。
        """
        _refuse_empty(room_name, "room_name")
        names = _as_list(room_name, "room_name") or []
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "roomName": ",".join(map(str, names)) if names else None,
            }
        )
        result = self._client._call("vault.wechat-chatroom.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

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
        pool_id: FilterValue = "all",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询股票池内的证券列表（vault.stock-pool.stocks）。

        pool_id 默认 "all" 表示全部股票池, 显式传空列表或空白字符串同样查全部股票池;
        真实 ID 见 stock_pool_list。
        """
        # TS sends ["all"] for an omitted AND an empty --pool-id.
        body = {"poolIdList": _as_list(pool_id, "pool_id") or ["all"]}
        result = self._client._call("vault.stock-pool.stocks", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- stock-pool writes (TS v0.40.0) ----
    # Writes return the server's `data` dict as is: the batch ones carry `partial`
    # next to `successList` / `failList`, which a DataFrame would drop. `raw` is
    # accepted only to keep the signature uniform.

    def stock_pool_create(self, *, name: str, raw: bool = False) -> dict[str, Any]:
        """新建股票池（vault.stock-pool.create），返回 {poolId, poolName}。

        免费；写操作，改动当前账号的数据。name 规则: ≤10 个字符（按字符计，中文算 1
        个，超出 230007；在 Gangtise 终端里建的老池名可以更长，通过本接口建池 / 改名
        一律受此上限）；不能与已有池重名（230006，判重是整串精确比较——首尾空格不去、
        大小写不归一，" A " 与 "A"、abc 与 ABC 可并存）；每账号最多 30 个池（230003）。

        该端点标 no-replay: 超时 / 5xx 不自动重发——重发一个其实已建成的请求只会撞
        重名、把成功报成失败。超时后先 stock_pool_list() 看池建成没有，再决定重来。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"poolName": name})
        return self._client._call("vault.stock-pool.create", body=body)  # type: ignore[no-any-return]

    def stock_pool_rename(self, *, pool_id: str, name: str, raw: bool = False) -> dict[str, Any]:
        """股票池改名（vault.stock-pool.rename），返回 {poolId, poolName}。

        免费；只改名，池内自选股不受影响。pool_id 取自 stock_pool_list()。新名的长度与
        重名规则同 stock_pool_create（≤10 个字符否则 230007，重名 230006）；改成该池
        自己当前的名字算成功。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"poolId": pool_id, "poolName": name})
        return self._client._call("vault.stock-pool.rename", body=body)  # type: ignore[no-any-return]

    def stock_pool_add_stock(
        self, *, pool_id: str, security: FilterValue, raw: bool = False
    ) -> dict[str, Any]:
        """向股票池批量添加证券（vault.stock-pool.add-stock），返回 {successList, failList}。

        免费。pool_id 取自 stock_pool_list()；security 支持单值或列表，单池上限 10000 只。
        代码要带市场后缀且大小写敏感: 600519.SH / 00700.HK / AAPL.O 可混在一次请求里；
        600519（缺后缀）、600519.sh、aapl.o、700.HK（港股要 5 位）都会进 failList 报
        「证券代码不存在」，而不是报错。首尾空格服务端自动去掉，重复代码去重。

        逐条处理: 单条失败服务端仍回 000000，明细在 failList（{securityCode, failReason}）；
        failList 非空时发 UserWarning 列出失败项，并在返回 dict 上标 partial=True。
        幂等: 重复添加已在池内的证券算成功、计入 successList。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body(
            {"poolId": pool_id, "securityCodeList": _as_named_list(security, "security")}
        )
        return self._client._call("vault.stock-pool.add-stock", body=body)  # type: ignore[no-any-return]

    def stock_pool_remove_stock(
        self, *, pool_id: str, security: FilterValue, raw: bool = False
    ) -> dict[str, Any]:
        """从股票池批量移出证券（vault.stock-pool.remove-stock），返回 {successList, failList}。

        免费。代码规则同 stock_pool_add_stock（带市场后缀、大小写敏感，写错进 failList）。
        逐条处理: 单条失败服务端仍回 000000，明细在 failList；非空时发 UserWarning 并在
        返回 dict 上标 partial=True。幂等: 移出本就不在池内的证券算成功。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body(
            {"poolId": pool_id, "securityCodeList": _as_named_list(security, "security")}
        )
        return self._client._call("vault.stock-pool.remove-stock", body=body)  # type: ignore[no-any-return]

    def stock_pool_delete(
        self, *, pool_id: FilterValue, confirm: bool = False, raw: bool = False
    ) -> dict[str, Any]:
        """批量删除股票池（vault.stock-pool.delete），返回 {successList, failList}。

        🔴 不可恢复: 删池会同时移除池内全部证券的关注关系（个股的投资笔记独立保留、
        不受影响）。必须传 confirm=True，否则在发请求前抛 ValidationError（直接调
        client._call 同样要 confirm）。先用 stock_pool_list() 核对 ID 对应的池名；被拒后
        别自动补 confirm=True 重跑，先把要删的池名给用户确认。

        pool_id 支持单值或列表。删不存在的 poolId 算幂等成功、计入 successList；单条
        失败进 failList（按 poolId），非空时发 UserWarning 并标 partial=True。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"poolIdList": _as_list(pool_id, "pool_id")})
        return self._client._call(  # type: ignore[no-any-return]
            "vault.stock-pool.delete", body=body, confirm=confirm
        )

    # ---- drive management (TS v0.41.0 ③) ----
    # All free. Folder IDs come from drive_folder_list ("root" = a space's root);
    # file IDs from drive_folder_list or drive_list. Same-name files and folders are
    # allowed (told apart only by ID), so upload / create-folder / copy are no-replay.

    def drive_folder_list(
        self,
        *,
        space_type: int = 1,
        parent_id: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """列出云盘某文件夹的直接子文件夹与文件（vault.drive.folder-list，免费）。

        返回 {folderTotal, folderList, fileTotal, fileList}，只含直接下级、不递归:
        folderList[]{folderId, parentId, folderName, spaceType, createTime}，
        fileList[]{fileId, title, fileSize, createTime}。两张表同在一个 dict 里，所以返回
        服务端原始 data；raw 仅为签名统一，返回相同。

        space_type: 1=我的云盘（默认）, 2=租户云盘。parent_id 为该空间里的文件夹 ID，
        不传（或 "root"）即该空间根目录；属于另一空间的 ID 报 100003
        （「parentId 与 spaceType 不一致」）。
        """
        _validate_enum(space_type, name="space_type", allowed=_DRIVE_SPACES)
        body = _request_body({"spaceType": space_type, "parentId": parent_id})
        return self._client._call("vault.drive.folder-list", body=body)  # type: ignore[no-any-return]

    def drive_upload(
        self,
        *,
        file: str | Path,
        space_type: int = 1,
        folder_id: str | None = None,
        title: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """上传文件到 AI 云盘（vault.drive.upload，免费），返回 {fileId, title, folderId, spaceType, fileSize}。

        单个文件 ≤100MB；试用账号每天累计上传 ≤500MB（超出 230008）。发请求前本地先拦:
        文件不存在 / 不是文件 / 空文件 / 超过 100MB / 名称超长。

        title 为云盘里的名称，不传用本地文件名；名称 ≤200 个字符，按 UTF-16 计——中文算
        1、emoji 算 2（服务端这样计，超出报 230004），本地按同一口径先拦。
        space_type: 1=我的云盘（默认）, 2=租户云盘（对整个租户可见）；folder_id 为该空间
        里的目标文件夹 ID，不传（或 "root"）即根目录，属于另一空间报 100003。

        🔴 云盘允许同名（以 ID 区分），每上传一次就多一份: 该端点标 no-replay，超时 /
        5xx 不自动重发（超时下限 300 秒）；对同一内容别重复执行。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        upload = _read_drive_upload(file, space_type=space_type, folder_id=folder_id, title=title)
        return self._client._call("vault.drive.upload", body=upload)  # type: ignore[no-any-return]

    def drive_create_folder(
        self,
        *,
        name: str,
        space_type: int = 1,
        parent_id: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """新建云盘文件夹（vault.drive.create-folder，免费），返回 {folderId, parentId, folderName, spaceType, createTime}。

        name ≤200 个字符（按 UTF-16 计，emoji 算 2；超出 230004）。space_type: 1=我的云盘
        （默认）, 2=租户云盘；parent_id 为该空间里的父文件夹 ID，不传（或 "root"）即根目录，
        属于另一空间报 100003。

        同名文件夹允许（以 ID 区分），每执行一次就多建一个: 该端点标 no-replay，超时 /
        5xx 不自动重发。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        _validate_enum(space_type, name="space_type", allowed=_DRIVE_SPACES)
        body = _request_body({"folderName": name, "spaceType": space_type, "parentId": parent_id})
        return self._client._call("vault.drive.create-folder", body=body)  # type: ignore[no-any-return]

    def drive_rename(self, *, type_: str, id_: str, name: str, raw: bool = False) -> dict[str, Any]:
        """重命名云盘文件或文件夹（vault.drive.rename，免费），返回 {id, name}。

        type_: file / folder（本地校验），指明 id_ 是文件 ID 还是文件夹 ID（映射为请求
        字段 type / id）。name ≤200 个字符（按 UTF-16 计，超出 230004）。重复执行结果
        不变，保留默认重试。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        _check_choice(type_, name="type_", allowed=_DRIVE_RENAME_TYPES)
        body = _request_body({"type": type_, "id": id_, "name": name})
        return self._client._call("vault.drive.rename", body=body)  # type: ignore[no-any-return]

    def drive_move_file(
        self, *, file_id: FilterValue, target_folder_id: str, raw: bool = False
    ) -> dict[str, Any]:
        """把云盘文件移到同一空间的文件夹（vault.drive.move-file，免费），返回 {successList, failList}。

        file_id 支持单值或列表；target_folder_id 为目标文件夹 ID 或 "root"。只能在同一
        空间内移动: 另一空间的文件进 failList（「空间不一致」）——跨空间用 drive_copy()。
        单条失败服务端仍回 000000，明细在 failList（{fileId, failReason}）；非空时发
        UserWarning 并在返回 dict 上标 partial=True。重复执行结果不变，保留默认重试。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body(
            {"fileIdList": _as_list(file_id, "file_id"), "targetFolderId": target_folder_id}
        )
        return self._client._call("vault.drive.move-file", body=body)  # type: ignore[no-any-return]

    def drive_move_folder(
        self, *, folder_id: str, target_parent_id: str, raw: bool = False
    ) -> dict[str, Any]:
        """把云盘文件夹移到同一空间的另一文件夹下（vault.drive.move-folder，免费），返回 {folderId, parentId}。

        target_parent_id 为目标父文件夹 ID 或 "root"；移到另一空间、文件夹自身或其子文件夹
        报 230005——跨空间用 drive_copy(folder_id=..., target_parent_id=...)。重复执行结果
        不变，保留默认重试。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"folderId": folder_id, "targetParentId": target_parent_id})
        return self._client._call("vault.drive.move-folder", body=body)  # type: ignore[no-any-return]

    def drive_copy(
        self,
        *,
        file_id: FilterValue | None = None,
        target_folder_id: str | None = None,
        folder_id: str | None = None,
        target_parent_id: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """把云盘文件或整个文件夹复制到另一空间: 我的云盘 ↔ 租户云盘（vault.drive.copy，免费）。

        源保留不动，目标 ID 必须在另一空间（"root" 即另一空间的根目录），同空间复制报
        100003。两种用法二选一，混传、只传一半或都不传都在发请求前抛 ValidationError:

        - 复制文件: file_id（单值或列表）+ target_folder_id，返回 {successList, failList}。
          successList[]{fileId, newFileId}（newFileId 是副本的 ID）；单条失败进 failList
          （{fileId, failReason}），非空时发 UserWarning 并标 partial=True。
        - 复制文件夹: folder_id + target_parent_id，连同其中的子文件夹与文件一起复制，
          返回 {folderId, newFolderId}（newFolderId 是另一空间里副本文件夹的 ID）。

        云盘允许同名，每复制一次就多一份: 该端点标 no-replay，超时 / 5xx 不自动重发。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _drive_copy_body(file_id, target_folder_id, folder_id, target_parent_id)
        return self._client._call("vault.drive.copy", body=body)  # type: ignore[no-any-return]

    def drive_delete_file(
        self, *, file_id: FilterValue, confirm: bool = False, raw: bool = False
    ) -> dict[str, Any]:
        """删除云盘文件（vault.drive.delete-file，免费），返回 {successList, failList}。

        🔴 不可恢复，必须传 confirm=True，否则在发请求前抛 ValidationError（直接调
        client._call 同样要 confirm）。先用 drive_folder_list() / drive_list() 核对文件 ID
        对应的文件名；被拒后别自动补 confirm=True 重跑，先把要删的文件名给用户确认。

        file_id 支持单值或列表；单条失败（如「文件不存在」）进 failList（{fileId, failReason}），
        非空时发 UserWarning 并标 partial=True。该端点标 no-replay: 重发一个已生效的删除
        会回「文件不存在」或 130002，把成功报成失败。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"fileIdList": _as_list(file_id, "file_id")})
        return self._client._call(  # type: ignore[no-any-return]
            "vault.drive.delete-file", body=body, confirm=confirm
        )

    def drive_delete_folder(
        self, *, folder_id: str, confirm: bool = False, raw: bool = False
    ) -> dict[str, Any]:
        """删除云盘文件夹（vault.drive.delete-folder，免费），返回 {folderId}。

        🔴 连同其中全部子文件夹与文件一起删除，不可恢复；必须传 confirm=True，否则在发
        请求前抛 ValidationError（直接调 client._call 同样要 confirm）。删前先
        drive_folder_list(space_type=..., parent_id=folder_id) 看清里面有什么；被拒后
        别自动补 confirm=True 重跑。该端点标 no-replay（理由同 drive_delete_file）。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"folderId": folder_id})
        return self._client._call(  # type: ignore[no-any-return]
            "vault.drive.delete-folder", body=body, confirm=confirm
        )

    # ---- download endpoints ----

    def drive_download(
        self,
        *,
        file_id: str,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载网盘文件（vault.drive.download）。

        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="vault.drive.download",
            query={"fileId": file_id},
            output=output,
            fallback_name=f"file-{file_id}",
            title_lookup=("vault.drive.list", "fileId", file_id, resolve_title),
        )

    def record_download(
        self,
        *,
        record_id: str,
        content_type: str,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载录音转写文件（vault.record.download）。

        content_type 取值: original=原始文件, asr=语音识别, summary=AI 速记（「与我分享」
        类型的录音无法下载原始文件）。其他取值在本地拒绝、不发请求——接口对错值报的是
        130003「没有文件可供下载」, 容易误读成这条记录没附件。
        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        _check_choice(content_type, name="content_type", allowed=_RECORD_CONTENT_TYPES)
        return download_to_path(
            client=self._client,
            endpoint_key="vault.record.download",
            query={"recordId": record_id, "contentType": content_type},
            output=output,
            fallback_name=f"record-{record_id}-{content_type}",
            title_lookup=("vault.record.list", "recordId", record_id, resolve_title),
        )

    def my_conference_download(
        self,
        *,
        conference_id: str,
        content_type: str,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载会议资源文件（vault.my-conference.download）。

        30 积分/篇, 超时 / 5xx 不自动重发。content_type 取值: asr=语音识别, summary=AI 速记;
        其他取值在本地拒绝、不发请求——接口对错值报的是 130003「没有文件可供下载」,
        容易误读成这场会议没附件。
        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        _check_choice(content_type, name="content_type", allowed=_CONFERENCE_CONTENT_TYPES)
        return download_to_path(
            client=self._client,
            endpoint_key="vault.my-conference.download",
            query={"conferenceId": conference_id, "contentType": content_type},
            output=output,
            fallback_name=f"conference-{conference_id}-{content_type}",
            title_lookup=("vault.my-conference.list", "conferenceId", conference_id, resolve_title),
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
        file_type: FilterValue | None = None,
        space_type: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询个人网盘文件列表（vault.drive.list）。

        space_type 取值: 1=我的文件, 2=租户文件; 支持单值或列表。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "fileTypeList": _as_list(file_type, "file_type"),
                "spaceTypeList": _as_list(space_type, "space_type"),
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
        category: FilterValue | None = None,
        space_type: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询录音转写记录列表（vault.record.list）。

        category 录音来源: upload/link/mobile/gtNote/pc/share;
        space_type 取值: 1=我的记录, 2=租户记录; 均支持单值或列表。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "categoryList": _as_list(category, "category"),
                "spaceTypeList": _as_list(space_type, "space_type"),
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
        research_area: FilterValue | None = None,
        security: FilterValue | None = None,
        institution: FilterValue | None = None,
        category: FilterValue | None = None,
        source: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询我的会议列表（vault.my-conference.list）。

        source 录制来源（数字，可单值或列表）: 1=企微会议助理 2=会议服务微信群。
        可查范围前溯 1 个月（各档相同）。
        按条计费 0.1 积分/条: 省略 size 时按 total × 单价估算，超过 1000 积分拒绝；
        传 size 取一部分，或 confirm=True 确认全量。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area, "research_area"),
                "securityList": _as_list(security, "security"),
                "institutionList": _as_list(institution, "institution"),
                "categoryList": _as_list(category, "category"),
                "sourceList": _as_list(source, "source"),
            }
        )
        result = await self._client._call("vault.my-conference.list", body=body, confirm=confirm)
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
        security: FilterValue | None = None,
        wechat_group_id: FilterValue | None = None,
        industry: FilterValue | None = None,
        category: FilterValue | None = None,
        tag: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询微信群消息列表（vault.wechat-message.list）。

        category 消息类型: text/image/documents/url; tag 标签: roadShow=路演,
        research=调研, strategyMeeting=策略会, meetingSummary=会议纪要,
        industryComment=行业点评, companyComment=公司点评, earningsReview=业绩点评。
        industry 只收中信码 (1008001xx); 申万码与未知值被接口以 100005 拒绝
        (2026-09 起——此前是静默忽略并返回未过滤的全量, 那更危险)。

        按偏移量最多取到第 10000 条（from_ + 条数不能超过 10000），窗口外的行取不到
        也数不到；total 最多也只报到 10000——正好报 10000 时实际条数可能更多，按封顶
        处理（告警并标 partial + totalCapped）。要更多请缩短时间范围分段取，每段的
        total 低于 10000 才说明取全了。
        """
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "securityList": _as_list(security, "security"),
                "wechatGroupIdList": _as_list(wechat_group_id, "wechat_group_id"),
                "industryIdList": _as_named_list(industry, "industry"),
                "categoryList": _as_list(category, "category"),
                "tagList": _as_list(tag, "tag"),
            }
        )
        result = await self._client._call("vault.wechat-message.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def wechat_chatroom_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        room_name: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询微信群 chatroomId 列表（vault.wechat-chatroom.list）。

        room_name 支持单值或列表; 请求时会拼成逗号分隔字符串。
        省略 size 拉取全部群（接口返回 {total, list}，按 total 并发翻页，
        单页上限 50）；传 size=N 仅取前 N 条。
        """
        _refuse_empty(room_name, "room_name")
        names = _as_list(room_name, "room_name") or []
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "roomName": ",".join(map(str, names)) if names else None,
            }
        )
        result = await self._client._call("vault.wechat-chatroom.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

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
        pool_id: FilterValue = "all",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询股票池内的证券列表（vault.stock-pool.stocks）。

        pool_id 默认 "all" 表示全部股票池, 显式传空列表或空白字符串同样查全部股票池;
        真实 ID 见 stock_pool_list。
        """
        # TS sends ["all"] for an omitted AND an empty --pool-id.
        body = {"poolIdList": _as_list(pool_id, "pool_id") or ["all"]}
        result = await self._client._call("vault.stock-pool.stocks", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- stock-pool writes (TS v0.40.0) ----
    # Writes return the server's `data` dict as is: the batch ones carry `partial`
    # next to `successList` / `failList`, which a DataFrame would drop. `raw` is
    # accepted only to keep the signature uniform.

    async def stock_pool_create(self, *, name: str, raw: bool = False) -> dict[str, Any]:
        """新建股票池（vault.stock-pool.create），返回 {poolId, poolName}。

        免费；写操作，改动当前账号的数据。name 规则: ≤10 个字符（按字符计，中文算 1
        个，超出 230007；在 Gangtise 终端里建的老池名可以更长，通过本接口建池 / 改名
        一律受此上限）；不能与已有池重名（230006，判重是整串精确比较——首尾空格不去、
        大小写不归一，" A " 与 "A"、abc 与 ABC 可并存）；每账号最多 30 个池（230003）。

        该端点标 no-replay: 超时 / 5xx 不自动重发——重发一个其实已建成的请求只会撞
        重名、把成功报成失败。超时后先 stock_pool_list() 看池建成没有，再决定重来。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"poolName": name})
        return await self._client._call("vault.stock-pool.create", body=body)  # type: ignore[no-any-return]

    async def stock_pool_rename(
        self, *, pool_id: str, name: str, raw: bool = False
    ) -> dict[str, Any]:
        """股票池改名（vault.stock-pool.rename），返回 {poolId, poolName}。

        免费；只改名，池内自选股不受影响。pool_id 取自 stock_pool_list()。新名的长度与
        重名规则同 stock_pool_create（≤10 个字符否则 230007，重名 230006）；改成该池
        自己当前的名字算成功。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"poolId": pool_id, "poolName": name})
        return await self._client._call("vault.stock-pool.rename", body=body)  # type: ignore[no-any-return]

    async def stock_pool_add_stock(
        self, *, pool_id: str, security: FilterValue, raw: bool = False
    ) -> dict[str, Any]:
        """向股票池批量添加证券（vault.stock-pool.add-stock），返回 {successList, failList}。

        免费。pool_id 取自 stock_pool_list()；security 支持单值或列表，单池上限 10000 只。
        代码要带市场后缀且大小写敏感: 600519.SH / 00700.HK / AAPL.O 可混在一次请求里；
        600519（缺后缀）、600519.sh、aapl.o、700.HK（港股要 5 位）都会进 failList 报
        「证券代码不存在」，而不是报错。首尾空格服务端自动去掉，重复代码去重。

        逐条处理: 单条失败服务端仍回 000000，明细在 failList（{securityCode, failReason}）；
        failList 非空时发 UserWarning 列出失败项，并在返回 dict 上标 partial=True。
        幂等: 重复添加已在池内的证券算成功、计入 successList。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body(
            {"poolId": pool_id, "securityCodeList": _as_named_list(security, "security")}
        )
        return await self._client._call("vault.stock-pool.add-stock", body=body)  # type: ignore[no-any-return]

    async def stock_pool_remove_stock(
        self, *, pool_id: str, security: FilterValue, raw: bool = False
    ) -> dict[str, Any]:
        """从股票池批量移出证券（vault.stock-pool.remove-stock），返回 {successList, failList}。

        免费。代码规则同 stock_pool_add_stock（带市场后缀、大小写敏感，写错进 failList）。
        逐条处理: 单条失败服务端仍回 000000，明细在 failList；非空时发 UserWarning 并在
        返回 dict 上标 partial=True。幂等: 移出本就不在池内的证券算成功。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body(
            {"poolId": pool_id, "securityCodeList": _as_named_list(security, "security")}
        )
        return await self._client._call("vault.stock-pool.remove-stock", body=body)  # type: ignore[no-any-return]

    async def stock_pool_delete(
        self, *, pool_id: FilterValue, confirm: bool = False, raw: bool = False
    ) -> dict[str, Any]:
        """批量删除股票池（vault.stock-pool.delete），返回 {successList, failList}。

        🔴 不可恢复: 删池会同时移除池内全部证券的关注关系（个股的投资笔记独立保留、
        不受影响）。必须传 confirm=True，否则在发请求前抛 ValidationError（直接调
        client._call 同样要 confirm）。先用 stock_pool_list() 核对 ID 对应的池名；被拒后
        别自动补 confirm=True 重跑，先把要删的池名给用户确认。

        pool_id 支持单值或列表。删不存在的 poolId 算幂等成功、计入 successList；单条
        失败进 failList（按 poolId），非空时发 UserWarning 并标 partial=True。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"poolIdList": _as_list(pool_id, "pool_id")})
        return await self._client._call(  # type: ignore[no-any-return]
            "vault.stock-pool.delete", body=body, confirm=confirm
        )

    # ---- drive management (TS v0.41.0 ③) ----
    # All free. Folder IDs come from drive_folder_list ("root" = a space's root);
    # file IDs from drive_folder_list or drive_list. Same-name files and folders are
    # allowed (told apart only by ID), so upload / create-folder / copy are no-replay.

    async def drive_folder_list(
        self,
        *,
        space_type: int = 1,
        parent_id: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """列出云盘某文件夹的直接子文件夹与文件（vault.drive.folder-list，免费）。

        返回 {folderTotal, folderList, fileTotal, fileList}，只含直接下级、不递归:
        folderList[]{folderId, parentId, folderName, spaceType, createTime}，
        fileList[]{fileId, title, fileSize, createTime}。两张表同在一个 dict 里，所以返回
        服务端原始 data；raw 仅为签名统一，返回相同。

        space_type: 1=我的云盘（默认）, 2=租户云盘。parent_id 为该空间里的文件夹 ID，
        不传（或 "root"）即该空间根目录；属于另一空间的 ID 报 100003
        （「parentId 与 spaceType 不一致」）。
        """
        _validate_enum(space_type, name="space_type", allowed=_DRIVE_SPACES)
        body = _request_body({"spaceType": space_type, "parentId": parent_id})
        return await self._client._call("vault.drive.folder-list", body=body)  # type: ignore[no-any-return]

    async def drive_upload(
        self,
        *,
        file: str | Path,
        space_type: int = 1,
        folder_id: str | None = None,
        title: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """上传文件到 AI 云盘（vault.drive.upload，免费），返回 {fileId, title, folderId, spaceType, fileSize}。

        单个文件 ≤100MB；试用账号每天累计上传 ≤500MB（超出 230008）。发请求前本地先拦:
        文件不存在 / 不是文件 / 空文件 / 超过 100MB / 名称超长。

        title 为云盘里的名称，不传用本地文件名；名称 ≤200 个字符，按 UTF-16 计——中文算
        1、emoji 算 2（服务端这样计，超出报 230004），本地按同一口径先拦。
        space_type: 1=我的云盘（默认）, 2=租户云盘（对整个租户可见）；folder_id 为该空间
        里的目标文件夹 ID，不传（或 "root"）即根目录，属于另一空间报 100003。

        🔴 云盘允许同名（以 ID 区分），每上传一次就多一份: 该端点标 no-replay，超时 /
        5xx 不自动重发（超时下限 300 秒）；对同一内容别重复执行。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        # Reading up to 100MB off disk is blocking I/O: keep it off the event loop.
        upload = await anyio.to_thread.run_sync(
            partial(
                _read_drive_upload,
                file,
                space_type=space_type,
                folder_id=folder_id,
                title=title,
            )
        )
        return await self._client._call("vault.drive.upload", body=upload)  # type: ignore[no-any-return]

    async def drive_create_folder(
        self,
        *,
        name: str,
        space_type: int = 1,
        parent_id: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """新建云盘文件夹（vault.drive.create-folder，免费），返回 {folderId, parentId, folderName, spaceType, createTime}。

        name ≤200 个字符（按 UTF-16 计，emoji 算 2；超出 230004）。space_type: 1=我的云盘
        （默认）, 2=租户云盘；parent_id 为该空间里的父文件夹 ID，不传（或 "root"）即根目录，
        属于另一空间报 100003。

        同名文件夹允许（以 ID 区分），每执行一次就多建一个: 该端点标 no-replay，超时 /
        5xx 不自动重发。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        _validate_enum(space_type, name="space_type", allowed=_DRIVE_SPACES)
        body = _request_body({"folderName": name, "spaceType": space_type, "parentId": parent_id})
        return await self._client._call("vault.drive.create-folder", body=body)  # type: ignore[no-any-return]

    async def drive_rename(
        self, *, type_: str, id_: str, name: str, raw: bool = False
    ) -> dict[str, Any]:
        """重命名云盘文件或文件夹（vault.drive.rename，免费），返回 {id, name}。

        type_: file / folder（本地校验），指明 id_ 是文件 ID 还是文件夹 ID（映射为请求
        字段 type / id）。name ≤200 个字符（按 UTF-16 计，超出 230004）。重复执行结果
        不变，保留默认重试。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        _check_choice(type_, name="type_", allowed=_DRIVE_RENAME_TYPES)
        body = _request_body({"type": type_, "id": id_, "name": name})
        return await self._client._call("vault.drive.rename", body=body)  # type: ignore[no-any-return]

    async def drive_move_file(
        self, *, file_id: FilterValue, target_folder_id: str, raw: bool = False
    ) -> dict[str, Any]:
        """把云盘文件移到同一空间的文件夹（vault.drive.move-file，免费），返回 {successList, failList}。

        file_id 支持单值或列表；target_folder_id 为目标文件夹 ID 或 "root"。只能在同一
        空间内移动: 另一空间的文件进 failList（「空间不一致」）——跨空间用 drive_copy()。
        单条失败服务端仍回 000000，明细在 failList（{fileId, failReason}）；非空时发
        UserWarning 并在返回 dict 上标 partial=True。重复执行结果不变，保留默认重试。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body(
            {"fileIdList": _as_list(file_id, "file_id"), "targetFolderId": target_folder_id}
        )
        return await self._client._call("vault.drive.move-file", body=body)  # type: ignore[no-any-return]

    async def drive_move_folder(
        self, *, folder_id: str, target_parent_id: str, raw: bool = False
    ) -> dict[str, Any]:
        """把云盘文件夹移到同一空间的另一文件夹下（vault.drive.move-folder，免费），返回 {folderId, parentId}。

        target_parent_id 为目标父文件夹 ID 或 "root"；移到另一空间、文件夹自身或其子文件夹
        报 230005——跨空间用 drive_copy(folder_id=..., target_parent_id=...)。重复执行结果
        不变，保留默认重试。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"folderId": folder_id, "targetParentId": target_parent_id})
        return await self._client._call("vault.drive.move-folder", body=body)  # type: ignore[no-any-return]

    async def drive_copy(
        self,
        *,
        file_id: FilterValue | None = None,
        target_folder_id: str | None = None,
        folder_id: str | None = None,
        target_parent_id: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """把云盘文件或整个文件夹复制到另一空间: 我的云盘 ↔ 租户云盘（vault.drive.copy，免费）。

        源保留不动，目标 ID 必须在另一空间（"root" 即另一空间的根目录），同空间复制报
        100003。两种用法二选一，混传、只传一半或都不传都在发请求前抛 ValidationError:

        - 复制文件: file_id（单值或列表）+ target_folder_id，返回 {successList, failList}。
          successList[]{fileId, newFileId}（newFileId 是副本的 ID）；单条失败进 failList
          （{fileId, failReason}），非空时发 UserWarning 并标 partial=True。
        - 复制文件夹: folder_id + target_parent_id，连同其中的子文件夹与文件一起复制，
          返回 {folderId, newFolderId}（newFolderId 是另一空间里副本文件夹的 ID）。

        云盘允许同名，每复制一次就多一份: 该端点标 no-replay，超时 / 5xx 不自动重发。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _drive_copy_body(file_id, target_folder_id, folder_id, target_parent_id)
        return await self._client._call("vault.drive.copy", body=body)  # type: ignore[no-any-return]

    async def drive_delete_file(
        self, *, file_id: FilterValue, confirm: bool = False, raw: bool = False
    ) -> dict[str, Any]:
        """删除云盘文件（vault.drive.delete-file，免费），返回 {successList, failList}。

        🔴 不可恢复，必须传 confirm=True，否则在发请求前抛 ValidationError（直接调
        client._call 同样要 confirm）。先用 drive_folder_list() / drive_list() 核对文件 ID
        对应的文件名；被拒后别自动补 confirm=True 重跑，先把要删的文件名给用户确认。

        file_id 支持单值或列表；单条失败（如「文件不存在」）进 failList（{fileId, failReason}），
        非空时发 UserWarning 并标 partial=True。该端点标 no-replay: 重发一个已生效的删除
        会回「文件不存在」或 130002，把成功报成失败。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"fileIdList": _as_list(file_id, "file_id")})
        return await self._client._call(  # type: ignore[no-any-return]
            "vault.drive.delete-file", body=body, confirm=confirm
        )

    async def drive_delete_folder(
        self, *, folder_id: str, confirm: bool = False, raw: bool = False
    ) -> dict[str, Any]:
        """删除云盘文件夹（vault.drive.delete-folder，免费），返回 {folderId}。

        🔴 连同其中全部子文件夹与文件一起删除，不可恢复；必须传 confirm=True，否则在发
        请求前抛 ValidationError（直接调 client._call 同样要 confirm）。删前先
        drive_folder_list(space_type=..., parent_id=folder_id) 看清里面有什么；被拒后
        别自动补 confirm=True 重跑。该端点标 no-replay（理由同 drive_delete_file）。

        返回服务端原始 data（dict）；raw 仅为签名统一，返回相同。
        """
        body = _request_body({"folderId": folder_id})
        return await self._client._call(  # type: ignore[no-any-return]
            "vault.drive.delete-folder", body=body, confirm=confirm
        )

    async def drive_download(
        self,
        *,
        file_id: str,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载网盘文件（vault.drive.download）。

        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="vault.drive.download",
            query={"fileId": file_id},
            output=output,
            fallback_name=f"file-{file_id}",
            title_lookup=("vault.drive.list", "fileId", file_id, resolve_title),
        )

    async def record_download(
        self,
        *,
        record_id: str,
        content_type: str,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载录音转写文件（vault.record.download）。

        content_type 取值: original=原始文件, asr=语音识别, summary=AI 速记（「与我分享」
        类型的录音无法下载原始文件）。其他取值在本地拒绝、不发请求——接口对错值报的是
        130003「没有文件可供下载」, 容易误读成这条记录没附件。
        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        _check_choice(content_type, name="content_type", allowed=_RECORD_CONTENT_TYPES)
        return await download_to_path_async(
            client=self._client,
            endpoint_key="vault.record.download",
            query={"recordId": record_id, "contentType": content_type},
            output=output,
            fallback_name=f"record-{record_id}-{content_type}",
            title_lookup=("vault.record.list", "recordId", record_id, resolve_title),
        )

    async def my_conference_download(
        self,
        *,
        conference_id: str,
        content_type: str,
        output: str | Path | None = None,
        resolve_title: bool = False,
    ) -> Path:
        """下载会议资源文件（vault.my-conference.download）。

        30 积分/篇, 超时 / 5xx 不自动重发。content_type 取值: asr=语音识别, summary=AI 速记;
        其他取值在本地拒绝、不发请求——接口对错值报的是 130003「没有文件可供下载」,
        容易误读成这场会议没附件。
        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。

        resolve_title=True 时, 标题缓存未命中会回查 list 接口拿文件名 (额外 4 次请求, 这些 list 多数按条计费), 默认关闭。
        """
        _check_choice(content_type, name="content_type", allowed=_CONFERENCE_CONTENT_TYPES)
        return await download_to_path_async(
            client=self._client,
            endpoint_key="vault.my-conference.download",
            query={"conferenceId": conference_id, "contentType": content_type},
            output=output,
            fallback_name=f"conference-{conference_id}-{content_type}",
            title_lookup=("vault.my-conference.list", "conferenceId", conference_id, resolve_title),
        )
