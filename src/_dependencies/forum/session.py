"""HTTP session for talking to the LA forum.

Single place for the forum proxy configuration: every scanner and parser that
talks to the forum gets the same session type and the same proxies
(``get_forum_proxies``), instead of each component keeping its own copy.
"""

from functools import lru_cache

import requests

from _dependencies.common.commons import get_forum_proxies


@lru_cache
def get_requests_session() -> requests.Session:
    """Forum HTTP session with the configured proxies applied."""
    session = requests.Session()
    session.proxies.update(get_forum_proxies())
    return session
