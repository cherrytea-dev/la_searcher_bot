# Runbook: single container in "parse → compose → send" mode

Goal: run the whole bot as one process (`python -m app.main`) against a **restored production DB**
without the Yandex Cloud functions, parsing the forum over HTTP (no forum MySQL), composing
notifications and sending them. See [`doc/single-container.md`](../single-container.md) for the
runtime itself.

## 1. Schema prerequisites (do this first)

A database restored from an older dump can miss objects the code relies on. Run the idempotent
migration script:

```bash
# credentials come from the environment (POSTGRES_HOST/PORT/USER/PASSWORD/DB)
uv run python scripts/apply_db_migrations.py

# or from a dotenv file
uv run python scripts/apply_db_migrations.py --env-file .env.prod

# see what it would do, change nothing
uv run python scripts/apply_db_migrations.py --dry-run
```

It applies only what is missing and is safe to re-run. The **critical** one is migration 008
(`notif_by_user_unique_unsent_idx`): without it `compose_notifications` fails on every
`INSERT ... ON CONFLICT` and no notification is ever created.

> Note: `doc/migrations/008_notif_by_user_unique_constraint.sql` used to wrap
> `CREATE UNIQUE INDEX CONCURRENTLY` in `BEGIN/COMMIT`, which PostgreSQL rejects — that is why the
> index was missing on production. The transaction block has been removed.

Heavy/destructive steps are opt-in:

```bash
uv run python scripts/apply_db_migrations.py --purge-search-first-posts-history  # 007 DELETE (>30d)
uv run python scripts/apply_db_migrations.py --apply-data-policy                 # 010 drop "finished" subs
```

## 2. Environment

| Variable | Value for this mode | Why |
|---|---|---|
| `APP_MODE` | `k8s` | enables the PostgreSQL queue, in-process scheduler, local title recognition, HTTP server |
| `FORUM_LEGACY_DATA_SOURCE` | `true` | parse the forum over HTTP — no forum MySQL access |
| `NOTIFY_SEARCHES_SINCE` | e.g. `2026-10-08` | never notify about searches started before this date (skip the backlog) |
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | the target DB | data + the `pubsub_messages` queue |
| `BOT_API_TOKEN__PROD` | real token (or empty) | Telegram sending; empty = attempts fail, nothing is delivered |
| `WEBHOOK_PATH_TELEGRAM` / `_VK` / `_MAX` | any non-empty string | a non-empty value **disables the poller** for that bot; nothing calls the path, so bots stay off |
| `MAX_BOT_TOKEN` | set it (may be empty) | `MaxClient()` raises if it is unset (None) |
| `ARCHIVE_TO_BIGQUERY_ENABLED` | `false` | skip the S3 archive job |
| `WORKER_THREADS` | `4–6` recommended | the folder parser can occupy a worker for a long time |
| `CRON_CHECK_FIRST_POSTS` | `* * * * *` | first-post watcher |
| `CRON_CHECK_TOPICS_BY_UPD_TIME` | `*/5 * * * *` | legacy folder-tree scanner (only scheduled with `FORUM_LEGACY_DATA_SOURCE=true`) |

A ready-to-edit example launcher is kept locally at `build/run_container.sh` (`build/` is
git-ignored); copy it and adjust the credentials/tokens for the target environment.

## 3. Run

```bash
python -m app.main            # or: make run-app
```

The app creates the `pubsub_messages` queue table on start, starts the scheduler, the queue
workers and the HTTP server (`/health`, `/ready`).

## 4. Verify

```sql
-- the pipeline is alive
SELECT status, count(*) FROM pubsub_messages GROUP BY status;
SELECT count(*) FROM change_log WHERE notification_sent IS NULL;
SELECT message_id, user_id, messenger, message_type,
       completed IS NOT NULL AS sent, cancelled IS NOT NULL AS cancelled
FROM notif_by_user ORDER BY message_id DESC LIMIT 20;
```

## 5. Telegram is unreachable offline

For local debugging, mock the Bot API and point `BOT_API_HOST` at it:

```bash
python build/mock_telegram.py            # http://127.0.0.1:9999, logs to build/mock_telegram.log
BOT_API_HOST=http://127.0.0.1:9999 ...   # then start the container
```

Notifications get marked `completed` and every request is written to `build/mock_telegram.log`.
