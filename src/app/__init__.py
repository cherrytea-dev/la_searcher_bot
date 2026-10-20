"""Single-container runtime for la_searcher_bot.

See ``doc/single-container.md``: one process that replaces the ~18 Yandex Cloud Functions —
HTTP endpoints, a cron scheduler, queue workers on top of PostgreSQL, and long-polling bots.
"""
