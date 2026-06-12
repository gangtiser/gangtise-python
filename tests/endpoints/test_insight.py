from __future__ import annotations

import datetime as dt

import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.insight import Insight, _to_unix_ms


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


def test_opinion_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/chief-opinion/getList").mock(
            return_value=_row_response(
                {"id": "1", "title": "x", "broker": "A", "chief": "B"},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).opinion_list(industry=1)
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "1"


def test_summary_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/summary/v2/getList").mock(
            return_value=_row_response({"summaryId": "s1", "title": "调研纪要"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).summary_list(security="000001.SZ")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["summaryId"] == "s1"


def test_roadshow_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/schedule/roadshow/getList").mock(
            return_value=_row_response({"id": "r1", "title": "路演"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).roadshow_list(permission=1)
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "r1"


def test_site_visit_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/schedule/site-visit/getList").mock(
            return_value=_row_response({"id": "v1", "title": "调研"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).site_visit_list(security="000001.SZ")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "v1"


def test_strategy_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/schedule/strategy-meeting/getList").mock(
            return_value=_row_response({"id": "st1", "title": "策略会"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).strategy_list(market="SH")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "st1"


def test_forum_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/schedule/forum/getList").mock(
            return_value=_row_response({"id": "f1", "title": "论坛"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).forum_list(object_="company")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "f1"


def test_research_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/broker-report/getList").mock(
            return_value=_row_response({"reportId": "rp1", "title": "研报"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).research_list(min_pages=5, max_pages=50)
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["reportId"] == "rp1"


def test_foreign_report_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/foreign-report/getList").mock(
            return_value=_row_response({"reportId": "fr1", "title": "外资研报"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).foreign_report_list(region="US")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["reportId"] == "fr1"


def test_announcement_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/announcement/getList").mock(
            return_value=_row_response({"announcementId": "a1", "title": "公告"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).announcement_list(security="000001.SZ")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["announcementId"] == "a1"


def test_announcement_list_converts_iso_to_ms(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/announcement/getList").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"total": 0, "list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Insight(client).announcement_list(start_time="2026-01-01T00:00:00+00:00")
    sent = route.calls.last.request.read()
    # 2026-01-01 UTC = 1767225600000 ms
    assert b'"startTime":1767225600000' in sent.replace(b" ", b"")


def test_announcement_list_scales_seconds_int_to_ms(tmp_path):
    # TS toTimestamp13 parity: a seconds-level int is scaled to milliseconds.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/announcement/getList").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"total": 0, "list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Insight(client).announcement_list(start_time=1767225600)
    sent = route.calls.last.request.read()
    assert b'"startTime":1767225600000' in sent.replace(b" ", b"")


def test_to_unix_ms_naive_datetime_uses_local_timezone():
    # Matches `new Date("2026-06-01 09:00:00")` in the CLI: system-local tz.
    expected = int(dt.datetime(2026, 6, 1, 9, 0, 0).astimezone().timestamp() * 1000)
    assert _to_unix_ms("2026-06-01 09:00:00") == expected


def test_to_unix_ms_date_only_stays_utc_midnight():
    # Matches `new Date("2026-01-01")`: date-only strings are UTC midnight.
    assert _to_unix_ms("2026-01-01") == 1767225600000


def test_to_unix_ms_seconds_int_scaled():
    assert _to_unix_ms(1767225600) == 1767225600000


def test_to_unix_ms_milliseconds_int_passthrough():
    assert _to_unix_ms(1767225600000) == 1767225600000


def test_announcement_hk_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/announcement-hk/getList").mock(
            return_value=_row_response({"announcementId": "hk1", "title": "港股公告"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).announcement_hk_list(security="00700.HK")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["announcementId"] == "hk1"


def test_foreign_opinion_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/foreign-opinion/getList").mock(
            return_value=_row_response({"id": "fo1", "title": "外资观点"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).foreign_opinion_list(region="US")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "fo1"


def test_independent_opinion_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/independent-opinion/getList").mock(
            return_value=_row_response({"id": "io1", "title": "独立观点"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).independent_opinion_list(industry=42)
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "io1"


# ---- Download endpoint tests ----


def test_summary_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).summary_download(
                summary_id="s1",
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"data"


def test_research_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).research_download(
                report_id="r1",
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"data"


def test_foreign_report_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/foreign-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).foreign_report_download(
                report_id="fr1",
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"data"


def test_announcement_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/announcement/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).announcement_download(
                announcement_id="a1",
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"data"


def test_announcement_hk_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/announcement-hk/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).announcement_hk_download(
                announcement_id="hk1",
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"data"


def test_independent_opinion_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/independent-opinion/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).independent_opinion_download(
                independent_opinion_id="io1",
                file_type=1,
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"data"


def test_independent_opinion_download_uses_title_cache(tmp_path, monkeypatch, seeded_config):
    monkeypatch.chdir(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-insight/independent-opinion/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"independentOpinionId": "io1", "title": "Independent Alpha"}],
                    },
                },
            )
        )
        router.get("/application/open-insight/independent-opinion/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-type": "text/html"},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            insight = Insight(client)
            insight.independent_opinion_list()
            path = insight.independent_opinion_download(
                independent_opinion_id="io1",
                file_type=1,
            )
    assert path.name == "Independent Alpha.html"


def test_research_download_uses_title_cache(tmp_path, monkeypatch, seeded_config):
    monkeypatch.chdir(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-insight/broker-report/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"reportId": "r1", "title": "Alpha Report 2026Q1"}],
                    },
                },
            )
        )
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-type": "application/pdf"},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            insight = Insight(client)
            insight.research_list()
            path = insight.research_download(report_id="r1")
    assert path.name.startswith("Alpha Report 2026Q1")
    assert path.suffix == ".pdf"
