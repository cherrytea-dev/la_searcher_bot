"""Tests for migration 004: user_identity_map table and internal_user_id.

Verifies:
1. Creating the user_identity_map table
2. Backfilling identity_map for existing telegram users
3. Adding internal_user_id column to users
4. Backfilling internal_user_id = user_id
5. Backfilling vk_id links into identity_map
6. NOT NULL constraint and unique index on internal_user_id

**IMPORTANT**: These tests modify DB schema (DDL) and must NOT run in parallel
with any other test. The ``Makefile`` runs them sequentially (``-p no:xdist``).
Each test reverts the schema to pre-migration state before running,
then restores it to the state expected by ``db.sql`` after completion.
"""

from datetime import datetime

import pytest
import sqlalchemy

from _dependencies.common.commons import sqlalchemy_get_pool

# No xdist_group — these tests are executed serially via Makefile


# ─── helpers ──────────────────────────────────────────────────────────────────


def _revert_migration_state(conn: sqlalchemy.engine.Connection) -> None:
    """Remove migration artifacts to return DB to state *before* migration.

    This is the inverse of what ``db.sql`` creates — removes the table,
    the index, and the column *without* committing.
    """
    conn.execute(sqlalchemy.text('DROP TABLE IF EXISTS user_identity_map CASCADE;'))
    conn.execute(sqlalchemy.text('DROP INDEX IF EXISTS users_internal_user_id;'))
    conn.execute(sqlalchemy.text('ALTER TABLE users DROP COLUMN IF EXISTS internal_user_id;'))


def _restore_migration_state(conn: sqlalchemy.engine.Connection) -> None:
    """Re-apply migration artifacts — restores ``db.sql``-level state."""
    conn.execute(sqlalchemy.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS internal_user_id BIGINT;'))
    conn.execute(
        sqlalchemy.text(
            'UPDATE users SET internal_user_id = user_id WHERE internal_user_id IS NULL AND user_id IS NOT NULL;'
        )
    )
    conn.execute(
        sqlalchemy.text('CREATE UNIQUE INDEX IF NOT EXISTS users_internal_user_id ON users (internal_user_id);')
    )
    conn.execute(
        sqlalchemy.text("""
            CREATE TABLE IF NOT EXISTS user_identity_map (
                id              BIGSERIAL PRIMARY KEY,
                internal_user_id BIGINT NOT NULL,
                messenger       VARCHAR(20) NOT NULL,
                messenger_user_id VARCHAR(100) NOT NULL,
                linked_at       TIMESTAMP DEFAULT NOW(),
                UNIQUE(messenger, messenger_user_id),
                UNIQUE(internal_user_id, messenger)
            );
        """)
    )
    # Re-populate if missing
    conn.execute(
        sqlalchemy.text("""
            INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
            SELECT u.internal_user_id, 'telegram', u.internal_user_id::text
            FROM users u
            WHERE u.internal_user_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM user_identity_map m
                WHERE m.internal_user_id = u.internal_user_id AND m.messenger = 'telegram'
            );
        """)
    )


def _run_migration(conn: sqlalchemy.engine.Connection) -> None:
    """Execute the 004 migration SQL."""
    migration_sql = """
    CREATE TABLE IF NOT EXISTS user_identity_map (
        id              BIGSERIAL PRIMARY KEY,
        internal_user_id BIGINT NOT NULL,
        messenger       VARCHAR(20) NOT NULL,
        messenger_user_id VARCHAR(100) NOT NULL,
        linked_at       TIMESTAMP DEFAULT NOW(),
        UNIQUE(messenger, messenger_user_id),
        UNIQUE(internal_user_id, messenger)
    );

    INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
    SELECT user_id, 'telegram', user_id::text FROM users
    WHERE user_id IS NOT NULL
    ON CONFLICT (messenger, messenger_user_id) DO NOTHING;

    ALTER TABLE users ADD COLUMN IF NOT EXISTS internal_user_id BIGINT;

    UPDATE users SET internal_user_id = user_id WHERE internal_user_id IS NULL AND user_id IS NOT NULL;

    ALTER TABLE users ALTER COLUMN internal_user_id SET NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS users_internal_user_id ON users (internal_user_id);

    INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
    SELECT u.internal_user_id, 'vk', u.vk_id FROM users u
    WHERE u.vk_id IS NOT NULL
    ON CONFLICT (messenger, messenger_user_id) DO NOTHING;
    """
    for statement in migration_sql.split(';'):
        stmt = statement.strip()
        if stmt:
            conn.execute(sqlalchemy.text(stmt + ';'))


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope='module')
def _migration_engine():
    """Dedicated engine for migration tests — same DB, separate connection pool."""
    return sqlalchemy_get_pool()


@pytest.fixture(autouse=True)
def _migration_cleanup(_migration_engine: sqlalchemy.engine.Engine):
    """Before each test: drop migration artifacts to simulate pre-migration DB.

    After each test: restore the schema to the state expected by ``db.sql``
    so that other tests continue to work.

    DDL in psycopg2 is auto-committed (non-transactional), so we need
    explicit revert/restore rather than a transaction rollback.
    """
    conn = _migration_engine.connect()
    try:
        _revert_migration_state(conn)
        yield
    finally:
        _restore_migration_state(conn)
        conn.close()


# ─── tests ────────────────────────────────────────────────────────────────────


class TestMigration004:
    """Test migration 004: user_identity_map."""

    def test_table_created(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify user_identity_map table exists after migration."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            result = conn.execute(
                sqlalchemy.text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'user_identity_map'
                    );
                """)
            )
            assert result.scalar() is True

    def test_internal_user_id_column_added(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify internal_user_id column exists in users table."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            result = conn.execute(
                sqlalchemy.text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'users' AND column_name = 'internal_user_id'
                    );
                """)
            )
            assert result.scalar() is True

    def test_internal_user_id_not_null(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify internal_user_id is NOT NULL after migration."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            result = conn.execute(
                sqlalchemy.text("""
                    SELECT is_nullable FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'internal_user_id';
                """)
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == 'NO'

    def test_internal_user_id_unique_index(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify unique index on internal_user_id exists."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            result = conn.execute(
                sqlalchemy.text("""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes
                        WHERE tablename = 'users' AND indexname = 'users_internal_user_id'
                    );
                """)
            )
            assert result.scalar() is True

    def test_backfill_existing_users(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify that existing users get internal_user_id = user_id and identity_map entries."""
        with _migration_engine.connect() as conn:
            # Setup: create users in pre-migration state (no internal_user_id column)
            ts = datetime(2024, 1, 1, 12, 0, 0)
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO users (user_id, username_telegram, reg_date, status)
                    VALUES (:uid, :uname, :reg, :status)
                    ON CONFLICT (user_id) DO NOTHING;
                """),
                {'uid': 999001, 'uname': 'test_user_999001', 'reg': ts, 'status': 'new'},
            )
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO users (user_id, username_telegram, reg_date, status)
                    VALUES (:uid, :uname, :reg, :status)
                    ON CONFLICT (user_id) DO NOTHING;
                """),
                {'uid': 999002, 'uname': 'test_user_999002', 'reg': ts, 'status': 'new'},
            )

            # Run migration
            _run_migration(conn)

            # Verify internal_user_id was set correctly
            rows = conn.execute(
                sqlalchemy.text("""
                    SELECT user_id, internal_user_id FROM users
                    WHERE user_id IN (999001, 999002)
                    ORDER BY user_id;
                """)
            ).fetchall()
            assert len(rows) == 2
            for row in rows:
                assert row[0] == row[1], f'user_id {row[0]} should equal internal_user_id {row[1]}'

            # Verify identity_map entries created
            rows = conn.execute(
                sqlalchemy.text("""
                    SELECT internal_user_id, messenger, messenger_user_id FROM user_identity_map
                    WHERE internal_user_id IN (999001, 999002)
                    ORDER BY internal_user_id;
                """)
            ).fetchall()
            assert len(rows) == 2
            assert rows[0] == (999001, 'telegram', '999001')
            assert rows[1] == (999002, 'telegram', '999002')

    def test_backfill_vk_id(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify that existing vk_id links get identity_map entries."""
        with _migration_engine.connect() as conn:
            # Setup: create user with vk_id (before migration)
            ts = datetime(2024, 1, 1, 12, 0, 0)
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO users (user_id, username_telegram, reg_date, status, vk_id)
                    VALUES (:uid, :uname, :reg, :status, :vk)
                    ON CONFLICT (user_id) DO NOTHING;
                """),
                {'uid': 999003, 'uname': 'test_user_999003', 'reg': ts, 'status': 'new', 'vk': '111222333'},
            )

            # Run migration
            _run_migration(conn)

            # Verify vk identity_map entry created
            rows = conn.execute(
                sqlalchemy.text("""
                    SELECT internal_user_id, messenger, messenger_user_id
                    FROM user_identity_map
                    WHERE internal_user_id = 999003 AND messenger = 'vk';
                """)
            ).fetchall()
            assert len(rows) == 1
            assert rows[0] == (999003, 'vk', '111222333')

            # Verify telegram identity_map also created
            rows = conn.execute(
                sqlalchemy.text("""
                    SELECT internal_user_id, messenger, messenger_user_id
                    FROM user_identity_map
                    WHERE internal_user_id = 999003 AND messenger = 'telegram';
                """)
            ).fetchall()
            assert len(rows) == 1
            assert rows[0] == (999003, 'telegram', '999003')

    def test_user_without_vk_no_extra_entry(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify that user without vk_id only gets telegram identity_map entry."""
        with _migration_engine.connect() as conn:
            ts = datetime(2024, 1, 1, 12, 0, 0)
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO users (user_id, username_telegram, reg_date, status)
                    VALUES (:uid, :uname, :reg, :status)
                    ON CONFLICT (user_id) DO NOTHING;
                """),
                {'uid': 999004, 'uname': 'test_user_999004', 'reg': ts, 'status': 'new'},
            )

            _run_migration(conn)

            rows = conn.execute(
                sqlalchemy.text("""
                    SELECT messenger FROM user_identity_map
                    WHERE internal_user_id = 999004
                    ORDER BY messenger;
                """)
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 'telegram'

    def test_unique_constraint_messenger_user_id(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify UNIQUE(messenger, messenger_user_id) constraint."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            # Insert first entry
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
                    VALUES (:uid, :m, :mid);
                """),
                {'uid': 999010, 'm': 'telegram', 'mid': '999010'},
            )

            # Insert duplicate should raise
            with pytest.raises(Exception):
                conn.execute(
                    sqlalchemy.text("""
                        INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
                        VALUES (:uid, :m, :mid);
                    """),
                    {'uid': 999011, 'm': 'telegram', 'mid': '999010'},
                )

    def test_unique_constraint_internal_user_id_messenger(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify UNIQUE(internal_user_id, messenger) constraint."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            # Insert first entry
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
                    VALUES (:uid, :m, :mid);
                """),
                {'uid': 999020, 'm': 'telegram', 'mid': '999020'},
            )

            # Same internal_user_id with same messenger should fail
            with pytest.raises(Exception):
                conn.execute(
                    sqlalchemy.text("""
                        INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
                        VALUES (:uid, :m, :mid);
                    """),
                    {'uid': 999020, 'm': 'telegram', 'mid': '999021'},
                )

            # Same internal_user_id with different messenger should succeed
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
                    VALUES (:uid, :m, :mid);
                """),
                {'uid': 999020, 'm': 'vk', 'mid': '111'},
            )

    def test_rollback_drops_table(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify that table is removed on rollback."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            # Simulate rollback
            conn.execute(sqlalchemy.text('DROP TABLE IF EXISTS user_identity_map CASCADE;'))
            conn.execute(sqlalchemy.text('DROP INDEX IF EXISTS users_internal_user_id;'))
            conn.execute(sqlalchemy.text('ALTER TABLE users DROP COLUMN IF EXISTS internal_user_id;'))

            result = conn.execute(
                sqlalchemy.text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'user_identity_map'
                    );
                """)
            )
            assert result.scalar() is False

    def test_rollback_removes_column(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify that column is removed on rollback."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            # Simulate rollback
            conn.execute(sqlalchemy.text('DROP INDEX IF EXISTS users_internal_user_id;'))
            conn.execute(sqlalchemy.text('ALTER TABLE users DROP COLUMN IF EXISTS internal_user_id;'))

            result = conn.execute(
                sqlalchemy.text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'users' AND column_name = 'internal_user_id'
                    );
                """)
            )
            assert result.scalar() is False

    def test_rollback_removes_index(self, _migration_engine: sqlalchemy.engine.Engine) -> None:
        """Verify that index is removed on rollback."""
        with _migration_engine.connect() as conn:
            _run_migration(conn)

            # Simulate rollback
            conn.execute(sqlalchemy.text('DROP INDEX IF EXISTS users_internal_user_id;'))
            conn.execute(sqlalchemy.text('ALTER TABLE users DROP COLUMN IF EXISTS internal_user_id;'))

            result = conn.execute(
                sqlalchemy.text("""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes
                        WHERE tablename = 'users' AND indexname = 'users_internal_user_id'
                    );
                """)
            )
            assert result.scalar() is False
