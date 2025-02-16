import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from urllib.parse import quote, urlencode

import pytest
from flask import Flask

from _dependencies.commons import TopicType
from src.user_provide_info.main import _get_searches_from_db, get_user_data_from_db
from tests.factories.db_factories import (
    ChangeLogFactory,
    GeoFolderFactory,
    GeoRegionFactory,
    SearchCoordinatesFactory,
    SearchFactory,
    SearchFirstPostFactory,
    SearchHealthCheckFactory,
    UserCoordinateFactory,
    UserFactory,
    UserPrefRadiusFactory,
    UserRegionalPreferenceFactory,
)
from user_provide_info import main


@pytest.fixture
def app() -> Flask:
    return Flask(__name__)


def test_verify_telegram_data_string():
    # NO SMOKE TEST user_provide_info.main.verify_telegram_data_string
    hash_for_foo = '58e12c073b212a320f893933f1d62cbbef82c9df6a6a6d061a37a1a1c3ad861d'
    token = 'token'
    assert main.verify_telegram_data_string(f'foo&hash={hash_for_foo}', token) is True
    assert main.verify_telegram_data_string(f'bar&hash={hash_for_foo}', token) is False


def test_main_cors(app: Flask):
    with app.test_request_context('/', method='OPTIONS') as app_request:
        resp, code, _ = main.main(app_request.request)
    assert code == 204


def test_main_query_str(app: Flask):
    """lock current behavior"""

    user_data = {
        'id': 1234567890,
        'first_name': 'some_name',
        'last_name': '',
        'username': 'some_name',
        'language_code': 'ru',
        'allows_write_to_pm': True,
        'photo_url': 'https:\\/\\/t.me\\/i\\/userpic\\/320\\/aa-bb-cc.svg',
    }
    query_dict = {
        'query_id': 'AAGaPjcFAwAAAJo-NwXzGddd',
        'user': str(user_data).replace("'", '"').replace(' ', ''),
        'auth_date': 1739639621,
        'signature': '-NKmZbtIMmvVNG_TWPKGwcxAyrEugx7ARhXMmNDIqsA18tr_xNjzC5EoEGTmOhbLtUDJ2lBgrOV78VzTRUR8CA',
        'hash': 'b798f5038b718cccadbda76830eb25f34328820b605b25e8bbdcecad5ac034ef',  # calculated in debug mode
    }
    query = urlencode(query_dict, quote_via=quote)
    with app.test_request_context('/', method='POST', json=query) as app_request:
        resp, code, headers = main.main(app_request.request)
    assert code == 200
    assert headers == {'Access-Control-Allow-Origin': 'https://storage.googleapis.com'}
    resp_json = json.loads(resp)
    assert resp_json == {
        'ok': True,
        'user_id': 1234567890,
        'params': {
            'curr_user': False,
            'home_lat': 55.752702,
            'home_lon': 37.622914,
            'radius': 100,
            'regions': [28, 29],
            'searches': [],
        },
    }


def test_main_validate_no_data(app: Flask):
    with (
        app.test_request_context('/', method='POST') as app_request,
        patch.object(main, 'verify_telegram_data', MagicMock(return_value=True)),
    ):
        resp, code, _ = main.main(app_request.request)
    assert code == 200
    resp_json = json.loads(resp)
    assert resp_json['ok'] is False
    assert resp_json['reason'] == 'No json/string received'


def test_main_validate_incorrect_signature(app: Flask):
    user_data = {
        'id': 1234567890,
        'first_name': 'some_name',
        'last_name': '',
        'username': 'some_name',
        'language_code': 'ru',
        'allows_write_to_pm': True,
        'photo_url': 'https:\\/\\/t.me\\/i\\/userpic\\/320\\/aa-bb-cc.svg',
    }
    query_dict = {
        'query_id': 'AAGaPjcFAwAAAJo-NwXzGddd',
        'user': str(user_data).replace("'", '"').replace(' ', ''),
    }
    query = urlencode(query_dict, quote_via=quote)
    with (
        app.test_request_context('/', method='POST', json=query) as app_request,
        patch.object(main, 'verify_telegram_data', MagicMock(return_value=False)),
    ):
        resp, code, headers = main.main(app_request.request)
    assert code == 200
    resp_json = json.loads(resp)
    assert resp_json['ok'] is False
    assert resp_json['reason'] == 'Provided json is not validated'


class TestGetUserDataFromDb:
    def test_get_user_data_from_db_valid_user(self):
        # Create user and related data using factories
        user = UserFactory.create_sync()
        user_id = user.user_id
        UserCoordinateFactory.create_sync(user_id=user_id, latitude='55.7558', longitude='37.6173')
        UserPrefRadiusFactory.create_sync(user_id=user_id, radius=50)
        region1 = UserRegionalPreferenceFactory.create_sync(user_id=user_id)

        geo_folder = GeoFolderFactory.create_sync(folder_id=region1.forum_folder_num)
        geo_region = GeoRegionFactory.create_sync(division_id=geo_folder.division_id)

        with (
            patch.object(main, 'time_counter_since_search_start', side_effect=[('1 day ago', 1), ('2 days ago', 2)]),
            patch.object(main, 'clean_up_content', return_value='Cleaned content'),
        ):
            result = get_user_data_from_db(user.user_id)

        assert result.model_dump() == {
            'curr_user': True,
            'user_id': user_id,
            'home_lat': 55.7558,
            'home_lon': 37.6173,
            'radius': 50,
            'regions': [geo_region.polygon_id],
            'searches': [],
        }

    def test_get_searches_from_db_registered_user(self, connection_psy):
        coords = [[54.1234, 55.1234]]
        user = UserFactory.create_sync()
        user_id = user.user_id
        folder = GeoFolderFactory.create_sync(folder_type='searches')
        UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=folder.folder_id)

        search = SearchFactory.create_sync(
            forum_folder_id=folder.folder_id,
            status='Active',
            topic_type_id=TopicType.search_patrol,
            city_locations=str(coords),
            search_start_time=datetime.now(),
        )
        search_first_post = SearchFirstPostFactory.create_sync(search_id=search.search_forum_num, actual=True)
        SearchCoordinatesFactory.create_sync(search_id=search.id)
        SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')
        ChangeLogFactory.create_sync(search_forum_num=search.search_forum_num)

        result = _get_searches_from_db(user_id, connection_psy, True)

        assert len(result) == 1
        first_item = result[0].model_dump()
        assert first_item['name'] == search.search_forum_num
        assert first_item['display_name'] == search.display_name
        assert first_item == {
            'name': search.search_forum_num,
            'coords': coords,
            'exact_coords': False,
            'content': search_first_post.content,
            'display_name': search.display_name,
            'freshness': 'Начинаем искать',
            'link': f'https://lizaalert.org/forum/viewtopic.php?t={search.search_forum_num}',
            'search_status': 'Active',
            'search_type': 'Особый поиск',
            'search_is_old': False,
        }
