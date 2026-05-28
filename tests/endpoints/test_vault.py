import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.vault import Vault


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_drive_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/drive/getList").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
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
                200, json={
                    "code": "000000", "status": True,
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
                200, json={
                    "code": "000000", "status": True,
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


def test_wechat_message_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-vault/wechatgroupmsg/list").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
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
                200, json={
                    "code": "000000", "status": True,
                    "data": [{"chatroomId": "r1", "roomName": "group1"}],
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).wechat_chatroom_list(room_name=["group1", "group2"])
        body = route.calls.last.request.read().replace(b" ", b"")
        # roomName must be a comma-joined STRING, not a list.
        assert b'"roomName":"group1,group2"' in body
    assert df.iloc[0]["chatroomId"] == "r1"


def test_stock_pool_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/stock-pool/getPoolList").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
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
                200, json={
                    "code": "000000", "status": True,
                    "data": [{"securityCode": "000001.SZ", "poolId": "p1"}],
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Vault(client).stock_pool_stocks()
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"poolIdList":["all"]' in body
    assert df.iloc[0]["securityCode"] == "000001.SZ"
