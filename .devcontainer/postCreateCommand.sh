# sed -i -e 's/PYTHONPATH=$/PYTHONPATH=src/g' ./src/.env

# продублировать файлы в корень для удобства работы с poetry
# ln -r -s src/.env .env
# ln -r -s src/pyproject.toml pyproject.toml
# ln -r -s src/poetry.lock poetry.lock

# инициализировать настройки vscode
cp ./.vscode/launch.template.json ./.vscode/launch.json
cp ./.vscode/settings.template.json ./.vscode/settings.json


# POETRY_VIRTUALENVS_CREATE=false poetry install -C src