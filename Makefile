SRC_FUNCTIONS_REGEX := '^[a-z].*'
# all dirs not starting with underscore

venv:
	uv sync --all-groups --all-extras --locked

test:
	uv run pytest . -v -n 4 --dist loadgroup

initdb:
	uv run python tests/tools/init_testing_db.py --db=TEST

lint:
	uv run ruff format src tests
	uv run ruff check src tests --select I --fix

lint-check:
	uv run ruff format src tests --check --diff
	uv run ruff check src tests --select I --diff

mypy:
	uv run mypy

requirements:
	for d in $$(ls -1 src | grep -E ${SRC_FUNCTIONS_REGEX}); do \
		uv export --extra $$d --no-hashes > src/$$d/requirements.txt; \
	done

ci-test:
	docker compose run --build --rm bot make initdb
	docker compose run --rm bot make test

dependencies:
	echo "Copy common code to deploy Google Cloud Functions"
	echo "Don't run locally"

	for d in $$(ls -1 src | grep -E ${SRC_FUNCTIONS_REGEX}); do \
		cp src/_dependencies src/$$d/ -r ; \
	done

sqlalchemy-models:
	uv run sqlacodegen \
		postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB} \
		--outfile=tests/factories/db_models.py
	# then fix "_old_search_event_stages"


prepare-environment:
	pip install uv
	make venv
	# Apply initial settings (.env, VSCode):
	cp .vscode/launch.template.json .vscode/launch.json
	cp .vscode/settings.template.json .vscode/settings.json
	cp .env.example .env
	cp .env.example .env.test
