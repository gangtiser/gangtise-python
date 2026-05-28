from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.ai.viewpoint_debate(
        viewpoint="白酒行业估值修复具备持续性",
        wait=False,
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
