# LA Searcher Bot — Project Map

**LA Searcher Bot** is the [LizaAlert](https://lizaalert.org/) bot for volunteer searchers. It
monitors the LA phpBB forum, detects new and updated searches, and sends personalized
notifications through Telegram, VK and MAX. It also gives users a settings interface in all
three messengers. Around 9.7k active users and ~30k messages per day as of 2023.

This file is the map, not the encyclopedia:

- [`README.md`](README.md) — what the project is and how to start.
- [`doc/components.md`](doc/components.md) — detailed per-function and per-bot descriptions.
- [`doc/reference.md`](doc/reference.md) — stack, data flow, topics, DB, configuration, HTTP contracts.
- [`doc/single-container.md`](doc/single-container.md) — the single-container runtime.

## Start here: three run modes

| Mode | How to run | What it is |
| --- | --- | --- |
| **Yandex Cloud Functions** | deploy from [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) | historical cloud path: timer, queue and HTTP triggers call one function each. The code default is `APP_MODE=yc`. |
| **Single container** | `make run-app` (or `PYTHONPATH=src uv run python -m app.main`) with `APP_MODE=k8s` and the environment from `.env.example` | one process with HTTP server, cron scheduler, PostgreSQL queue workers and long-polling bots. Docker: `docker compose -f docker-compose.app.yml up --build`. |
| **One bot locally** | `uv run python tests/tools/run_bot.py` | Telegram long polling against your `.env`. Also `run_vk_bot.py` and `run_max_bot.py` in the same folder. |

Both production paths share the same function code: handlers keep `main(event, context)` (queue)
or `main(request)` (HTTP), so the container only changes how they are called.

## System architecture

```text
LA Forum (phpBB) — two cron scanners:
   |  check_first_posts_for_changes   every minute, the main entry point
   |  check_topics_by_upd_time        every 5 min, only FORUM_LEGACY_DATA_SOURCE=true
   v
queue topics  -->  identify_updates_of_first_posts / identify_updates_of_topics
   |                    |  change_log
   |                    v
   |              compose_notifications
   |                    |  notif_by_user
   |                    v
   |              send_notifications  --> Telegram / VK / MAX
   |                    |  completed
   |                    v
   +--> archive_notifications (hourly) --> archive_to_bigquery (daily) --> Object Storage

Telegram/VK/MAX updates --> communicate / vk_bot / max_bot
LA Map / external apps  --> user_provide_info / api_get_active_searches
```

In the cloud the edges are YMQ topics and API Gateway routes. In the container they are the
`pubsub_messages` table, an in-process scheduler and an HTTP server (`src/app/`). PostgreSQL,
Object Storage and the forum stay outside in both modes.

## Components

| Component | What it does | Code |
| --- | --- | --- |
| `check_first_posts_for_changes` | Finds changed forum topics, compares first-post hashes, saves hashes/statuses, publishes the next topics | [`src/check_first_posts_for_changes/main.py`](src/check_first_posts_for_changes/main.py) |
| `identify_updates_of_topics` | Parses folders, detects status/title/comment/trip changes, writes `change_log` | [`src/identify_updates_of_topics/main.py`](src/identify_updates_of_topics/main.py) |
| `identify_updates_of_first_posts` | Diffs old/new first posts and writes the diff to `change_log` | [`src/identify_updates_of_first_posts/main.py`](src/identify_updates_of_first_posts/main.py) |
| `check_topics_by_upd_time` | Legacy folder-tree scanner over HTTP (only with `FORUM_LEGACY_DATA_SOURCE=true`) | [`src/check_topics_by_upd_time/main.py`](src/check_topics_by_upd_time/main.py) |
| `connect_to_forum` | Logs into the forum, scrapes the linked profile, saves `user_forum_attributes` | [`src/connect_to_forum/main.py`](src/connect_to_forum/main.py) |
| `compose_notifications` | Matches `change_log` against user preferences and writes personalized `notif_by_user` rows | [`src/compose_notifications/main.py`](src/compose_notifications/main.py) |
| `send_notifications` | Sends pending notifications via Telegram, VK or MAX; handles retries and rate limits | [`src/send_notifications/main.py`](src/send_notifications/main.py) |
| `send_debug_to_admin` | Sends debug/error messages to the admin's Telegram | [`src/send_debug_to_admin/main.py`](src/send_debug_to_admin/main.py) |
| `communicate` | Telegram user-facing handler chain: onboarding, searches, settings | [`src/communicate/main.py`](src/communicate/main.py) |
| `vk_bot` | Full VK interface: onboarding, regions, searches, settings, forum linking | [`src/vk_bot/main.py`](src/vk_bot/main.py) |
| `max_bot` | MAX interface: registration, regions, radius, coordinates | [`src/max_bot/main.py`](src/max_bot/main.py) |
| `api_get_active_searches` | JSON API with active searches for external apps | [`src/api_get_active_searches/main.py`](src/api_get_active_searches/main.py) |
| `user_provide_info` | LA Map API: user settings plus searches with coordinates | [`src/user_provide_info/main.py`](src/user_provide_info/main.py) |
| `title_recognize` | Russian title NER: topic type, person, age, location | [`src/title_recognize/main.py`](src/title_recognize/main.py) |
| `archive_notifications` | Moves completed rows and old first posts to `__history`, purges old history | [`src/archive_notifications/main.py`](src/archive_notifications/main.py) |
| `archive_to_bigquery` | Exports `notif_by_user__history` to CSV/zip and uploads it to Object Storage | [`src/archive_to_bigquery/main.py`](src/archive_to_bigquery/main.py) |
| `users_activate` | One-time onboarding migration utility (manual, no trigger) | [`src/users_activate/main.py`](src/users_activate/main.py) |
| `src/app` | Single-container entry point: queue, scheduler, HTTP, bots | [`src/app/main.py`](src/app/main.py) |

## Function → trigger → handler

The queue rows come from [`src/app/dispatch.py`](src/app/dispatch.py); the cloud matrix comes
from [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml).

| Function | Trigger | Handler |
| --- | --- | --- |
| `check_first_posts_for_changes` | cron every minute (cloud timer or container scheduler) | `check_first_posts_for_changes.main.main` |
| `check_topics_by_upd_time` | cron `*/5 * * * *` in the container, only with `FORUM_LEGACY_DATA_SOURCE=true` | `check_topics_by_upd_time.main.main` |
| `archive_to_bigquery` | cron `13 11 * * *` (daily) | `archive_to_bigquery.main.main` |
| `archive_notifications` | queue `topic_to_archive_notifs` and hourly cron | `archive_notifications.main.main` |
| `identify_updates_of_topics` | queue `topic_to_run_parsing_script` | `identify_updates_of_topics.main.main` |
| `identify_updates_of_first_posts` | queue `topic_for_first_post_processing` | `identify_updates_of_first_posts.main.main` |
| `compose_notifications` | queue `topic_for_notification` | `compose_notifications.main.main` |
| `send_notifications` | queue `topic_to_send_notifications` | `send_notifications.main.main` |
| `send_debug_to_admin` | queue `topic_notify_admin` | `send_debug_to_admin.main.main` |
| `connect_to_forum` | queue `parse_user_profile_from_forum` | `connect_to_forum.main.main` |
| `communicate` | Telegram webhook (cloud) / polling (container) | `communicate.main.main` |
| `vk_bot` | VK Callback API webhook (cloud) / polling (container) | `vk_bot.main.main` |
| `max_bot` | MAX webhook (cloud) / polling (container) | `max_bot.main.main` |
| `api_get_active_searches` | HTTP API | `api_get_active_searches.main.main` |
| `user_provide_info` | HTTP API | `user_provide_info.main.main` |
| `title_recognize` | HTTP call from `identify_updates_of_topics`; in-process in the container | `title_recognize.main.main` |
| `users_activate` | none (manual one-off) | `users_activate.main.main` |

## Single container (`src/app`)

[`src/app/main.py`](src/app/main.py) starts and stops all components. The routing lives in
[`dispatch.py`](src/app/dispatch.py) (topic → handler), [`http_server.py`](src/app/http_server.py)
(HTTP routes and `/health` / `/ready`), [`scheduler.py`](src/app/scheduler.py) (cron jobs),
[`queue_worker.py`](src/app/queue_worker.py) (PostgreSQL queue) and [`bots.py`](src/app/bots.py)
(long polling). It is active only with `APP_MODE=k8s`; see
[`doc/single-container.md`](doc/single-container.md).

## Shared code

[`src/_dependencies/`](src/_dependencies/) is copied into each cloud function by
`make dependencies`; `app` imports it in place. It is split into `common/` (config, DB, queue,
pub/sub, locking, logging, cron, telemetry, HTTP wrappers), `bot/` (Telegram/VK clients, user
management), `forum/` (content cleaning, topic management, recognition models) and
`user_repository/` (user and preference mixins shared by all three bots). See
[`doc/reference.md`](doc/reference.md) for the module list.

## Conventions

### Code

- Python 3.12+, type-annotated; `mypy` with `disallow_untyped_defs` for `src/` (except
  `src/users_activate/`).
- `ruff` (line length 120, single quotes): `make lint` writes, `make lint-check` only checks.
- SQLAlchemy 2.0 Core (not ORM); Pydantic v2 for models and validation.
- **Imports at the top of the file.** A lazy import is allowed only to break a circular
  dependency inside `_dependencies/` (for example `common/yandex_tools.py` ↔
  `common/commons.py`). In every other case, refactor.
- Comments: minimal. Explain non-obvious edge cases and API quirks, not the obvious structure.
- Do not add comments that restate code; module docstrings are fine.

### Tests and checks

```bash
make test          # initdb + pytest -n 4 --dist loadgroup
make test-serial   # same in one process (what CI uses)
make mypy          # type checking
make lint          # ruff format + fix
make ci-test       # tests in Docker with PostgreSQL
```

- Tests live in [`tests/`](tests/). PostgreSQL must be running in Docker; `make initdb`
  initializes it.
- The test database is **not** recreated between runs. Use unique values (for example
  `random.randint()` or `uuid`) for columns with uniqueness constraints.
- If you change a table, update both [`tests/tools/db.sql`](tests/tools/db.sql) and
  [`tests/factories/db_models.py`](tests/factories/db_models.py).
- `make requirements` **does not exist**. For cloud functions CI generates
  `requirements.txt` with `uv export --extra <function> --no-hashes --no-dev` (see
  [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)). `make dependencies` only
  copies the shared package into the function folders.

### Git

- Never push to `main` directly. Use a feature branch and open a Pull Request.
- CI/CD details are in [`.github/workflows/`](.github/).

### For AI agents

- Never read, reference or output `.env`, `.env.test` or credentials.
- Prefix Python and test commands with `uv run` (the venv is managed by `uv`).
- `src/` is already on `sys.path` in pytest (`pyproject.toml`), so `uv run pytest` works from
  the repo root. For scripts use `PYTHONPATH=src uv run python ...` or `make initdb`.
- Prefer `make test` / `make mypy` / `make lint`; they set all paths correctly.
- Third-party sources are not vendored in this repo. Read the installed package in `.venv`
  when you need its implementation, and record the finding in `doc/` if it matters.

## Where to look next

| Question | File |
| --- | --- |
| What does a specific function do? | [`doc/components.md`](doc/components.md) |
| Which topics, tables and env vars exist? | [`doc/reference.md`](doc/reference.md) |
| How does the single container work? | [`doc/single-container.md`](doc/single-container.md) |
| How do I run parse → compose → send on a restored DB? | [`doc/runbooks/parse-compose-send-container.md`](doc/runbooks/parse-compose-send-container.md) |
| How do I cut over a temporary DB? | [`doc/runbooks/temp-db-cutover.md`](doc/runbooks/temp-db-cutover.md) |
| What does the old cloud architecture look like? | [`doc/cloud_functions_architecture.html`](doc/cloud_functions_architecture.html) |
| How do I contribute? | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Is Terraform the current deployment? | [`terraform/README.md`](terraform/README.md) — no, it is a first-time scaffold |
