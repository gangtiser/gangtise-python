from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.fundamental.income_statement_hk(
        security_code="00700.HK",
        start_date="2025-01-01",
        end_date="2026-05-28",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
