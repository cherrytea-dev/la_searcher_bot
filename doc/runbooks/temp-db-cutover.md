# Временная БД: бот на бэкапе (runbook)

Статус: рабочий документ под ветку `feat/temp-db-mode`.
Контекст: прод-БД упала. Поднимаем бота на бэкапе (состояние на **08.10.2026**) на своей инфре
(PostgreSQL + docker compose, без k8s — см. `doc/single-container.md`). Задача — чтобы
пользователи получали уведомления только о поисках, начатых **начиная с 08.10.2026**, и не
получили залпом весь backlog за месяцы.

## Чем этот прогон отличается от обычного

* **Форум в legacy-режиме** (`FORUM_LEGACY_DATA_SOURCE=true`). Значит:
  * нет `LAST_CHANGE_ID_IN_PHPBB_DB` и нет MySQL-истории — «baseline», который можно было бы
    сдвинуть, отсутствует;
  * детект изменений — `check_first_posts_for_changes/_legacy`: берёт из БД поиски
    `status='Ищем'`, делит на 20 групп по 5% и опрашивает первую страницу каждой по HTTP,
    сравнивая хеш с `search_first_posts.content_hash`;
  * новые поиски добираются косвенно: изменение first post → `parse_folders` →
    `identify_updates_of_topics` перепарсивает папку и вставляет новые поиски.
* **Против залпа — только SQL-подготовка** (см. «Перед стартом»): висящие уведомления в
  `notif_by_user` отменяются вручную. Никакого «обнулить baseline» здесь нет.

## Настройки (env)

| Переменная | Значение для temp | Смысл |
|---|---|---|
| `ARCHIVE_TO_BIGQUERY_ENABLED` | `false` | BigQuery/S3 недоступны — ежедневный джоб пропускается целиком |
| `WEBHOOK_PATH_TELEGRAM` / `_VK` / `_MAX` | `/webhook/telegram` и т.п. | непустое значение = поллер бота не стартует (бот не читает апдейты) |
| `APP_MODE` | `k8s` | это режим «единый контейнер»; docker compose подходит, k8s не обязателен |

## Перед стартом (SQL на восстановленном бэкапе)

```sql
-- 1) схема: код требует миграции 004/005/008 — если бэкап старше, применить doc/migrations/*
SELECT to_regclass('public.user_identity_map');                 -- 004: должно быть НЕ NULL
SELECT column_name FROM information_schema.columns
 WHERE table_name='notif_by_user' AND column_name='messenger';  -- 005: должна быть строка
SELECT indexname FROM pg_indexes
 WHERE indexname='notif_by_user_unique_unsent_idx';             -- 008: должен быть индекс

-- 2) висяки: send_notifications шлёт всё с completed IS NULL — отменяем, чтобы не улетело залпом
UPDATE notif_by_user SET cancelled = now() WHERE completed IS NULL AND cancelled IS NULL;

-- 3) записи, снятые «в полёте»: перекомпоузятся
UPDATE change_log SET notification_sent = NULL WHERE notification_sent = 's';
```

## Старт

```bash
cp .env.example .env.app   # заполнить токены и POSTGRES_*
docker compose -f docker-compose.app.yml up --build -d
curl -s localhost:8080/health
```

Ожидаемо на первом прогоне: тяжёлый HTTP-шторм к форуму (пересоздание first posts + перепарсинг
папок) и большой объём записей в `change_log`. Уведомления по старым поискам при этом
композер соберёт — поэтому висяки в `notif_by_user` отменены заранее (шаг 2 SQL выше), а
очередь стоит посматривать руками. Группы дренятся с частотой 2^n — «добор» 08.10→now
занимает время, не мгновенно. Если нужен гарантированный добор новых поисков — прогнать
`identify_updates_of_topics` по нужным папкам один раз вручную.

## Возврат на прод-БД

1. Поднять прод-БД (состояние на 08.10) и переключить бота на неё.
2. Гасить temp **целиком** (поллеры + воркеры) до старта прод-бота — два поллера на одном
   токене дают 409 и дубли.
3. Если у Telegram-бота был webhook — снять (`deleteWebhook`), иначе апдейты уйдут не туда.

## Оговорки

* 2-дневное правило для «новых» поисков (`topic_new`) не трогаем — анонсы поисков, начатых
  08.10–10.10, отсекутся (им уже ≥2 дней).
