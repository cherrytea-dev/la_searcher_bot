test:
	pytest .

lint:
	ruff format src tests --line-length=120 --config "format.quote-style = 'single'"
	ruff check src tests --fix --line-length=120 --config "format.quote-style = 'single'"

lint-check:
	ruff check src tests --line-length=120 --config "format.quote-style = 'single'"
	ruff format src tests --check --line-length=120 --config "format.quote-style = 'single'"
