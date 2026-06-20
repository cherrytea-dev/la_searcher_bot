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

import logging

import click
from dotenv import load_dotenv
from flask import Flask, request  # type:ignore[import-not-found]

from ._utils.bot_polling import run_polling
from ._utils.event_dispatcher import dispatch_event

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
            return dispatch_event(data)

        except Exception:
            logger.exception('Error processing VK callback')
            return 'ok'

    @app.get('/')
    def health() -> str:
        """Health check endpoint."""
        return 'VK Bot is running'

    logger.info('Starting Flask server on %s:%s', host, port)
    logger.info('VK Callback API endpoint: POST http://%s:%s/', host, port)
    logger.info('Use NGrok, localhost.run or cloudpub service to make public https endpoint')
    logger.info('Press Ctrl+C to stop.')

    app.run(host, port, debug=True)


@click.command()
@click.option(
    '--polling',
    is_flag=True,
    default=False,
    help='Run in LongPoll polling mode instead of Flask web server',
)
@click.option(
    '--port',
    type=int,
    default=8888,
    show_default=True,
    help='Port for Flask server',
)
@click.option(
    '--host',
    type=str,
    default='0.0.0.0',
    show_default=True,
    help='Host for Flask server',
)
def main(polling: bool, port: int, host: str) -> None:
    """VK Bot launcher — Flask web server or LongPoll polling mode."""
    load_dotenv()

    if polling:
        logger.info('Starting VK bot in LongPoll polling mode...')
        run_polling()
    else:
        run_flask(host=host, port=port)


if __name__ == '__main__':
    main()
