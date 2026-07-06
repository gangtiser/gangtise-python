from __future__ import annotations

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.vault import AsyncVault


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def _row_response(row: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"total": 1, "list": [row]},
        },
    )


@pytest.mark.anyio
async def test_async_drive_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/drive/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"id": "f1", "name": "doc.pdf"}],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).drive_list(keyword="doc")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "f1"


@pytest.mark.anyio
async def test_async_drive_list_body_shape_and_raw(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/drive/getList").mock(
            return_value=_row_response({"fileId": "f1", "title": "doc"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            raw = await AsyncVault(client).drive_list(file_type=1, space_type=2, raw=True)
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"fileTypeList":[1]' in body
        assert b'"spaceTypeList":[2]' in body
    assert raw == {"total": 1, "list": [{"fileId": "f1", "title": "doc"}]}


@pytest.mark.anyio
async def test_async_record_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/record/getList").mock(
            return_value=_row_response({"recordId": "r1", "title": "调研1"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).record_list(category="cat1", space_type=2)
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"categoryList":["cat1"]' in body
        assert b'"spaceTypeList":[2]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["recordId"] == "r1"


@pytest.mark.anyio
async def test_async_my_conference_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/my-conference/getList").mock(
            return_value=_row_response({"conferenceId": "c1", "title": "策略会"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).my_conference_list(
                research_area="medicine",
                security="000001.SZ",
                institution="i1",
                category="cat1",
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"researchAreaList":["medicine"]' in body
        assert b'"securityList":["000001.SZ"]' in body
        assert b'"institutionList":["i1"]' in body
        assert b'"categoryList":["cat1"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["conferenceId"] == "c1"


@pytest.mark.anyio
async def test_async_my_conference_list_source_maps_to_numeric_source_list(tmp_path):
    # v0.23.0 async sibling: --source 1/2 → numeric sourceList.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/my-conference/getList").mock(
            return_value=_row_response({"conferenceId": "c1", "title": "策略会"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncVault(client).my_conference_list(source=[1, 2])
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"sourceList":[1,2]' in body


@pytest.mark.anyio
async def test_async_wechat_message_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/wechatgroupmsg/list").mock(
            return_value=_row_response({"id": "m1", "content": "msg"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).wechat_message_list(
                security="000001.SH",
                wechat_group_id="g1",
                industry="ind1",
                category="cat1",
                tag="tag1",
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityList":["000001.SH"]' in body
        assert b'"wechatGroupIdList":["g1"]' in body
        assert b'"industryIdList":["ind1"]' in body
        assert b'"categoryList":["cat1"]' in body
        assert b'"tagList":["tag1"]' in body
    assert df.iloc[0]["id"] == "m1"


@pytest.mark.anyio
async def test_async_wechat_chatroom_list_joins_room_names(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/wechatgroupmsg/chatroomId").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": [{"chatroomId": "r1", "roomName": "group1"}],
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).wechat_chatroom_list(room_name=["group1", "group2"])
        body = route.calls.last.request.read().replace(b" ", b"")
        # roomName must be a comma-joined STRING, not a list.
        assert b'"roomName":"group1,group2"' in body
    assert df.iloc[0]["chatroomId"] == "r1"


@pytest.mark.anyio
async def test_async_wechat_chatroom_list_paginates_by_total(tmp_path):
    # Async sibling of test_wechat_chatroom_list_paginates_by_total (v0.23.0 {total, list}):
    # first page (50) learns total=52, one more page completes it via the fan-out.
    page1 = [{"chatroomId": f"r{i}", "roomName": f"g{i}"} for i in range(50)]
    page2 = [{"chatroomId": "r50", "roomName": "g50"}, {"chatroomId": "r51", "roomName": "g51"}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/wechatgroupmsg/chatroomId").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"code": "000000", "status": True, "data": {"total": 52, "list": page1}},
                ),
                httpx.Response(
                    200,
                    json={"code": "000000", "status": True, "data": {"total": 52, "list": page2}},
                ),
            ]
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).wechat_chatroom_list()
    assert route.call_count == 2
    body2 = route.calls[1].request.read().replace(b" ", b"")
    assert b'"from":50' in body2
    assert b'"size":2' in body2
    assert len(df) == 52
    assert df.iloc[0]["chatroomId"] == "r0"
    assert df.iloc[-1]["chatroomId"] == "r51"


@pytest.mark.anyio
async def test_async_stock_pool_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/stock-pool/getPoolList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"poolList": [{"poolId": "p1", "poolName": "核心池"}]},
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).stock_pool_list()
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["poolId"] == "p1"


@pytest.mark.anyio
async def test_async_stock_pool_list_accepts_bare_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/stock-pool/getPoolList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": [{"poolId": "p2", "poolName": "备选池"}],
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).stock_pool_list()
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["poolId"] == "p2"


@pytest.mark.anyio
async def test_async_raw_passthrough(tmp_path):
    payload = {"total": 1, "list": [{"id": "x", "title": "t"}]}
    paths = [
        "/application/open-vault/record/getList",
        "/application/open-vault/my-conference/getList",
        "/application/open-vault/wechatgroupmsg/list",
        "/application/open-vault/wechatgroupmsg/chatroomId",
        "/application/open-vault/stock-pool/getPoolList",
        "/application/open-vault/stock-pool/getStockList",
    ]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        for path in paths:
            router.post(path).mock(
                return_value=httpx.Response(
                    200,
                    json={"code": "000000", "status": True, "data": payload},
                )
            )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            vault = AsyncVault(client)
            assert await vault.record_list(raw=True) == payload
            assert await vault.my_conference_list(raw=True) == payload
            assert await vault.wechat_message_list(raw=True) == payload
            assert await vault.wechat_chatroom_list(raw=True) == payload
            assert await vault.stock_pool_list(raw=True) == payload
            assert await vault.stock_pool_stocks(raw=True) == payload


@pytest.mark.anyio
async def test_async_stock_pool_stocks_default_all(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/stock-pool/getStockList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": [{"securityCode": "000001.SZ", "poolId": "p1"}],
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).stock_pool_stocks()
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"poolIdList":["all"]' in body
    assert df.iloc[0]["securityCode"] == "000001.SZ"


@pytest.mark.anyio
async def test_async_drive_download_writes_file(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-vault/drive/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"file",
                headers={"content-disposition": 'attachment; filename="f.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            path = await AsyncVault(client).drive_download(
                file_id="f1",
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"file"


@pytest.mark.anyio
async def test_async_record_download_includes_content_type(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-vault/record/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"audio",
                headers={"content-disposition": 'attachment; filename="r.mp3"'},
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            await AsyncVault(client).record_download(
                record_id="r1",
                content_type="original",
                output=tmp_path / "out.mp3",
            )
        sent_url = str(route.calls.last.request.url)
        assert "recordId=r1" in sent_url
        assert "contentType=original" in sent_url


@pytest.mark.anyio
async def test_async_my_conference_download_includes_content_type(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-vault/my-conference/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"summary",
                headers={"content-disposition": 'attachment; filename="c.txt"'},
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            await AsyncVault(client).my_conference_download(
                conference_id="c1",
                content_type="summary",
                output=tmp_path / "out.txt",
            )
        sent_url = str(route.calls.last.request.url)
        assert "conferenceId=c1" in sent_url
        assert "contentType=summary" in sent_url
