# Use Airflow image with explicit Python 3.12 to match your expected path
FROM apache/airflow:latest-python3.12

# Install dependencies as root
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libpq-dev libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - \
    && chmod -R 755 /opt/poetry \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Verify Poetry and Python version (for debugging)
RUN poetry --version && python3 --version

# Switch to airflow user for package installation
USER airflow
WORKDIR /home/airflow

# Copy Poetry configuration files
COPY --chown=airflow:airflow pyproject.toml poetry.lock* ./

# Install dependencies to the airflow user's site-packages (use verbose for debugging if needed)
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

# Verify installed packages
RUN pip list --user > /home/airflow/installed_packages.txt

# Set Airflow working directory
WORKDIR /opt/airflow

# Copy DAGs, plugins, and config (uncomment as needed)
# COPY --chown=airflow:airflow dags/ ./dags/
# COPY --chown=airflow:airflow plugins/ ./plugins/
# COPY --chown=airflow:airflow config/ ./config/

# Entry point for Airflow
ENTRYPOINT ["/entrypoint"]
CMD ["api-server"]