"""The Yandex geocoder must not be called when no API key is configured.

Without a key the request can only come back 403 (``InvalidKey``), so it is a pointless HTTP
round-trip per address. Both the current and the legacy geocoding modules must skip it.
"""

from types import SimpleNamespace

import pytest

from identify_updates_of_topics._legacy._utils import external_api as legacy_external_api
from identify_updates_of_topics._utils import external_api

ADDRESS = 'Екатеринбург, Ленина 1'


@pytest.fixture(params=[external_api, legacy_external_api], ids=['current', 'legacy'])
def yandex_api(request):
    return request.param


@pytest.mark.parametrize('api_key', ['', '   '])
def test_no_client_is_created_without_a_key(yandex_api, api_key, monkeypatch) -> None:
    """An empty (or blank) key means the client is never even constructed, let alone called."""

    monkeypatch.setattr(yandex_api, 'get_app_config', lambda: SimpleNamespace(yandex_api_key=api_key))
    created: list[str] = []
    monkeypatch.setattr(yandex_api, 'Client', lambda key: created.append(key))

    assert yandex_api.get_coordinates_from_address_by_yandex(ADDRESS) == (0.0, 0.0)
    assert created == []


def test_client_is_created_with_a_key(yandex_api, monkeypatch) -> None:
    """A configured key keeps the normal path intact: the request is made and coordinates returned."""

    monkeypatch.setattr(yandex_api, 'get_app_config', lambda: SimpleNamespace(yandex_api_key='a-real-key'))
    created: list[str] = []

    class FakeClient:
        def __init__(self, key: str) -> None:
            created.append(key)

        def coordinates(self, address: str) -> tuple[str, str]:
            return '60.6', '56.8'  # (longitude, latitude)

    monkeypatch.setattr(yandex_api, 'Client', FakeClient)

    # the module returns (latitude, longitude), i.e. the pair in the opposite order
    assert yandex_api.get_coordinates_from_address_by_yandex(ADDRESS) == (56.8, 60.6)
    assert created == ['a-real-key']
