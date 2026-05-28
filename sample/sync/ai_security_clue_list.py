from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.ai.security_clue_list(
        start_time="2026-05-01",
        end_time="2026-05-28",
        query_mode="bySecurity",
        size=5,
        gts_code="000001.SZ",
        source="research",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
