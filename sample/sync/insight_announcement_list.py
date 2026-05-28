from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.insight.announcement_list(
        size=5,
        security="000001.SZ",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
