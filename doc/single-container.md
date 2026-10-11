# Единый контейнер: la_searcher_bot без Yandex Cloud Functions

Статус: в работе (ветка `feat/single-container`).
Цель: один контейнер, в котором живут все 18 функций репозитория. Целевые лимиты —
**1 CPU / 1 GB RAM**. Причина переезда: облако больше не тянет.

## Что было

Три способа запуска (по `terraform/`):

| Триггер | Функции |
|---|---|
| **Cron** | `check_first_posts_for_changes` (каждую минуту), `archive_to_bigquery` (11:13 ежедневно), `archive_notifications` (каждый час) |
| **HTTP (API-gateway)** | `communicate` (вебхук Telegram), `vk_bot`, `max_bot`, `api_get_active_searches`, `user_provide_info`, `title_recognize` (вызывается по HTTP другими функциями) |
| **Очередь YMQ** | `compose_notifications`, `send_notifications`, `identify_updates_of_topics`, `identify_updates_of_first_posts`, `connect_to_forum`, `send_debug_to_admin`, `archive_notifications` |

Сердце системы — pub/sub-цепочка: `check_first_posts` → очередь → `identify_updates_of_topics`
→ `compose_notifications` → `send_notifications`.

## Что стало

Один процесс (`python -m app.main`), внутри четыре подсистемы:

1. **Очередь на PostgreSQL** (`_dependencies/common/queue_pg.py`) — вместо YMQ.
   Таблица `pubsub_messages`: `INSERT` на публикацию, `UPDATE ... FOR UPDATE SKIP LOCKED`
   на получение, backoff и dead-letter при ошибках, visibility timeout для сообщений,
   чей воркер умер. Отдельный брокер не нужен — очередь живёт в той же БД, что и данные.
2. **Воркеры** (`app/queue_worker.py`) — N потоков, каждый забирает сообщение из очереди и
   вызывает существующую функцию `main(event, context)` **без изменений**: событие
   собирается в том же YC-формате (`{'messages': [{'details': {'message': {'body': ...}}}]}`),
   поэтому `process_pubsub_message(event)` продолжает работать как раньше.
3. **Планировщик** (`app/scheduler.py` + `_dependencies/common/cron.py`) — три cron-джоба
   вместо timer-триггеров. Выражения разбирает библиотека `cronsim` (чистый Python, без своих
   зависимостей, семантика Debian-cron, живёт в Healthchecks) — свой матчер не пишем.
4. **HTTP-сервер** (`app/http_server.py`, стандартная библиотека) — эндпоинты веб-приложения
   (`api_get_active_searches`, `user_provide_info`), пробы `/health` (liveness, БД не трогает)
   и `/ready` (readiness, отвечает очередь) и (по флагу) вебхуки ботов. Функции вызываются
   через тот же `@request_response_converter`, что и в облаке: сервер собирает YC-запрос
   `{'httpMethod', 'body', 'headers'}` и разбирает ответ. У async-вебхука (`max_bot`) один
   общий event loop в отдельном потоке — как в облаке, где loop жил между вызовами.

Дополнительно:

* **Боты** (`app/bots.py`) — long-polling вместо вебхуков: Telegram (`Updater.start_polling`),
  VK (`VkLongPoll`), MAX (`dp.start_polling`). Публичный ingress для ботов не нужен.
* **`title_recognize`** — прямой вызов в процессе вместо HTTP-хопа
  (`recognize_title_via_api`; включается режимом `APP_MODE=k8s`).
* **Снаружи остаются**: PostgreSQL, Object Storage (S3-совместимый), форумный phpbb (MySQL),
  сами форумы. В контейнер их не тащим.

## Конфигурация (env)

Все новые ключи — в `AppConfig` (`_dependencies/common/commons.py`), читаются
pydantic-settings'ом из окружения:

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `APP_MODE` | `yc` | режим работы: `yc` — функции в облаке, `k8s` — единый контейнер. Всё, что зависит от режима, выводится из него (таблица ниже) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `10` при `APP_MODE=k8s`, иначе `2` / `2` | размер пула соединений БД; дефолт следует за режимом, env переопределяет |
| `WORKER_THREADS` | `2` | сколько сообщений обрабатывается параллельно |
| `WORKER_POLL_INTERVAL_SECS` | `1.0` | пауза, когда очередь пуста |
| `QUEUE_VISIBILITY_TIMEOUT_SECS` | `900` | через сколько возвращать «зависшее» сообщение в очередь |
| `QUEUE_MAX_ATTEMPTS` | `5` | после этого — dead letter (`status='failed'`) |
| `QUEUE_RETRY_BASE_SECS` / `QUEUE_RETRY_MAX_SECS` | `30` / `900` | экспоненциальный backoff |
| `SCHEDULER_TIMEZONE` | `UTC` | пояс, в котором считаются cron-расписания |
| `HTTP_HOST` / `HTTP_PORT` | `0.0.0.0` / `8080` | адрес HTTP-сервера |
| `CRON_CHECK_FIRST_POSTS` | `* * * * *` | расписание джобов (5 полей) |
| `CRON_ARCHIVE_TO_BIGQUERY` | `13 11 * * *` | |
| `CRON_ARCHIVE_NOTIFICATIONS` | `0 * * * *` | |
| `API_PATH_ACTIVE_SEARCHES` | `/api/v1/active-searches` | путь для веб-приложения |
| `API_PATH_USER_INFO` | `/api/v1/user-info` | путь для веб-приложения |

Из `APP_MODE` выводится всё, что описывает способ развёртывания. Это **не настройки**, а
свойства конфига: смешанных состояний (например, локальное распознавание заголовков поверх
очереди YMQ) быть не может.

| Что | `APP_MODE=yc` | `APP_MODE=k8s` |
|---|---|---|
| очередь | `ymq` — Yandex Message Queue | `pg` — таблица в PostgreSQL |
| распознавание заголовков | по HTTP, функцией `title_recognize` | в процессе |
| cron-планировщик | выключен (в облаке работают timer-триггеры) | включён |
| HTTP-сервер | выключен (функции вызывает API-gateway) | включён |
| боты | выключены (каждый бот — своя функция) | long-polling всех трёх |

> Пути API настраиваемые: в облаке их задавал API-gateway, в репозитории их нет.
> Перед выкаткой сверить с фронтендом и при необходимости поменять через env.

> Дефолт в коде — «облачный» (`APP_MODE=yc`): деплой облачных функций ничего не меняет.
> Контейнер включает новый режим явно — в `.env.example` стоит `APP_MODE=k8s`. Воркеры
> очереди и планировщик запускаются только в режиме `k8s`.

## Схема БД

Таблица создаётся самим приложением при старте (`CREATE TABLE IF NOT EXISTS`), отдельная
миграция не нужна:

```sql
CREATE TABLE IF NOT EXISTS pubsub_messages (
    id            bigserial PRIMARY KEY,
    topic         text        NOT NULL,
    payload       jsonb       NOT NULL,
    status        text        NOT NULL DEFAULT 'pending',  -- pending|processing|done|failed
    attempts      integer     NOT NULL DEFAULT 0,
    available_at  timestamptz NOT NULL DEFAULT now(),
    locked_at     timestamptz,
    locked_by     text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    last_error    text
);
```

## Запуск

```bash
# локально: приложение + postgres
docker compose -f docker-compose.app.yml up --build
curl localhost:8080/health
```

## Бюджет 1 CPU / 1 GB

* база процесса (Python + SQLAlchemy/psycopg2 + SDK мессенджеров + bs4/lxml) ≈ 200–350 MB;
* пик даёт распознавание (pymorphy3, словари грузятся лениво) и параллельные воркеры;
* рычаги, если упрёмся: `WORKER_THREADS=1`, `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` поменьше, режим
  «процесс на сообщение» (изоляция памяти, пока не реализован — потоки дешевле по CPU).
  Боты и распознавание включаются вместе с режимом `k8s`: отдельного «контейнера без
  telegram-бота» нет — понадобится, это будет новая настройка, а не комбинация старых.

## Что проверено

* `make lint-check` и `make mypy` — чисто (182 файла).
* Полный прогон тестов: **1091 passed, 18 skipped** — включая новые тесты очереди (unit + интеграция
  на живой PostgreSQL), cron-матчера, воркеров, реестра топиков, HTTP-слоя и реестра статусов.
* Очередь на живой PostgreSQL 16 (`tests/test_queue_pg_integration.py`, тот же сценарий теперь в CI):
  publish/claim, отложенные сообщения, visibility timeout (`requeue_stale`), backoff и dead letter;
  и главное — 4 воркера разбирают 40 сообщений, ни одно не выдано дважды (`FOR UPDATE SKIP LOCKED`).
* Смоук всего контейнера (`python -m app.main`: HTTP + 2 воркера): `/health` (liveness) → 200,
  `/ready` → 200 со статистикой очереди, неизвестный путь → 404, сообщение, положенное в таблицу руками, разобрано воркером
  (хендлер `send_debug_to_admin` импортировался лениво, вызвался и вернул ответ), `SIGTERM` →
  корректная остановка компонентов.

## Известные мелочи

* `setup_logging_cloud` при импорте каждой функции перевешивает root-хендлер на свой
  `stream_name` — в одном процессе поле `stream_name` в логах становится именем последней
  импортированной функции. В облаке это было незаметно (у каждой функции свой процесс).
  Косметика, не трогал.
* Очередь живёт в той же БД, что и данные: при пересоздании базы (как `make initdb`) сообщения
  теряются. Для боевой базы это не проблема (её не пересоздают), но помнить стоит.
* HTTP-сервер держит не больше 32 одновременных хендлеров и закрывает соединение через 30 с.
  Зависший хендлер (например, `communicate` на медленном форуме) занимает слот, пока не
  ответит, — слоты ограничены, поэтому число потоков не растёт бесконечно.

## Открытые вопросы

* Реальный пик RSS/CPU на боевом профиле нагрузки — замерить на месте (в облаке замер снять
  не успели).
* Пути API-эндпоинтов сверить с фронтендом «Карты».
* `check_first_posts_for_changes` раз в минуту с `ThreadPoolExecutor(max_workers=8)` —
  единственное место, которое может упереться в 1 vCPU.
* Что перезапускается при падении: контейнер целиком (k8s restartPolicy) — окно простоя
  ≈ время старта процесса.
