# Siteship Workflows

This project provides an Apache Airflow workflow to:
1. Unzip a Supabase storage file (.zip)
2. Push files to Github
3. Deploy to Vercel

## Project Structure
- `src/siteship_workflows/dags.py`: Main Airflow DAG and tasks
- `Dockerfile`: Container setup for Airflow and Poetry
- `.gitignore`: Standard Python, Poetry, Airflow, and venv ignores
- `pyproject.toml`: Poetry dependency management

## Setup

### 1. Install Poetry
[Poetry installation guide](https://python-poetry.org/docs/#installation)

### 2. Install dependencies
```bash
poetry install
```

### 3. Activate the virtual environment
```bash
poetry shell
```

### 4. Run Airflow (local)
```bash
airflow db init
airflow webserver
```

### 5. Run with Docker
```bash
docker build -t siteship-workflows .
docker run -p 8080:8080 siteship-workflows
```

## Customization
- Update `src/siteship_workflows/dags.py` with your Supabase, Github, and Vercel credentials and logic.

## Notes
- This is a boilerplate. The DAG tasks contain placeholders for you to implement the actual logic for each step.
