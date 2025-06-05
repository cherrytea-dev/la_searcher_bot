import datetime

import pytest
from flask import Flask
from polyfactory import Use

from _dependencies.commons import sql_connect_by_psycopg2
from api_get_active_searches import main
from tests.factories.db_factories import (
    GeoFolderFactory,
    SearchFactory,
    SearchFirstPostFactory,
    SearchHealthCheckFactory,
)


@pytest.fixture
def app() -> Flask:
    return Flask(__name__)


class ActiveSearchFactory(SearchFactory):
    search_start_time = Use(datetime.datetime.now)
    status = 'Active'


def test_main(app: Flask):
    with app.test_request_context('/', json={'app_id': 1}) as app_request:
        main.main(app_request.request)
    assert True


def test_main_empty_json(app: Flask):
    with app.test_request_context('/', json={}) as app_request:
        resp = main.main(app_request.request)
    answer = main.FailResponse.model_validate_json(resp.data)
    assert 'app_id' in answer.reason
    assert 'validation error' in answer.reason


def test_main_no_json(app: Flask):
    with app.test_request_context('/', data='not a json') as app_request:
        resp = main.main(app_request.request)
    answer = main.FailResponse.model_validate_json(resp.data)
    assert 'Invalid JSON' in answer.reason


def test_main_incorrect_app_id(app: Flask):
    with app.test_request_context('/', json={'app_id': 'unexisting'}) as app_request:
        resp = main.main(app_request.request)
    answer = main.FailResponse.model_validate_json(resp.data)
    assert answer.reason == 'Incorrect app_id'


def test_main_cors(app: Flask):
    with app.test_request_context('/', method='OPTIONS') as app_request:
        resp = main.main(app_request.request)
    assert resp.status_code == 204


def test_get_searches_from_db():
    folder1 = GeoFolderFactory.create_sync(folder_type='searches')
    search1 = ActiveSearchFactory.create_sync(forum_folder_id=folder1.folder_id)
    SearchHealthCheckFactory.create_sync(search_forum_num=search1.search_forum_num, status='ok')
    SearchFirstPostFactory.create_sync(search_id=search1.search_forum_num, actual=True)

    with sql_connect_by_psycopg2() as conn_psy:
        searches = main.get_list_of_active_searches_from_db(conn_psy, main.UserRequest(app_id=1))
    assert searches  # TODO find correct params for db factory


def test_get_query_results_with_folders():
    folder1, folder2 = GeoFolderFactory.create_batch_sync(2, folder_type='searches')

    search1 = ActiveSearchFactory.create_sync(forum_folder_id=folder1.folder_id)
    search2 = ActiveSearchFactory.create_sync(forum_folder_id=folder2.folder_id)

    SearchHealthCheckFactory.create_sync(search_forum_num=search1.search_forum_num, status='ok')
    SearchFirstPostFactory.create_sync(search_id=search1.search_forum_num, actual=True)

    SearchHealthCheckFactory.create_sync(search_forum_num=search2.search_forum_num, status='ok')
    SearchFirstPostFactory.create_sync(search_id=search2.search_forum_num, actual=True)

    depth_days = 30
    folders_list = [folder1.folder_id, folder2.folder_id]
    with sql_connect_by_psycopg2() as conn_psy:
        result = main.get_query_results(conn_psy, depth_days, folders_list)

    # Assert that the result is a list of Search objects with the correct data
    assert len(result) == 2
    assert isinstance(result[0], main.Search)
    assert result[0].search_start_time == search1.search_start_time
    assert result[0].forum_folder_id == search1.forum_folder_id
    assert result[1].search_start_time == search2.search_start_time
    assert result[1].forum_folder_id == search2.forum_folder_id


def test_get_query_results_with_no_folders():
    folder1 = GeoFolderFactory.create_sync(folder_type='searches')
    search1 = ActiveSearchFactory.create_sync(forum_folder_id=folder1.folder_id)
    SearchHealthCheckFactory.create_sync(search_forum_num=search1.search_forum_num, status='ok')
    SearchFirstPostFactory.create_sync(search_id=search1.search_forum_num, actual=True)

    depth_days = 30
    folders_list = []
    with sql_connect_by_psycopg2() as conn_psy:
        result = main.get_query_results(conn_psy, depth_days, folders_list)

    assert result
    assert isinstance(result[0], main.Search)
