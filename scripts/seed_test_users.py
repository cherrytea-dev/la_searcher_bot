#!/usr/bin/env python3
"""Seed script: populate test database with sample users BEFORE applying migrations 004 and 005.

Creates several test users in the **old** DB schema (pre-migration), so you can:
1. Run this script to populate the DB
2. Apply migration 004 (``user_identity_map`` table + ``internal_user_id`` column)
3. Apply migration 005 (``notif_by_user.messenger`` column)
4. Verify that backfill works correctly

The script:
- Drops migration 004/005 artifacts if present (``user_identity_map`` table,
  ``internal_user_id`` column, ``notif_by_user.messenger`` column)
- Creates users in the **old** schema only
- Prints instructions for applying migrations afterward

Usage:
    uv run python scripts/seed_test_users.py                          # drop migrations + seed
    uv run python scripts/seed_test_users.py --reset                   # delete users + re-seed
    uv run python scripts/seed_test_users.py --skip-migration-drop     # keep migrations, seed old schema
    uv run python scripts/seed_test_users.py --env-file .env.test      # custom env file

After seeding, apply migrations:
    psql $POSTGRES_URL -f doc/migrations/004_user_identity_map.sql
    psql $POSTGRES_URL -f doc/migrations/005_notif_by_user_messenger.sql

Then verify:
    SELECT internal_user_id, user_id, vk_id FROM users;
    SELECT * FROM user_identity_map;
    SELECT message_id, user_id, messenger FROM notif_by_user;
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy
from dotenv import load_dotenv

# Add src/ to sys.path so we can import project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from _dependencies.commons import sqlalchemy_get_pool

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ─── Test user definitions ───────────────────────────────────────────────────

# Each user is a dict with fields matching the OLD schema (pre-migration 004/005):
#   tag:        human-readable label
#   user_id:    Telegram user_id (for Telegram users) or generated seq (for VK-only)
#   username:   display name (stored in username_telegram)
#   vk_id:      legacy vk_id column (pre-migration 004, this is the only VK link)
#   folders:    list of forum_folder_id to subscribe to
#   radius_km:  notification radius (optional)
#   lat, lon:   home coordinates (optional)
#   age_prefs:  list of (period_name, period_min, period_max) tuples (optional)

TEST_USERS = [
    {
        'tag': 'Telegram-only user (Alice)',
        'user_id': 900000001,
        'username': 'alice_telegram',
        'vk_id': None,
        'folders': [120, 121],
        'radius_km': 100,
        'lat': '55.7558',
        'lon': '37.6173',
        'age_prefs': [('adults', 18, 60)],
    },
    {
        'tag': 'VK-only user (Bob)',
        'user_id': None,  # will be generated from users_id_seq
        'username': 'bob_vk',
        'vk_id': '900000101',
        'folders': [120],
        'radius_km': 50,
        'lat': '59.9343',
        'lon': '30.3351',
        'age_prefs': [('children', 0, 17), ('adults', 18, 60)],
    },
    {
        'tag': 'Dual-messenger user (Charlie — Telegram + VK linked)',
        'user_id': 900000002,
        'username': 'charlie_dual',
        'vk_id': '900000102',
        'folders': [120, 121, 122],
        'radius_km': 200,
        'lat': '56.8389',
        'lon': '60.6057',
        'age_prefs': [('adults', 18, 60), ('elderly', 61, 120)],
    },
    {
        'tag': 'Telegram-only user, no radius (Diana)',
        'user_id': 900000003,
        'username': 'diana_no_radius',
        'vk_id': None,
        'folders': [121],
        'radius_km': None,
        'lat': None,
        'lon': None,
        'age_prefs': [],
    },
    {
        'tag': 'VK-only user, no folder prefs (Eve)',
        'user_id': None,  # will be generated
        'username': 'eve_vk_minimal',
        'vk_id': '900000103',
        'folders': [],
        'radius_km': None,
        'lat': None,
        'lon': None,
        'age_prefs': [],
    },
]


# ─── Migration helpers ───────────────────────────────────────────────────────


def _has_column(conn: sqlalchemy.engine.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    result = conn.execute(
        sqlalchemy.text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
        """),
        {'table': table, 'column': column},
    )
    return result.fetchone() is not None


def _has_table(conn: sqlalchemy.engine.Connection, table: str) -> bool:
    """Check if a table exists."""
    result = conn.execute(
        sqlalchemy.text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = :table AND table_schema = 'public'
        """),
        {'table': table},
    )
    return result.fetchone() is not None


def _drop_migration_artifacts(conn: sqlalchemy.engine.Connection) -> None:
    """Drop migration 004 and 005 artifacts to restore pre-migration schema.

    Drops (in order):
    1. ``user_identity_map`` table (migration 004)
    2. ``users.internal_user_id`` column + its unique index (migration 004)
    3. ``notif_by_user.messenger`` column (migration 005)
    4. ``notif_by_user__history.messenger`` column (migration 005, if exists)
    """
    log.info('Checking for migration artifacts...')

    # 1. Drop user_identity_map table
    if _has_table(conn, 'user_identity_map'):
        log.info('  Dropping table: user_identity_map')
        conn.execute(sqlalchemy.text('DROP TABLE IF EXISTS user_identity_map CASCADE'))

    # 2. Drop internal_user_id column + its unique index from users
    if _has_column(conn, 'users', 'internal_user_id'):
        log.info('  Dropping column: users.internal_user_id')
        # Drop the unique index first (if it exists)
        conn.execute(sqlalchemy.text('DROP INDEX IF EXISTS users_internal_user_id'))
        conn.execute(sqlalchemy.text('ALTER TABLE users DROP COLUMN IF EXISTS internal_user_id'))

    # 3. Drop messenger column from notif_by_user
    if _has_column(conn, 'notif_by_user', 'messenger'):
        log.info('  Dropping column: notif_by_user.messenger')
        conn.execute(sqlalchemy.text('ALTER TABLE notif_by_user DROP COLUMN IF EXISTS messenger'))

    # 4. Drop messenger column from notif_by_user__history
    if _has_column(conn, 'notif_by_user__history', 'messenger'):
        log.info('  Dropping column: notif_by_user__history.messenger')
        conn.execute(sqlalchemy.text('ALTER TABLE notif_by_user__history DROP COLUMN IF EXISTS messenger'))

    log.info('Migration artifacts removed. Schema is now pre-migration 004/005.')


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _resolve_user_ids(users: list[dict], conn: sqlalchemy.engine.Connection) -> list[dict]:
    """Generate user_id from sequence for VK-only users (no Telegram ID)."""
    for user in users:
        if user['user_id'] is None:
            result = conn.execute(sqlalchemy.text("SELECT nextval('users_id_seq'::regclass)"))
            user['user_id'] = result.scalar()
    return users


def _delete_test_users(users: list[dict], conn: sqlalchemy.engine.Connection) -> None:
    """Delete all test users and their associated data."""
    all_user_ids = [u['user_id'] for u in users]

    log.info('Deleting existing test data...')

    tables_in_order = [
        'user_pref_search_whitelist',
        'user_pref_topic_type',
        'user_pref_urgency',
        'user_pref_region',
        'user_pref_age',
        'user_pref_radius',
        'user_coordinates',
        'user_regional_preferences',
        'user_preferences',
        'user_onboarding',
        'user_statuses_history',
        'user_stat',
        'user_roles',
        'user_forum_attributes',
        'notif_by_user',
        'users',
    ]
    for table in tables_in_order:
        conn.execute(
            sqlalchemy.text(f'DELETE FROM {table} WHERE user_id = ANY(:ids)'),
            {'ids': list(all_user_ids)},
        )

    log.info(f'Deleted {len(all_user_ids)} test users and all associated data.')


def _insert_user(user: dict, conn: sqlalchemy.engine.Connection) -> None:
    """Insert a single test user into the OLD schema (pre-migration 004/005).

    Does NOT write to:
    - ``internal_user_id`` column (doesn't exist yet)
    - ``user_identity_map`` table (doesn't exist yet)
    - ``notif_by_user.messenger`` column (doesn't exist yet)
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tag = user['tag']
    uid = user['user_id']
    log.info(f'Creating user: {tag} (user_id={uid})')

    # 1. Insert into users table (OLD schema — no internal_user_id)
    conn.execute(
        sqlalchemy.text("""
            INSERT INTO users (user_id, username_telegram, reg_date, status, vk_id)
            VALUES (:user_id, :username, :reg_date, :status, :vk_id)
            ON CONFLICT (user_id) DO UPDATE SET
                username_telegram = EXCLUDED.username_telegram,
                vk_id = EXCLUDED.vk_id
        """),
        {
            'user_id': uid,
            'username': user['username'],
            'reg_date': now,
            'status': 'unblocked',
            'vk_id': user['vk_id'],
        },
    )

    # 2. Insert default notification preferences
    default_prefs = [
        (uid, 'new_searches', 0),
        (uid, 'status_changes', 1),
        (uid, 'inforg_comments', 4),
        (uid, 'first_post_changes', 8),
        (uid, 'bot_news', 20),
    ]
    stmt = sqlalchemy.text("""
        INSERT INTO user_preferences (user_id, preference, pref_id)
        VALUES (:user_id, :preference, :pref_id)
        ON CONFLICT (user_id, pref_id) DO NOTHING
    """)
    for pref_user_id, pref_name, pref_id in default_prefs:
        conn.execute(stmt, {'user_id': pref_user_id, 'preference': pref_name, 'pref_id': pref_id})

    # 3. Insert onboarding step
    conn.execute(
        sqlalchemy.text("""
            INSERT INTO user_onboarding (user_id, step_id, step_name, timestamp)
            VALUES (:user_id, :step_id, :step_name, :timestamp)
            ON CONFLICT DO NOTHING
        """),
        {'user_id': uid, 'step_id': 80, 'step_name': 'finished', 'timestamp': now},
    )

    # 4. Insert user_statuses_history
    conn.execute(
        sqlalchemy.text("""
            INSERT INTO user_statuses_history (status, date, user_id)
            VALUES (:status, :date, :user_id)
            ON CONFLICT (user_id, date) DO NOTHING
        """),
        {'status': 'new', 'date': now, 'user_id': uid},
    )

    # 5. Subscribe to forum folders (regions)
    for folder_id in user['folders']:
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO user_regional_preferences (user_id, forum_folder_num)
                VALUES (:user_id, :folder_id)
                ON CONFLICT DO NOTHING
            """),
            {'user_id': uid, 'folder_id': folder_id},
        )

    # 6. Set notification radius (if provided)
    if user.get('radius_km') is not None:
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO user_pref_radius (user_id, type, radius)
                VALUES (:user_id, :type, :radius)
                ON CONFLICT (user_id) DO UPDATE SET radius = EXCLUDED.radius
            """),
            {'user_id': uid, 'type': 'km', 'radius': user['radius_km']},
        )

    # 7. Set home coordinates (if provided)
    if user.get('lat') is not None and user.get('lon') is not None:
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time)
                VALUES (:user_id, :latitude, :longitude, :upd_time)
                ON CONFLICT DO NOTHING
            """),
            {'user_id': uid, 'latitude': user['lat'], 'longitude': user['lon'], 'upd_time': now},
        )

    # 8. Set age preferences (if provided)
    for period_name, period_min, period_max in user.get('age_prefs', []):
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max)
                VALUES (:user_id, :period_name, :period_set_date, :period_min, :period_max)
                ON CONFLICT (user_id, period_min, period_max) DO NOTHING
            """),
            {
                'user_id': uid,
                'period_name': period_name,
                'period_set_date': now,
                'period_min': period_min,
                'period_max': period_max,
            },
        )

    # 9. Create user_stat record
    conn.execute(
        sqlalchemy.text("""
            INSERT INTO user_stat (user_id, num_of_new_search_notifs)
            VALUES (:user_id, 0)
            ON CONFLICT (user_id) DO NOTHING
        """),
        {'user_id': uid},
    )

    log.info(f'  ✓ Created user {tag} (user_id={uid})')


def seed(conn: sqlalchemy.engine.Connection, reset: bool = False, skip_migration_drop: bool = False) -> None:
    """Main seeding logic."""
    users = TEST_USERS
    _resolve_user_ids(users, conn)

    if reset:
        _delete_test_users(users, conn)

    if not skip_migration_drop:
        _drop_migration_artifacts(conn)

    for user in users:
        _insert_user(user, conn)

    log.info(f'Done. Created {len(users)} test users.')


def print_summary(users: list[dict]) -> None:
    """Print a human-readable summary of created users."""
    print()
    print('═' * 70)
    print('  TEST USERS SUMMARY (pre-migration schema)')
    print('═' * 70)
    for user in users:
        uid = user['user_id']
        print(f'\n  [{user["tag"]}]')
        print(f'    user_id          = {uid}')
        print(f'    username         = {user["username"]}')
        if user['vk_id']:
            print(f'    vk_id (legacy)   = {user["vk_id"]}')
        if user['folders']:
            print(f'    subscribed folders: {user["folders"]}')
        if user.get('radius_km'):
            print(f'    radius           = {user["radius_km"]} km')
        if user.get('lat') and user.get('lon'):
            print(f'    coordinates      = {user["lat"]}, {user["lon"]}')
        if user.get('age_prefs'):
            print(f'    age preferences  = {user["age_prefs"]}')
    print()
    print('═' * 70)
    print('  NEXT STEPS:')
    print('  1. Apply migration 004:')
    print('     psql $POSTGRES_URL -f doc/migrations/004_user_identity_map.sql')
    print('  2. Apply migration 005:')
    print('     psql $POSTGRES_URL -f doc/migrations/005_notif_by_user_messenger.sql')
    print('  3. Verify:')
    print('     SELECT internal_user_id, user_id, vk_id FROM users;')
    print('     SELECT * FROM user_identity_map;')
    print('     SELECT message_id, user_id, messenger FROM notif_by_user;')
    print('═' * 70)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Seed test DB with users BEFORE migrations 004/005.',
    )
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Delete existing test users before inserting.',
    )
    parser.add_argument(
        '--skip-migration-drop',
        action='store_true',
        help='Skip dropping migration artifacts (use if schema is already pre-migration).',
    )
    parser.add_argument(
        '--env-file',
        default='.env.test',
        help='Path to .env file with DB credentials (default: .env.test).',
    )
    args = parser.parse_args()

    # Load env file so AppConfig can find POSTGRES_* vars
    env_path = Path(__file__).resolve().parent.parent / args.env_file
    if env_path.exists():
        loaded = load_dotenv(env_path, override=True)
        log.info(f'Loaded env file: {env_path} (loaded={loaded})')
    else:
        log.warning(f'Env file not found: {env_path}. Relying on existing env vars.')

    pool = sqlalchemy_get_pool()
    with pool.connect() as conn:
        trans = conn.begin()
        try:
            seed(conn, reset=args.reset, skip_migration_drop=args.skip_migration_drop)
            trans.commit()
        except Exception:
            trans.rollback()
            raise

    # Print summary
    print_summary(TEST_USERS)


if __name__ == '__main__':
    main()
