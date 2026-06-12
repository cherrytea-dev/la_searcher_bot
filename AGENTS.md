# LA Searcher Bot — Project Overview

## What is this project?

**LA Searcher Bot** is a Telegram bot for [LizaAlert](https://lizaalert.org/) — a non-profit volunteer Search & Rescue organization. The bot monitors the [LA phpBB Forum](https://lizaalert.org/forum/), detects new/updated searches (lost people), and sends **personalized notifications** to volunteer searchers via Telegram (and experimentally VKontakte).

As of early 2023: ~9700 active users, ~6000 DAU, ~30000 daily messages. Annual growth ~2x.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Yandex Cloud (or GCP)                               │
│                                                                              │
│  ┌─────────────────┐    ┌──────────────┐    ┌─────────────────────────┐     │
│  │  Cron Triggers   │    │  Message     │    │  HTTP Gateways          │     │
│  │  (every minute,  │───▶│  Queues      │◀───│  (Telegram / Map API)   │     │
│  │   hourly, daily) │    │  (YMQ/SQS)   │    └─────────────────────────┘     │
│  └─────────────────┘    └──────┬───────┘                                     │
│                                │                                             │
│         ┌──────────────────────┼──────────────────────┐                      │
│         ▼                      ▼                      ▼                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐           │
│  │ Forum        │    │ Notification │    │ User Communication   │           │
│  │ Parsing      │───▶│ Pipeline     │───▶│ & Sending            │           │
│  │ Functions    │    │ Functions    │    │ Functions            │           │
│  └──────────────┘    └──────────────┘    └──────────────────────┘           │
│         │                   │                       │                       │
│         ▼                   ▼                       ▼                       │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                    PostgreSQL (Yandex Managed DB)                   │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ▼                                                                   │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │            S3 Object Storage (Yandex Object Storage)                │     │
│  │            (archived notifications backup)                          │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     External Systems                                         │
│                                                                              │
│  ┌────────────────┐    ┌──────────────┐    ┌──────────────────────┐         │
│  │ LA phpBB Forum  │    │  Telegram    │    │  VKontakte API       │         │
│  │ (parsed via     │    │  Bot API     │    │  (experimental       │         │
│  │  HTTP + BS4)    │    │              │    │   notifications)     │         │
│  └────────────────┘    └──────────────┘    └──────────────────────┘         │
│                                                                              │
│  ┌──────────────┐    ┌──────────────────────┐                               │
│  │ LA Map       │    │ Forum phpMyAdmin DB   │                               │
│  │ (WebApp)     │    │ (MySQL, read-only     │                               │
│  │              │    │  for change detection)│                               │
│  └──────────────┘    └──────────────────────┘                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Catalog

The project is decomposed into **independent serverless functions**, each with a single responsibility. Functions communicate via **Yandex Message Queue (YMQ, SQS-compatible)** pub/sub topics.

### 1. Forum Parsing Pipeline

These functions monitor the LA phpBB forum and detect changes.

#### [`check_first_posts_for_changes`](src/check_first_posts_for_changes/main.py)
- **Trigger**: Cron (every minute)
- **Purpose**: Detects changes in the forum's MySQL database (via direct MySQL connection), identifies which topics/folders were modified, and:
  - Updates first-post content hashes in PSQL
  - Sends changed topic IDs to `topic_for_first_post_processing`
  - Sends changed folder IDs to `topic_to_run_parsing_script`
- **Key logic**: Compares content hashes, detects new/modified first posts

#### [`identify_updates_of_topics`](src/identify_updates_of_topics/main.py)
- **Trigger**: Pub/sub (`topic_to_run_parsing_script`)
- **Purpose**: Parses forum folders, retrieves lists of topics (searches), detects status/title/comment/field-trip changes. Saves changes to `change_log` table. Triggers notification composition via `topic_for_notification`.
- **Key sub-modules**: [`folder_updater.py`](src/identify_updates_of_topics/_utils/folder_updater.py), [`forum.py`](src/identify_updates_of_topics/_utils/forum.py), [`parse.py`](src/identify_updates_of_topics/_utils/parse.py)

#### [`identify_updates_of_first_posts`](src/identify_updates_of_first_posts/main.py)
- **Trigger**: Pub/sub (`topic_for_first_post_processing`)
- **Purpose**: Compares previous vs current first-post content for searches that had their first post changed. Saves diffs to `change_log` with `ChangeType.topic_first_post_change`. Triggers folder re-parsing and notification composition.

#### [`connect_to_forum`](src/connect_to_forum/main.py)
- **Trigger**: Pub/sub (`parse_user_profile_from_forum`)
- **Purpose**: When a user links their forum account, this function logs into the forum as a bot, scrapes the user's profile data (callsign, region, phone, age, etc.), saves it to `user_forum_attributes`, and sends a confirmation message via Telegram.

### 2. Notification Pipeline

These functions process `change_log` records and create/send notifications.

#### [`compose_notifications`](src/compose_notifications/main.py)
- **Trigger**: Pub/sub (`topic_for_notification`)
- **Purpose**: Reads the latest unprocessed record from `change_log`, determines which users should receive a notification (based on region preferences, search whitelist, notification type preferences), composes personalized text/location messages, saves them to `notif_by_user` table, and triggers `topic_to_send_notifications`.
- **Locking**: Uses [`lock_manager`](src/_dependencies/lock_manager.py) to prevent parallel execution.
- **Sub-modules**: [`notifications_maker.py`](src/compose_notifications/_utils/notifications_maker.py), [`users_list_composer.py`](src/compose_notifications/_utils/users_list_composer.py), [`message_composer.py`](src/compose_notifications/_utils/message_composer.py)

#### [`send_notifications`](src/send_notifications/main.py)
- **Trigger**: Pub/sub (`topic_to_send_notifications`)
- **Purpose**: Fetches unsent notifications from `notif_by_user`, sends them via Telegram Bot API (and VK API if user has linked VK account). Uses `ThreadPoolExecutor` for parallel sending. Handles rate limits, blocked users, retries. Auto-re-triggers itself if time runs out with more messages pending.
- **Locking**: Uses `lock_manager` to prevent parallel execution.
- **Key features**: Deadlock detection, message deduplication, analytics logging

#### [`send_debug_to_admin`](src/send_debug_to_admin/main.py)
- **Trigger**: Pub/sub (`topic_notify_admin`)
- **Purpose**: Sends debug/error notification messages to the bot admin via a service Telegram bot account.

### 3. User Communication

#### [`communicate`](src/communicate/main.py)
- **Trigger**: HTTP (Telegram webhook)
- **Purpose**: Main user-facing function. Receives Telegram updates (messages, button clicks, commands), processes them via a chain of handlers, and replies. Handles:
  - User onboarding (region selection, notification settings)
  - View active searches
  - Link forum/VK accounts
  - Settings management
  - Help & feedback
- **Handlers**: Each handler is a separate file in [`_utils/handlers/`](src/communicate/_utils/handlers/)

### 4. API Endpoints

#### [`api_get_active_searches`](src/api_get_active_searches/main.py)
- **Trigger**: HTTP (public)
- **Purpose**: Returns JSON list of active searches for external apps (e.g., phone-call group app). Accepts `app_id`, folder list filter, depth in days. Validates `app_id` against configured list.
- **CORS**: Supports OPTIONS preflight.

#### [`user_provide_info`](src/user_provide_info/main.py)
- **Trigger**: HTTP (public)
- **Purpose**: Serves the [LA Map WebApp](https://github.com/cherrytea-dev/la_map). Verifies Telegram login, returns user's saved coordinates, radius, regions, and a list of active searches with coordinates for map display.
- **CORS**: Supports OPTIONS preflight, validates allowed origins.

#### [`title_recognize`](src/title_recognize/main.py)
- **Trigger**: HTTP (internal, called by other functions)
- **Purpose**: NLP service that recognizes topic type (search/event/info), person info (name/age), and location from forum topic titles. Uses `natasha` library for Russian-language NER.
- **Models**: [`recognizer.py`](src/title_recognize/_utils/recognizer.py), [`person.py`](src/title_recognize/_utils/person.py), [`tokenizer.py`](src/title_recognize/_utils/tokenizer.py)

### 5. Housekeeping

#### [`archive_notifications`](src/archive_notifications/main.py)
- **Trigger**: Pub/sub (`topic_to_archive_notifs`) + cron (hourly)
- **Purpose**: Moves completed notifications from `notif_by_user` to `notif_by_user__history` table. Also archives old first-post snapshots.

#### [`archive_to_bigquery`](src/archive_to_bigquery/main.py)
- **Trigger**: Cron (daily)
- **Purpose**: Unloads archived notifications from `notif_by_user__history` to CSV, zips them, uploads to S3-compatible storage (Yandex Object Storage), then deletes from DB. Used for long-term cost-effective storage.

#### [`users_activate`](src/users_activate/main.py)
- **Purpose**: One-time migration script for onboarding old users. Iterates through users and assigns onboarding steps based on historical data. Currently mostly commented out.

### 6. VK Bot

#### [`vk_bot`](src/vk_bot/main.py)
- **Trigger**: HTTP (VK Callback API) or polling mode
- **Purpose**: Allows users to link their Telegram and VK accounts. When a user sends the invite text to the VK bot, it validates the hash and saves `vk_id` in the `users` table.

---

## Data Flow (Pipeline)

```
LA Forum (phpBB)
    │
    ▼
[check_first_posts_for_changes]  ← Cron: every minute
    │  Reads MySQL change log
    │  Compares first-post hashes
    ├──▶ topic_for_first_post_processing ──▶ [identify_updates_of_first_posts]
    │                                            │ Compares old/new content
    │                                            │ Saves diff to change_log
    │                                            └──▶ topic_for_notification
    │
    └──▶ topic_to_run_parsing_script ──▶ [identify_updates_of_topics]
                                             │ Parses forum folders
                                             │ Detects status/title/comment changes
                                             │ Saves to change_log
                                             └──▶ topic_for_notification
                                                      │
                                                      ▼
                                             [compose_notifications]
                                               │ Reads change_log
                                               │ Matches users by preferences
                                               │ Creates notif_by_user records
                                               └──▶ topic_to_send_notifications
                                                        │
                                                        ▼
                                               [send_notifications]
                                                 │ Sends via Telegram/VK API
                                                 │ Marks as completed/cancelled
                                                 │
                                                 └──▶ topic_to_archive_notifs ──▶ [archive_notifications]
                                                                                    │ Moves to __history
                                                                                    │
                                                                                    └──▶ [archive_to_bigquery]  ← Cron: daily
                                                                                         │ Exports to S3
                                                                                         │ Deletes from DB

[communicate]  ← HTTP (Telegram webhook)
    │ Handles user messages, settings, commands
    └──▶ parse_user_profile_from_forum ──▶ [connect_to_forum]
                                             │ Logs into forum
                                             │ Scrapes user profile
                                             │ Saves to user_forum_attributes

[title_recognize]  ← HTTP (internal)
    │ Called by identify_updates_of_topics
    │ Parses topic title for person/location info

[api_get_active_searches]  ← HTTP (public)
    │ Serves active searches JSON for external apps

[user_provide_info]  ← HTTP (public)
    │ Serves user data + searches for LA Map WebApp

[send_debug_to_admin]  ← Pub/sub (notify_admin)
    │ Sends debug/error messages to admin's Telegram
```

---

## Technology Stack

| Layer           | Technology                                                    |
| --------------- | ------------------------------------------------------------- |
| **Runtime**     | Python 3.12+                                                  |
| **Framework**   | Serverless (Yandex Cloud Functions)                           |
| **Message Bus** | Yandex Message Queue (YMQ, SQS-compatible) via boto3          |
| **Database**    | PostgreSQL (Yandex Managed DB) via SQLAlchemy 1.4 + psycopg2  |
| **External DB** | MySQL (phpBB forum, direct connection, read-only) via PyMySQL |
| **Storage**     | Yandex Object Storage (S3-compatible) via boto3               |
| **Telegram**    | python-telegram-bot 21.x (webhook mode)                       |
| **VK API**      | vk-api library                                                |
| **NLP**         | natasha (Russian NER), python-dateutil                        |
| **Parsing**     | BeautifulSoup 4 + lxml                                        |
| **Geocoding**   | yandex-geocoder, geopy                                        |
| **Config**      | pydantic-settings (environment variables)                     |
| **Deploy**      | GitHub Actions + Terraform                                    |
| **Monorepo**    | UV package manager                                            |

---

## Key Design Patterns

### 1. Serverless Function Chain via Message Queue

Functions never call each other directly. Instead:
- A function publishes a message to a YMQ topic
- The topic triggers the next function
- This provides: decoupling, retry semantics, async processing, independent scaling

### 2. Distributed Locking via DB

[`lock_manager.py`](src/_dependencies/lock_manager.py) provides a context manager that:
- Writes a `time_start` record in `functions_registry` table
- Checks if another instance of the same function is already running
- Prevents parallel execution (critical for `compose_notifications` and `send_notifications`)

### 3. Request/Response HTTP Wrapper

[`misc.py`](src/_dependencies/misc.py) provides:
- [`request_response_converter`](src/_dependencies/misc.py:123) — decorator that converts Yandex Cloud Functions HTTP request format to a standardized [`RequestWrapper`](src/_dependencies/misc.py:108) / [`ResponseWrapper`](src/_dependencies/misc.py:116) format
- Enables smooth migration between GCP Cloud Functions and Yandex Cloud Functions

### 4. Pub/Sub Helper Layer

[`pubsub.py`](src/_dependencies/pubsub.py) provides:
- Typed [`Topics`](src/_dependencies/pubsub.py:9) enum for all message queue topics
- Helper functions for each pipeline step (e.g., `pubsub_compose_notifications`, `pubsub_parse_folders`)
- `process_pubsub_message` to parse incoming YMQ messages
- `recognize_title_via_api` for HTTP call to title recognition service

### 5. Content Cleaning Pipeline

[`content.py`](src/_dependencies/content.py) provides a comprehensive set of regex patterns to clean up forum post content (remove irrelevant boilerplate, formatting, phone numbers, coordinator info) before sending to users.

---

## Message Queue Topics (YMQ / SQS)

| Topic Name                        | Producer(s)                                                                                                                                              | Consumer(s)                                                                      |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `topic_notify_admin`              | Any function (via `notify_admin()`)                                                                                                                      | [`send_debug_to_admin`](src/send_debug_to_admin/main.py)                         |
| `topic_to_run_parsing_script`     | [`check_first_posts_for_changes`](src/check_first_posts_for_changes/main.py)                                                                             | [`identify_updates_of_topics`](src/identify_updates_of_topics/main.py)           |
| `topic_for_first_post_processing` | [`check_first_posts_for_changes`](src/check_first_posts_for_changes/main.py)                                                                             | [`identify_updates_of_first_posts`](src/identify_updates_of_first_posts/main.py) |
| `topic_for_notification`          | [`identify_updates_of_topics`](src/identify_updates_of_topics/main.py), [`identify_updates_of_first_posts`](src/identify_updates_of_first_posts/main.py) | [`compose_notifications`](src/compose_notifications/main.py)                     |
| `topic_to_send_notifications`     | [`compose_notifications`](src/compose_notifications/main.py)                                                                                             | [`send_notifications`](src/send_notifications/main.py)                           |
| `topic_to_archive_notifs`         | [`send_notifications`](src/send_notifications/main.py)                                                                                                   | [`archive_notifications`](src/archive_notifications/main.py)                     |
| `parse_user_profile_from_forum`   | [`communicate`](src/communicate/main.py)                                                                                                                 | [`connect_to_forum`](src/connect_to_forum/main.py)                               |

---

## Shared Library (`_dependencies`)

Located at [`src/_dependencies/`](src/_dependencies/). This package is copied into each function's deployment package during CI/CD build.

| File                                                                   | Responsibility                                                                                                      |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| [`commons.py`](src/_dependencies/commons.py)                           | `AppConfig` (env-based config), DB pool, `ChangeLogSavedValue`, enums (`ChangeType`, `TopicType`), phone formatting |
| [`db_client.py`](src/_dependencies/db_client.py)                       | Base DB client, key-value storage mixin                                                                             |
| [`content.py`](src/_dependencies/content.py)                           | Forum content cleaning, regex patterns, HTML soup processing                                                        |
| [`pubsub.py`](src/_dependencies/pubsub.py)                             | Typed topics enum, publish helpers, message parsing                                                                 |
| [`yandex_tools.py`](src/_dependencies/yandex_tools.py)                 | JSON logging setup, YMQ (SQS) client via boto3, HTTP API call helper, pub/sub message parsing                       |
| [`lock_manager.py`](src/_dependencies/lock_manager.py)                 | DB-based distributed lock (context manager)                                                                         |
| [`telegram_api_wrapper.py`](src/_dependencies/telegram_api_wrapper.py) | Raw Telegram Bot API client (sendMessage, editMessage, etc.), block/unblock handling                                |
| [`users_management.py`](src/_dependencies/users_management.py)         | User CRUD (register, block, delete), onboarding step tracking                                                       |
| [`topic_management.py`](src/_dependencies/topic_management.py)         | Save topic status/visibility changes to DB, trigger notifications                                                   |
| [`misc.py`](src/_dependencies/misc.py)                                 | Telegram API clients, time formatting (Russian), bearing calc, HTTP request/response wrappers                       |
| [`recognition_schema.py`](src/_dependencies/recognition_schema.py)     | Pydantic models for NLP recognition results (Person, Location, RecognitionResult)                                   |
| [`vk_api_client.py`](src/_dependencies/vk_api_client.py)               | VK API client (send messages, get user by login)                                                                    |

---

## Configuration (`AppConfig`)

All configuration comes from **environment variables** via [`AppConfig`](src/_dependencies/commons.py:20) (pydantic-settings). Key variables:

| Variable                                      | Purpose                                            |
| --------------------------------------------- | -------------------------------------------------- |
| `POSTGRES_*`                                  | PostgreSQL connection (host, port, user, pass, db) |
| `BOT_API_TOKEN`                               | Telegram bot token (testing)                       |
| `BOT_API_TOKEN__PROD`                         | Telegram bot token (production)                    |
| `MY_TELEGRAM_ID`                              | Admin user ID for debug messages                   |
| `WEB_APP_URL` / `WEB_APP_URL_TEST`            | LA Map WebApp URLs                                 |
| `YANDEX_API_KEY`                              | Yandex Geocoder API key                            |
| `TITLE_RECOGNIZE_URL`                         | Internal URL for title_recognize function          |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | YMQ + S3 credentials                               |
| `AWS_BACKUP_BUCKET_NAME`                      | S3 bucket for notification archives                |
| `VK_API_KEY`                                  | VK group API token                                 |
| `FORUM_BOT_LOGIN` / `FORUM_BOT_PASSWORD`      | Forum login for scraping                           |
| `MYSQL_*`                                     | MySQL connection for phpBB forum change detection  |

---

## Deployment

### Infrastructure (Terraform)

See [`terraform/`](terraform/):
- [`main.tf`](terraform/main.tf) — Yandex provider, AWS provider (for YMQ), service account, S3 bucket
- [`_func_cron_trigger.tf`](terraform/_func_cron_trigger.tf) — Functions triggered by timer: `check-first-posts-for-changes`, `archive-to-bigquery`
- [`_func_event_trigger.tf`](terraform/_func_event_trigger.tf) — Functions triggered by YMQ: `compose-notifications`, `connect-to-forum`, `identify-updates-of-*`, `send-*`, `archive-notifications`
- [`_func_api_trigger.tf`](terraform/_func_api_trigger.tf) — HTTP-triggered functions: `communicate`, `api-get-active-searches`, `title-recognize`, `user-provide-info`

### CI/CD (GitHub Actions)

Located in [`.github/`](.github/). Uses **reusable workflows** to:
1. Package each function's code + dependencies into a zip archive
2. Deploy to Yandex Cloud Functions
3. Update environment variables

### Local Development

```bash
make prepare-environment   # Install uv, create venv, start Postgres in Docker
make test                  # Run tests
make mypy                  # Type checking
make lint                  # Format code
make requirements          # Update requirements.txt for each function
make ci-test               # Run tests in Docker with Postgres
```

---

## Database Notes

The PostgreSQL database is central. Key tables (inferred from code):

| Table                         | Purpose                                            |
| ----------------------------- | -------------------------------------------------- |
| `users`                       | Bot users, Telegram ID, status, VK ID              |
| `user_preferences`            | Notification type preferences per user             |
| `user_regional_preferences`   | Region (forum folder) subscriptions                |
| `user_coordinates`            | Home coordinates per user                          |
| `user_pref_radius`            | Notification radius per user                       |
| `user_pref_search_whitelist`  | Per-search follow/unfollow                         |
| `searches`                    | Active/completed searches parsed from forum        |
| `search_first_posts`          | Content + hash of first post per search            |
| `search_first_posts__history` | Archived first post snapshots                      |
| `search_health_check`         | Topic visibility (deleted/hidden/regular)          |
| `search_coordinates`          | Geocoded coordinates per search                    |
| `change_log`                  | All detected changes (status, title, content...)   |
| `notif_by_user`               | Pending/completed notifications per user           |
| `notif_by_user__history`      | Archived notifications                             |
| `functions_registry`          | Distributed lock registry                          |
| `user_onboarding`             | Onboarding step tracking                           |
| `user_forum_attributes`       | Forum profile data linked to Telegram user         |
| `user_roles`                  | Admin/tester roles                                 |
| `dialogs`                     | User-bot message history                           |
| `geo_folders`                 | Geographic folder hierarchy                        |
| `geo_regions`                 | Geographic regions                                 |
| `key_value_storage`           | Key-value settings (e.g., last processed MySQL ID) |
| `geocoding`                   | Cached geocoding results                           |

---

## HTTP Function Contracts

### `communicate` (Telegram Webhook)
- **Method**: POST
- **Body**: Telegram `Update` JSON object
- **Response**: `"finished successfully..."` or error

### `api_get_active_searches`
- **Method**: POST (JSON) or OPTIONS (CORS preflight)
- **Body**: `{ "app_id": ..., "forum_folder_id_list": [...], "depth_days": ... }`
- **Response**: `{ "ok": true, "searches": [...] }` or `{ "ok": false, "reason": "..." }`

### `user_provide_info` (LA Map API)
- **Method**: POST (JSON) or OPTIONS (CORS preflight)
- **Body**: Telegram WebApp init data (with `hash` for verification) or `{ "id": <user_id> }`
- **Response**: `{ "ok": true, "user_id": ..., "params": { ... } }` or `{ "ok": false, "reason": "..." }`
- **Auth**: Telegram login verification via HMAC-SHA256

### `title_recognize`
- **Method**: POST (JSON)
- **Body**: `{ "title": "...", "reco_type": "status_only" | null }`
- **Response**: `{ "status": "ok", "recognition": { "topic_type": ..., "persons": ..., "locations": ... } }`
- **Called by**: `identify_updates_of_topics` via internal HTTP

---

## Development Guidelines

### Code Style
- Python 3.12+, type-annotated (`mypy` strict mode)
- Formatted with `ruff` (line length 120, single quotes)
- SQLAlchemy 1.4 (Core, not ORM) for DB access
- Pydantic v2 for data models and validation

### Adding a New Feature
1. Identify which function(s) need changes
2. If adding a new function, create a new folder under `src/` with `main.py`
3. Add to terraform configs if needed
4. Add tests in `tests/`
5. Run `make requirements` to update requirements.txt
6. Run `make test && make mypy && make lint` before committing

### Testing
- Tests are in [`tests/`](tests/)
- Run with: `make test` (or `uv run pytest . -v -n 4 --dist loadgroup`)
- Requires PostgreSQL running in Docker
- Test database is initialized via: `make initdb`
- **IMPORTANT**: The test database is NOT recreated between test runs. Data persists across runs. When writing tests that insert data with specific values (e.g., `vk_id`), always use unique values per test run (e.g., `random.randint()` or `uuid`) to avoid collisions with stale data from previous runs.

### For AI agents:
- use `uv run python foo.py` instead of `python foo.py` to avoid ModuleNotFoundError: there is `venv` using in development.
- remember that `src` should be present in PYTHONPATH for correct import project modules.

### For AI agents:
- Always use `uv run` prefix (e.g., `uv run python foo.py`, `uv run pytest`) — the venv is managed by `uv`.
- `src/` is already added to `sys.path` by pytest via `pyproject.toml` (`[tool.pytest.ini_options]`), so `uv run pytest` works out of the box.
- For non-pytest scripts (e.g., `initdb`), use `PYTHONPATH=src uv run python ...` or simply `make initdb`.
- Prefer `make test` / `make mypy` / `make lint` — they handle all paths correctly.

---

