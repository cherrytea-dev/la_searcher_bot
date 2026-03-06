import datetime

import pytest
from polyfactory import Use
from sqlalchemy.engine.base import Connection

from api_get_active_searches import main
from tests.common import get_http_request
from tests.factories.db_factories import (
    GeoFolderFactory,
    SearchFactory,
    SearchFirstPostFactory,
    SearchHealthCheckFactory,
)


class ActiveSearchFactory(SearchFactory):
    search_start_time = Use(datetime.datetime.now)
    status = 'Active'


class TestMain:
    def test_main(self):
        request = get_http_request(method='POST', data={'app_id': 1})

        main.main(request)

        assert True

    def test_main_empty_json(self):
        request = get_http_request(method='POST', data={})

        resp = main.main(request)

        answer = main.FailResponse.model_validate_json(resp['body'])
        assert 'app_id' in answer.reason
        assert 'validation error' in answer.reason

    def test_main_no_json(self):
        request = {
            'body': 'not a json',
            'httpMethod': 'GET',
        }

        resp = main.main(request)

        answer = main.FailResponse.model_validate_json(resp['body'])
        assert 'Invalid JSON' in answer.reason

    def test_main_incorrect_app_id(self):
        request = get_http_request(method='POST', data={'app_id': 'unexisting'})

        resp = main.main(request)

        answer = main.FailResponse.model_validate_json(resp['body'])
        assert answer.reason == 'Incorrect app_id'

    def test_main_cors(self):
        request = get_http_request(method='OPTIONS')

        resp = main.main(request)

        assert resp['statusCode'] == 204


def test_get_searches_from_db(connection: Connection):
    folder1 = GeoFolderFactory.create_sync(folder_type='searches')
    search1 = ActiveSearchFactory.create_sync(forum_folder_id=folder1.folder_id)
    SearchHealthCheckFactory.create_sync(search_forum_num=search1.search_forum_num, status='ok')
    SearchFirstPostFactory.create_sync(search_id=search1.search_forum_num, actual=True)

    searches = main.get_list_of_active_searches_from_db(connection, main.UserRequest(app_id=1))
    assert searches  # TODO find correct params for db factory


def test_get_query_results_with_folders(connection: Connection):
    folder1, folder2 = GeoFolderFactory.create_batch_sync(2, folder_type='searches')

    search1 = ActiveSearchFactory.create_sync(forum_folder_id=folder1.folder_id)
    search2 = ActiveSearchFactory.create_sync(forum_folder_id=folder2.folder_id)

    SearchHealthCheckFactory.create_sync(search_forum_num=search1.search_forum_num, status='ok')
    SearchFirstPostFactory.create_sync(search_id=search1.search_forum_num, actual=True)

    SearchHealthCheckFactory.create_sync(search_forum_num=search2.search_forum_num, status='ok')
    SearchFirstPostFactory.create_sync(search_id=search2.search_forum_num, actual=True)

    depth_days = 30
    folders_list = [folder1.folder_id, folder2.folder_id]
    result = main.get_query_results(connection, depth_days, folders_list)

    # Assert that the result is a list of Search objects with the correct data
    assert len(result) == 2
    assert isinstance(result[0], main.Search)
    assert result[0].search_start_time == search1.search_start_time
    assert result[0].forum_folder_id == search1.forum_folder_id
    assert result[1].search_start_time == search2.search_start_time
    assert result[1].forum_folder_id == search2.forum_folder_id


def test_get_query_results_with_no_folders(connection: Connection):
    folder1 = GeoFolderFactory.create_sync(folder_type='searches')
    search1 = ActiveSearchFactory.create_sync(forum_folder_id=folder1.folder_id)
    SearchHealthCheckFactory.create_sync(search_forum_num=search1.search_forum_num, status='ok')
    SearchFirstPostFactory.create_sync(search_id=search1.search_forum_num, actual=True)

    depth_days = 30
    folders_list = []
    result = main.get_query_results(connection, depth_days, folders_list)

    assert result
    assert isinstance(result[0], main.Search)
