# Base Airflow image
FROM apache/airflow:3.1.1-python3.11

# Switch to root to install OS packages and Poetry
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

# Install Poetry system-wide (for all users)
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && mv /root/.local /opt/poetry \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Verify Poetry is installed (optional)
RUN /usr/local/bin/poetry --version

# Switch back to airflow user
USER airflow
WORKDIR /opt/airflow

# Add Poetry to PATH explicitly for airflow user
ENV PATH="/usr/local/bin:/opt/poetry/bin:$PATH"

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Disable virtualenv creation (install into system Python)
RUN poetry config virtualenvs.create false

# Install Python dependencies
RUN poetry install --no-interaction --no-ansi

# Copy DAGs and plugins
COPY dags/ /opt/airflow/dags/
COPY plugins/ /opt/airflow/plugins/

# Environment variables
ENV AIRFLOW_HOME=/opt/airflow
ENV PYTHONPATH="${AIRFLOW_HOME}"

EXPOSE 8080

ENTRYPOINT ["/entrypoint"]
CMD ["webserver"]
