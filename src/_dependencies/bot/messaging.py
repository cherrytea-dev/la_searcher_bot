"""Telegram API client factories — cached main and service account instances.

Extracted from ``_dependencies.common.misc`` to keep the ``common`` package
free of messenger-specific dependencies.
"""

from functools import lru_cache

from _dependencies.bot.telegram_api_wrapper import TGApiBase
from _dependencies.common.commons import get_app_config


@lru_cache
def tg_api_service_account() -> TGApiBase:
    config = get_app_config()
    return TGApiBase(token=config.bot_api_token, host=config.bot_api_host)


@lru_cache
def tg_api_main_account() -> TGApiBase:
    config = get_app_config()
    return TGApiBase(token=config.bot_api_token__prod, host=config.bot_api_host)
