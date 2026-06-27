"""CLI entry point for the MAX bot.

Supports long-polling mode for local development.

Usage:
    ``uv run python -m src.max_bot.cli --polling``
"""

import logging

import click
from dotenv import load_dotenv

from ._utils.bot_polling import run_polling

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    '--polling',
    is_flag=True,
    default=True,
    help='Run in long-polling mode (default: True)',
)
def main(polling: bool) -> None:
    """MAX Bot launcher — long-polling mode."""
    load_dotenv()

    if polling:
        logger.info('Starting MAX bot in long-polling mode...')
        run_polling()
    else:
        logger.info('Webhook mode not yet implemented. Use --polling.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
