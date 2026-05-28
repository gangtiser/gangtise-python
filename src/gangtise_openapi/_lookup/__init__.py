from __future__ import annotations

from typing import Any

from gangtise_openapi._lookup.announcement_categories import ANNOUNCEMENT_CATEGORIES
from gangtise_openapi._lookup.broker_orgs import BROKER_ORGS
from gangtise_openapi._lookup.industries import INDUSTRIES
from gangtise_openapi._lookup.industry_codes import INDUSTRY_CODES
from gangtise_openapi._lookup.meeting_orgs import MEETING_ORGS
from gangtise_openapi._lookup.regions import REGIONS
from gangtise_openapi._lookup.research_areas import RESEARCH_AREAS
from gangtise_openapi._lookup.theme_ids import THEME_IDS

LOOKUP_LOADERS: dict[str, list[Any]] = {
    "lookup.research-areas.list": RESEARCH_AREAS,
    "lookup.broker-orgs.list": BROKER_ORGS,
    "lookup.meeting-orgs.list": MEETING_ORGS,
    "lookup.industries.list": INDUSTRIES,
    "lookup.regions.list": REGIONS,
    "lookup.announcement-categories.list": ANNOUNCEMENT_CATEGORIES,
    "lookup.industry-codes.list": INDUSTRY_CODES,
    "lookup.theme-ids.list": THEME_IDS,
}


def get_lookup(endpoint_key: str) -> list[Any]:
    try:
        return LOOKUP_LOADERS[endpoint_key]
    except KeyError as exc:
        raise KeyError(f"Unknown lookup endpoint: {endpoint_key}") from exc
