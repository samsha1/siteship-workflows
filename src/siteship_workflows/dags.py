from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import os
from pipeline.tasks import unzip_file, push_to_github, deploy_to_vercel
from pipeline.notify import notify_telegram, update_supabase_status

def with_notification(task_func, status_text):
    def wrapper(*args, **kwargs):
        notify_telegram(f"🚀 Step started: {status_text}")
        update_supabase_status(kwargs['run_id'], status_text)
        result = task_func(*args, **kwargs)
        notify_telegram(f"✅ Step completed: {status_text}")
        update_supabase_status(kwargs['run_id'], f"{status_text} completed")
        return result
    return wrapper

def unzip_supabase_file(**kwargs):
    # Placeholder: Download and unzip .zip file from Supabase storage
    # Example: Use requests to download, then unzip
    print("Unzipping Supabase storage file...")
    # TODO: Implement actual logic

def push_files_to_github(**kwargs):
    # Placeholder: Push files to Github using PyGithub
    print("Pushing files to Github...")
    # TODO: Implement actual logic

def deploy_to_vercel(**kwargs):
    # Placeholder: Deploy to Vercel (e.g., via API or CLI)
    print("Deploying to Vercel...")
    # TODO: Implement actual logic

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
}

dag = DAG(
    'supabase_to_vercel_pipeline',
    default_args=default_args,
    description='Unzip Supabase file, push to Github, deploy to Vercel',
    schedule_interval=None,
    catchup=False,
)


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

unzip_sb_storage_file >> github_push_code >> vercel_deploy_task 