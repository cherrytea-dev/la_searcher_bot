import datetime
from unittest.mock import Mock, patch

import pytest
import requests
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from _dependencies.commons import sqlalchemy_get_pool
from identify_updates_of_first_posts import main
from src.identify_updates_of_first_posts.main import (
    process_first_page_comparison,
    split_text_to_deleted_and_regular_parts,
)
from tests.common import get_event_with_data
from tests.factories import db_factories


@pytest.fixture(autouse=True)
def patch_http():
    # disable http patching
    pass


def test_main():
    # TODO paste some posts in db
    main.main(get_event_with_data('[1,2]'), 'context')
    assert True


def test_compose_diff_message():
    current = ['line1', 'line2']
    previous = ['line1', 'line3']
    message = main.compose_diff_message(current, previous)
    assert message.message == 'Удалено:\n<s>line3\n</s>\nДобавлено:\nline2\n'
    assert message.deletions == ['line3']
    assert message.additions == ['line2']


class TestSplitText:
    def test_split_text_with_deleted_and_regular_parts(self):
        input_text = """
        <p>This is <span style="text-decoration:line-through">deleted text</span> and this is regular text.</p>
        """
        deleted, regular = split_text_to_deleted_and_regular_parts(input_text)
        assert deleted == 'deleted text'

    def test_split_text_with_only_regular_text(self):
        input_text = '<p>This is only regular text.</p>'
        deleted, regular = split_text_to_deleted_and_regular_parts(input_text)
        assert deleted == ''

    def test_split_text_with_multiple_deleted_parts(self):
        input_text = """
        <p>This is <span style="text-decoration:line-through">deleted text 1</span> and 
        <span style="text-decoration:line-through">deleted text 2</span> with some regular text.</p>
        """
        deleted, regular = split_text_to_deleted_and_regular_parts(input_text)
        assert 'deleted text 1' in deleted
        assert 'deleted text 2' in deleted


@pytest.fixture
def connection() -> Connection:
    pool = sqlalchemy_get_pool(10, 10)
    with pool.connect() as conn:
        yield conn


@pytest.fixture
def session() -> Session:
    with db_factories.get_session() as session:
        yield session


class TestProcessFirstPageComparison:
    def test_process_first_page_comparison_no_changes(self, connection):
        # Create a search using SearchFactory
        search = db_factories.SearchFactory.create_sync(
            display_name='Test Name', status='Ищем', family_name='Family Name', age=30
        )

        first_page_content_prev = '<p>Ищем человека</p>'
        first_page_content_curr = '<p>Ищем человека</p>'

        changes = process_first_page_comparison(
            connection, search.search_forum_num, first_page_content_prev, first_page_content_curr
        )

        assert not changes.message
        assert not changes.additions
        assert not changes.deletions

    def test_process_first_page_comparison_with_changes(self, connection):
        search = db_factories.SearchFactory.create_sync(
            display_name='Test Name', status='Ищем', family_name='Family Name', age=30
        )

        first_page_content_prev = '<p>Ищем человека</p>'
        first_page_content_curr = '<p>Ищем человека. Найден жив.</p>'

        changes = process_first_page_comparison(
            connection, search.search_forum_num, first_page_content_prev, first_page_content_curr
        )

        assert changes is not None
        assert 'Добавлено:' in changes.message
        assert 'Найден жив.' in changes.additions[0]

    def test_process_first_page_comparison_search_finished(self, connection):
        search = db_factories.SearchFactory.create_sync(
            display_name='Test Name', status='Завершен', family_name='Family Name', age=30
        )
        first_page_content_prev = '<p>Ищем человека</p>'
        first_page_content_curr = '<p>Ищем человека. Найден жив.</p>'

        changes = process_first_page_comparison(
            connection, search.search_forum_num, first_page_content_prev, first_page_content_curr
        )

        assert changes is None


def test_empty_list_of_updated_searches():
    with patch('identify_updates_of_first_posts.main.process_pubsub_message', return_value=[]):
        assert main.main({}, {}) == 'ok'


def test_multiple_updated_searches():
    with (
        # patch('identify_updates_of_first_posts.main.process_pubsub_message', return_value=[123, 456]),
        patch('identify_updates_of_first_posts.main.sql_connect'),
        patch('identify_updates_of_first_posts.main.get_compressed_first_post'),
        patch('identify_updates_of_first_posts.main.process_first_page_comparison'),
        patch('identify_updates_of_first_posts.main.save_new_record_into_change_log'),
        patch('identify_updates_of_first_posts.main.parse_search_folder_num'),
        patch('identify_updates_of_first_posts.main.save_function_into_register'),
    ):
        assert main.main(get_event_with_data('[1,2]'), {}) == 'ok'


class TestParseSearchFolder:
    @pytest.fixture(scope='class')
    def mock_response(self):
        with patch.object(requests.Session, 'get') as mock_get:
            yield mock_get

    def test_parse_search_folder(self, mock_response):
        mock_response.return_value.content = (
            b'<html><body><span class="crumb" data-forum-id="123"></span></body></html>'
        )
        assert main.parse_search_folder_num(777) == 123

    def test_parse_search_folder_no_folder(self, mock_response):
        mock_response.return_value.content = b'<html><body></body></html>'
        assert main.parse_search_folder_num(777) is None

    def test_parse_search_folder_invalid_folder(self, mock_response):
        mock_response.return_value.content = (
            b'<html><body><span class="crumb" data-forum-id="abc"></span></body></html>'
        )
        assert main.parse_search_folder_num(777) is None


class TestCompressedFirstPost:
    def test_get_compressed_first_post(self):
        initial_text = '<html><body><p>This is a test string.</p></body></html>'
        expected_output = 'This is a test string.\n'
        assert main.get_compressed_first_post(initial_text) == expected_output

    def test_get_compressed_first_post_empty_string(self):
        initial_text = ''
        expected_output = ''
        assert main.get_compressed_first_post(initial_text) == expected_output

    def test_get_compressed_first_post_long_string(self):
        initial_text = (
            '<html><body><p>This is a very long test string that should be split into multiple lines.</p></body></html>'
        )
        expected_output = 'This is a very long test string that should be spl\nit into multiple lines.\n'
        fact_out = main.get_compressed_first_post(initial_text)
        assert fact_out == expected_output


class TestProcessOneUpdate:
    def test__process_one_update(self, connection):
        prev_search_first_post = db_factories.SearchFirstPostFactory.create_sync(
            actual=False, timestamp=datetime.datetime.now()
        )
        search_first_post = db_factories.SearchFirstPostFactory.create_sync(
            actual=True, timestamp=datetime.datetime.now(), search_id=prev_search_first_post.search_id
        )
        search = db_factories.SearchFactory.create_sync(
            search_forum_num=prev_search_first_post.search_id, status='Ищем'
        )
        change_log_ids = []

        with patch.object(main, 'parse_search_folder_num', Mock(return_value=1)):
            res = main._process_one_update(
                change_log_ids,
                connection,
                search_first_post.search_id,
            )

        assert len(change_log_ids) == 1


def test__process_folders_with_updated_searches(connection):
    mocked_context = Mock()
    mocked_context.event_id = 1
    with patch.object(main, 'parse_search_folder_num', Mock(return_value=1)):
        main._process_folders_with_updated_searches(
            context=mocked_context,
            function_id=5,
            analytics_func_start=datetime.datetime.now(),
            list_of_updated_searches=[1, 2],
            change_log_ids=[1, 2],
            conn=connection,
        )


def test__get_actual_and_previous_page_content(connection):
    prev_search_first_post = db_factories.SearchFirstPostFactory.create_sync(
        actual=False, timestamp=datetime.datetime.now()
    )
    search_first_post = db_factories.SearchFirstPostFactory.create_sync(
        actual=True, timestamp=datetime.datetime.now(), search_id=prev_search_first_post.search_id
    )
    db_factories.SearchFactory.create_sync(search_forum_num=prev_search_first_post.search_id, status='Ищем')

    actual, prev = main._get_actual_and_previous_page_content(
        search_id=prev_search_first_post.search_id,
        conn=connection,
    )
    assert prev == prev_search_first_post.content
    assert actual == search_first_post.content
