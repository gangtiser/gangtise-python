# ruff: noqa: RUF001
# (the knowledge-batch query deliberately holds a fullwidth comma)
"""ai changes ported from TS v0.39.0 to v0.44.0: local enum guards on hot-topic /
security-clue (v0.43.0 ⑧), knowledge-batch queries sent whole (v0.40.0 ⑧) and its
bare end date read as the end of that day (v0.44.0 ⑧), and the terminal-failure
wording split by msg (v0.44.0 ⑫) on the non-blocking ``*_check`` path too."""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains.ai import AI, AsyncAI

_BEIJING = dt.timezone(dt.timedelta(hours=8))
_HOT_TOPIC = "/application/open-ai/hot-topic/getList"
_CLUE = "/application/open-ai/security-clue/getList"
_KNOWLEDGE = "/application/open-data/ai/search/knowledge/batch"
_ER_CONTENT = "/application/open-ai/agent/earnings-review-getcontent"
_VD_CONTENT = "/application/open-ai/agent/viewpoint-debate-getcontent"


def _ok(data) -> httpx.Response:
    return httpx.Response(200, json={"code": "000000", "status": True, "data": data})


def _sent(route) -> dict:
    return json.loads(route.calls.last.request.content)


def _millis(*args: int) -> int:
    return int(dt.datetime(*args, tzinfo=_BEIJING).timestamp() * 1000)


# ---------------------------------------------------------------- enum guards


@pytest.mark.parametrize(
    ("path", "call"),
    [
        (_HOT_TOPIC, lambda ai: ai.hot_topic(category=["morningBriefing", "lunchBriefing"])),
        (
            _CLUE,
            lambda ai: ai.security_clue_list(
                start_time="2026-09-01",
                end_time="2026-09-02",
                query_mode="bySecurity",
                gts_code="600519.SH",
                source="bogusSource",
            ),
        ),
    ],
)
def test_bad_enum_is_refused_before_the_request(seeded_config, path, call):
    # Neither endpoint refuses an unknown value: security-clue ignores it and answers
    # the unfiltered, fully billed set — so the typo has to fail here.
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(path)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="is not one of"):
                call(AI(client))
    assert not route.called


def test_hot_topic_sends_every_category_when_none_is_named(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_HOT_TOPIC).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=seeded_config) as client:
            AI(client).hot_topic(size=1, raw=True)
            default = _sent(route)["categoryList"]
            AI(client).hot_topic(size=1, category="eveningBriefing", raw=True)
            named = _sent(route)["categoryList"]
    assert default == ["morningBriefing", "noonBriefing", "afternoonFlash", "eveningBriefing"]
    assert named == ["eveningBriefing"]


@pytest.mark.anyio
async def test_async_bad_enums_are_refused(seeded_config):
    async with AsyncGangtiseClient(_config=seeded_config) as client:
        ai = AsyncAI(client)
        with pytest.raises(ValidationError, match="invalid category"):
            await ai.hot_topic(category="daily")
        with pytest.raises(ValidationError, match="invalid source"):
            await ai.security_clue_list(
                start_time="2026-09-01",
                end_time="2026-09-02",
                query_mode="byIndustry",
                gts_code="821035.SWI",
                source=["view", "news"],
            )


# ---------------------------------------------------------------- knowledge-batch


def test_knowledge_batch_sends_each_query_whole_and_ends_a_bare_date_at_day_end(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_KNOWLEDGE).mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            AI(client).knowledge_batch(
                query="比较两家公司毛利率，并解释差异,以及原因",
                start_time="2026-09-01",
                end_time="2026-09-01",
                raw=True,
            )
    body = _sent(route)
    # A comma inside a question is punctuation, never a separator.
    assert body["queries"] == ["比较两家公司毛利率，并解释差异,以及原因"]
    assert body["startTime"] == _millis(2026, 9, 1)
    assert body["endTime"] == _millis(2026, 9, 2) - 1


@pytest.mark.anyio
async def test_async_knowledge_batch_keeps_a_list_of_queries_and_timed_ends(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_KNOWLEDGE).mock(return_value=_ok([]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            await AsyncAI(client).knowledge_batch(
                query=["毛利率, 净利率", "现金流"],
                end_time="2026-09-01 10:00:00",
                raw=True,
            )
    body = _sent(route)
    assert body["queries"] == ["毛利率, 净利率", "现金流"]
    assert body["endTime"] == _millis(2026, 9, 1, 10)


# ---------------------------------------------------------------- terminal wording


_TERMINAL = {"code": "410111", "status": False, "msg": "业务处理失败", "traceId": "T-1"}


def test_check_reraises_a_terminal_failure_with_the_split_wording(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_ER_CONTENT).mock(return_value=httpx.Response(400, json=_TERMINAL))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as exc:
                AI(client).earnings_review_check(data_id="d1")
    text = str(exc.value)
    assert exc.value.code == "410111"
    assert exc.value.trace_id == "T-1"
    assert "not about the parameters" in text
    # The per-code hint ("换参数后重新提交") would contradict that — it is replaced.
    assert "换参数后重新提交" not in text
    assert "与参数无关" in text


def test_check_leaves_a_pending_answer_as_the_servers_error(seeded_config):
    pending = {"code": "410110", "status": False, "msg": "正在生成中"}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_VD_CONTENT).mock(return_value=httpx.Response(400, json=pending))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as exc:
                AI(client).viewpoint_debate_check(data_id="d1")
    assert exc.value.code == "410110"
    assert str(exc.value).startswith("正在生成中")


@pytest.mark.anyio
async def test_async_check_reraises_a_terminal_failure_with_the_split_wording(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_VD_CONTENT).mock(return_value=httpx.Response(400, json=_TERMINAL))
        router.post(_ER_CONTENT).mock(return_value=_ok({"content": "点评"}))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            ai = AsyncAI(client)
            with pytest.raises(ApiError, match="not about the parameters") as exc:
                await ai.viewpoint_debate_check(data_id="d1")
            done = await ai.earnings_review_check(data_id="d2")
    assert exc.value.trace_id == "T-1"
    assert done == {"content": "点评"}
