"""Local development script for running the MAX bot in long-polling mode.

Usage:
    ``uv run python tests/tools/run_max_bot.py``

This script:
1. Loads environment variables from ``.env`` (via ``get_dotenv_config``)
2. Patches the app config to use local env values
3. Starts the MAX bot in long-polling mode
"""

import logging

from tests.common import get_dotenv_config, setup_logging_to_console

if __name__ == '__main__':
    setup_logging_to_console()
    logging.info('Starting MAX bot in long-polling mode...')

    # Patch the app config to use local .env values
    from unittest.mock import patch

    from max_bot._utils.bot_polling import run_polling

    with patch('_dependencies.common.commons._get_config', get_dotenv_config):
        run_polling()
