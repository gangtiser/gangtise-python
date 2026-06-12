import pytest

from gangtise_openapi._lookup import LOOKUP_LOADERS, get_lookup


def test_only_api_uncovered_lookup_keys_remain():
    # v0.16.0: research-areas/industries/regions/announcement-categories/
    # industry-codes/theme-ids retired in favour of reference.* APIs.
    assert set(LOOKUP_LOADERS.keys()) == {
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
    }


def test_each_loader_returns_non_empty_list():
    for key, data in LOOKUP_LOADERS.items():
        assert isinstance(data, list), key
        assert len(data) > 0, key
        assert isinstance(data[0], dict), key


def test_get_lookup_unknown():
    with pytest.raises(KeyError):
        get_lookup("nope")
