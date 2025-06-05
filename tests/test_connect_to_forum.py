from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from bs4 import BeautifulSoup

from connect_to_forum import main
from tests.common import get_event_with_data


def get_user_attributes_mocked(user_id: str):
    """get user data from forum"""

    content = Path('tests/fixtures/forum_user_info.html').read_text()
    soup = BeautifulSoup(content, features='html.parser')
    block_with_user_attr = soup.find('div', {'class': 'page-body'})

    return block_with_user_attr


@pytest.mark.parametrize(
    'user_id',
    [
        0,  # not found
        123,  # found
    ],
)
def test_main(user_id: int):
    # TODO check if message to user was sent
    user_name = 'testuser'
    data = (user_id, user_name)
    with (
        patch('connect_to_forum.main.get_session'),
        patch('connect_to_forum.main.login_into_forum'),
        patch('connect_to_forum.main.get_user_id', Mock(return_value=user_id)),
        patch('connect_to_forum.main.get_user_attributes', get_user_attributes_mocked),
    ):
        main.main(get_event_with_data(data), 'context')


@pytest.fixture
def patch_http():
    # bypass http patching in this tests
    pass


@pytest.mark.skip(reason='manual testing')
def test_get_user_id(patch_http):
    login = 'Admin'

    main.login_into_forum()
    user_id = main.get_user_id(login)
    assert user_id

    user_attrs = main.get_user_attributes(user_id)
    assert user_attrs

    user_data = main.get_user_data(user_attrs)
    assert user_data.reg_date
