from datetime import datetime
from unittest.mock import MagicMock

from manage_users import main


def test_main():
    # NO SMOKE TEST manage_users.main.main
    main.main(MagicMock(), 'context')
    assert True


def test_save_updated_status_for_user():
    # NO SMOKE TEST manage_users.main.save_updated_status_for_user
    res = main.save_updated_status_for_user('block_user', 1, datetime.now())
