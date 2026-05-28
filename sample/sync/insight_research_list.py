from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.insight.research_list(
        size=5,
        min_pages=5,
        max_pages=50,
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
