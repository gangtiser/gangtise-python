from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    result = gangtise.lookup.broker_orgs()
    show_result(result, __file__)


if __name__ == "__main__":
    main()
