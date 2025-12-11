from datetime import datetime
from airflow.decorators import dag, task  # Correct import path

@task
def print_dag_id(**kwargs):
    """Print the DAG ID from the runtime context."""
    dag_id = kwargs['dag_run'].dag_id if 'dag_run' in kwargs else kwargs.get('dag').dag_id
    print(f"DAG ID: {dag_id}")
    return dag_id

@dag(
    dag_id="display_dag_id",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    default_args={"owner": "airflow", "retries": 1},
    description="Simple DAG to display the DAG ID when trkiggered",
)
def display_dag_id_pipeline():
    print_dag_id()

# Instantiate the DAG
display_dag_id_pipeline()