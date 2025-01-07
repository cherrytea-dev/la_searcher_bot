test:
	pytest .
lint:
	flake8 --config=.flake8/.flake8 src tests
