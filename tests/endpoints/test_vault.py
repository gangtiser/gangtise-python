import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.vault import Vault


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_drive_list(tmp_path):
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).drive_list(keyword="doc")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "f1"


def test_record_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/record/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"id": "r1", "title": "调研1"}],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).record_list()
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "r1"


def test_my_conference_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/my-conference/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"id": "c1", "title": "策略会"}],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).my_conference_list()
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "c1"


def test_my_conference_list_source_maps_to_numeric_source_list(tmp_path):
    # v0.23.0: --source 1/2 (录制来源) → numeric sourceList in the body.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/my-conference/getList").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"total": 0, "list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Vault(client).my_conference_list(source=[1, 2], category="earningsCall")
        body = route.calls.last.request.read().replace(b" ", b"")
        # sourceList is numeric (not stringified), categoryList is a string list.
        assert b'"sourceList":[1,2]' in body
        assert b'"categoryList":["earningsCall"]' in body


def test_wechat_message_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/wechatgroupmsg/list").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"id": "m1", "content": "msg"}],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).wechat_message_list(
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


def test_wechat_chatroom_list_joins_room_names(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/wechatgroupmsg/chatroomId").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"chatroomId": "r1", "roomName": "group1"}],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).wechat_chatroom_list(room_name=["group1", "group2"])
        body = route.calls.last.request.read().replace(b" ", b"")
        # roomName must be a comma-joined STRING, not a list.
        assert b'"roomName":"group1,group2"' in body
    assert df.iloc[0]["chatroomId"] == "r1"


def test_wechat_chatroom_list_paginates_by_total(tmp_path):
    # v0.23.0: the server now returns {total, list}, so the wrapper fans out by total
    # like any other paginated endpoint — first page (50) learns total=52, one more page
    # completes it. Exercises the whole consume chain → normalize_rows → merged DataFrame.
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).wechat_chatroom_list()
    assert route.call_count == 2
    # the fan-out advanced from=50 for the 2 remaining rows (size clamped to what's left)
    body2 = route.calls[1].request.read().replace(b" ", b"")
    assert b'"from":50' in body2
    assert b'"size":2' in body2
    assert len(df) == 52
    assert df.iloc[0]["chatroomId"] == "r0"
    assert df.iloc[-1]["chatroomId"] == "r51"


def test_stock_pool_list(tmp_path):
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).stock_pool_list()
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["poolId"] == "p1"


def test_stock_pool_stocks_default_all(tmp_path):
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).stock_pool_stocks()
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"poolIdList":["all"]' in body
    assert df.iloc[0]["securityCode"] == "000001.SZ"


def test_drive_download_writes_file(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-vault/drive/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"file",
                headers={"content-disposition": 'attachment; filename="f.pdf"'},
            )
        )
        with GangtiseClient(_config=cfg) as client:
            path = Vault(client).drive_download(file_id="f1", output=tmp_path / "out.pdf")
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"file"


def test_record_download_includes_content_type(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-vault/record/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"audio",
                headers={"content-disposition": 'attachment; filename="r.mp3"'},
            )
        )
        with GangtiseClient(_config=cfg) as client:
            Vault(client).record_download(
                record_id="r1",
                content_type="original",
                output=tmp_path / "out.mp3",
            )
        sent_url = str(route.calls.last.request.url)
        assert "contentType=original" in sent_url


def test_my_conference_download_includes_content_type(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-vault/my-conference/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"summary",
                headers={"content-disposition": 'attachment; filename="c.txt"'},
            )
        )
        with GangtiseClient(_config=cfg) as client:
            Vault(client).my_conference_download(
                conference_id="c1",
                content_type="summary",
                output=tmp_path / "out.txt",
            )
        sent_url = str(route.calls.last.request.url)
        assert "contentType=summary" in sent_url
