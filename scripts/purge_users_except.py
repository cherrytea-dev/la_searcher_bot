#!/usr/bin/env python3
"""Delete every user's data except one — for experimenting on a copy of the production DB.

The script walks every ``public`` table that carries a user key (``user_id``, or
``internal_user_id`` for the tables that only have that one), reports what it would remove and —
with ``--apply`` — deletes it inside a single transaction. ``users`` is cleaned up last, because
``user_pref_search_whitelist.user_id`` has a foreign key to it.

It is **dry-run by default**: nothing is deleted until ``--apply`` is passed. The user to keep
must exist in ``users``, otherwise the script refuses to run — a typo in the id must never wipe
the database.

Rows whose user key is NULL belong to no user: they go away together with the other users, unless
``--keep-null-user-rows`` is passed.

Usage:
    uv run python scripts/purge_users_except.py --keep-user-id 196282174            # dry run
    uv run python scripts/purge_users_except.py --keep-user-id 196282174 --apply    # for real
    uv run python scripts/purge_users_except.py --keep-internal-user-id 42 --apply
    uv run python scripts/purge_users_except.py --keep-user-id 196282174 --apply --env-file .env.temp
"""

import argparse
import logging
import sys
from pathlib import Path

import sqlalchemy
from dotenv import load_dotenv

# Add src/ to sys.path so we can import project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from _dependencies.common.commons import sqlalchemy_get_pool

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# The last table to clean up: ``user_pref_search_whitelist.user_id`` references ``users.user_id``.
FK_TARGET = 'users'


def _discover_tables(conn: sqlalchemy.engine.Connection) -> list[tuple[str, str]]:
    """``(table, key column)`` for every user-keyed table, with ``users`` last."""
    rows = conn.execute(
        sqlalchemy.text("""
            SELECT c.table_name, c.column_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
              AND c.column_name IN ('user_id', 'internal_user_id')
            ORDER BY c.table_name, c.column_name
        """)
    ).fetchall()

    columns: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        columns.setdefault(table_name, set()).add(column_name)

    ordered = sorted(table for table in columns if table != FK_TARGET)
    if FK_TARGET in columns:
        ordered.append(FK_TARGET)

    # ``user_id`` is the identity most tables are keyed by; ``internal_user_id`` is the fallback
    # for the tables that only carry that one (``user_identity_map``).
    return [(table, 'user_id' if 'user_id' in columns[table] else 'internal_user_id') for table in ordered]


def _resolve_keep_user(
    conn: sqlalchemy.engine.Connection, user_id: int | None, internal_user_id: int | None
) -> sqlalchemy.engine.Row | None:
    """Look the user up in ``users`` so the script knows both of their ids."""
    if user_id is not None:
        query = sqlalchemy.text('SELECT user_id, internal_user_id, username_telegram FROM users WHERE user_id = :v')
        return conn.execute(query, {'v': user_id}).fetchone()
    query = sqlalchemy.text(
        'SELECT user_id, internal_user_id, username_telegram FROM users WHERE internal_user_id = :v'
    )
    return conn.execute(query, {'v': internal_user_id}).fetchone()


def _predicate(column: str, keep: int | None, keep_null_rows: bool) -> tuple[str, dict[str, int]]:
    """The WHERE clause matching the rows to delete for one table."""
    if keep is None:
        # The kept user has no value in this column, so every non-NULL row belongs to somebody else.
        return f'"{column}" IS NOT NULL', {}
    if keep_null_rows:
        return f'"{column}" IS NOT NULL AND "{column}" <> :keep', {'keep': keep}
    return f'"{column}" IS DISTINCT FROM :keep', {'keep': keep}


def _plan(
    conn: sqlalchemy.engine.Connection,
    tables: list[tuple[str, str]],
    keep_user_id: int | None,
    keep_internal_user_id: int | None,
    keep_null_rows: bool,
) -> list[tuple[str, str, str, dict[str, int], int, int]]:
    """Per table: the WHERE clause, the count of rows to delete and the count of NULL-key rows."""
    plan = []
    for table, column in tables:
        keep = keep_user_id if column == 'user_id' else keep_internal_user_id
        where, params = _predicate(column, keep, keep_null_rows)
        to_delete = conn.execute(sqlalchemy.text(f'SELECT count(*) FROM "{table}" WHERE {where}'), params).scalar()
        nulls = conn.execute(sqlalchemy.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL')).scalar()
        plan.append((table, column, where, params, int(to_delete), int(nulls)))
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete every user's data except one (dry run by default).")
    parser.add_argument('--keep-user-id', type=int, default=None, help='Telegram user_id of the user to keep.')
    parser.add_argument('--keep-internal-user-id', type=int, default=None, help='internal_user_id to keep.')
    parser.add_argument('--apply', action='store_true', help='Actually delete. Without it the script only reports.')
    parser.add_argument(
        '--keep-null-user-rows',
        action='store_true',
        help='Leave rows whose user key is NULL (they belong to no user).',
    )
    parser.add_argument('--env-file', default='.env.test', help='Path to the .env file with DB credentials.')
    args = parser.parse_args()

    if args.keep_user_id is None and args.keep_internal_user_id is None:
        parser.error('pass --keep-user-id or --keep-internal-user-id')

    env_path = Path(__file__).resolve().parent.parent / args.env_file
    if env_path.exists():
        load_dotenv(env_path, override=True)
        log.info(f'Loaded env file: {env_path}')
    else:
        log.warning(f'Env file not found: {env_path}. Relying on existing env vars.')

    pool = sqlalchemy_get_pool()
    with pool.connect() as conn:
        trans = conn.begin()
        try:
            db_name, db_user, db_addr = conn.execute(
                sqlalchemy.text('SELECT current_database(), current_user, inet_server_addr()')
            ).fetchone()  # type: ignore[misc]
            log.info(f'Connected to database "{db_name}" as "{db_user}" ({db_addr})')

            keep_row = _resolve_keep_user(conn, args.keep_user_id, args.keep_internal_user_id)
            if keep_row is None:
                log.error('The user to keep is not in "users" — refusing to run (a wrong id must not wipe the DB).')
                trans.rollback()
                sys.exit(2)

            keep_user_id, keep_internal_user_id = keep_row[0], keep_row[1]
            log.info(
                f'Keeping user_id={keep_user_id} internal_user_id={keep_internal_user_id} username={keep_row[2]!r}'
            )
            if keep_user_id is None:
                log.warning('The kept user has no user_id (VK-only?) — user_id-keyed tables will be emptied.')
            if keep_internal_user_id is None:
                log.warning('The kept user has no internal_user_id — internal_user_id-keyed tables will be emptied.')

            users_before = conn.execute(sqlalchemy.text('SELECT count(*) FROM users')).scalar()
            plan = _plan(conn, _discover_tables(conn), keep_user_id, keep_internal_user_id, args.keep_null_user_rows)

            log.info(f'{len(plan)} user-keyed tables (users has {users_before} rows in total):')
            for table, column, _where, _params, to_delete, nulls in plan:
                log.info(f'  {table:<40} by {column:<18} delete {to_delete:>10}   (NULL keys: {nulls})')
            log.info(f'  TOTAL rows to delete: {sum(row[4] for row in plan)}')

            if not args.apply:
                log.info('DRY RUN — nothing was deleted. Re-run with --apply to delete for real.')
                trans.rollback()
                return

            deleted_total = 0
            for table, _column, where, params, _to_delete, _nulls in plan:
                result = conn.execute(sqlalchemy.text(f'DELETE FROM "{table}" WHERE {where}'), params)
                deleted_total += result.rowcount
                log.info(f'  deleted {result.rowcount:>10} from {table}')

            users_after = conn.execute(sqlalchemy.text('SELECT count(*) FROM users')).scalar()
            log.info(f'Done: {deleted_total} rows deleted, "users" went {users_before} -> {users_after}')
            if users_after != 1:
                log.warning(f'Expected exactly 1 row left in "users", got {users_after} — check the result.')
            trans.commit()
        except Exception:
            trans.rollback()
            raise


if __name__ == '__main__':
    main()
