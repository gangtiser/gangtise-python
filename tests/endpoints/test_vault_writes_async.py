# ruff: noqa: RUF001
# (RUF001 disabled file-wide: the warnings under test quote fullwidth brackets.)
"""Async mirror of test_vault_writes.py: stock-pool writes (CLI v0.40.0), drive
management (CLI v0.41.0 ③) and the download content_type guard (CLI v0.43.0 ⑧)."""

from __future__ import annotations

import json
import re

import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains.vault import AsyncVault

_BASE = "https://api.test"
_POOL = "/application/open-vault/stock-pool"
_DRIVE = "/application/open-vault/drive"

pytestmark = pytest.mark.anyio


def _ok(data: object) -> httpx.Response:
    return httpx.Response(
        200, json={"code": "000000", "msg": "操作成功", "status": True, "data": data}
    )


def _body(route: respx.Route) -> object:
    return json.loads(route.calls.last.request.read())


def _field(content: bytes, name: str, value: str) -> bool:
    pattern = re.escape(f'name="{name}"\r\n\r\n{value}\r\n'.encode())
    return re.search(pattern, content) is not None


# ─────────────────────────────── stock-pool writes ───────────────────────────────


async def test_async_stock_pool_write_bodies(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        create = router.post(f"{_POOL}/createPool").mock(
            return_value=_ok({"poolId": "1", "poolName": "核心池"})
        )
        rename = router.post(f"{_POOL}/updatePool").mock(
            return_value=_ok({"poolId": "1", "poolName": "新池"})
        )
        add = router.post(f"{_POOL}/addStock").mock(
            return_value=_ok({"successList": ["600519.SH"], "failList": []})
        )
        remove = router.post(f"{_POOL}/deleteStock").mock(
            return_value=_ok({"successList": ["600519.SH"], "failList": []})
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            v = AsyncVault(client)
            created = await v.stock_pool_create(name="核心池")
            await v.stock_pool_rename(pool_id="1", name="新池")
            added = await v.stock_pool_add_stock(pool_id="1", security="600519.SH")
            await v.stock_pool_remove_stock(pool_id="1", security=["600519.SH"])
    assert _body(create) == {"poolName": "核心池"}
    assert _body(rename) == {"poolId": "1", "poolName": "新池"}
    assert _body(add) == {"poolId": "1", "securityCodeList": ["600519.SH"]}
    assert _body(remove) == {"poolId": "1", "securityCodeList": ["600519.SH"]}
    assert created == {"poolId": "1", "poolName": "核心池"}
    assert "partial" not in added


async def test_async_stock_pool_add_stock_failures_are_flagged(seeded_config):
    data = {
        "successList": ["600519.SH"],
        "failList": [{"securityCode": "BAD1.XX", "failReason": "证券代码不存在"}],
    }
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        router.post(f"{_POOL}/addStock").mock(return_value=_ok(data))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.warns(UserWarning, match=r"BAD1\.XX（证券代码不存在）"):
                result = await AsyncVault(client).stock_pool_add_stock(
                    pool_id="1", security=["600519.SH", "BAD1.XX"]
                )
    assert result["partial"] is True


async def test_async_stock_pool_create_is_not_replayed(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_POOL}/createPool").mock(return_value=httpx.Response(503))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ApiError):
                await AsyncVault(client).stock_pool_create(name="核心池")
    assert route.call_count == 1


async def test_async_stock_pool_delete_needs_confirm(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=False) as router:
        route = router.post(f"{_POOL}/deletePool").mock(
            return_value=_ok({"successList": ["1", "2"], "failList": []})
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match="confirm=True"):
                await AsyncVault(client).stock_pool_delete(pool_id="1")
            assert route.call_count == 0
            await AsyncVault(client).stock_pool_delete(pool_id=["1", "2"], confirm=True)
    assert _body(route) == {"poolIdList": ["1", "2"]}


# ─────────────────────────────── drive management ───────────────────────────────


async def test_async_drive_folder_commands_map_their_fields(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        folder_list = router.post(f"{_DRIVE}/getFolderList").mock(
            return_value=_ok({"folderTotal": 0, "folderList": [], "fileTotal": 0, "fileList": []})
        )
        create = router.post(f"{_DRIVE}/createFolder").mock(return_value=_ok({"folderId": "103"}))
        rename = router.post(f"{_DRIVE}/rename").mock(return_value=_ok({"id": "103", "name": "x"}))
        move = router.post(f"{_DRIVE}/moveFolder").mock(return_value=_ok({"folderId": "103"}))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            v = AsyncVault(client)
            await v.drive_folder_list(space_type=2, parent_id="101")
            await v.drive_create_folder(name="2026Q3")
            await v.drive_rename(type_="file", id_="49412", name="x")
            await v.drive_move_folder(folder_id="103", target_parent_id="root")
    assert _body(folder_list) == {"spaceType": 2, "parentId": "101"}
    assert _body(create) == {"folderName": "2026Q3", "spaceType": 1}
    assert _body(rename) == {"type": "file", "id": "49412", "name": "x"}
    assert _body(move) == {"folderId": "103", "targetParentId": "root"}


async def test_async_drive_enum_arguments_are_refused_locally(seeded_config):
    with respx.mock(base_url=_BASE):
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            v = AsyncVault(client)
            with pytest.raises(ValidationError, match="invalid space_type"):
                await v.drive_folder_list(space_type=3)
            with pytest.raises(ValidationError, match="invalid space_type"):
                await v.drive_create_folder(name="x", space_type=0)
            with pytest.raises(ValidationError, match="invalid type_"):
                await v.drive_rename(type_="dir", id_="1", name="x")


async def test_async_drive_move_file_and_copy(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        move = router.post(f"{_DRIVE}/moveFile").mock(
            return_value=_ok(
                {"successList": [], "failList": [{"fileId": "9", "failReason": "空间不一致"}]}
            )
        )
        copy = router.post(f"{_DRIVE}/copy").mock(
            return_value=_ok({"successList": [{"fileId": "1", "newFileId": "2"}], "failList": []})
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            v = AsyncVault(client)
            with pytest.warns(UserWarning, match="9（空间不一致）"):
                moved = await v.drive_move_file(file_id=["9"], target_folder_id="root")
            copied = await v.drive_copy(file_id="1", target_folder_id="root")
    assert _body(move) == {"fileIdList": ["9"], "targetFolderId": "root"}
    assert _body(copy) == {"copyType": "file", "fileIdList": ["1"], "targetFolderId": "root"}
    assert moved["partial"] is True
    assert "partial" not in copied


async def test_async_drive_copy_folder_and_local_refusals(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        copy = router.post(f"{_DRIVE}/copy").mock(
            return_value=_ok({"folderId": "201", "newFolderId": "301"})
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            v = AsyncVault(client)
            with pytest.raises(ValidationError, match="not both"):
                await v.drive_copy(file_id="1", target_parent_id="root")
            with pytest.raises(ValidationError, match="needs both folder_id and target_parent_id"):
                await v.drive_copy(folder_id="201")
            with pytest.raises(ValidationError, match="pass either"):
                await v.drive_copy()
            copied = await v.drive_copy(folder_id="201", target_parent_id="root")
    assert copy.call_count == 1
    assert _body(copy) == {"copyType": "folder", "folderId": "201", "targetParentId": "root"}
    assert copied == {"folderId": "201", "newFolderId": "301"}


async def test_async_drive_deletes_need_confirm(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=False) as router:
        delete_file = router.post(f"{_DRIVE}/deleteFile").mock(
            return_value=_ok({"successList": ["1"], "failList": []})
        )
        delete_folder = router.post(f"{_DRIVE}/deleteFolder").mock(
            return_value=_ok({"folderId": "103"})
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            v = AsyncVault(client)
            with pytest.raises(ValidationError, match="无法恢复"):
                await v.drive_delete_file(file_id="1")
            with pytest.raises(ValidationError, match="全部子文件夹"):
                await v.drive_delete_folder(folder_id="103")
            assert delete_file.call_count == 0
            assert delete_folder.call_count == 0
            await v.drive_delete_file(file_id="1", confirm=True)
            await v.drive_delete_folder(folder_id="103", confirm=True)
    assert _body(delete_file) == {"fileIdList": ["1"]}
    assert _body(delete_folder) == {"folderId": "103"}


# ─────────────────────────────── drive upload ───────────────────────────────


async def test_async_drive_upload_sends_multipart_fields(tmp_path, seeded_config):
    file = tmp_path / "report.pdf"
    file.write_bytes(b"pdf-bytes")
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_DRIVE}/uploadFile").mock(return_value=_ok({"fileId": "50001"}))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            result = await AsyncVault(client).drive_upload(
                file=file, space_type=2, folder_id="101", title="深度报告.pdf"
            )
    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    content = request.read()
    assert _field(content, "spaceType", "2")
    assert _field(content, "folderId", "101")
    assert _field(content, "title", "深度报告.pdf")
    assert b'filename="report.pdf"' in content
    assert b"pdf-bytes" in content
    assert result == {"fileId": "50001"}


async def test_async_drive_upload_is_not_replayed(tmp_path, seeded_config):
    file = tmp_path / "report.pdf"
    file.write_bytes(b"x")
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_DRIVE}/uploadFile").mock(return_value=httpx.Response(503))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ApiError):
                await AsyncVault(client).drive_upload(file=file)
    assert route.call_count == 1


async def test_async_drive_upload_local_refusals_send_nothing(tmp_path, seeded_config):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    named = tmp_path / "纪要.docx"
    named.write_bytes(b"content")
    with respx.mock(base_url=_BASE):
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            v = AsyncVault(client)
            with pytest.raises(ValidationError, match="file not found"):
                await v.drive_upload(file=tmp_path / "nope.pdf")
            with pytest.raises(ValidationError, match="not a file"):
                await v.drive_upload(file=tmp_path)
            with pytest.raises(ValidationError, match="file is empty"):
                await v.drive_upload(file=empty)
            with pytest.raises(ValidationError, match="at most 200"):
                await v.drive_upload(file=named, title="字" * 199 + "😀")
            with pytest.raises(ValidationError, match="invalid space_type"):
                await v.drive_upload(file=named, space_type=3)


# ─────────────────────── download content_type / per-row confirm ───────────────────────


async def test_async_download_content_type_is_checked_locally(tmp_path, seeded_config):
    # An unknown contentType comes back as 130003 「没有文件可供下载」, which reads as
    # "this record has no file". No route: nothing may be sent.
    with respx.mock(base_url=_BASE):
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            v = AsyncVault(client)
            with pytest.raises(ValidationError, match="original/asr/summary"):
                await v.record_download(
                    record_id="1", content_type="summery", output=tmp_path / "r.txt"
                )
            with pytest.raises(ValidationError, match="asr/summary"):
                await v.my_conference_download(
                    conference_id="1", content_type="original", output=tmp_path / "c.txt"
                )
    assert not (tmp_path / "r.txt").exists()
    assert not (tmp_path / "c.txt").exists()


async def test_async_my_conference_list_passes_confirm_to_call(seeded_config, monkeypatch):
    seen: list[bool] = []

    async def fake_call(endpoint_key, body=None, query=None, *, confirm=False):
        seen.append(confirm)
        return {"total": 0, "list": []}

    async with AsyncGangtiseClient(_config=seeded_config) as client:
        monkeypatch.setattr(client, "_call", fake_call)
        await AsyncVault(client).my_conference_list()
        await AsyncVault(client).my_conference_list(confirm=True)
    assert seen == [False, True]
