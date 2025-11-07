# Use the official Airflow image
FROM apache/airflow:latest

# Install dependencies as root
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libpq-dev libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry for the airflow user
USER airflow
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/airflow/.local/bin:$PATH"

# Copy Poetry configuration files
WORKDIR /home/airflow
COPY --chown=airflow:airflow pyproject.toml poetry.lock* ./

# Install dependencies to the airflow user's site-packages
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

# Set Airflow working directory
WORKDIR /opt/airflow

# Copy DAGs, plugins, and config (uncomment as needed)
# COPY --chown=airflow:airflow dags/ ./dags/
# COPY --chown=airflow:airflow plugins/ ./plugins/
# COPY --chown=airflow:airflow config/ ./config/

# Entry point for Airflow
ENTRYPOINT ["/entrypoint"]
CMD ["api-server"]