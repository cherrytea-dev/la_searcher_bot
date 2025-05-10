FROM python:3.10-slim AS template

ENV PYTHONPATH=src
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install --assume-yes make && \
    apt-get clean

RUN pip install uv


WORKDIR /opt/bot

FROM template AS vscode_devcontainer

COPY pyproject.toml uv.lock ./
COPY .env.example .env.test

COPY Makefile ./
RUN --mount=type=cache,destination=/root/.cache/uv <<EOF
    make venv
EOF

COPY src ./src
COPY tests ./tests
