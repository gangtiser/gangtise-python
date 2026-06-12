from __future__ import annotations

from typing import Any

from gangtise_openapi._lookup.broker_orgs import BROKER_ORGS
from gangtise_openapi._lookup.meeting_orgs import MEETING_ORGS

LOOKUP_LOADERS: dict[str, list[Any]] = {
    "lookup.broker-orgs.list": BROKER_ORGS,
    "lookup.meeting-orgs.list": MEETING_ORGS,
}


def get_lookup(endpoint_key: str) -> list[Any]:
    try:
        return LOOKUP_LOADERS[endpoint_key]
    except KeyError as exc:
        raise KeyError(f"Unknown lookup endpoint: {endpoint_key}") from exc
