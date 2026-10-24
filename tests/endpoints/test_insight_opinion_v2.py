"""Opinion lists on v2, the two detail endpoints, meeting highlights (TS v0.41.0),
the per-element detail handling (TS v0.43.1) and the A-share announcement end-of-day
``end_time`` (TS v0.44.0)."""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains.insight import AsyncInsight, Insight, _OpinionDetails

_BEIJING = dt.timezone(dt.timedelta(hours=8))
_DOMESTIC_DETAIL = "/application/open-insight/chief-opinion/getDetail"
_FOREIGN_DETAIL = "/application/open-insight/foreign-opinion/getDetail"


def _ok(data) -> httpx.Response:
    return httpx.Response(200, json={"code": "000000", "status": True, "data": data})


def _page(rows: list[dict]) -> httpx.Response:
    return _ok({"total": len(rows), "list": rows})


def _ids(n: int, prefix: str = "ID") -> list[str]:
    return [f"{prefix}{i + 1}" for i in range(n)]


def _sent(route) -> dict:
    return json.loads(route.calls.last.request.content)


def _detail_route(router, *, path=_DOMESTIC_DETAIL, field="chiefOpinionIdList", answer=None):
    """Answers every batch with one body per requested ID unless ``answer(ids)`` says
    otherwise; records what each call asked for."""
    id_field = field.removesuffix("List")
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ids = json.loads(request.content)[field]
        calls.append(ids)
        if answer is not None:
            return answer(ids)
        return _ok([{id_field: i, "content": f"body {i}"} for i in ids])

    router.post(path).mock(side_effect=handler)
    return calls


# ---------------------------------------------------------------- opinion lists


@pytest.mark.parametrize(
    ("method", "v2", "v1"),
    [
        (
            "opinion_list",
            "/application/open-insight/chief-opinion/v2/getList",
            "/application/open-insight/chief-opinion/getList",
        ),
        (
            "foreign_opinion_list",
            "/application/open-insight/foreign-opinion/v2/getList",
            "/application/open-insight/foreign-opinion/getList",
        ),
    ],
)
def test_opinion_lists_default_to_v2_and_with_content_to_v1(seeded_config, method, v2, v1):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        brief = router.post(v2).mock(return_value=_page([{"brief": "摘要"}]))
        full = router.post(v1).mock(return_value=_page([{"content": "正文"}]))
        with GangtiseClient(_config=seeded_config) as client:
            insight = Insight(client)
            df = getattr(insight, method)(security="600519.SH", size=1)
            raw = getattr(insight, method)(
                security="600519.SH", size=1, with_content=True, raw=True
            )
    assert df.iloc[0]["brief"] == "摘要"
    assert raw["list"][0]["content"] == "正文"
    # Same filters either way — only the endpoint changes.
    assert _sent(brief) == _sent(full)
    assert _sent(brief)["securityList"] == ["600519.SH"]


def test_opinion_list_with_content_keeps_the_legacy_shape(seeded_config):
    # v1 domestic rows carry title and body under contentList (an OBJECT), with no
    # top-level title / brief — passed through as is, not reshaped.
    row = {"chiefOpinionId": "o1", "contentList": {"title": "标题", "content": "正文"}}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/chief-opinion/getList").mock(
            return_value=_page([row])
        )
        with GangtiseClient(_config=seeded_config) as client:
            df = Insight(client).opinion_list(with_content=True, size=1)
    assert "title" not in df.columns
    assert df.iloc[0]["contentList"] == {"title": "标题", "content": "正文"}


@pytest.mark.anyio
async def test_async_opinion_lists_switch_endpoint_on_with_content(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        v2 = router.post("/application/open-insight/foreign-opinion/v2/getList").mock(
            return_value=_page([{"briefTranslate": "摘要"}])
        )
        v1 = router.post("/application/open-insight/chief-opinion/getList").mock(
            return_value=_page([{"contentList": {"content": "正文"}}])
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            insight = AsyncInsight(client)
            df = await insight.foreign_opinion_list(region="us", size=1)
            raw = await insight.opinion_list(with_content=True, size=1, raw=True)
    assert df.iloc[0]["briefTranslate"] == "摘要"
    assert raw["list"][0]["contentList"]["content"] == "正文"
    assert _sent(v2)["regionList"] == ["us"]
    assert v1.called


_OPINION_V2 = "/application/open-insight/chief-opinion/v2/getList"


def test_opinion_list_sends_category_and_broker_tag(seeded_config):
    # TS v0.47.0: opinion category and broker tag are their own filters next to llm_tag.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_OPINION_V2).mock(return_value=_page([{"categoryList": []}]))
        with GangtiseClient(_config=seeded_config) as client:
            Insight(client).opinion_list(
                category=["earningsReview", "tradingDesk"],
                llm_tag="beatExpect",
                broker_tag="topBroker",
                size=1,
            )
    sent = _sent(route)
    assert sent["categoryList"] == ["earningsReview", "tradingDesk"]
    assert sent["llmTagList"] == ["beatExpect"]
    assert sent["brokerTagList"] == ["topBroker"]


@pytest.mark.parametrize("filters", [{"category": "earningsReview"}, {"broker_tag": "topBroker"}])
def test_with_content_refuses_the_filters_its_v1_list_ignores(seeded_config, filters):
    # The v1 list drops categoryList / brokerTagList unread: sent, the filter would widen
    # to every opinion at 30 credits a row.
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        catch_all = router.route().mock(return_value=_page([]))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="opinion_detail"):
                Insight(client).opinion_list(with_content=True, size=1, **filters)
    assert not catch_all.called


@pytest.mark.anyio
async def test_async_with_content_refuses_category(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        catch_all = router.route().mock(return_value=_page([]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match="with_content"):
                await AsyncInsight(client).opinion_list(
                    with_content=True, broker_tag="newFortune", size=1
                )
    assert not catch_all.called


@pytest.mark.anyio
async def test_async_opinion_list_sends_category_and_broker_tag(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_OPINION_V2).mock(return_value=_page([{"brief": "b"}]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            await AsyncInsight(client).opinion_list(
                category="industryAnalysis", broker_tag="newFortune", size=1
            )
    assert _sent(route)["categoryList"] == ["industryAnalysis"]
    assert _sent(route)["brokerTagList"] == ["newFortune"]


# ---------------------------------------------------------------- detail batching


def test_detail_dedupes_and_sends_at_most_20_ids_per_call_in_order(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        calls = _detail_route(router)
        with GangtiseClient(_config=seeded_config) as client:
            result = Insight(client).opinion_detail(
                chief_opinion_id=[*_ids(45), "ID1", "ID2"], raw=True
            )
    assert [len(c) for c in calls] == [20, 20, 5]
    assert [i for c in calls for i in c] == _ids(45)
    assert result["total"] == 45
    assert "partial" not in result


def test_detail_default_returns_the_bodies_as_a_dataframe(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router)
        with GangtiseClient(_config=seeded_config) as client:
            df = Insight(client).opinion_detail(chief_opinion_id="ID7")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["content"] == "body ID7"


def test_detail_names_the_ids_the_server_skipped(seeded_config):
    def answer(ids):
        return _ok([{"chiefOpinionId": i, "content": "x"} for i in ids if i not in ("ID2", "ID21")])

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=answer)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match=r"no body returned for 2 ID\(s\): ID2, ID21"):
                result = Insight(client).opinion_detail(chief_opinion_id=_ids(25), raw=True)
    assert result["missingIds"] == ["ID2", "ID21"]
    assert result["partial"] is True
    assert result["total"] == 23
    assert "unfetchedIds" not in result


def test_detail_keeps_earlier_bodies_when_a_later_batch_fails(seeded_config):
    failure = {"code": "100003", "status": False, "msg": "参数值非法", "traceId": "T-2"}

    def answer(ids):
        if ids[0] == "ID21":
            return httpx.Response(200, json=failure)
        return _ok([{"chiefOpinionId": i, "content": "x"} for i in ids])

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=answer)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match=r"failed on batch 2 .*10 ID\(s\) not fetched"):
                result = Insight(client).opinion_detail(chief_opinion_id=_ids(30), raw=True)
    assert result["total"] == 20
    assert result["unfetchedIds"] == _ids(30)[20:]
    assert result["unfetchedError"] == {"message": "参数值非法", "code": "100003", "traceId": "T-2"}
    # Not fetched is not the same as skipped: none of these may be reported as missing.
    assert "missingIds" not in result
    assert result["partial"] is True


def test_detail_first_batch_failure_propagates(seeded_config):
    failure = {"code": "100003", "status": False, "msg": "参数值非法"}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=lambda ids: httpx.Response(200, json=failure))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as exc:
                Insight(client).opinion_detail(chief_opinion_id=_ids(3))
    assert exc.value.code == "100003"


def test_detail_null_element_is_a_missing_body_beside_kept_bodies(seeded_config):
    def answer(ids):
        if ids[0] == "ID21":
            return _ok([None])
        return _ok([*[{"chiefOpinionId": i, "content": "x"} for i in ids[1:]], None])

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=answer)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(
                UserWarning,
                match=r"no body returned for 2 ID\(s\): ID1, ID21 \(2 came back as a null element\)",
            ):
                result = Insight(client).opinion_detail(chief_opinion_id=_ids(21), raw=True)
    assert result["total"] == 19
    assert result["missingIds"] == ["ID1", "ID21"]
    assert "unfetchedIds" not in result
    assert result["partial"] is True


@pytest.mark.parametrize("element", [1, "x", []])
def test_detail_malformed_element_in_a_later_batch_lists_the_rest_as_unfetched(
    seeded_config, element
):
    def answer(ids):
        if ids[0] == "ID21":
            return _ok([element])
        return _ok([{"chiefOpinionId": i, "content": "x"} for i in ids])

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=answer)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="non-object element"):
                result = Insight(client).opinion_detail(chief_opinion_id=_ids(21), raw=True)
    assert result["total"] == 20
    assert result["unfetchedIds"] == ["ID21"]
    assert "non-object element" in result["unfetchedError"]["message"]
    assert result["partial"] is True


def test_detail_malformed_first_batch_with_no_body_raises_structurally(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=lambda ids: _ok(["x"]))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="non-object element") as exc:
                Insight(client).opinion_detail(chief_opinion_id="ID21")
    assert exc.value.structural is True


def test_detail_keeps_bodies_returned_beside_a_malformed_element(seeded_config):
    def answer(ids):
        if ids[0] == "ID21":
            return _ok([{"chiefOpinionId": "ID21", "content": "x"}, "x"])
        return _ok([{"chiefOpinionId": i, "content": "x"} for i in ids])

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=answer)
        with GangtiseClient(_config=seeded_config) as client:
            insight = Insight(client)
            with pytest.warns(UserWarning, match="non-object element"):
                later = insight.opinion_detail(chief_opinion_id=_ids(22), raw=True)
            # In the first batch too: a body was delivered, so it is kept, not thrown away.
            with pytest.warns(UserWarning, match="non-object element"):
                first = insight.opinion_detail(chief_opinion_id=["ID21", "ID22"], raw=True)
    assert later["total"] == 21
    assert later["unfetchedIds"] == ["ID22"]
    assert "missingIds" not in later
    assert first["total"] == 1
    assert first["unfetchedIds"] == ["ID22"]
    assert first["partial"] is True


def test_detail_non_array_payload_is_refused_by_the_transport(seeded_config):
    # expects="array": an object answer is a changed layout, not "no bodies" — it must
    # not report every paid-for ID as missing.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=lambda ids: _ok({"list": []}))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="returned no array payload") as exc:
                Insight(client).opinion_detail(chief_opinion_id="ID1")
    assert exc.value.structural is True


def test_detail_refuses_an_empty_id_list_before_any_request(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(_DOMESTIC_DETAIL)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="chief_opinion_id"):
                Insight(client).opinion_detail(chief_opinion_id=[])
    assert not route.called


def test_foreign_detail_sends_its_own_id_list_field(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        calls = _detail_route(router, path=_FOREIGN_DETAIL, field="foreignOpinionIdList")
        with GangtiseClient(_config=seeded_config) as client:
            result = Insight(client).foreign_opinion_detail(
                foreign_opinion_id=["F1", "F2", "F1"], raw=True
            )
    assert calls == [["F1", "F2"]]
    assert [r["foreignOpinionId"] for r in result["list"]] == ["F1", "F2"]


def test_detail_carries_the_envelope_trace_of_a_malformed_batch():
    # The rows ride on the structural error as ``details``; when the transport tags
    # the payload with its envelope traceId, ``unfetchedError`` reports it.
    class TracedRows(list):
        envelope_trace_id = "T-21"

    job = _OpinionDetails(
        "insight.opinion.detail", "chiefOpinionIdList", "chiefOpinionId", _ids(21)
    )
    job.take([{"chiefOpinionId": i} for i in _ids(20)])
    with pytest.raises(ApiError) as exc:
        job.take(TracedRows(["x"]))
    with pytest.warns(UserWarning, match="not fetched: ID21"):
        job.fail(20, exc.value)
    result = job.result()
    assert result["unfetchedError"]["traceId"] == "T-21"
    assert result["unfetchedIds"] == ["ID21"]


@pytest.mark.anyio
async def test_async_detail_batches_and_reports_missing(seeded_config):
    def answer(ids):
        return _ok([{"foreignOpinionId": i, "content": "x"} for i in ids if i != "F22"])

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        calls = _detail_route(
            router, path=_FOREIGN_DETAIL, field="foreignOpinionIdList", answer=answer
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.warns(UserWarning, match=r"no body returned for 1 ID\(s\): F22"):
                result = await AsyncInsight(client).foreign_opinion_detail(
                    foreign_opinion_id=_ids(25, "F"), raw=True
                )
    assert [len(c) for c in calls] == [20, 5]
    assert result["missingIds"] == ["F22"]
    assert result["partial"] is True


@pytest.mark.anyio
async def test_async_detail_keeps_earlier_bodies_when_a_later_batch_fails(seeded_config):
    failure = {"code": "999999", "status": False, "msg": "系统内部错误", "traceId": "T-9"}

    def answer(ids):
        if ids[0] == "ID21":
            return httpx.Response(200, json=failure)
        return _ok([{"chiefOpinionId": i, "content": "x"} for i in ids])

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=answer)
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.warns(UserWarning, match="failed on batch 2"):
                result = await AsyncInsight(client).opinion_detail(
                    chief_opinion_id=_ids(21), raw=True
                )
            df = await AsyncInsight(client).opinion_detail(chief_opinion_id="ID3")
    assert result["unfetchedIds"] == ["ID21"]
    assert result["unfetchedError"]["code"] == "999999"
    assert result["unfetchedError"]["traceId"] == "T-9"
    assert df.iloc[0]["content"] == "x"


@pytest.mark.anyio
async def test_async_detail_malformed_first_batch_raises(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=lambda ids: _ok([[]]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ApiError, match="non-object element") as exc:
                await AsyncInsight(client).opinion_detail(chief_opinion_id="ID1")
    assert exc.value.structural is True


# ---------------------------------------------------------------- highlight


_HIGHLIGHT = "/application/open-insight/summary/highlight/getList"


def test_highlight_list_body_and_frame(seeded_config):
    row = {
        "highlightId": "h1",
        "title": "业绩会",
        "content": "<p><strong>要点</strong>内容</p>",
        "securityList": [],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_HIGHLIGHT).mock(return_value=_page([row]))
        with GangtiseClient(_config=seeded_config) as client:
            df = Insight(client).highlight_list(
                size=1,
                start_time="2026/09/01",
                end_time="2026-09-02 23:59:59",
                security="09992.HK",
                research_area=[100800101, "122000001"],
            )
    assert _sent(route) == {
        "from": 0,
        "size": 1,
        "startTime": "2026-09-01",
        "endTime": "2026-09-02 23:59:59",
        "securityList": ["09992.HK"],
        "researchAreaList": [100800101, "122000001"],
    }
    assert df.iloc[0]["highlightId"] == "h1"


def test_highlight_list_takes_no_keyword():
    # The endpoint has no keyword / rank_type; the signature must not pretend otherwise.
    import inspect

    params = inspect.signature(Insight.highlight_list).parameters
    assert "keyword" not in params
    assert "rank_type" not in params


@pytest.mark.anyio
async def test_async_highlight_list_raw(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_HIGHLIGHT).mock(return_value=_page([{"highlightId": "h1"}]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            raw = await AsyncInsight(client).highlight_list(size=1, raw=True)
    assert raw["list"] == [{"highlightId": "h1"}]


# ---------------------------------------------------------------- A-share end_time


def _beijing_millis(*args: int) -> int:
    return int(dt.datetime(*args, tzinfo=_BEIJING).timestamp() * 1000)


@pytest.mark.parametrize(
    ("end_time", "expected"),
    [
        # A bare date is the WHOLE day: its last millisecond, not its midnight.
        ("2026-09-01", _beijing_millis(2026, 9, 2) - 1),
        ("2026/09/01", _beijing_millis(2026, 9, 2) - 1),
        ("20260901", _beijing_millis(2026, 9, 2) - 1),
        # Anything carrying a time converts as written.
        ("2026-09-01 15:00:00", _beijing_millis(2026, 9, 1, 15)),
        ("2026-09-01T00:00", _beijing_millis(2026, 9, 1)),
        ("1756656000000", 1756656000000),
    ],
)
def test_announcement_list_bare_end_date_is_the_end_of_that_beijing_day(
    seeded_config, end_time, expected
):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/announcement/getList").mock(
            return_value=_page([])
        )
        with GangtiseClient(_config=seeded_config) as client:
            Insight(client).announcement_list(start_time="2026-09-01", end_time=end_time, size=1)
    body = _sent(route)
    assert body["startTime"] == _beijing_millis(2026, 9, 1)
    assert body["endTime"] == expected


@pytest.mark.anyio
async def test_async_announcement_list_same_day_window_is_not_empty(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/announcement/getList").mock(
            return_value=_page([])
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            await AsyncInsight(client).announcement_list(
                start_time="2026-09-01", end_time="2026-09-01", size=1
            )
    body = _sent(route)
    assert body["endTime"] - body["startTime"] == 86_400_000 - 1
