from unittest.mock import MagicMock

from user_provide_info import main


def test_main():
    main.main(MagicMock())
    assert True


def test_verify_telegram_data_string():
    # NO SMOKE TEST user_provide_info.main.verify_telegram_data_string
    hash_for_foo = '58e12c073b212a320f893933f1d62cbbef82c9df6a6a6d061a37a1a1c3ad861d'
    token = 'token'
    assert main.verify_telegram_data_string(f'foo&hash={hash_for_foo}', token) is True
    assert main.verify_telegram_data_string(f'bar&hash={hash_for_foo}', token) is False
