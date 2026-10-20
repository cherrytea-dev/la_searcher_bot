# Reference: stack, pipeline, configuration

Reference material extracted from the old `AGENTS.md`. For the project map see
[`AGENTS.md`](../AGENTS.md); for per-component descriptions see [`components.md`](components.md).

## Technology stack

| Layer | Technology |
| --- | --- |
| Runtime | Python 3.12+ |
| Cloud runtime | Yandex Cloud Functions (`python312`) |
| Container runtime | one process: HTTP server + cron scheduler + PG queue workers + long-polling bots |
| Message bus | Yandex Message Queue (YMQ, SQS-compatible) or the `pubsub_messages` table in PostgreSQL |
| Database | PostgreSQL via SQLAlchemy 2.0 + psycopg2 |
| External DB | MySQL (phpBB forum, read-only) via PyMySQL, used by the non-legacy change detector (`FORUM_LEGACY_DATA_SOURCE=false`) |
| Storage | S3-compatible Object Storage via boto3 |
| Telegram | python-telegram-bot 22.x |
| VK | `vk-api` |
| MAX | `maxapi` 1.2.0 |
| NLP | `pymorphy3` |
| Parsing | BeautifulSoup 4 + lxml |
| Geocoding | `yandex-geocoder`, `geopy` |
| Config | pydantic-settings |
| Deploy | GitHub Actions; Terraform is a first-time scaffold only |
| Package manager | uv |

## Data flow

```text
LA Forum (phpBB, MySQL or HTTP)
    |
    v
check_first_posts_for_changes            cron: every minute
    |-- topic_for_first_post_processing --> identify_updates_of_first_posts
    |                                            | change_log
    |                                            v
    |                                       topic_for_notification
    |-- topic_to_run_parsing_script ------> identify_updates_of_topics
                                                 | change_log
                                                 v
                                            topic_for_notification
                                                 |
                                                 v
                                            compose_notifications
                                                 | notif_by_user
                                                 v
                                            topic_to_send_notifications
                                                 |
                                                 v
                                            send_notifications
                                                 | Telegram / VK / MAX
                                                 v
                                            notif_by_user (completed)
                                                 |
                          archive_notifications (hourly, self-requeued)
                                                 | notif_by_user__history
                                                 v
                          archive_to_bigquery (daily) --> Object Storage
```

HTTP paths:

```text
Telegram update  -> communicate -> parse_user_profile_from_forum -> connect_to_forum
VK event         -> vk_bot      -> parse_user_profile_from_forum -> connect_to_forum
MAX event        -> max_bot
LA Map WebApp    -> user_provide_info (data + searches)
External apps    -> api_get_active_searches
identify_updates_of_topics -> title_recognize (HTTP, or in-process in the container)
```

## Queue topics

| Topic | Producer(s) | Consumer |
| --- | --- | --- |
| `topic_notify_admin` | any function via `notify_admin()` | `send_debug_to_admin` |
| `topic_to_run_parsing_script` | `check_first_posts_for_changes`, `check_topics_by_upd_time`, `identify_updates_of_first_posts` (legacy) | `identify_updates_of_topics` |
| `topic_for_first_post_processing` | `check_first_posts_for_changes` | `identify_updates_of_first_posts` |
| `topic_for_notification` | `identify_updates_of_topics`, `identify_updates_of_first_posts` | `compose_notifications` |
| `topic_to_send_notifications` | `compose_notifications` | `send_notifications` |
| `topic_to_archive_notifs` | `archive_notifications` (self-requeue), hourly scheduler | `archive_notifications` |
| `parse_user_profile_from_forum` | `communicate`, `vk_bot` | `connect_to_forum` |

The enum and publish helpers live in
[`src/_dependencies/common/pubsub.py`](../src/_dependencies/common/pubsub.py). The container
routing dict is [`src/app/dispatch.py`](../src/app/dispatch.py).

## Shared library (`src/_dependencies`)

The package is copied into each cloud function's deployment package by `make dependencies`
(except `app`, which imports it in place). It is split into four areas:

| Path | Responsibility |
| --- | --- |
| [`common/`](../src/_dependencies/common/) | `AppConfig`, DB pool, pub/sub, queue, locking, logging, cron, telemetry, HTTP wrappers, geo, message params |
| [`bot/`](../src/_dependencies/bot/) | Telegram/VK clients, messenger clients, user management, handler registry, button texts |
| [`forum/`](../src/_dependencies/forum/) | content cleaning, topic management, recognition schema/cache |
| [`user_repository/`](../src/_dependencies/user_repository/) | user, region, geo, age, notification, topic-type, identity and settings mixins |

Notable modules:

| Module | Responsibility |
| --- | --- |
| [`common/commons.py`](../src/_dependencies/common/commons.py) | `AppConfig`, `AppMode`, DB pool, enums (`ChangeType`, `TopicType`, `Messenger`), phone formatting |
| [`common/pubsub.py`](../src/_dependencies/common/pubsub.py) | topic enum, publish helpers, message models, title-recognition dispatch |
| [`common/yandex_tools.py`](../src/_dependencies/common/yandex_tools.py) | JSON logging, YMQ client, HTTP call helper, pub/sub parsing |
| [`common/lock_manager.py`](../src/_dependencies/common/lock_manager.py) | DB-based distributed lock (`functions_registry`) |
| [`common/queue_pg.py`](../src/_dependencies/common/queue_pg.py) | PostgreSQL queue backend for the container |
| [`common/misc.py`](../src/_dependencies/common/misc.py) | request/response wrappers, time formatting, bearing, random function id |
| [`common/telegram_message.py`](../src/_dependencies/common/telegram_message.py) | Telegram message model and split helpers |
| [`bot/telegram_api_wrapper.py`](../src/_dependencies/bot/telegram_api_wrapper.py) | raw Telegram Bot API client |
| [`bot/users_management.py`](../src/_dependencies/bot/users_management.py) | register, block, delete users; onboarding steps |
| [`bot/vk_api_client.py`](../src/_dependencies/bot/vk_api_client.py) | VK API client |
| [`forum/content.py`](../src/_dependencies/forum/content.py) | forum content cleaning and regex patterns |
| [`forum/topic_management.py`](../src/_dependencies/forum/topic_management.py) | save status/visibility changes, trigger notifications |
| [`forum/recognition_schema.py`](../src/_dependencies/forum/recognition_schema.py) | pydantic models for recognition results |

## Key design patterns

1. **Function chain through a queue.** Functions do not call each other directly: a function
   publishes to a topic, and the trigger (YMQ or the `pubsub_messages` worker) calls the next
   function. This gives decoupling, retries and asynchronous processing.
2. **Distributed locking through the database.**
   [`common/lock_manager.py`](../src/_dependencies/common/lock_manager.py) writes a
   `functions_registry` row and prevents two copies of `compose_notifications` or
   `send_notifications` from running in parallel.
3. **Request/response wrapper.**
   [`common/misc.py`](../src/_dependencies/common/misc.py) provides
   `request_response_converter`, which turns the Yandex Cloud HTTP shape into
   `RequestWrapper` / `ResponseWrapper`. The container HTTP server reuses it, so HTTP functions
   are unchanged.
4. **Pub/sub helper layer.**
   [`common/pubsub.py`](../src/_dependencies/common/pubsub.py) holds the `Topics` enum, typed
   message models and one publish helper per pipeline step. The backend is chosen by
   `APP_MODE`.
5. **Content cleaning.**
   [`forum/content.py`](../src/_dependencies/forum/content.py) contains the regex/HTML cleanup
   applied to forum posts before they reach users.

## Configuration

All configuration comes from environment variables via `AppConfig`
([`common/commons.py`](../src/_dependencies/common/commons.py)). Key variables:

| Variable | Purpose |
| --- | --- |
| `APP_MODE` | `yc` (cloud functions, default) or `k8s` (single container) |
| `POSTGRES_*` | PostgreSQL connection |
| `BOT_API_TOKEN` / `BOT_API_TOKEN__PROD` | Telegram bot tokens |
| `MY_TELEGRAM_ID` | admin user ID for debug messages |
| `WEB_APP_URL` / `WEB_APP_URL_TEST` | LA Map WebApp URLs |
| `YANDEX_API_KEY` | Yandex Geocoder |
| `TITLE_RECOGNIZE_URL` | cloud URL of `title_recognize` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | YMQ / Object Storage credentials |
| `AWS_BACKUP_BUCKET_NAME` | archive bucket |
| `VK_API_KEY`, `VK_CONFIRMATION_CODE`, `VK_GROUP_ID` | VK bot |
| `MAX_BOT_TOKEN`, `MAX_BOT_WEBHOOK_SECRET` | MAX bot |
| `FORUM_BOT_LOGIN` / `FORUM_BOT_PASSWORD` | forum scraping |
| `FORUM_LEGACY_DATA_SOURCE` | parse the forum over HTTP, no forum MySQL |
| `MYSQL_*` | forum phpBB MySQL connection |
| `ARCHIVE_TO_BIGQUERY_ENABLED` | enable the daily S3 archive job |

Container-only variables (`WORKER_THREADS`, `CRON_*`, `HTTP_*`, `WEBHOOK_PATH_*`,
`DB_POOL_SIZE`, ...) are listed in [`doc/single-container.md`](single-container.md) and
[`.env.example`](../.env.example).

## Database notes

The schema source of truth is [`tests/tools/db.sql`](../tests/tools/db.sql) plus the
migrations in [`doc/migrations/`](migrations/). Main groups:

| Group | Tables |
| --- | --- |
| Users and preferences | `users`, `user_identity_map`, `user_preferences`, `user_regional_preferences`, `user_pref_radius`, `user_pref_age`, `user_pref_topic_type`, `user_pref_search_whitelist`, `user_coordinates`, `user_forum_attributes`, `user_onboarding`, `user_roles` |
| Searches | `searches`, `search_first_posts`, `search_first_posts__history`, `search_health_check`, `search_coordinates`, `search_activities`, `search_places` |
| Geography | `geo_folders`, `geo_regions`, `geo_divisions`, `geocoding` |
| Pipeline | `change_log`, `notif_by_user`, `notif_by_user__history`, `functions_registry`, `key_value_storage`, `dialogs` |
| Container runtime | `pubsub_messages` — created by the app on start (`CREATE TABLE IF NOT EXISTS`) |

## HTTP contracts

### `communicate` (Telegram webhook)

- `POST`, body is a Telegram `Update`.
- Returns a text acknowledgement or an error.

### `api_get_active_searches`

- `POST` JSON or `OPTIONS` (CORS).
- Request: `{ "app_id": ..., "forum_folder_id_list": [...], "depth_days": ... }`.
- Response: `{ "ok": true, "searches": [...] }` or `{ "ok": false, "reason": "..." }`.

### `user_provide_info` (LA Map API)

- `POST` JSON or `OPTIONS` (CORS).
- Body: Telegram WebApp init data with `hash`, or `{ "id": <user_id> }`.
- Response: `{ "ok": true, "user_id": ..., "params": { ... } }` or `{ "ok": false, "reason": "..." }`.
- Auth: Telegram login verification with HMAC-SHA256.

### `title_recognize`

- `POST` JSON: `{ "title": "...", "reco_type": "status_only" | null }`.
- Response: `{ "status": "ok", "recognition": { ... } }`.
- Called by `identify_updates_of_topics` over HTTP, or in-process in the container.

### `vk_bot` (VK Callback API)

- `POST`, body is a VK Callback API event.
- Returns `"ok"`, or the confirmation code for the `confirmation` event.
- `message_edit` and `message_reply` are ignored.

### `max_bot` (MAX API)

- `POST` webhook or long polling.
- Body is a MAX update (`bot_started`, `message_created`, `message_callback`, ...).
- Returns `"ok"`; checks `X-Max-Bot-Api-Secret` when configured.

## Deployment

- [`src/app/`](../src/app/main.py) — single-container runtime.
- [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) — actual cloud deployment:
  a per-function matrix, `uv export --extra <function> --no-hashes --no-dev` for
  `requirements.txt`, then deploy to Yandex Cloud Functions.
- [`terraform/`](../terraform/) — first-time scaffold (providers, service account, bucket,
  example triggers), not the current deployment description; see
  [`terraform/README.md`](../terraform/README.md).
- [`doc/single-container.md`](single-container.md) — container design and limits.
- [`doc/runbooks/`](runbooks/) — operational runbooks.
