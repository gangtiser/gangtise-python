from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.quote.minute_kline(
        security="000001.SZ",
        start_time="2026-05-28 09:30:00",
        end_time="2026-05-28 15:00:00",
        limit=10,
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
