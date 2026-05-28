from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.quote.index_day_kline(
        security="000300.SH",
        start_date="2026-05-01",
        end_date="2026-05-28",
        limit=10,
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
