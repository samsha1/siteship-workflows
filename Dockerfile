# Base Airflow image
FROM apache/airflow:2.9.1-python3.10

# Switch to root to install system deps
USER root

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        build-essential \
        libpq-dev \
        libssl-dev \
        libffi-dev \
        && rm -rf /var/lib/apt/lists/*

# Install Poetry globally
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Switch back to airflow user
USER airflow
WORKDIR /opt/airflow

# Copy dependency files first (for layer caching)
COPY pyproject.toml poetry.lock* ./

# Ensure poetry is available in PATH for airflow user
ENV PATH="/usr/local/bin:$PATH"

# Configure Poetry to use the same env as Airflow
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi

# Copy DAGs and plugins
COPY dags/ /opt/airflow/dags/
# COPY plugins/ /opt/airflow/plugins/

# Environment variables
ENV AIRFLOW_HOME=/opt/airflow
ENV PYTHONPATH="${AIRFLOW_HOME}"

EXPOSE 8080

ENTRYPOINT ["/entrypoint"]
CMD ["webserver"]
