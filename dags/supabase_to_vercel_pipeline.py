from datetime import datetime
from airflow.sdk import dag, task
from airflow.providers.standard.operators.python import PythonOperator
from airflow.models import Variable
# from pipelines.tasks import unzip_file, push_to_github, deploy_to_vercel
# from pipelines.notify import notify_telegram, update_supabase_status

TELEGRAM_BOT_TOKEN = Variable.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = Variable.get("TELEGRAM_CHAT_ID")
SUPABASE_URL = Variable.get("SUPABASE_URL")
SUPABASE_KEY = Variable.get("SUPABASE_KEY")
VERCEL_ACCESS_TOKEN = Variable.get("VERCEL_ACCESS_TOKEN")

def with_notification(task_func, status_text):
    def wrapper(*args, **kwargs):
        notify_telegram(f"🚀 Step started: {status_text}", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        update_supabase_status(kwargs['run_id'], status_text, SUPABASE_URL, SUPABASE_KEY)
        result = task_func(*args, **kwargs)
        notify_telegram(f"✅ Step completed: {status_text}", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        update_supabase_status(kwargs['run_id'], f"{status_text} completed", SUPABASE_URL, SUPABASE_KEY)
        return result
    return wrapper

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
    "depends_on_past": False,
    'retries': 1,
}

@dag(
    'supabase_to_vercel_pipeline',
    default_args=default_args,
)


@task()
def unzip_file(url: str, run_id: str) -> str:
    print(f"Unzipping file from {url} for run {run_id}")
    # Placeholder logic for unzipping
    with_notification(unzip_file, 'Unzipping project')(url, run_id)
    return "file unzipped"

with DAG(
    'supabase_to_vercel_pipeline',
    default_args=default_args,
    description='Unzip Supabase file, push to Github, deploy to Vercel',
    schedule=None,
    catchup=False,
) as dag:
    # Task 1: Unzip
    unzip_sb_storage_file = PythonOperator(
        task_id='unzip_file',
        python_callable=with_notification(unzip_file, 'Unzipping project'),
        op_kwargs={'url': '{{ dag_run.conf["url"] }}', 'run_id': '{{ dag_run.run_id }}'},
        dag=dag,
    )

    # Task 2: GitHub Push
    github_push_code = PythonOperator(
        task_id='push_to_github',
        python_callable=with_notification(push_to_github, 'Pushing code to GitHub'),
        op_kwargs={'repo': '{{ dag_run.conf["repo"] }}', 'run_id': '{{ dag_run.run_id }}'},
        dag=dag,
    )

    # Task 3: Deploy to Vercel
    vercel_deploy_task = PythonOperator(
        task_id='deploy_to_vercel',
        python_callable=with_notification(deploy_to_vercel, 'Deploying to Vercel'),
        op_kwargs={'project_name': '{{ dag_run.conf["project_name"] }}', 'run_id': '{{ dag_run.run_id }}'},
        dag=dag,
    )

    unzip_sb_storage_file.set_downstream(github_push_code)
    github_push_code.set_downstream(vercel_deploy_task)