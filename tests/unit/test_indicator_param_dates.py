"""``indicator_param`` date values: normalized like ``date``, year-last refused (TS v0.44.0 ⑧)."""

from __future__ import annotations

import pytest

from gangtise_openapi.domains._common import ValidationError
from gangtise_openapi.domains.indicator import _normalize_param_dates

# ───────────── indicator_param date values (TS v0.44.0 ⑧) ─────────────


def test_date_keyed_params_are_normalized_like_date():
    spec = {
        "is_op_rev": {"reportDate": "2025/12/31", "reportType": "1"},
        "qte_vol_intvl": {"sDate": "20240102"},
        "div_cash_yld": {"tradeDate": "2026-03-31", "reportDate": "2025-12-31"},
        "pty_shr_reg": {"currency": "CNY", "tradeDate": None},
    }
    assert _normalize_param_dates(spec) == {
        "is_op_rev": {"reportDate": "2025-12-31", "reportType": "1"},
        "qte_vol_intvl": {"sDate": "2024-01-02"},
        "div_cash_yld": {"tradeDate": "2026-03-31", "reportDate": "2025-12-31"},
        # A suppression marker is not a value: left alone.
        "pty_shr_reg": {"currency": "CNY", "tradeDate": None},
    }


def test_date_keyed_params_refuse_year_last_and_name_the_param():
    with pytest.raises(ValidationError, match=r"indicator_param\['is_op_rev'\]\['reportDate'\]"):
        _normalize_param_dates({"is_op_rev": {"reportDate": "12-31-2025"}})
    with pytest.raises(ValidationError, match="not a real calendar date"):
        _normalize_param_dates({"qte_close": {"baseDate": "2025-02-30"}})


def test_non_date_params_pass_through_untouched():
    spec = {"qte_close": {"adjustType": "2"}, "finc_roe_avg_avg": {"periodNum": 4}}
    assert _normalize_param_dates(spec) == spec
    assert _normalize_param_dates(None) is None
    assert _normalize_param_dates({}) == {}
