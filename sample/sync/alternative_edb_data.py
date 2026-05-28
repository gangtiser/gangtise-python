from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    indicators = gangtise.alternative.edb_search(keyword="空调", limit=1)
    if indicators.empty:
        raise SystemExit("No EDB indicator found for keyword '空调'.")
    indicator_id = str(indicators.iloc[0].get("indicatorId") or indicators.iloc[0].get("id"))
    result = gangtise.alternative.edb_data(
        indicator_id=indicator_id,
        start_date="2026-01-01",
        end_date="2026-05-28",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
