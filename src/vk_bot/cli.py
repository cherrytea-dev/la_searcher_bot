"""CLI entry points for the VK bot.

Supports two modes:
1. Flask web server (default) — receives VK Callback API events via HTTP POST.
   Use with ngrok/localhost.run to expose locally.
2. LongPoll polling mode — uses VK LongPoll API (legacy, for testing without webhook).

Usage:
    uv run python -m src.vk_bot.cli                    # Flask server (default)
    uv run python -m src.vk_bot.cli --polling           # LongPoll mode
    uv run python -m src.vk_bot.cli --port 9999         # Custom port for Flask
"""

import argparse
import logging
import sys

from dotenv import load_dotenv

from ._utils.bot_polling import run_polling
from .main import main_raw

logger = logging.getLogger(__name__)


def run_flask(host: str = '0.0.0.0', port: int = 8888) -> None:
    """Run a local Flask web server for VK Callback API.

    VK sends POST requests to the Callback API URL with JSON body:
        {"type": "confirmation", "group_id": ...}
        {"type": "message_new", "object": {"message": {...}}}
        {"type": "message_event", "object": {...}}

    The server parses the JSON, delegates to main_raw(), and returns
    the response (e.g. confirmation code or 'ok').

    Args:
        host: Host to bind to (default: 0.0.0.0).
        port: Port to listen on (default: 8888).
    """
    from flask import Flask, request  # type:ignore[import-not-found]

    app = Flask(__name__)

    @app.post('/')
    def vk_callback() -> str:
        """Handle incoming VK Callback API POST request."""
        try:
            data = request.get_json(silent=True)
            if data is None:
                logger.error('Received non-JSON request body')
                return 'ok'

            logger.debug('VK callback: %s', data.get('type', 'unknown'))
            return main_raw(data)

        except Exception:
            logger.exception('Error processing VK callback')
            return 'ok'

    @app.get('/')
    def health() -> str:
        """Health check endpoint."""
        return 'VK Bot is running'

    logger.info('Starting Flask server on %s:%s', host, port)
    logger.info('VK Callback API endpoint: POST http://%s:%s/', host, port)
    logger.info('')
    logger.info('To expose to the internet, use:')
    logger.info('  ssh -R 80:localhost:%s localhost.run', port)
    logger.info('  # or')
    logger.info('  ngrok http %s', port)
    logger.info('')
    logger.info('Then set this URL as VK Callback API in VK App settings.')
    logger.info('Press Ctrl+C to stop.')

    app.run(host, port, debug=True)


def main() -> None:
    """Parse CLI args and run the appropriate mode."""
    load_dotenv()

    parser = argparse.ArgumentParser(description='VK Bot launcher')
    parser.add_argument(
        '--polling',
        action='store_true',
        help='Run in LongPoll polling mode instead of Flask web server',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8888,
        help='Port for Flask server (default: 8888)',
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host for Flask server (default: 0.0.0.0)',
    )
    args = parser.parse_args()

    if args.polling:
        logger.info('Starting VK bot in LongPoll polling mode...')
        run_polling()
    else:
        run_flask(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
