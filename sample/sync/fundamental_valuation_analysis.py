from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.fundamental.valuation_analysis(
        security_code="000001.SZ",
        indicator="pe_ttm",
        start_date="2025-01-01",
        end_date="2026-05-28",
        limit=20,
        skip_null=True,
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
