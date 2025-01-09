venv:
	uv sync --all-groups --all-extras

test:
	pytest .

lint:
	uv run ruff format src tests
	uv run ruff check src tests

lint-check:
	uv run ruff check src tests
	uv run ruff format src tests

requirements:
	for d in $$(ls -1 src); do \
		uv export --extra $$d --no-hashes > src/$$d/requirements.txt; \
	done
