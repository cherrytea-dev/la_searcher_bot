"""Utility functions for send_notifications — pure helpers, no side effects."""

import ast
import datetime
import re
from typing import Any

from send_notifications._utils.database import MessageToSend

FUNC_NAME = 'send_notifications'

SCRIPT_SOFT_TIMEOUT_SECONDS = 40  # after which iterations should stop to prevent the whole script timeout
INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS = 50  # window within which we check for started parallel function
SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS = 5
WORKERS_COUNT = 2

USE_VK_API = True  # feature-flag


def _prepare_message(message_to_send: MessageToSend) -> tuple[str, dict[str, Any]]:
    """Truncate long content and parse message_params from string."""
    message_content = message_to_send.message_content
    message_params_str = message_to_send.message_params

    # limitation to avoid telegram "message too long"
    if message_content and len(message_content) > 3000:
        message_content = f'{message_content[:1500]}...{message_content[-1000:]}'

    message_params: dict[str, Any] = ast.literal_eval(message_params_str) if message_params_str else {}
    if message_params:
        # convert string to bool
        if 'disable_web_page_preview' in message_params:
            message_params['disable_web_page_preview'] = message_params['disable_web_page_preview'] == 'True'

    return message_content, message_params


def seconds_between(datetime1: datetime.datetime, datetime2: datetime.datetime | None = None) -> float:
    delta = datetime1 - (datetime2 or datetime.datetime.now())
    return abs(delta.total_seconds())


def seconds_between_round_2(datetime1: datetime.datetime, datetime2: datetime.datetime | None = None) -> float:
    return round(seconds_between(datetime1, datetime2), 2)


def time_is_out(start: datetime.datetime) -> bool:
    # check if not too much time passed from start to now
    delta = datetime.datetime.now() - start
    return delta.total_seconds() > SCRIPT_SOFT_TIMEOUT_SECONDS


def format_mesage_for_vk(message: str) -> str:
    """Clean HTML for VK messages (preserved typo for backward compatibility)."""
    # Handle different types of <a> tags based on their href
    # Pattern to match <a href="URL">text</a>
    a_tag_pattern = re.compile(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>')

    def replace_a_tag(match: re.Match) -> str:
        url = match.group(1)
        text = match.group(2)

        # Rule 1: For links starting with https://lizaalert.org/forum/memberlist.php
        # Remove the link but keep the text
        if url.startswith('https://lizaalert.org/forum/memberlist.php'):
            return text

        # Rule 2: For links starting with https://lizaalert.org/forum/viewtopic.php and containing "start" in query
        # Remove the link but keep the text
        if url.startswith('https://lizaalert.org/forum/viewtopic.php') and 'start=' in url:
            return text

        # Rule 3: For phone number links (tel:)
        # Remove the link but keep the text
        if url.startswith('tel:'):
            return text

        # Rule 4: For other links (including lizaalert.org/forum/viewtopic.php without start),
        # unfold the link: show URL followed by text
        return f'{url} {text}'

    # Replace all <a> tags
    result = a_tag_pattern.sub(replace_a_tag, message)

    # Remove any remaining HTML tags (including self-closing tags)
    # Pattern matches < followed by any characters (non-greedy) up to >
    html_tag_pattern = re.compile(r'<[^>]+>')
    result = html_tag_pattern.sub('', result)

    return result
