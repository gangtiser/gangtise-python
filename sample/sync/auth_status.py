from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def mask_sensitive(value):
    if isinstance(value, dict):
        return {key: mask_sensitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    if isinstance(value, str) and value:
        return "[redacted]"
    return value


def main():
    result = gangtise.auth.status()
    show_result(mask_sensitive(result), __file__)


if __name__ == "__main__":
    main()
