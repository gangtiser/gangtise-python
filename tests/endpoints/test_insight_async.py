from __future__ import annotations

import datetime as dt

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.insight import AsyncInsight


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        page_concurrency=3,
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
async def test_async_opinion_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/chief-opinion/getList").mock(
            return_value=_row_response(
                {"id": "1", "title": "x", "broker": "A", "chief": "B"},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).opinion_list(industry=1)
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "1"


@pytest.mark.anyio
async def test_async_announcement_list_scales_seconds_int_to_ms(tmp_path):
    # TS toTimestamp13 parity: a seconds-level int is scaled to milliseconds.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/announcement/getList").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"total": 0, "list": []}},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncInsight(client).announcement_list(start_time=1767225600)
    sent = route.calls.last.request.read()
    assert b'"startTime":1767225600000' in sent.replace(b" ", b"")


@pytest.mark.anyio
async def test_async_opinion_list_body_shape_and_raw(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/chief-opinion/getList").mock(
            return_value=_row_response({"id": "1", "title": "x"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            raw = await AsyncInsight(client).opinion_list(
                research_area="medicine",
                chief="c1",
                security="000001.SZ",
                broker="b1",
                industry=1,
                concept="ai",
                llm_tag="t1",
                source="research",
                raw=True,
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"rankType":1' in body
        assert b'"researchAreaList":["medicine"]' in body
        assert b'"chiefList":["c1"]' in body
        assert b'"securityList":["000001.SZ"]' in body
        assert b'"brokerList":["b1"]' in body
        assert b'"industryList":[1]' in body
        assert b'"conceptList":["ai"]' in body
        assert b'"llmTagList":["t1"]' in body
        assert b'"sourceList":["research"]' in body
    assert raw == {"total": 1, "list": [{"id": "1", "title": "x"}]}


@pytest.mark.anyio
async def test_async_summary_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/summary/v2/getList").mock(
            return_value=_row_response({"summaryId": "s1", "title": "调研纪要"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).summary_list(
                source="meeting",
                research_area="medicine",
                security="000001.SZ",
                institution="i1",
                category="c1",
                market="SH",
                participant_role=1,
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"searchType":1' in body
        assert b'"rankType":1' in body
        assert b'"sourceList":["meeting"]' in body
        assert b'"researchAreaList":["medicine"]' in body
        assert b'"securityList":["000001.SZ"]' in body
        assert b'"institutionList":["i1"]' in body
        assert b'"categoryList":["c1"]' in body
        assert b'"marketList":["SH"]' in body
        assert b'"participantRoleList":[1]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["summaryId"] == "s1"


@pytest.mark.anyio
async def test_async_roadshow_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/schedule/roadshow/getList").mock(
            return_value=_row_response({"id": "r1", "title": "路演"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).roadshow_list(
                research_area="medicine",
                institution="i1",
                security="000001.SZ",
                category="c1",
                market="SH",
                participant_role=1,
                broker_type=2,
                object_="company",
                permission=1,
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"researchAreaList":["medicine"]' in body
        assert b'"institutionList":["i1"]' in body
        assert b'"securityList":["000001.SZ"]' in body
        assert b'"categoryList":["c1"]' in body
        assert b'"marketList":["SH"]' in body
        assert b'"participantRoleList":[1]' in body
        assert b'"brokerTypeList":[2]' in body
        assert b'"objectList":["company"]' in body
        assert b'"permission":[1]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "r1"


@pytest.mark.anyio
async def test_async_site_visit_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/schedule/site-visit/getList").mock(
            return_value=_row_response({"id": "v1", "title": "调研"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).site_visit_list(security="000001.SZ")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityList":["000001.SZ"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "v1"


@pytest.mark.anyio
async def test_async_strategy_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/schedule/strategy-meeting/getList").mock(
            return_value=_row_response({"id": "st1", "title": "策略会"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).strategy_list(market="SH")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"marketList":["SH"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "st1"


@pytest.mark.anyio
async def test_async_forum_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/schedule/forum/getList").mock(
            return_value=_row_response({"id": "f1", "title": "论坛"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).forum_list(object_="company")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"objectList":["company"]' in body
        assert b'"object":' not in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "f1"


@pytest.mark.anyio
async def test_async_research_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/broker-report/getList").mock(
            return_value=_row_response({"reportId": "rp1", "title": "研报"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).research_list(
                broker="b1",
                security="000001.SZ",
                industry=1,
                category="c1",
                llm_tag="t1",
                rating="buy",
                rating_change="up",
                min_pages=5,
                max_pages=50,
                source="research",
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"brokerList":["b1"]' in body
        assert b'"securityList":["000001.SZ"]' in body
        assert b'"industryList":[1]' in body
        assert b'"categoryList":["c1"]' in body
        assert b'"llmTagList":["t1"]' in body
        assert b'"ratingList":["buy"]' in body
        assert b'"ratingChangeList":["up"]' in body
        assert b'"minReportPages":5' in body
        assert b'"maxReportPages":50' in body
        assert b'"sourceList":["research"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["reportId"] == "rp1"


@pytest.mark.anyio
async def test_async_foreign_report_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/foreign-report/getList").mock(
            return_value=_row_response({"reportId": "fr1", "title": "外资研报"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).foreign_report_list(
                security="AAPL.O",
                region="US",
                category="c1",
                industry=1,
                broker="b1",
                llm_tag="t1",
                rating="buy",
                rating_change="up",
                min_pages=5,
                max_pages=50,
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityList":["AAPL.O"]' in body
        assert b'"regionList":["US"]' in body
        assert b'"categoryList":["c1"]' in body
        assert b'"industryList":[1]' in body
        assert b'"brokerList":["b1"]' in body
        assert b'"llmTagList":["t1"]' in body
        assert b'"ratingList":["buy"]' in body
        assert b'"ratingChangeList":["up"]' in body
        assert b'"minReportPages":5' in body
        assert b'"maxReportPages":50' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["reportId"] == "fr1"


@pytest.mark.anyio
async def test_async_announcement_list_body_shape_converts_times(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/announcement/getList").mock(
            return_value=_row_response({"announcementId": "a1", "title": "公告"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).announcement_list(
                start_time="2026-01-01T00:00:00",
                end_time=1767312000000,
                security="000001.SZ",
                announcement_type="annual",
                category="dividend",
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        # naive ISO string with time is interpreted in the local tz (TS parity)
        expected_start = int(dt.datetime(2026, 1, 1, 0, 0, 0).astimezone().timestamp() * 1000)
        assert f'"startTime":{expected_start}'.encode() in body
        # int timestamps pass through unchanged
        assert b'"endTime":1767312000000' in body
        assert b'"securityList":["000001.SZ"]' in body
        assert b'"announcementTypeList":["annual"]' in body
        assert b'"categoryList":["dividend"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["announcementId"] == "a1"


@pytest.mark.anyio
async def test_async_announcement_hk_list_keeps_string_times(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/announcement-hk/getList").mock(
            return_value=_row_response({"announcementId": "hk1", "title": "港股公告"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).announcement_hk_list(
                start_time="2026-01-01",
                security="00700.HK",
                announcement_type="annual",
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"startTime":"2026-01-01"' in body
        assert b'"securityList":["00700.HK"]' in body
        assert b'"announcementTypeList":["annual"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["announcementId"] == "hk1"


@pytest.mark.anyio
async def test_async_foreign_opinion_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/foreign-opinion/getList").mock(
            return_value=_row_response({"id": "fo1", "title": "外资观点"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).foreign_opinion_list(
                security="AAPL.O",
                region="US",
                industry=1,
                broker="b1",
                rating="buy",
                rating_change="up",
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"regionList":["US"]' in body
        assert b'"industryList":[1]' in body
        assert b'"securityList":["AAPL.O"]' in body
        assert b'"brokerList":["b1"]' in body
        assert b'"ratingList":["buy"]' in body
        assert b'"ratingChangeList":["up"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "fo1"


@pytest.mark.anyio
async def test_async_independent_opinion_list_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/independent-opinion/getList").mock(
            return_value=_row_response({"id": "io1", "title": "独立观点"})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).independent_opinion_list(
                security="AAPL.O",
                industry=42,
                rating="buy",
                rating_change="up",
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"industryList":[42]' in body
        assert b'"securityList":["AAPL.O"]' in body
        assert b'"ratingList":["buy"]' in body
        assert b'"ratingChangeList":["up"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "io1"


@pytest.mark.anyio
async def test_async_raw_passthrough(tmp_path):
    row = {"id": "x", "title": "t"}
    expected = {"total": 1, "list": [row]}
    paths = [
        "/application/open-insight/summary/v2/getList",
        "/application/open-insight/schedule/site-visit/getList",
        "/application/open-insight/broker-report/getList",
        "/application/open-insight/foreign-report/getList",
        "/application/open-insight/announcement/getList",
        "/application/open-insight/announcement-hk/getList",
        "/application/open-insight/foreign-opinion/getList",
        "/application/open-insight/independent-opinion/getList",
    ]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        for path in paths:
            router.post(path).mock(return_value=_row_response(row))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            insight = AsyncInsight(client)
            for method in (
                insight.summary_list,
                insight.site_visit_list,
                insight.research_list,
                insight.foreign_report_list,
                insight.announcement_list,
                insight.announcement_hk_list,
                insight.foreign_opinion_list,
                insight.independent_opinion_list,
            ):
                assert await method(raw=True) == expected


# ---- Download endpoint tests ----


@pytest.mark.anyio
async def test_async_summary_download_includes_file_type(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            path = await AsyncInsight(client).summary_download(
                summary_id="s1",
                file_type=2,
                output=tmp_path / "out.pdf",
            )
        sent_url = str(route.calls.last.request.url)
        assert "summaryId=s1" in sent_url
        assert "fileType=2" in sent_url
    assert path.read_bytes() == b"data"


@pytest.mark.anyio
async def test_async_foreign_report_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-insight/foreign-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            path = await AsyncInsight(client).foreign_report_download(
                report_id="fr1",
                output=tmp_path / "out.pdf",
            )
        sent_url = str(route.calls.last.request.url)
        assert "reportId=fr1" in sent_url
        assert "fileType=1" in sent_url
    assert path.read_bytes() == b"data"


@pytest.mark.anyio
async def test_async_announcement_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-insight/announcement/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            path = await AsyncInsight(client).announcement_download(
                announcement_id="a1",
                output=tmp_path / "out.pdf",
            )
        sent_url = str(route.calls.last.request.url)
        assert "announcementId=a1" in sent_url
        assert "fileType=1" in sent_url
    assert path.read_bytes() == b"data"


@pytest.mark.anyio
async def test_async_announcement_hk_download_has_no_file_type(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-insight/announcement-hk/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            path = await AsyncInsight(client).announcement_hk_download(
                announcement_id="hk1",
                output=tmp_path / "out.pdf",
            )
        sent_url = str(route.calls.last.request.url)
        assert "announcementId=hk1" in sent_url
        assert "fileType" not in sent_url
    assert path.read_bytes() == b"data"


@pytest.mark.anyio
async def test_async_independent_opinion_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-insight/independent-opinion/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            path = await AsyncInsight(client).independent_opinion_download(
                independent_opinion_id="io1",
                file_type=1,
                output=tmp_path / "out.pdf",
            )
        sent_url = str(route.calls.last.request.url)
        assert "independentOpinionId=io1" in sent_url
        assert "fileType=1" in sent_url
    assert path.read_bytes() == b"data"


@pytest.mark.anyio
async def test_async_research_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            path = await AsyncInsight(client).research_download(
                report_id="r1",
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"data"
