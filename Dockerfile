# -----------------------------
# Stage 1: Builder
# -----------------------------
FROM python:3.11-slim as builder

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry system-wide
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 -

ENV PATH="/opt/poetry/bin:$PATH"

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies into system environment, excluding the project
RUN poetry cache clear --all pypi \
    && poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi -vvv

# -----------------------------
# Stage 2: Final Airflow image
# -----------------------------
FROM apache/airflow:3.0.3

# System dependencies required at runtime
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

USER airflow
WORKDIR /opt/airflow

# Copy DAGs and other necessary files
COPY dags/ /opt/airflow/dags/
COPY siteship-wf/ /opt/airflow/siteship-wf/
# COPY plugins/ /opt/airflow/plugins/

# Set environment variables
ENV AIRFLOW_HOME=/opt/airflow
ENV PYTHONPATH="${AIRFLOW_HOME}:${AIRFLOW_HOME}/siteship-wf"

EXPOSE 8080

ENTRYPOINT ["/entrypoint"]
CMD ["webserver"]