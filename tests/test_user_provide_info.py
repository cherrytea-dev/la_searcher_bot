import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from urllib.parse import quote, urlencode

import pytest

from _dependencies.commons import TopicType
from tests.common import get_http_request
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


def test_verify_telegram_data_string():
    hash_for_foo = '58e12c073b212a320f893933f1d62cbbef82c9df6a6a6d061a37a1a1c3ad861d'
    token = 'token'
    assert main.verify_telegram_data_string(f'foo&hash={hash_for_foo}', token) is True
    assert main.verify_telegram_data_string(f'bar&hash={hash_for_foo}', token) is False


class TestMain:
    def test_main_cors(self):
        request = get_http_request(method='OPTIONS')

        resp = main.main(request)

        assert resp['statusCode'] == 204

    def test_main_query_str(self):
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
            'hash': '4d7e3fae1f4ea4df602d2601fb0d9e2c4d15005bb432e3d4180e0fccfbd402fb',  # calculated in debug mode
        }
        query = urlencode(query_dict, quote_via=quote)
        request = get_http_request(method='POST', data=query)

        resp = main.main(request)

        assert resp['statusCode'] == 200
        assert resp['headers']['Access-Control-Allow-Origin'] == 'https://storage.googleapis.com'
        assert json.loads(resp['body']) == {
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

    def test_main_validate_no_data(self):
        request = get_http_request(method='POST')

        with patch.object(main, 'verify_telegram_data', MagicMock(return_value=True)):
            resp = main.main(request)

        assert resp['statusCode'] == 200
        resp_data = json.loads(resp['body'])
        assert resp_data['ok'] is False
        assert resp_data['reason'] == 'No json/string received'

    def test_main_validate_incorrect_signature(self):
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
        request = get_http_request(method='POST', data=query)

        with patch.object(main, 'verify_telegram_data', MagicMock(return_value=False)):
            resp = main.main(request)

        assert resp['statusCode'] == 200
        resp_data = json.loads(resp['body'])
        assert resp_data['ok'] is False
        assert resp_data['reason'] == 'Provided json is not validated'


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
            result = main.get_user_data_from_db(user.user_id)

        assert result.model_dump() == {
            'curr_user': True,
            'user_id': user_id,
            'home_lat': 55.7558,
            'home_lon': 37.6173,
            'radius': 50,
            'regions': [geo_region.polygon_id],
            'searches': [],
        }

    def test_get_searches_from_db_registered_user(self, connection):
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

        result = main._get_searches_from_db(user_id, connection, True)

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

    def test_get_user_data_from_db_valid_user_without_radius(self):
        # Create user and related data using factories
        # ToDo Make this test stable, now it fails sometimes
        user = UserFactory.create_sync()
        user_id = user.user_id
        UserCoordinateFactory.create_sync(user_id=user_id, latitude='55.7558', longitude='37.6173')
        region1 = UserRegionalPreferenceFactory.create_sync(user_id=user_id)

        geo_folder = GeoFolderFactory.create_sync(folder_id=region1.forum_folder_num)
        geo_region = GeoRegionFactory.create_sync(division_id=geo_folder.division_id)

        with (
            patch.object(main, 'time_counter_since_search_start', side_effect=[('1 day ago', 1), ('2 days ago', 2)]),
            patch.object(main, 'clean_up_content', return_value='Cleaned content'),
        ):
            result = main.get_user_data_from_db(user.user_id)

        assert result.model_dump() == {
            'curr_user': True,
            'user_id': user_id,
            'home_lat': 55.7558,
            'home_lon': 37.6173,
            'radius': None,
            'regions': [geo_region.polygon_id],
            'searches': [],
        }


def test_evaluate_city_locations_success():
    res = main.evaluate_city_locations('[[56.0, 64.0]]')
    assert res == [[56.0, 64.0]]


@pytest.mark.parametrize(
    'param',
    [
        [],
        [1],
        [None],
        '"foo"',
        '',
    ],
)
def test_evaluate_city_locations_fail(param):
    res = main.evaluate_city_locations(str(param))
    assert res is None
