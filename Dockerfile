# Use official Airflow base image
FROM apache/airflow:2.9.1-python3.10

# Switch to root to install system deps
USER root

# Install OS dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        build-essential \
        libpq-dev \
        libssl-dev \
        libffi-dev \
        && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /home/airflow/.local/bin/poetry /usr/local/bin/poetry

# Switch back to airflow user
USER airflow
WORKDIR /opt/airflow

# Copy only dependency files first (for layer caching)
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to install packages in the same environment as Airflow
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi

# Copy application files (DAGs, plugins, etc.)
COPY dags/ /opt/airflow/dags/
COPY plugins/ /opt/airflow/plugins/

# Set environment variables
ENV AIRFLOW_HOME=/opt/airflow
ENV PYTHONPATH="${AIRFLOW_HOME}"

# Expose port
EXPOSE 8080

# Default command
ENTRYPOINT ["/entrypoint"]
CMD ["webserver"]
