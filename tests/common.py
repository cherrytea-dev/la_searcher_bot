import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Config:
    bot_api_token: str
    my_telegram_id: str


def emulated_get_secrets(secret_name: str) -> str:
    """Temporary replacement for def get_secrets() in tests"""
    if secret_name == 'bot_api_token':
        return get_config().bot_api_token
    elif secret_name == 'my_telegram_id':
        return get_config().my_telegram_id
    else:
        raise NotImplementedError(f'Unknown secret {secret_name}')


@lru_cache
def get_config() -> Config:
    return Config(
        bot_api_token=os.getenv('TG_BOT_TOKEN'),
        my_telegram_id=os.getenv('ADMIN_USER_ID'),
    )
