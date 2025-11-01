# Stage 1: Builder
FROM python:3.10-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && mv /root/.local /opt/poetry \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

ENV PATH="/usr/local/bin:/opt/poetry/bin:$PATH"

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to install in the same environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi

# Stage 2: Final Airflow image
FROM apache/airflow:3.1.1-python3.11

# Switch to root to install system dependencies
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

USER airflow
WORKDIR /opt/airflow

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy DAGs and plugins
COPY dags/ /opt/airflow/dags/
# COPY plugins/ /opt/airflow/plugins/

# Set environment variables
ENV AIRFLOW_HOME=/opt/airflow
ENV PYTHONPATH="${AIRFLOW_HOME}"

EXPOSE 8080

ENTRYPOINT ["/entrypoint"]
CMD ["webserver"]
