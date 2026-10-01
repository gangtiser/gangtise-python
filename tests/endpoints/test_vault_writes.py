# ruff: noqa: RUF001
# (RUF001 disabled file-wide: the warnings under test quote fullwidth brackets.)
"""Vault write wrappers: stock-pool writes (CLI v0.40.0) and drive management
(CLI v0.41.0 ③). Bodies are asserted field-for-field against the TS body literals
in `src/commands/vault.ts`; every local refusal is asserted to send nothing."""

from __future__ import annotations

import json
import re

import httpx
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains import vault as vault_mod
from gangtise_openapi.domains.vault import Vault

_BASE = "https://api.test"
_POOL = "/application/open-vault/stock-pool"
_DRIVE = "/application/open-vault/drive"


def _ok(data: object) -> httpx.Response:
    return httpx.Response(
        200, json={"code": "000000", "msg": "操作成功", "status": True, "data": data}
    )


def _body(route: respx.Route) -> object:
    return json.loads(route.calls.last.request.read())


# ─────────────────────────────── stock-pool writes ───────────────────────────────


def test_stock_pool_create_and_rename_bodies(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        create = router.post(f"{_POOL}/createPool").mock(
            return_value=_ok({"poolId": "808477293", "poolName": "核心池"})
        )
        rename = router.post(f"{_POOL}/updatePool").mock(
            return_value=_ok({"poolId": "808477293", "poolName": "新池"})
        )
        with GangtiseClient(_config=seeded_config) as client:
            created = Vault(client).stock_pool_create(name="核心池")
            renamed = Vault(client).stock_pool_rename(pool_id="808477293", name="新池")
    assert _body(create) == {"poolName": "核心池"}
    assert _body(rename) == {"poolId": "808477293", "poolName": "新池"}
    # Writes hand back the server's data dict as is.
    assert created == {"poolId": "808477293", "poolName": "核心池"}
    assert renamed["poolName"] == "新池"


def test_stock_pool_create_is_not_replayed(seeded_config):
    # A duplicate name is rejected with 230006, so replaying a create whose first
    # attempt went through would report a failure for a pool that now exists.
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_POOL}/createPool").mock(return_value=httpx.Response(503))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError):
                Vault(client).stock_pool_create(name="核心池")
    assert route.call_count == 1


def test_stock_pool_add_stock_maps_pool_and_security_list(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_POOL}/addStock").mock(
            return_value=_ok(
                {"successList": ["600519.SH", "000858.SZ", "00700.HK"], "failList": []}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            result = Vault(client).stock_pool_add_stock(
                pool_id="808477293", security=["600519.SH", "000858.SZ", "00700.HK"]
            )
    assert _body(route) == {
        "poolId": "808477293",
        "securityCodeList": ["600519.SH", "000858.SZ", "00700.HK"],
    }
    # An all-success write (empty failList) is not partial and does not warn
    # (pytest turns a stray UserWarning into an error).
    assert "partial" not in result


def test_stock_pool_add_stock_failures_inside_000000_are_flagged(seeded_config):
    # The request itself succeeds; two of the three codes never went in.
    data = {
        "successList": ["600519.SH"],
        "failList": [
            {"securityCode": "BAD1.XX", "failReason": "证券代码不存在"},
            {"securityCode": "BAD2.XX", "failReason": "证券代码不存在"},
        ],
    }
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        router.post(f"{_POOL}/addStock").mock(return_value=_ok(data))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match=r"BAD1\.XX（证券代码不存在）.*BAD2\.XX"):
                result = Vault(client).stock_pool_add_stock(
                    pool_id="808477293", security=["600519.SH", "BAD1.XX", "BAD2.XX"]
                )
    assert result["partial"] is True
    assert [f["securityCode"] for f in result["failList"]] == ["BAD1.XX", "BAD2.XX"]


def test_stock_pool_remove_stock_scalar_security(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_POOL}/deleteStock").mock(
            return_value=_ok({"successList": ["600519.SH"], "failList": []})
        )
        with GangtiseClient(_config=seeded_config) as client:
            Vault(client).stock_pool_remove_stock(pool_id="808477293", security="600519.SH")
    assert _body(route) == {"poolId": "808477293", "securityCodeList": ["600519.SH"]}


def test_stock_pool_delete_needs_confirm_before_any_request(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=False) as router:
        route = router.post(f"{_POOL}/deletePool").mock(
            return_value=_ok({"successList": ["808477293", "808477294"], "failList": []})
        )
        with GangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match="confirm=True"):
                Vault(client).stock_pool_delete(pool_id="808477293")
            assert route.call_count == 0
            Vault(client).stock_pool_delete(pool_id=["808477293", "808477294"], confirm=True)
    assert route.call_count == 1
    assert _body(route) == {"poolIdList": ["808477293", "808477294"]}


def test_stock_pool_delete_failures_key_on_pool_id(seeded_config):
    data = {"successList": ["1"], "failList": [{"poolId": "BAD9", "failReason": "无权限"}]}
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        router.post(f"{_POOL}/deletePool").mock(return_value=_ok(data))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="BAD9（无权限）"):
                result = Vault(client).stock_pool_delete(pool_id=["1", "BAD9"], confirm=True)
    assert result["partial"] is True


# ─────────────────────────────── drive management ───────────────────────────────


def test_drive_folder_commands_map_their_fields(seeded_config):
    # Translated from the TS "drive folder commands map their flags" case.
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        folder_list = router.post(f"{_DRIVE}/getFolderList").mock(
            return_value=_ok({"folderTotal": 0, "folderList": [], "fileTotal": 0, "fileList": []})
        )
        create = router.post(f"{_DRIVE}/createFolder").mock(
            return_value=_ok({"folderId": "103", "parentId": "101", "folderName": "2026Q3"})
        )
        rename = router.post(f"{_DRIVE}/rename").mock(
            return_value=_ok({"id": "103", "name": "2026三季报"})
        )
        move = router.post(f"{_DRIVE}/moveFolder").mock(
            return_value=_ok({"folderId": "103", "parentId": "root"})
        )
        with GangtiseClient(_config=seeded_config) as client:
            v = Vault(client)
            listed = v.drive_folder_list(parent_id="101")
            v.drive_create_folder(name="2026Q3", parent_id="101")
            v.drive_rename(type_="folder", id_="103", name="2026三季报")
            v.drive_move_folder(folder_id="103", target_parent_id="root")
    assert _body(folder_list) == {"spaceType": 1, "parentId": "101"}
    assert _body(create) == {"folderName": "2026Q3", "spaceType": 1, "parentId": "101"}
    assert _body(rename) == {"type": "folder", "id": "103", "name": "2026三季报"}
    assert _body(move) == {"folderId": "103", "targetParentId": "root"}
    # Two tables in one payload: returned as the raw dict.
    assert set(listed) == {"folderTotal", "folderList", "fileTotal", "fileList"}


def test_drive_folder_list_root_of_tenant_space_omits_parent(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_DRIVE}/getFolderList").mock(
            return_value=_ok({"folderTotal": 0, "folderList": [], "fileTotal": 0, "fileList": []})
        )
        with GangtiseClient(_config=seeded_config) as client:
            Vault(client).drive_folder_list(space_type=2)
    assert _body(route) == {"spaceType": 2}


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda v: v.drive_folder_list(space_type=3), "invalid space_type"),
        (lambda v: v.drive_folder_list(space_type=True), "invalid space_type"),
        (lambda v: v.drive_create_folder(name="x", space_type=0), "invalid space_type"),
        (lambda v: v.drive_rename(type_="dir", id_="1", name="x"), "invalid type_"),
    ],
)
def test_drive_enum_arguments_are_refused_locally(seeded_config, call, match):
    # No respx route: any request would be an unmatched-route error.
    with respx.mock(base_url=_BASE), GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match=match):
            call(Vault(client))


def test_drive_move_file_and_copy_bodies_and_partial(seeded_config):
    fail = {"fileId": "BAD1", "failReason": "文件不存在"}
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        move = router.post(f"{_DRIVE}/moveFile").mock(
            return_value=_ok({"successList": ["49412"], "failList": []})
        )
        copy = router.post(f"{_DRIVE}/copy").mock(
            return_value=_ok(
                {"successList": [{"fileId": "49412", "newFileId": "50001"}], "failList": [fail]}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            v = Vault(client)
            moved = v.drive_move_file(file_id="49412", target_folder_id="101")
            with pytest.warns(UserWarning, match="BAD1（文件不存在）"):
                copied = v.drive_copy(file_id=["49412", "BAD1"], target_folder_id="root")
    assert _body(move) == {"fileIdList": ["49412"], "targetFolderId": "101"}
    # Files only: the folder copy answers 000000 but leaves the copy empty.
    assert _body(copy) == {
        "copyType": "file",
        "fileIdList": ["49412", "BAD1"],
        "targetFolderId": "root",
    }
    assert "partial" not in moved
    assert copied["partial"] is True
    assert copied["successList"][0]["newFileId"] == "50001"


def test_drive_deletes_need_confirm_before_any_request(seeded_config):
    with respx.mock(base_url=_BASE, assert_all_called=False) as router:
        delete_file = router.post(f"{_DRIVE}/deleteFile").mock(
            return_value=_ok(
                {
                    "successList": ["49412"],
                    "failList": [{"fileId": "BAD1", "failReason": "文件不存在"}],
                }
            )
        )
        delete_folder = router.post(f"{_DRIVE}/deleteFolder").mock(
            return_value=_ok({"folderId": "103"})
        )
        with GangtiseClient(_config=seeded_config) as client:
            v = Vault(client)
            with pytest.raises(ValidationError, match="无法恢复"):
                v.drive_delete_file(file_id="49412")
            with pytest.raises(ValidationError, match="全部子文件夹"):
                v.drive_delete_folder(folder_id="103")
            assert delete_file.call_count == 0
            assert delete_folder.call_count == 0

            with pytest.warns(UserWarning, match="BAD1（文件不存在）"):
                result = v.drive_delete_file(file_id=["49412", "BAD1"], confirm=True)
            folder = v.drive_delete_folder(folder_id="103", confirm=True)
    assert _body(delete_file) == {"fileIdList": ["49412", "BAD1"]}
    assert _body(delete_folder) == {"folderId": "103"}
    assert result["partial"] is True
    assert folder == {"folderId": "103"}


# ─────────────────────────────── drive upload ───────────────────────────────


def _field(content: bytes, name: str, value: str) -> bool:
    pattern = re.escape(f'name="{name}"\r\n\r\n{value}\r\n'.encode())
    return re.search(pattern, content) is not None


def test_drive_upload_sends_file_and_target_as_form_fields(tmp_path, seeded_config):
    file = tmp_path / "report.pdf"
    file.write_bytes(b"pdf-bytes")
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_DRIVE}/uploadFile").mock(
            return_value=_ok({"fileId": "50001", "title": "深度报告.pdf", "spaceType": 2})
        )
        with GangtiseClient(_config=seeded_config) as client:
            result = Vault(client).drive_upload(
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
    assert result["fileId"] == "50001"


def test_drive_upload_defaults_send_only_space_type(tmp_path, seeded_config):
    file = tmp_path / "report.pdf"
    file.write_bytes(b"x")
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_DRIVE}/uploadFile").mock(return_value=_ok({"fileId": "1"}))
        with GangtiseClient(_config=seeded_config) as client:
            Vault(client).drive_upload(file=str(file))
    content = route.calls.last.request.read()
    assert _field(content, "spaceType", "1")
    assert b'name="folderId"' not in content
    assert b'name="title"' not in content


def test_drive_upload_is_not_replayed(tmp_path, seeded_config):
    # Same-name files are allowed, so a replay after a lost response would leave a
    # second copy in the drive.
    file = tmp_path / "report.pdf"
    file.write_bytes(b"x")
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_DRIVE}/uploadFile").mock(return_value=httpx.Response(503))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError):
                Vault(client).drive_upload(file=file)
    assert route.call_count == 1


def _refused(seeded_config, match: str, **kwargs) -> None:
    # No respx route: any request would be an unmatched-route error.
    with respx.mock(base_url=_BASE), GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match=match):
            Vault(client).drive_upload(**kwargs)


def test_drive_upload_rejects_missing_directory_and_empty_before_any_request(
    tmp_path, seeded_config
):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    _refused(seeded_config, "file not found", file=tmp_path / "nope.pdf")
    _refused(seeded_config, "not a file", file=tmp_path)
    _refused(seeded_config, "file is empty", file=empty)
    _refused(seeded_config, "invalid space_type", file=empty, space_type=3)


def test_drive_upload_rejects_files_over_the_cap(tmp_path, seeded_config, monkeypatch):
    file = tmp_path / "big.pdf"
    file.write_bytes(b"12345")
    monkeypatch.setattr(vault_mod, "DRIVE_UPLOAD_MAX_BYTES", 4)
    _refused(seeded_config, "at most 100MB", file=file)


def test_drive_upload_counts_the_name_cap_in_utf16_units(tmp_path, seeded_config):
    file = tmp_path / "纪要.docx"
    file.write_bytes(b"content")
    # 199 CJK characters + one emoji = 200 code points but 201 UTF-16 units: over
    # the cap, although Python's len() says 200.
    over = "字" * 199 + "😀"
    assert len(over) == 200
    _refused(seeded_config, "at most 200", file=file, title=over)

    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_DRIVE}/uploadFile").mock(return_value=_ok({"fileId": "1"}))
        with GangtiseClient(_config=seeded_config) as client:
            Vault(client).drive_upload(file=file, title="字" * 200)
    assert route.call_count == 1


def test_drive_upload_checks_the_local_name_when_no_title(tmp_path, seeded_config):
    file = tmp_path / ("a" * 197 + ".pdf")  # 201 characters
    file.write_bytes(b"x")
    _refused(seeded_config, "pass a shorter title", file=file)

    # A title replaces the local name, so it is the title that is measured.
    with respx.mock(base_url=_BASE, assert_all_called=True) as router:
        route = router.post(f"{_DRIVE}/uploadFile").mock(return_value=_ok({"fileId": "1"}))
        with GangtiseClient(_config=seeded_config) as client:
            Vault(client).drive_upload(file=file, title="short.pdf")
    assert route.call_count == 1


# ─────────────────────── per-row billed list: confirm pass-through ───────────────────────


def test_my_conference_list_passes_confirm_to_call(seeded_config, monkeypatch):
    # Billed per row: without confirm a size-less fetch past 1000 credits is refused
    # by the pagination guard, so the wrapper must give the caller a way through.
    seen: list[bool] = []

    def fake_call(endpoint_key, body=None, query=None, *, confirm=False):
        seen.append(confirm)
        return {"total": 0, "list": []}

    with GangtiseClient(_config=seeded_config) as client:
        monkeypatch.setattr(client, "_call", fake_call)
        Vault(client).my_conference_list()
        Vault(client).my_conference_list(confirm=True)
    assert seen == [False, True]
