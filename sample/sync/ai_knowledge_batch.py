from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.ai.knowledge_batch(
        query="贵州茅台",
        top=3,
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
