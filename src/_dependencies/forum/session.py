"""HTTP session for talking to the LA forum.

Single place for the forum proxy configuration: every scanner and parser that
talks to the forum gets the same session type and the same proxies
(``get_forum_proxies``), instead of each component keeping its own copy.

A ``requests.Session`` is not thread-safe and the app runs scanners on several
threads at once (cron thread plus queue workers), so the session is cached
per-thread rather than process-wide.
"""

import threading

import requests

from _dependencies.common.commons import get_forum_proxies

_local = threading.local()


def get_requests_session() -> requests.Session:
    """Forum HTTP session with the configured proxies applied (one per thread)."""
    session = getattr(_local, 'session', None)
    if session is None:
        session = requests.Session()
        session.proxies.update(get_forum_proxies())
        _local.session = session
    return session
