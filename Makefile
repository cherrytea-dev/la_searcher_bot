test:
	pytest .

lint:
	ruff format src tests --line-length=120
	ruff check src tests --fix --line-length=120

lint-check:
	ruff check src tests --line-length=120
