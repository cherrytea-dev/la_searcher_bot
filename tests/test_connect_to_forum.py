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
    # NO SMOKE TEST connect_to_forum.main.main
    user_name = 'testuser'
    data = (user_id, user_name)
    with (
        patch('connect_to_forum.main.session'),
        patch('connect_to_forum.main.login_into_forum'),
        patch('connect_to_forum.main.get_user_id', Mock(return_value=user_id)),
        patch('connect_to_forum.main.get_user_attributes', get_user_attributes_mocked),
    ):
        main.main(get_event_with_data(data), 'context')
