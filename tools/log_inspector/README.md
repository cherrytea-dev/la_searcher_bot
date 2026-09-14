# YC Log Inspector

Инструмент для разбора ошибок в **Yandex Cloud Logging** (gRPC через `yandexcloud` SDK).

Используется для расследования проблем на проде бота (ЛизаАлерт).

## Установка и авторизация

```bash
uv sync --all-groups --all-extras --locked
```

Авторизация — через сервисный аккаунт:

```bash
yc iam key create --service-account-name <name> --output key.json
export YC_LOG_INSPECTOR_SA_JSON="$(cat key.json)"
```

## Команды

```bash
# Топ ошибок за 24 часа
uv run python -m tools.log_inspector.main top-errors <log-group-id> --hours 24 --top 10

# Полный трейс по конкретному request_id
uv run python -m tools.log_inspector.main trace <log-group-id> <request-id> --hours 24

# Список лог-групп в каталоге
uv run python -m tools.log_inspector.main list-groups <folder-id>

# Сырой JSON (для скриптов)
uv run python -m tools.log_inspector.main raw <log-group-id> --hours 1 --level ERROR

# Объём логов по сервисам за сутки (читает окно по часам, ~1 мин на час)
uv run python -m tools.log_inspector.main volume <log-group-id> --hours 24
```

## Как найти log-group-id

```bash
YC_LOG_INSPECTOR_SA_JSON="$YC_LOG_INSPECTOR_SA_JSON" \
  uv run python -m tools.log_inspector.main list-groups <folder-id>
```

## Важные грабли YC Logging (найдены 2026-08-15)

### 1. `page_token` и `criteria` — это protobuf `oneof` ⚠️

В `ReadRequest` поля `page_token` и `criteria` **взаимоисключающие**.
Нельзя передать `ReadRequest(criteria=..., page_token=...)` — criteria **молча отбрасывается**,
и вы получите пустые/неправильные страницы.

**Правильно:**
- Первый запрос: `ReadRequest(criteria=...)`
- Последующие: `ReadRequest(page_token=...)` — **без criteria**

### 2. `until` в criteria ломает пагинацию ⚠️

Если в criteria указан `until` (верхняя граница времени), первая страница приходит,
но следующий `page_token`-запрос возвращает **пустую страницу** (и пагинация обрывается).

**Правильно:** не отправлять `until` вообще. Читать от `since` до «сейчас»,
а `to_time` отфильтровывать на клиенте по `timestamp`.

### 3. Большие окна и gRPC UNAVAILABLE

- Запрос на 24+ часа с фильтром может упасть с `UNAVAILABLE: could not handle request`.
- Сессия чтения ограничена (~20k записей).
- Наблюдались «дырявые» страницы: 100 записей, потом пусто, потом снова 100.

**Правильно:** дробить окно на часовые куски (`slice_hours=1.0` по умолчанию в `read_all_logs`)
и делать ретраи на каждый кусок.

### 4. Следствие: раньше top-errors показывал только 100 записей

Из-за граблей №1–№2 старый код видел только первую страницу (~100 записей)
и выдавал «100 ERROR entries» даже за неделю, хотя реально ошибок было 497.
**Если видите ровно 100 записей — это симптом, а не реальное число.**

## Команда `volume` — кто съедает логи

Отвечает на вопрос «сколько логов в сутки и какой сервис их пишет»: таблица по сервисам
(записи, МБ, доля, байт на запись, МБ/сутки, записей/сутки), уровни, топ сообщений
и самые «жирные» отдельные записи. Группировка — по `json_payload['stream_name']`
(имя пакета из `setup_logging(__package__)`), иначе по платформенному `stream_name`.

Чтение идёт часовыми слайсами с фолдом на лету — память не зависит от размера окна.
На продовой группе ЛизаАлерт час — это ~50 тыс. записей и ~30 МБ, то есть ~70 секунд
на слайс; полные сутки ≈ 25–30 минут:

```bash
# Полные сутки
uv run python -m tools.log_inspector.main volume <log-group-id> --hours 24

# Быстрая оценка: каждый шестой час, остальное экстраполируется (≈5 минут)
uv run python -m tools.log_inspector.main volume <log-group-id> --hours 24 --sample-every 6

# Машиночитаемо
uv run python -m tools.log_inspector.main volume <log-group-id> --hours 24 --json
```

Для справки, замер на продовой группе (2026-09-14): **0,96 ГБ и ~1,62 млн записей в сутки**,
больше половины объёма — `send_notifications` и `identify_updates_of_topics._legacy`.

⚠️ **Что именно считается.** Размер записи — это её JSON в том виде, как его отдаёт Logging API
(после `MessageToDict`), в UTF-8 байтах. Это стабильный **прокси** для объёма хранения, а не
точная цифра биллинга YC: обвязка/метаданные платформы в него не входят. Ориентироваться стоит
на соотношение сервисов и на порядок величины, а не на байт в байт.

## Структура

```
tools/log_inspector/
├── main.py                      # CLI (click): top-errors / trace / list-groups / volume / raw
├── _utils/
│   ├── yc_logging.py            # gRPC-клиент: YCLoggingClient (auth, list, read)
│   ├── analytics.py             # нормализация ошибок и агрегация по шаблонам
│   └── volume.py                # агрегация объёма по сервисам (команда volume)
└── README.md
```

## Тесты

```bash
uv run pytest tests/test_log_inspector -q
```
