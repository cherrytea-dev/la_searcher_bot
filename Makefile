SRC_FUNCTIONS_REGEX := '^[a-z].*'
# all dirs not starting with underscore

venv:
	uv sync --all-groups --all-extras --locked

test:
	uv run pytest .

lint:
	uv run ruff format src tests
	uv run ruff check src tests --select I --fix

lint-check:
	uv run ruff format src tests --check
	uv run ruff check src tests --select I

requirements:
	for d in $$(ls -1 src | grep -E ${SRC_FUNCTIONS_REGEX}); do \
		uv export --extra $$d --no-hashes > src/$$d/requirements.txt; \
	done

ci-test:
	docker compose run --build --rm bot make test


dependencies:
	# copy common code to deploy Google Cloud Functions
	for d in $$(ls -1 src | grep -E ${SRC_FUNCTIONS_REGEX}); do \
		cp src/_dependencies src/$$d/ -r ; \
	done
	