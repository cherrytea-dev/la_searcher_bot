"""HTTP session for talking to the LA forum.

Every scanner and parser that talks to the forum uses this one factory, so the
proxy configuration (``get_forum_proxies``) is defined once instead of in seven
copies. The login flow in ``connect_to_forum`` keeps its own session on purpose:
it carries the bot's cookie jar.

A ``requests.Session`` is not thread-safe and the app runs scanners on several
threads at once (cron thread plus queue workers), so the session is cached
per-thread rather than process-wide. Short-lived threads (one per cron tick)
therefore start with a fresh session and lose keep-alive across ticks — the price
of not sharing a cookie jar between threads.
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
