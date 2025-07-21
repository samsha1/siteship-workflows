FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.7.1
RUN pip install "poetry==$POETRY_VERSION"

# Set workdir
WORKDIR /app

# Copy only requirements to cache dependencies
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Copy rest of the code
COPY . .

# Airflow env vars
ENV AIRFLOW_HOME=/app/airflow
RUN mkdir -p $AIRFLOW_HOME

# Expose Airflow webserver port
EXPOSE 8080

# Entrypoint for Airflow webserver
CMD ["airflow", "webserver"] 