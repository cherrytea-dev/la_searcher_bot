# Components in detail

Detailed descriptions of every function and bot. For the map and the trigger table see
[`AGENTS.md`](../AGENTS.md); for the stack, topics, configuration and HTTP contracts see
[`doc/reference.md`](reference.md). Runtime details of the single container live in
[`doc/single-container.md`](single-container.md).

All functions keep the cloud signature `main(event, context)` (queue handlers) or
`main(request)` (HTTP handlers), so the same code runs in Yandex Cloud Functions and in the
single container. In the container the routing lives in [`src/app/dispatch.py`](../src/app/dispatch.py)
(queue) and [`src/app/http_server.py`](../src/app/http_server.py) (HTTP).

## 1. Forum parsing pipeline

### [`check_first_posts_for_changes`](../src/check_first_posts_for_changes/main.py)

Runs every minute (cloud timer or the container scheduler). Detects which forum topics changed,
compares first-post content hashes, updates the stored first posts and statuses, and publishes:

- changed topic IDs to `topic_for_first_post_processing` (first-post diffing);
- changed folder/topic IDs to `topic_to_run_parsing_script` (folder re-parsing).

With `FORUM_LEGACY_DATA_SOURCE=true` it uses the HTTP-based `_legacy` path (no forum MySQL). It
also re-checks one hidden topic per run to notice when a topic becomes visible again.

### [`identify_updates_of_topics`](../src/identify_updates_of_topics/main.py)

Queue consumer of `topic_to_run_parsing_script`. Parses forum folders, takes the recent topics
(searches), and detects status / title / comment / field-trip changes. Saves them to `change_log`
and publishes `topic_for_notification`.

Key modules: [`topic_updater.py`](../src/identify_updates_of_topics/_utils/topic_updater.py),
[`change_detector.py`](../src/identify_updates_of_topics/_utils/change_detector.py),
[`forum.py`](../src/identify_updates_of_topics/_utils/forum.py),
[`parse.py`](../src/identify_updates_of_topics/_utils/parse.py). The legacy path lives under
[`_legacy/`](../src/identify_updates_of_topics/_legacy/main.py).

### [`identify_updates_of_first_posts`](../src/identify_updates_of_first_posts/main.py)

Queue consumer of `topic_for_first_post_processing`. Compares the previous and the current
first post, writes the diff to `change_log` with `ChangeType.topic_first_post_change`, and
publishes `topic_for_notification`.

### [`check_topics_by_upd_time`](../src/check_topics_by_upd_time/main.py)

Legacy folder-tree scanner: finds leaf folders whose last-update time changed and publishes
them to `topic_to_run_parsing_script`. Scheduled every 5 minutes only when
`FORUM_LEGACY_DATA_SOURCE=true`; otherwise it does nothing.

### [`connect_to_forum`](../src/connect_to_forum/main.py)

Queue consumer of `parse_user_profile_from_forum`. Logs into the forum as the bot, scrapes the
linked user's profile (callsign, region, phone, age, etc.), saves it to
`user_forum_attributes`, and sends a confirmation message via Telegram.

## 2. Notification pipeline

### [`compose_notifications`](../src/compose_notifications/main.py)

Queue consumer of `topic_for_notification`. Reads the next unprocessed `change_log` record,
selects recipients from their region / whitelist / notification-type preferences, builds
personalized text and location messages, saves them to `notif_by_user`, and publishes
`topic_to_send_notifications`. Re-publishes itself while unprocessed records remain.
Protected by the DB lock from
[`lock_manager.py`](../src/_dependencies/common/lock_manager.py).

Key modules: [`notifications_maker.py`](../src/compose_notifications/_utils/notifications_maker.py),
[`users_list_composer.py`](../src/compose_notifications/_utils/users_list_composer.py),
[`message_composer.py`](../src/compose_notifications/_utils/message_composer.py).

### [`send_notifications`](../src/send_notifications/main.py)

Queue consumer of `topic_to_send_notifications`. Reads unsent rows from `notif_by_user` and
sends them through Telegram, VK or MAX depending on the row's `messenger` and the user's
identity in `user_identity_map`. Uses `ThreadPoolExecutor`, handles rate limits, blocked users
and retries, and re-triggers itself when time runs out with messages still pending.
Protected by the same DB lock.

MAX is optional: without `MAX_BOT_TOKEN` the MAX client is skipped, while Telegram and VK keep
working.

### [`send_debug_to_admin`](../src/send_debug_to_admin/main.py)

Queue consumer of `topic_notify_admin`. Sends a debug/error message to the admin's Telegram via
the service bot account.

## 3. Telegram user communication

### [`communicate`](../src/communicate/main.py)

HTTP entry point for the Telegram webhook (polling in the single container). Receives Telegram
updates (messages, button clicks, commands), runs them through the handler chain and replies.
Handles onboarding (region selection, notification settings), active searches, forum linking,
settings, help and feedback.

Handlers live in [`_utils/handlers/`](../src/communicate/_utils/handlers/). The VK account-linking
flow was removed; a VK user is registered independently (see below).

## 4. API endpoints

### [`api_get_active_searches`](../src/api_get_active_searches/main.py)

Public HTTP API for external apps (for example the phone-call group app). Accepts `app_id`, an
optional forum-folder list and `depth_days`, validates `app_id`, and returns the active searches
as JSON. Supports CORS preflight (`OPTIONS`).

### [`user_provide_info`](../src/user_provide_info/main.py)

Public HTTP API for the [LA Map WebApp](https://github.com/cherrytea-dev/la_map). Verifies
Telegram login data with HMAC-SHA256, then returns the user's saved coordinates, radius and
regions plus active searches with coordinates. Supports CORS and validates allowed origins.

### [`title_recognize`](../src/title_recognize/main.py)

NLP service for forum topic titles: recognizes the topic type (search / event / info), person
names and ages, and locations. Uses `pymorphy3` for Russian morphology. In the cloud it is
called over HTTP by `identify_updates_of_topics`; in the container it is called in-process
(`APP_MODE=k8s`), so the HTTP hop disappears.

Models: [`recognizer.py`](../src/title_recognize/_utils/recognizer.py),
[`person.py`](../src/title_recognize/_utils/person.py),
[`tokenizer.py`](../src/title_recognize/_utils/tokenizer.py).

## 5. Housekeeping

### [`archive_notifications`](../src/archive_notifications/main.py)

Moves completed notifications from `notif_by_user` to `notif_by_user__history`, archives first
posts of completed searches, and purges `search_first_posts__history` older than 30 days. Runs
hourly (publishes `topic_to_archive_notifs` to itself) and re-publishes while there is more to
move.

### [`archive_to_bigquery`](../src/archive_to_bigquery/main.py)

Daily job. Exports `notif_by_user__history` rows to CSV, zips them, uploads the archive to
S3-compatible Object Storage, and deletes the exported rows. Skipped when
`ARCHIVE_TO_BIGQUERY_ENABLED=false`.

### [`users_activate`](../src/users_activate/main.py)

One-time onboarding migration for old users. Most calls in `main()` are commented out; it is
kept as a manual utility and has no trigger.

## 6. VK bot

### [`vk_bot`](../src/vk_bot/main.py)

VKontakte interface for user settings and search viewing. Shares PostgreSQL with the Telegram
and MAX bots, so a change in one messenger is immediately visible in the others. Runs as an
HTTP function in the cloud (VK Callback API) or as a long-polling thread in the single
container.

Entry point: [`main.py`](../src/vk_bot/main.py) wraps `dispatch_event` from
[`event_dispatcher.py`](../src/vk_bot/_utils/event_dispatcher.py) in
`@request_response_converter`.

**Event routing** (`VKEventDispatcher`):

| VK event | Action |
| --- | --- |
| `confirmation` | returns `vk_confirmation_code` if `group_id` matches |
| `message_new` | [`handle_new_message`](../src/vk_bot/_utils/message_processing.py) |
| `message_event` | [`handle_callback_event`](../src/vk_bot/_utils/message_processing.py) (inline buttons) |
| `message_edit` / `message_reply` | ignored (bot's own echo) |

The dispatcher keeps an LRU cache (1000 events) to drop VK resends. Handlers register via
`@vk_handle`; [`handler_chain.py`](../src/vk_bot/_utils/handler_chain.py) imports them and
provides the `handle_unknown` fallback.

**Features**:

| Feature | Handler module | Description |
| --- | --- | --- |
| Onboarding | [`onboarding_handlers.py`](../src/vk_bot/_utils/handlers/onboarding_handlers.py) | Role selection, Moscow region subscription |
| Region management | [`region_select_handlers.py`](../src/vk_bot/_utils/handlers/region_select_handlers.py) | Federal district selection, subscribe/unsubscribe with pagination |
| Search viewing | [`view_searches_handlers.py`](../src/vk_bot/_utils/handlers/view_searches_handlers.py) | Active searches, latest 20, follow/unfollow via `+12345` / `-12345` |
| Notification preferences | [`settings_handlers.py`](../src/vk_bot/_utils/handlers/settings_handlers.py) | Toggle notification types |
| Coordinates / radius / age / topic types | [`settings_handlers.py`](../src/vk_bot/_utils/handlers/settings_handlers.py) | Enter, view or delete settings |
| Forum linking | [`state_handlers.py`](../src/vk_bot/_utils/handlers/state_handlers.py) | Publishes `pubsub_parse_user_profile` |

**Key sub-components**:

- [`database.py`](../src/vk_bot/_utils/database.py) — DB client assembled from the shared
  [`user_repository`](../src/_dependencies/user_repository/) mixins.
- [`message_sending.py`](../src/vk_bot/_utils/message_sending.py) — `VKMessageSender`: rate
  limiting, flood control (914 / 917), blocked users (901 / 902), callbacks.
- [`keyboards.py`](../src/vk_bot/_utils/keyboards.py) — `VKKeyboardButtons`,
  `VKKeyboardBase`, `VKKeyboardLayouts`, `VKKeyboardPresets`.
- [`services/message_formatter.py`](../src/vk_bot/_utils/services/message_formatter.py) — text
  templates and LA links.
- [`vk_registration.py`](../src/vk_bot/_utils/vk_registration.py) — `register_vk_only_user`:
  a VK user without `user_identity_map` gets their own `users` row and preferences. There is
  no Telegram↔VK account-linking flow.
- [`bot_polling.py`](../src/vk_bot/_utils/bot_polling.py) — long-polling runner.
- [`cli.py`](../src/vk_bot/cli.py) — Flask server on `0.0.0.0:8888` by default, `--polling`
  for long polling.

## 7. MAX bot

### [`max_bot`](../src/max_bot/main.py)

Settings interface for the [MAX messenger](https://max.ru/). Uses the `maxapi` SDK
(Router / Dispatcher / inline keyboards). Shares PostgreSQL with the Telegram and VK bots.
Runs as an HTTP webhook function in the cloud or as a long-polling thread in the container.

The webhook `main()` is async, verifies `X-Max-Bot-Api-Secret` (when
`MAX_BOT_WEBHOOK_SECRET` is set), parses the update and dispatches it through the same router
as polling mode.

**Architecture**:

```text
src/max_bot/main.py          webhook entry point (async, request_response_converter)
        |
        v
src/max_bot/_utils/common.py         Router, PayloadCmd/DBStateFilter, shared helpers
        |
        v
src/max_bot/_utils/handlers/         domain handler modules (import order = behavior)
        |
        v
src/_dependencies/user_repository/   shared DB mixins
```

**Handlers** ([`_utils/handlers/`](../src/max_bot/_utils/handlers/)): the package is split by
domain — `onboarding_handlers`, `settings_handlers`, `region_select_handlers`,
`radius_settings_handlers`, `coords_settings_handlers`, `other_handlers`. Shared `router`, the
`PayloadCmd` / `DBStateFilter` filters and helpers live in the sibling
[`_utils/common.py`](../src/max_bot/_utils/common.py). The handlers cover registration and main
menu, district/region selection with pagination, radius, coordinates (text or native geo
button), enable/disable notifications and reset settings. `maxapi` runs the first matching
handler, so `handlers/__init__.py` imports the modules in a fixed order and the catch-all
`on_unknown_text` is registered last. Dialog state is persisted in PostgreSQL via
`DialogState` (`DialogStateMixin`), not in `maxapi`'s in-memory FSM.

**Key details**:

- `Callback.payload` is a JSON string (`str | None`), so the custom `PayloadCmd` filter parses
  it instead of using `F.callback.payload.cmd`.
- `DBStateFilter` matches the persisted `DialogState` for text-input steps.
- Every callback calls `event.ack(notification='...')`: MAX requires a message or a
  notification.
- Native geo button: `RequestGeoLocationButton` attachment.

**Sub-components**:

- [`keyboards.py`](../src/max_bot/_utils/keyboards.py) — `MaxKeyboardButtons`,
  `MaxKeyboardPresets` (`InlineKeyboardBuilder`), pagination with `page_size=6`.
- [`message_formatter.py`](../src/max_bot/_utils/message_formatter.py) — response templates.
- [`bot_polling.py`](../src/max_bot/_utils/bot_polling.py) — long-polling runner.
- [`cli.py`](../src/max_bot/cli.py) — polling mode only; webhook is served by `main.py`.

**Differences from the VK bot**:

| Aspect | VK bot | MAX bot |
| --- | --- | --- |
| Framework | Custom dispatcher + handler chain | `maxapi` Router/Dispatcher |
| Dialog state | `DialogState` in DB | `DialogState` in DB (`DBStateFilter`) |
| Keyboards | Custom JSON builder | `maxapi.InlineKeyboardBuilder` |
| Callback payload | JSON string parsed manually | `Callback.payload` string parsed by `PayloadCmd` |
| Geo button | VK `location` button | `RequestGeoLocationButton` |
| Onboarding | Roles, Moscow prompt | Welcome + main menu |
| Search viewing | Full list + follow/unfollow | Not implemented |
| Notification preferences | All types | Enable/disable + reset |

MAX users do receive notifications: `send_notifications` sends through MAX when
`MAX_BOT_TOKEN` is configured.

## 8. Single-container runtime

[`src/app/`](../src/app/main.py) runs every function in one process:

- [`main.py`](../src/app/main.py) — startup/shutdown, `--check-config`;
- [`dispatch.py`](../src/app/dispatch.py) — topic → handler registry;
- [`queue_worker.py`](../src/app/queue_worker.py) — PostgreSQL queue workers;
- [`scheduler.py`](../src/app/scheduler.py) — cron jobs (cronsim);
- [`http_server.py`](../src/app/http_server.py) — HTTP API, `/health`, `/ready`, optional
  webhooks;
- [`bots.py`](../src/app/bots.py) — long polling for Telegram, VK and MAX;
- [`status.py`](../src/app/status.py) — component status for `/health`.

The full design, configuration and limits are in
[`doc/single-container.md`](single-container.md). The parse → compose → send runbook is
[`doc/runbooks/parse-compose-send-container.md`](runbooks/parse-compose-send-container.md).
