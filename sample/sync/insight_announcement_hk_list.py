from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.insight.announcement_hk_list(
        size=5,
        security="00700.HK",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
