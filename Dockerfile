# -----------------------------
# Stage 1: Builder
# -----------------------------
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libpq-dev libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 -
ENV PATH="/opt/poetry/bin:$PATH"

WORKDIR /app

COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

# -----------------------------
# Stage 2: Runtime (Airflow DAG Image)
# -----------------------------
FROM apache/airflow:latest

USER root

# Copy poetry-installed dependencies
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

USER airflow
WORKDIR /opt/airflow

# Copy DAGs
COPY dags/ ./dags/
# COPY plugins/ ./plugins/
# COPY config/ ./config/


ENTRYPOINT ["/entrypoint"]
CMD ["api-server"]


