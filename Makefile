venv:
	uv sync --all-groups --all-extras

test:
	uv run pytest .

lint:
	uv run ruff format src tests
	uv run ruff check src tests --fix

lint-check:
	uv run ruff format src tests --check
	uv run ruff check src tests

requirements:
	for d in $$(ls -1 src); do \
		uv export --extra $$d --no-hashes > src/$$d/requirements.txt; \
	done
