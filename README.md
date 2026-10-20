# LizaAlert "Searcher Bot"

## Start here

There are three ways to run the project. They share the same function code; only the way the
functions are called differs.

| Mode | How to run | What it is |
| --- | --- | --- |
| **Yandex Cloud Functions** (historical cloud path) | deploy from [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) | timer, YMQ queue and HTTP triggers call one function each. `APP_MODE=yc` (the code default). |
| **Single container** | `make run-app` (or `PYTHONPATH=src uv run python -m app.main`) with `APP_MODE=k8s` and the environment from `.env.example` | one process: HTTP server, cron scheduler, PostgreSQL queue workers and long-polling bots. Docker: `docker compose -f docker-compose.app.yml up --build`. |
| **One bot locally** | `uv run python tests/tools/run_bot.py` | Telegram long polling against your `.env`. Also `run_vk_bot.py` and `run_max_bot.py`. |

How the project is put together: `check_first_posts_for_changes` watches the phpBB forum and
publishes changed topics; `identify_updates_of_*` write diffs to `change_log`;
`compose_notifications` matches them against user preferences and creates `notif_by_user` rows;
`send_notifications` delivers them to Telegram, VK or MAX. Users talk to the same database
through the `communicate`, `vk_bot` and `max_bot` functions. The shared code lives in
[`src/_dependencies/`](src/_dependencies/), and the container runtime in [`src/app/`](src/app/).

[`AGENTS.md`](AGENTS.md) is the project map. Runtime details:
[`doc/single-container.md`](doc/single-container.md) and the
[parse → compose → send runbook](doc/runbooks/parse-compose-send-container.md).

## What is LA Searcher Bot
[LizaAlert](https://lizaalert.org/) (aka LA) – is a non-profit volunteer
Search & Rescue Organization, which helps to find and
rescue lost people across Russian Federation.

LizaAlert volunteers work hard on daily basis to **save lives** by arranging and
speeding up lost-people searches.

This repo covers LA Searcher Bot in following messengers:
- [telegram](https://t.me/LizaAlert_Searcher_Bot)
- [vk](https://vk.com/club237036024)
- [max](https://max.ru/la_searcher_bot)

The bot officially is
not a part of LA central IT solutions, however it is developed from the scratch
& maintained by [one of LA Searchers](https://t.me/MikeMikeT).

Core audience of the Bot – are LA Searchers, that participate in
numerous "field" searches in urban / rural / natural environments.

Bot works by several scenarios:
* It sends personalized notifications on the New Searches
(and Searchers can immediately join the rescue activity)
* It sends updates on the active searches (and Searchers can stay up to date)
* Users can request a list of Active / the Latest searches

Every notification is personalized:
* User can choose his/her Region or list of Regions – and Bot sends
only info from there
* User can enter "home coordinates" – and Bot will
indicate direction & distance to a certain search
* User can tune the types of notifications – and only these types
of messages will be sent

Bot works across the whole Russian Federation.

There is the enthusiasts [Community](https://t.me/+56GrL4LQ-og2NGEy)
for discussion of ideas and issues in the Bot.

Bot was created in mid 2021.
As of January 2023 bot has +9700 active users, DAU (daily active users) +6000,
daily messages +30000. Annual Growth Rate is 2X.

Bot is built as a parser of phpbb [LA Forum](https://lizaalert.org/forum/),
which wraps phpbb-styled information into customized
notification for every user.

## Technological stack

* UI: Telegram + VKontakte + Max + Web-app [LA Map](https://github.com/cherrytea-dev/la_map)
* Language: Python 3.12+
* Git: GitHub
* CI/CD: GitHub Actions
* Infra: Yandex Cloud
* Executors: Yandex Cloud Functions (serverless)
* Message Broker: Yandex Message Queue (YMQ, SQS-compatible)
* Storage: Yandex Managed Service for PostgreSQL, Yandex Object Storage (S3-compatible)
* Monitoring: Yandex Cloud Logging, сервис Логи Selectel (через общий OTel-коллектор ядра — см. ниже)
* VK API: vk-api library
* Max API: maxapi 1.2.0 (native Python SDK)

## Логи (сервис Логи Selectel)

Логи приложений ядра доставляются в **сервис Логи Selectel** (его API совместим с AWS
CloudWatch Logs). Приходит на смену Monium: датацентры Яндекса недоступны, адрес логов
поменялся — см. `infra/docs/DECISIONS.md` (решение от 2026-10-13).

Схема работы: приложение пишет логи в stdout (JSON через `JsonFormatter`) и дополнительно
отправляет их по OpenTelemetry (OTLP, gRPC) в **общий OTel Collector ядра инфраструктуры**
(`http://otel-collector:4317`, сеть `data`). Коллектор пересылает записи в сервис Логи
Selectel (экспортёр `awscloudwatchlogs`). Ключи Selectel знает только коллектор — приложению
они не нужны, доступа к `/var/lib/docker` коллектору тоже не требуется.

Настройка приложения — `src/_dependencies/common/telemetry.py`. OTLP-хендлер вешается на
root logger в `setup_logging_cloud` (`src/_dependencies/common/yandex_tools.py` — облачные
функции и прод-контейнер) и в `setup_logging_to_console` (`tests/common.py` — запуск бота
локально и в докере). Без `OTEL_EXPORTER_OTLP_ENDPOINT` поведение не меняется: логи идут
только в stdout.

### Как это устроено в проде

Приложению не нужен ни свой коллектор, ни ключи логов — оно лишь читает две переменные,
которые уже лежат в файле секретов проекта:

* `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317` — адрес общего коллектора ядра;
* `OTEL_SERVICE_NAME=la_searcher` — имя сервиса, оно же имя стрима в сервисе Логи.

Файл `/srv/infra/secrets/la_searcher.env` создаёт `make db-create APP=la_searcher`
в репозитории infra и подключается как `env_file` в `docker-compose.shared.yml` (вместе
с внешней сетью `data` — там живёт коллектор). Свой коллектор в `docker-compose.prod.yml`
намеренно НЕ поднимается: общий коллектор ядра обслуживает все приложения, а родовое имя
`otel-collector` в плоской DNS сети `data` уже занято им (`infra/docker-compose.yml`).

Если переменная `OTEL_EXPORTER_OTLP_ENDPOINT` пуста, приложение не шлёт логи в OTLP и пишет
только в stdout (`docker compose -p la_searcher logs bot`).

Просмотр логов — в сервисе Логи Selectel: группа логов `SELECTEL_LOGS_GROUP` (по умолчанию
`/apps`), стрим = `OTEL_SERVICE_NAME` приложения (`la_searcher`). Параметры группы и креды
(`SELECTEL_LOGS_*`) задаются в `.env` хоста ядра — приложения их не видят.

## Repository

The repository contains the Python functions, the single-container runtime (`src/app/`), the
shared library (`src/_dependencies/`) and the GitHub Actions workflows that deploy the functions
to Yandex Cloud Functions. The cloud functions are no longer the only way to run the bot: the
same code runs as one container (see [`doc/single-container.md`](doc/single-container.md)).
[Architecture of the original Yandex Cloud Functions deployment](https://htmlpreview.github.io/?https://github.com/cherrytea-dev/la_searcher_bot/blob/main/doc/cloud_functions_architecture.html)

## Contribution

See a dedicated LA Searcher Bot
[contribution page](https://github.com/cherrytea-dev/la_searcher_bot/blob/main/CONTRIBUTING.md).

TL;DR:
* contributions to the current Python-based repo are welcome via pull requests
* contribution to CI/CD, PSQL, Yandex Cloud or
* improvement ideas – let's discuss in [community chat](https://t.me/+56GrL4LQ-og2NGEy).

## Environment 

1. First, prepare your environment:

``` bash
make prepare-environment
```
It will:
- install [UV](https://docs.astral.sh/uv) package/project manager
- create virtual environment
- apply initial settings for VSCode (if not present)
- create container with postgres
- create database for tests

2. Only for VSCode users: Activate virtual environment (commands(Ctrl+Shift+P), Python, create env, virtual env., use existing; close and reopen terminal)

3. Update values in `.env` and `.env.test` files: replace `POSTGRES_HOST=postgres` with `POSTGRES_HOST=localhost`, if you using automatically created postgres instance in docker. 

4. Make sure that the environment variable "PYTHONPATH" is set and the directory "src" is included in it. If not, run the command: export PYTHONPATH=.:src (bash)

Now you can run tests from the tests menu

### Logging level

All functions take their log level from the `LOG_LEVEL` environment variable:
`DEBUG` / `INFO` / `WARNING` (alias `WARN`) / `ERROR` / `CRITICAL`, case-insensitive, spaces tolerated.
If the variable is not set, or its value is not recognized, the code falls back to `WARN`
(and writes an `ERROR` record about the unknown value, so a typo in the environment does not go unnoticed).

Deployment passes `LOG_LEVEL` to every function from the repository variable of the same name
(`Settings -> Secrets and variables -> Actions -> Variables`), defaulting to `WARN` while it is not set.
The same level is used for all functions.

Every record carries `stream_name` — the name of the function that is running. In the cloud that
was the function's package (each function had its own process); in the single container the queue
worker, the cron job, the HTTP route and the bot poller each set it around their call
(`src/_dependencies/common/log_context.py`), so the field points at the function, not at the last
imported module.

Beware that the default `WARN` hides the `INFO` summary of long-running services (`script finished`,
`Lock acquired`, sending analytics). Set the variable to `INFO` if you need those lines back.

Third-party loggers that chat on INFO (`botocore`, `httpx`, `urllib3`, ...) are pinned to `WARNING`
regardless of `LOG_LEVEL`; the single list lives in `NOISY_LOGGERS`
(`src/_dependencies/common/yandex_tools.py`). Do not silence loggers inside other modules.

## Before commit:

1. Run tests: `make test`
2. Run type checker: `make mypy`
3. Format code: `make lint`

## Execution: 

Run tests with postgres database in docker container: `make ci-test`

> Note: on machines without AVX/SSE4.2 support, pin `numpy==1.26.4`
> (`uv pip install numpy==1.26.4`) and run tests without xdist:
> `uv run --no-sync pytest`.

Run the Telegram bot locally: `uv run python tests/tools/run_bot.py` (example is in
[launch.template.json](.vscode/launch.template.json)).

Or run the Telegram bot in the test container: `docker compose up -d`. This is not the single
container; for that use `docker compose -f docker-compose.app.yml up --build` (or `make run-app`).