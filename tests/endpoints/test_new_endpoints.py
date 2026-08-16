"""Endpoint tests for the wrappers added in the CLI v0.29.0-v0.34.1 sync.

Covers the Pamirs expert-summary library, the earnings calendar, and the async
PDF parse tool (upload -> poll -> ZIP).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains.insight import AsyncInsight, Insight
from gangtise_openapi.domains.tool import AsyncTool, Tool

_PAMIRS_LIST = "/application/open-insight/pamirs-summary/getList"
_PAMIRS_DL = "/application/open-insight/pamirs-summary/download/file"
_CALENDAR_LIST = "/application/open-insight/schedule/performance-calendar/getList"
_CALENDAR_DL = "/application/open-insight/schedule/performance-calendar/download/file"
_PARSE_SUBMIT = "/application/open-tool/file-parse/submit"
_PARSE_RESULT = "/application/open-tool/file-parse/result"


def _page(rows: list[dict], total: int | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"total": len(rows) if total is None else total, "list": rows},
        },
    )


# ───────────────────────── pamirs expert summaries ─────────────────────────


def test_pamirs_summary_list(seeded_config):
    rows = [{"summaryId": "p1", "title": "PCB 专家纪要"}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PAMIRS_LIST).mock(return_value=_page(rows))
        with GangtiseClient(_config=seeded_config) as client:
            df = Insight(client).pamirs_summary_list(
                keyword="PCB",
                category="companyAnalysis",
                market=["aShares", "hkStocks"],
                research_area="100800119",
                size=1,
            )
        body = json.loads(route.calls.last.request.read())
    assert body["keyword"] == "PCB"
    assert body["categoryList"] == ["companyAnalysis"]
    assert body["marketList"] == ["aShares", "hkStocks"]
    assert body["researchAreaList"] == ["100800119"]
    # Deliberately NOT a copy of summary_list's parameter set: the server silently
    # drops fields it does not recognise, so an unsupported filter would read as
    # applied while the caller actually got the unfiltered set.
    assert "sourceList" not in body
    assert "institutionList" not in body
    assert "participantRoleList" not in body
    assert df.iloc[0]["summaryId"] == "p1"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"category": "companyanalysis"}, "invalid category"),
        ({"market": "usEquities"}, "invalid market"),
    ],
)
def test_pamirs_summary_list_rejects_bad_enums(seeded_config, kwargs, match):
    # No respx mock: a request would be an unmatched-route error. The server
    # silently ignores a bad enum and returns the WHOLE library, so a typo has to
    # fail locally rather than masquerade as a filtered result.
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match=match):
            Insight(client).pamirs_summary_list(size=1, **kwargs)


def test_pamirs_summary_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get(_PAMIRS_DL).mock(
            return_value=httpx.Response(
                200,
                content=b"pdf",
                headers={"content-disposition": 'attachment; filename="f.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).pamirs_summary_download(
                summary_id="p1", file_type=2, output=tmp_path / "out.pdf"
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"pdf"
    assert dict(route.calls.last.request.url.params) == {"summaryId": "p1", "fileType": "2"}


# ─────────────────────────── earnings calendar ───────────────────────────


def test_performance_calendar_list(seeded_config):
    rows = [{"performanceReportId": "e1", "title": "业绩预告"}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CALENDAR_LIST).mock(return_value=_page(rows))
        with GangtiseClient(_config=seeded_config) as client:
            df = Insight(client).performance_calendar_list(
                start_date="2026-07-01",
                end_date="2026-07-31",
                market="aShares",
                category="performanceForecast",
            )
        body = json.loads(route.calls.last.request.read())
    # The only insight list filtered by DATE rather than the --start-time datetime
    # every sibling uses.
    assert body["startDate"] == "2026-07-01"
    assert body["endDate"] == "2026-07-31"
    assert body["marketList"] == ["aShares"]
    assert body["categoryList"] == ["performanceForecast"]
    assert df.iloc[0]["performanceReportId"] == "e1"


def test_performance_calendar_list_requires_a_bound(seeded_config):
    # Unfiltered this endpoint holds >120k rows and an omitted size means "fetch
    # everything" — 50k rows at 0.1 credits each. No respx mock: nothing may be sent.
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="without a bound"):
            Insight(client).performance_calendar_list()


def test_performance_calendar_list_start_date_alone_is_not_a_bound(seeded_config):
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="without a bound"):
            Insight(client).performance_calendar_list(start_date="2026-07-01")


def test_performance_calendar_security_only_caps_the_pull_at_1000_rows(seeded_config):
    # `security` is only a real bound while the server honours securityList. The
    # implicit 1000-row ceiling turns a filter regression into a truncated result
    # rather than a 5000-credit pull of the whole calendar.
    def respond(request):
        body = json.loads(request.read())
        start, size = body["from"], body["size"]
        return _page(
            [{"performanceReportId": f"e{i}"} for i in range(start, start + size)],
            total=126683,
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CALENDAR_LIST).mock(side_effect=respond)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="may not have narrowed anything"):
                out = Insight(client).performance_calendar_list(security="600519.SH", raw=True)
    assert len(out["list"]) == 1000
    assert out["partial"] is True
    assert json.loads(route.calls[0].request.read())["securityList"] == ["600519.SH"]


def test_performance_calendar_explicit_size_skips_the_cap(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CALENDAR_LIST).mock(return_value=_page([], total=0))
        with GangtiseClient(_config=seeded_config) as client:
            Insight(client).performance_calendar_list(security="600519.SH", size=5)
        body = json.loads(route.calls[0].request.read())
    assert body["size"] == 5


def test_performance_calendar_cap_hit_with_rows_remaining_is_partial(seeded_config):
    # 1000 rows back but total says there are more: the signature of a filter that
    # did not narrow anything, so what came back is a slice of the whole calendar.
    rows = [{"performanceReportId": f"e{i}"} for i in range(1000)]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CALENDAR_LIST).mock(return_value=_page(rows, total=126683))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="may not have narrowed anything"):
                out = Insight(client).performance_calendar_list(security="600519.SH", raw=True)
    assert out["partial"] is True


def test_performance_calendar_exactly_cap_rows_but_complete_is_not_partial(seeded_config):
    # A result that happens to be exactly `cap` rows long IS complete — flagging it
    # would make every automated caller read a full answer as truncated.
    rows = [{"performanceReportId": f"e{i}"} for i in range(1000)]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CALENDAR_LIST).mock(return_value=_page(rows, total=1000))
        with GangtiseClient(_config=seeded_config) as client:
            out = Insight(client).performance_calendar_list(security="600519.SH", raw=True)
    assert "partial" not in out


def test_performance_calendar_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get(_CALENDAR_DL).mock(
            return_value=httpx.Response(
                200,
                content=b"pdf",
                headers={"content-disposition": 'attachment; filename="f.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).performance_calendar_download(
                performance_report_id="e1", output=tmp_path / "out.pdf"
            )
    assert path.read_bytes() == b"pdf"
    assert dict(route.calls.last.request.url.params) == {"performanceReportId": "e1"}


# ───────────────────────────── file parse ─────────────────────────────


def _pdf(tmp_path, name: str = "a.pdf", body: bytes = b"%PDF-1.4 x") -> str:
    path = tmp_path / name
    path.write_bytes(body)
    return str(path)


def test_file_parse_submits_multipart_and_returns_task_id(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PARSE_SUBMIT).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"taskId": "t-1"}}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            task_id = Tool(client).file_parse(file=_pdf(tmp_path))
    assert task_id == "t-1"
    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b"%PDF-1.4 x" in request.read()


def test_file_parse_bare_numeric_task_id_comes_back_as_a_string(tmp_path, seeded_config):
    # `taskId` is registered in big_int_fields: whether the server quotes it or
    # not, the caller must always get the same type — the id has to be echoed back
    # verbatim to fetch a result that is already billed.
    raw = b'{"code":"000000","status":true,"data":{"taskId":1782345678901234567}}'
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_PARSE_SUBMIT).mock(
            return_value=httpx.Response(
                200, content=raw, headers={"content-type": "application/json"}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            task_id = Tool(client).file_parse(file=_pdf(tmp_path))
    assert task_id == "1782345678901234567"


def test_file_parse_missing_task_id_raises(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_PARSE_SUBMIT).mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {}})
        )
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="carried no taskId"):
                Tool(client).file_parse(file=_pdf(tmp_path))


@pytest.mark.parametrize(
    ("name", "content", "match"),
    [
        ("a.txt", b"x", "only PDF files are supported"),
        ("a.pdf", b"", "file is empty"),
    ],
)
def test_file_parse_rejects_bad_input_before_billing(tmp_path, seeded_config, name, content, match):
    # Billed at submit time (0.8 credits/page), so every reason to reject is
    # checked before the request goes out. No respx mock: nothing may be sent.
    path = tmp_path / name
    path.write_bytes(content)
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match=match):
            Tool(client).file_parse(file=str(path))


def test_file_parse_rejects_a_missing_file(tmp_path, seeded_config):
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="file not found"):
            Tool(client).file_parse(file=str(tmp_path / "nope.pdf"))


def test_file_parse_check_posts_the_task_id_and_writes_the_zip(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PARSE_RESULT).mock(
            return_value=httpx.Response(
                200,
                content=b"PK\x03\x04zip",
                headers={"content-disposition": 'attachment; filename="r.zip"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Tool(client).file_parse_check(task_id="t-1", output=tmp_path / "r.zip")
    assert path.read_bytes() == b"PK\x03\x04zip"
    # A POST download endpoint: the task id travels in the JSON body, not the query.
    assert json.loads(route.calls.last.request.read()) == {"taskId": "t-1"}


def test_file_parse_check_surfaces_pending_without_wait(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_PARSE_RESULT).mock(
            return_value=httpx.Response(
                409, json={"code": "140001", "status": False, "msg": "生成中"}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as excinfo:
                Tool(client).file_parse_check(task_id="t-1", output=tmp_path / "r.zip")
    assert excinfo.value.code == "140001"


def test_file_parse_check_wait_polls_until_ready(tmp_path, seeded_config, monkeypatch):
    monkeypatch.setattr("gangtise_openapi.domains.tool.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def respond(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(409, json={"code": "140001", "status": False, "msg": "生成中"})
        return httpx.Response(
            200,
            content=b"PK\x03\x04zip",
            headers={"content-disposition": 'attachment; filename="r.zip"'},
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_PARSE_RESULT).mock(side_effect=respond)
        with GangtiseClient(_config=seeded_config) as client:
            path = Tool(client).file_parse_check(
                task_id="t-1", output=tmp_path / "r.zip", wait=True
            )
    assert calls["n"] == 2
    assert path.read_bytes() == b"PK\x03\x04zip"


def test_file_parse_check_wait_aborts_on_a_terminal_failure(tmp_path, seeded_config, monkeypatch):
    # 140002 is terminal: re-checking will never change it, and resubmitting bills
    # the pages again — so it must not consume the whole poll budget.
    monkeypatch.setattr("gangtise_openapi.domains.tool.time.sleep", lambda _s: None)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PARSE_RESULT).mock(
            return_value=httpx.Response(
                500, json={"code": "140002", "status": False, "msg": "解析失败"}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="terminal 140002"):
                Tool(client).file_parse_check(task_id="t-1", output=tmp_path / "r.zip", wait=True)
    assert route.call_count == 1


@pytest.mark.anyio
async def test_async_file_parse_round_trip(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_PARSE_SUBMIT).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"taskId": "t-9"}}
            )
        )
        result = router.post(_PARSE_RESULT).mock(
            return_value=httpx.Response(
                200,
                content=b"PK\x03\x04zip",
                headers={"content-disposition": 'attachment; filename="r.zip"'},
            )
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            tool = AsyncTool(client)
            task_id = await tool.file_parse(file=_pdf(tmp_path))
            path = await tool.file_parse_check(task_id=task_id, output=tmp_path / "r.zip")
    assert task_id == "t-9"
    assert path.read_bytes() == b"PK\x03\x04zip"
    assert json.loads(result.calls.last.request.read()) == {"taskId": "t-9"}


@pytest.mark.anyio
async def test_async_pamirs_summary_list(seeded_config):
    rows = [{"summaryId": "p1", "title": "PCB 专家纪要"}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PAMIRS_LIST).mock(return_value=_page(rows))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            df = await AsyncInsight(client).pamirs_summary_list(category="industryAnalysis", size=1)
        body = json.loads(route.calls.last.request.read())
    assert body["categoryList"] == ["industryAnalysis"]
    assert df.iloc[0]["summaryId"] == "p1"


@pytest.mark.anyio
async def test_async_performance_calendar_requires_a_bound(seeded_config):
    async with AsyncGangtiseClient(_config=seeded_config) as client:
        with pytest.raises(ValidationError, match="without a bound"):
            await AsyncInsight(client).performance_calendar_list()
