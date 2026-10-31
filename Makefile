SRC_FUNCTIONS_REGEX := '^[a-z].*'
# all dirs not starting with underscore

venv:
	uv sync --all-groups --all-extras --locked

test:
	make initdb
	uv run pytest -v -n 4 --dist loadgroup

# CI runs the tests in a single process: xdist workers share one test database and their
# interleaving is a source of flaky runs. Slower, but stable (see .github/workflows/test.yml).
test-serial:
	make initdb
	uv run pytest -v

initdb:
	PYTHONPATH=.:src uv run python tests/tools/init_testing_db.py --db=TEST

initdb-data:
	PYTHONPATH=.:src uv run python tests/tools/init_testing_db.py --db=TEST --init-data-only

# Lint the whole tree, not just the shipped package: tools/ and scripts/ share the same
# ruff config (pyproject.toml), so leaving them out of CI lets their findings rot unnoticed.
LINT_PATHS := src tests tools scripts

lint:
	uv run ruff format $(LINT_PATHS)
	uv run ruff check $(LINT_PATHS) --fix

lint-check:
	uv run ruff format $(LINT_PATHS) --check --diff
	uv run ruff check $(LINT_PATHS) --diff

mypy:
	uv run mypy

precommit: lint mypy

ci-test:
	# docker compose run --build --rm bot make initdb
	docker compose run --rm bot make test-serial

dependencies:
	echo "Copy common code into each cloud function package"
	echo "Don't run locally"

	# `app` is the single-container runtime (see doc/single-container.md), not a cloud function:
	# it imports src/_dependencies directly and must not get a copy of it.
	for d in $$(ls -1 src | grep -E ${SRC_FUNCTIONS_REGEX} | grep -vx app); do \
		cp src/_dependencies src/$$d/ -r ; \
	done

run-app:
	# single container: HTTP + scheduler + queue workers + bots
	PYTHONPATH=src uv run python -m app.main

check-app-config:
	PYTHONPATH=src uv run python -m app.main --check-config

sqlalchemy-models:
	uv run sqlacodegen \
		postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB} \
		--outfile=tests/factories/db_models.py


prepare-environment:

	# Apply initial settings (.env, VSCode):
	cp -n .vscode/launch.template.json .vscode/launch.json
	cp -n .vscode/settings.template.json .vscode/settings.json

	# create .env files for running tests and for local debug
	cp -n .env.example .env
	cp -n .env.example .env.test

	# create venv
	pip install uv
	make venv

	# prepare test database
	docker compose run --build --rm bot make initdb

recreate-local-db:
	docker compose run --build --rm bot uv run python tests/tools/init_testing_db.py --db=PROD
