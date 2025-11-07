# Use the official Airflow image
FROM apache/airflow:latest

# Install dependencies as root
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libpq-dev libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry globally and ensure accessibility
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Set PATH for all users
ENV PATH="/root/.local/bin:/usr/local/bin:$PATH"

# Switch to airflow user for package installation
USER airflow
WORKDIR /home/airflow

# Copy Poetry configuration files
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