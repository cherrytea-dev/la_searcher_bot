#!/usr/bin/env python3
"""Apply the SQL migrations from ``doc/migrations`` that are still missing.

The single container (``python -m app.main``) needs a schema that matches the code. A production
database restored from an older dump can be missing objects the code relies on — the most painful
example is the partial unique index ``notif_by_user_unique_unsent_idx`` from migration 008:
without it ``compose_notifications`` fails on ``INSERT ... ON CONFLICT`` for every notification.

This script is **idempotent**: each migration is applied only when its target object is absent, so
running it twice is a no-op. Heavy/destructive migrations are opt-in (see the flags).

Usage:
    uv run python scripts/apply_db_migrations.py                       # safe set
    uv run python scripts/apply_db_migrations.py --dry-run             # only report
    uv run python scripts/apply_db_migrations.py --env-file .env.prod  # creds from a file
    uv run python scripts/apply_db_migrations.py --purge-search-first-posts-history
    uv run python scripts/apply_db_migrations.py --apply-data-policy

Credentials come from the environment (POSTGRES_HOST/PORT/USER/PASSWORD/DB), optionally overridden
by ``--env-file`` (dotenv format, ``override=True``).
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('apply_db_migrations')

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / 'doc' / 'migrations'

# 007 is heavy (deletes ~2M rows / ~6 GB). Only its index is applied by default; the DELETE is
# opt-in via --purge-search-first-posts-history.
_007_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_search_first_posts__history_timestamp
    ON search_first_posts__history (timestamp);
"""


def _migration(name: str) -> str:
    return (MIGRATIONS_DIR / name).read_text(encoding='utf-8')


def _to_regclass(cur: 'psycopg2.extensions.cursor', name: str) -> bool:
    cur.execute('SELECT to_regclass(%s) IS NOT NULL', (f'public.{name}',))
    row = cur.fetchone()
    return bool(row and row[0])


def _has_column(cur: 'psycopg2.extensions.cursor', table: str, column: str) -> bool:
    cur.execute(
        'SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s)',
        ('public', table, column),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def _split_statements(sql: str) -> list[str]:
    """Split a migration file into single statements (``--`` comments stripped).

    Needed because libpq runs a multi-statement string inside ONE implicit transaction:
    ``CREATE INDEX CONCURRENTLY`` there dies with "cannot run inside a transaction block" —
    exactly what happened to 008 on the first deploy of the container (the file is a DELETE
    followed by the CREATE INDEX, and the whole string went as one query). A single statement
    is not wrapped, so a migration containing CONCURRENTLY has to be sent statement by statement.
    """
    without_comments = '\n'.join(line.split('--', 1)[0] for line in sql.splitlines())
    return [statement.strip() for statement in without_comments.split(';') if statement.strip()]


def _run(cur: 'psycopg2.extensions.cursor', label: str, sql: str, dry_run: bool) -> None:
    if dry_run:
        log.info('[dry-run] would apply: %s', label)
        return
    log.info('applying: %s', label)
    statements = _split_statements(sql)
    if len(statements) < 2 or not any('CONCURRENTLY' in statement.upper() for statement in statements):
        # A single statement, or none of them is CONCURRENTLY: send the file as one query so the
        # statements stay in a single transaction (atomicity for multi-statement migrations).
        cur.execute(sql)
        return
    # CONCURRENTLY has to be alone in its transaction: send the statements one by one.
    for statement in statements:
        cur.execute(statement)


def main() -> None:
    parser = argparse.ArgumentParser(description='Apply missing DB migrations (idempotent).')
    parser.add_argument('--env-file', default=None, help='Optional dotenv file with DB credentials.')
    parser.add_argument('--dry-run', action='store_true', help='Only report what would be applied.')
    parser.add_argument(
        '--purge-search-first-posts-history',
        action='store_true',
        help='Also run the heavy DELETE from migration 007 (rows older than 30 days).',
    )
    parser.add_argument(
        '--apply-data-policy',
        action='store_true',
        help='Also run migration 010 (drop subscriptions to "searches finished" folders).',
    )
    args = parser.parse_args()

    if args.env_file:
        path = Path(args.env_file)
        if not path.exists():
            parser.error(f'env file not found: {path}')
        load_dotenv(path, override=True)
        log.info('loaded env file: %s', path)

    conn = psycopg2.connect(
        host=_env('POSTGRES_HOST', 'localhost'),
        port=int(_env('POSTGRES_PORT', '5432')),
        dbname=_env('POSTGRES_DB', 'postgres'),
        user=_env('POSTGRES_USER', 'postgres'),
        password=_env('POSTGRES_PASSWORD', ''),
    )
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute('SELECT current_database(), current_user, inet_server_addr()')
    info = cur.fetchone()
    db, user, addr = info if info is not None else ('?', '?', '?')
    log.info('connected to database "%s" as "%s" (%s)', db, user, addr)

    applied = 0

    # 001 — index for the comments duplicate check.
    if not _to_regclass(cur, 'idx_comments_global_num_search_forum_num'):
        _run(cur, '001 comments index', _migration('001_add_unique_constraint_comments.sql'), args.dry_run)
        applied += 1

    # 002/003 — remove the old notif_mailings schema (only if it is still around).
    if _to_regclass(cur, 'notif_mailings'):
        _run(cur, '002 notif_mailings columns', _migration('002_remove_stale_table_and_fields.sql'), args.dry_run)
        applied += 1
    if _has_column(cur, 'notif_by_user', 'mailing_id'):
        _run(cur, '003 drop notif_mailings', _migration('003_remove_notif_mailings_table.sql'), args.dry_run)
        applied += 1

    # 004/005 — identity map and messenger column.
    if not _to_regclass(cur, 'user_identity_map'):
        _run(cur, '004 user_identity_map', _migration('004_user_identity_map.sql'), args.dry_run)
        applied += 1
    if not _has_column(cur, 'notif_by_user', 'messenger'):
        _run(cur, '005 notif_by_user.messenger', _migration('005_notif_by_user_messenger.sql'), args.dry_run)
        applied += 1

    # 006 — drop unused tables / recreate dependent views.
    if _to_regclass(cur, 'feedback') or _to_regclass(cur, 'news') or _to_regclass(cur, 'old_dict_regions'):
        _run(cur, '006 drop unused tables', _migration('006_drop_unused_tables.sql'), args.dry_run)
        applied += 1

    # 007 — history TTL + index. The index always; the DELETE only when asked.
    if not _to_regclass(cur, 'idx_search_first_posts__history_timestamp'):
        _run(cur, '007 search_first_posts__history index', _007_INDEX_SQL, args.dry_run)
        applied += 1
    if args.purge_search_first_posts_history:
        _run(
            cur,
            '007 purge search_first_posts__history (>30d)',
            "DELETE FROM search_first_posts__history WHERE timestamp < NOW() - INTERVAL '30 days';",
            args.dry_run,
        )
        applied += 1

    # 008 — the critical partial unique index for compose_notifications.
    if not _to_regclass(cur, 'notif_by_user_unique_unsent_idx'):
        _run(cur, '008 notif_by_user unique index', _migration('008_notif_by_user_unique_constraint.sql'), args.dry_run)
        applied += 1

    # 009 — history archiving index.
    if not _to_regclass(cur, 'idx_notif_by_user__history_created_message_id'):
        _run(cur, '009 notif_by_user__history index', _migration('009_archive_notify_history_index.sql'), args.dry_run)
        applied += 1

    # 010 — data policy, opt-in.
    if args.apply_data_policy:
        _run(
            cur,
            '010 drop "searches finished" subscriptions',
            _migration('010_remove_finished_searches_subscriptions.sql'),
            args.dry_run,
        )
        applied += 1

    if args.dry_run:
        log.info('dry run: %d migration(s) would be applied', applied)
    else:
        log.info('done: %d migration(s) applied', applied)

    cur.close()
    conn.close()


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


if __name__ == '__main__':
    try:
        main()
    except psycopg2.Error as exc:
        log.error('database error: %s', exc)
        sys.exit(1)
