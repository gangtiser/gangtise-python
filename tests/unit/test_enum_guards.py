"""Local whitelists for enum-valued kwargs (CLI v0.32.0).

The server treats an out-of-range enum exactly like an unknown field: it drops the
condition and answers 200 with the UNFILTERED set. These guards turn that into a
local error, before any billed request.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._endpoints import ENDPOINTS, lookup
from gangtise_openapi._errors import ValidationError
from gangtise_openapi.domains._common import _request_body
from gangtise_openapi.domains.insight import Insight


def test_search_type_out_of_range_is_refused():
    # The worst case in the family: an illegal searchType takes `keyword` down
    # with it. Probed by the CLI 2026-08-08 — summary list for 茅台 goes from 135
    # rows to 196988 (the whole library) at exit 0.
    with pytest.raises(ValidationError, match="invalid search_type"):
        _request_body({"keyword": "茅台", "searchType": 99})


def test_rank_type_out_of_range_is_refused():
    with pytest.raises(ValidationError, match="invalid rank_type"):
        _request_body({"rankType": 3})


@pytest.mark.parametrize("value", [1, 2])
def test_legal_enum_values_pass_through(value):
    assert _request_body({"searchType": value, "rankType": value}) == {
        "searchType": value,
        "rankType": value,
    }


def test_unset_enum_is_not_validated():
    assert _request_body({"searchType": None}) == {}


def test_bool_is_not_an_enum_value():
    # bool is an int subclass, so `True in (1, 2)` is True — reject it explicitly.
    with pytest.raises(ValidationError, match="invalid search_type"):
        _request_body({"searchType": True})


def test_enum_guard_is_mounted_on_every_list_wrapper(seeded_config):
    # The guard lives in _request_body, the single seam every wrapper funnels
    # through, so it also covers wrappers added later. No respx mock: a request
    # would be an unmatched-route error.
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="invalid search_type"):
            Insight(client).summary_list(keyword="茅台", search_type=99)


# ─────────────────────────────── file_type ───────────────────────────────


def test_file_type_out_of_range_is_refused(tmp_path, seeded_config):
    # The server ignores an out-of-range fileType and hands back the DEFAULT
    # format, so a typo silently downloads something other than what was asked
    # for. No respx mock: nothing may be sent.
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="invalid file_type"):
            Insight(client).research_download(
                report_id="r1", file_type=9, output=tmp_path / "out.pdf"
            )


def test_foreign_report_accepts_its_wider_file_type_range(tmp_path, seeded_config):
    # foreign-report is the one endpoint whose fileType goes up to 4.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/foreign-report/download/file").mock(
            return_value=httpx.Response(
                200, content=b"x", headers={"content-disposition": 'attachment; filename="f.pdf"'}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).foreign_report_download(
                report_id="r1", file_type=4, output=tmp_path / "out.pdf"
            )
    assert path.read_bytes() == b"x"


def test_file_type_4_is_refused_where_only_1_2_are_legal(tmp_path, seeded_config):
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="invalid file_type"):
            Insight(client).summary_download(
                summary_id="s1", file_type=4, output=tmp_path / "out.pdf"
            )


def test_undeclared_endpoint_given_a_file_type_fails_loudly(tmp_path, seeded_config):
    # The "cannot forget it" half of the registry guard: a download endpoint that
    # is handed a fileType while declaring none is a wiring mistake, and it must
    # not degrade into "the server picks a format for you".
    from gangtise_openapi._download import download_to_path

    assert not lookup("insight.report-image.download").file_types
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="declares no legal values"):
            download_to_path(
                client=client,
                endpoint_key="insight.report-image.download",
                query={"chunkId": "c1", "fileType": 1},
                output=tmp_path / "out.png",
                fallback_name="x",
            )


def test_file_type_registry_matches_ts_source():
    # Translated 1:1 from gangtise-openapi-cli v0.32.0 cli.ts (the `choices` field
    # of each addDownloadCommand spec).
    assert {k: ep.file_types for k, ep in ENDPOINTS.items() if ep.file_types} == {
        "insight.summary.download": (1, 2),
        "insight.pamirs-summary.download": (1, 2),
        "insight.research.download": (1, 2),
        "insight.foreign-report.download": (1, 2, 3, 4),
        "insight.announcement.download": (1, 2),
        "insight.announcement-hk.download": (1, 2),
        "insight.announcement-us.download": (1, 2),
        "insight.independent-opinion.download": (1, 2),
        "insight.official-account.download": (1, 2),
    }


# ── file_type: bool is an int subclass ──


def test_file_type_true_is_not_file_type_1(tmp_path, seeded_config):
    # `True in (1, 2)` is True in Python, so a bool slips a naive membership test
    # and goes out as JSON `true`. Same judgement as the scalar enum guard.
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="invalid file_type"):
            Insight(client).research_download(
                report_id="r1", file_type=True, output=tmp_path / "out.pdf"
            )
