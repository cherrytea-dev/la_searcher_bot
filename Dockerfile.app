# Single container: every function of this repository in one process.
# See doc/single-container.md. The multi-stage Dockerfile next door is for tests/CI — this one
# is what goes to k8s.
FROM python:3.12-slim

ENV PYTHONPATH=/opt/bot/src \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/bot/.venv \
    UV_LINK_MODE=copy \
    PATH=/opt/bot/.venv/bin:$PATH

RUN apt-get update && \
    apt-get install --assume-yes --no-install-recommends make g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir uv

WORKDIR /opt/bot

COPY pyproject.toml uv.lock ./
# --all-extras: one process has to be able to run every function (see [optional-dependencies]).
# --no-dev: the test/lint toolchain stays out of the image.
RUN uv sync --locked --no-dev --all-extras

COPY src ./src
COPY doc ./doc
# The one-shot `migrate` service runs scripts/apply_db_migrations.py (it reads doc/migrations/),
# so the image has to carry the script — otherwise the container has no `scripts/` at all.
COPY scripts ./scripts

# The app writes nothing inside the image: it only needs to reach PostgreSQL.
RUN useradd --create-home --uid 10001 bot && \
    chown -R bot:bot /opt/bot
USER bot

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"

CMD ["python", "-m", "app.main"]
