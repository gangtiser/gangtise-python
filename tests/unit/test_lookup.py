import pytest

from gangtise_openapi._lookup import LOOKUP_LOADERS, get_lookup


def test_all_eight_lookup_keys_present():
    assert set(LOOKUP_LOADERS.keys()) == {
        "lookup.research-areas.list",
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
        "lookup.industries.list",
        "lookup.regions.list",
        "lookup.announcement-categories.list",
        "lookup.industry-codes.list",
        "lookup.theme-ids.list",
    }


def test_each_loader_returns_non_empty_list():
    for key, data in LOOKUP_LOADERS.items():
        assert isinstance(data, list), key
        assert len(data) > 0, key
        assert isinstance(data[0], dict), key


def test_get_lookup_unknown():
    with pytest.raises(KeyError):
        get_lookup("nope")
