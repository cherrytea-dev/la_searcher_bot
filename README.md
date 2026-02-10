# LizaAlert "Searcher Bot"

## What is LA Searcher Bot
[LizaAlert](https://lizaalert.org/) (aka LA) – is a non-profit volunteer 
Search & Resque Organization, which helps to find and 
resque lost people across Russian Federation.

LizaAlert volunteers work hard on daily basis to **save lives** by arranging and 
speeding up lost-people searches.

This repo covers [LA Searcher Bot](https://t.me/LizaAlert_Searcher_Bot). The bot officially is 
not a part of LA central IT solutions, however it is developed from the scratch 
& maintained by [one of LA Searchers](https://t.me/MikeMikeT).

Core audience of the Bot – are LA Searches, that participate in
numerous "field" searches in urban / rural / natural environments.

Bot works by several scenarios:
* It sends personalized notifications on the New Searches 
(and Searchers can immediately join the resque activity)
* It sends updates on the active searches (and Searches can stay up to date)
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

* UI: Telegram + Web-app [LA Map](https://github.com/cherrytea-dev/la_map)
* Language: Python 3.10 
* Git: GitHub
* CI/CD: GitHub Actions
* Infra: Google Cloud Platform
* Executors: Google Cloud Functions
* Message Broker: Google Pub/Sub
* Storage: Google Cloud SQL (Postgres), Cloud Storage, BigQuery
* Monitoring: Google Cloud Logging, Looker Studio

## Repository 

This repository covers only python scripts, which are sent to Google 
Cloud Functions and GitHub Actions Workflow files.
[Architecture of Google Cloud Functions](https://htmlpreview.github.io/?https://github.com/cherrytea-dev/la_searcher_bot/blob/main/doc/cloud_functions_architecture.html)

## Contribution

See a dedicated LA Searcher Bot 
[contribution page](https://github.com/cherrytea-dev/la_searcher_bot/blob/main/CONTRIBUTING.md).

TL;DR: 
* contributions to the current Python-based repo are welcome via pull requests
* contribution to CI/CD, PSQL, GCP or
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

4. Now you can run tests from the tests menu

## Before commit: 

1. Run tests: `make ci-test` (or new but unstable 'make test')
2. Run type checker: `make mypy`
3. Format code: `make lint`
4. Update nested "requirements.txt" files, if you changed "pyproject.toml": `make requirements`

## Execution: 

Run tests with postgres database in docker container: `make ci-test`

Run bot locally: `uv run python tests/tools/run_bot.py` (example is in [launch.template.json](.vscode/launch.template.json) )

Or run bot in container: `docker compose up -d`