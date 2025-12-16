FROM apache/airflow:latest-python3.12

# Install dependencies as root
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libpq-dev libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - \
    && chmod -R 755 /opt/poetry \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Verify Poetry and Python version
RUN poetry --version && python3 --version

# Switch to airflow user for package installation
USER airflow
WORKDIR /home/airflow

# Copy Poetry configuration files
COPY --chown=airflow:airflow pyproject.toml poetry.lock* ./

# Configure Poetry and install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi --no-root

# Verify installed packages
RUN pip list > /home/airflow/installed_packages.txt

# Set Airflow working directory
WORKDIR /opt/airflow