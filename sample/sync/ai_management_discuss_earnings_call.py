from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.ai.management_discuss_earnings_call(
        report_date="2025-12-31",
        security_code="000001.SZ",
        dimension="businessOperation",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
