from datetime import datetime
import os
import zipfile
import requests
import tempfile
import subprocess
from airflow.sdk import dag, task, DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.models import Variable

# --- Airflow Variables ---
TELEGRAM_BOT_TOKEN = Variable.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = Variable.get("TELEGRAM_CHAT_ID")
SUPABASE_URL = Variable.get("SUPABASE_URL")
SUPABASE_KEY = Variable.get("SUPABASE_KEY")
VERCEL_ACCESS_TOKEN = Variable.get("VERCEL_ACCESS_TOKEN")

# --- Notification and Status Wrapper ---
def with_notification(task_func, status_text):
    def wrapper(*args, **kwargs):
        notify_telegram(f"🚀 Step started: {status_text}", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        update_supabase_status(kwargs['run_id'], status_text, SUPABASE_URL, SUPABASE_KEY)
        result = task_func(*args, **kwargs)
        notify_telegram(f"✅ Step completed: {status_text}", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        update_supabase_status(kwargs['run_id'], f"{status_text} completed", SUPABASE_URL, SUPABASE_KEY)
        return result
    return wrapper

# --- Functions Implementation ---
def unzip_file(url, run_id):
    print(f"[{run_id}] Downloading file from {url}")
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed to download zip file. Status: {response.status_code}")

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "project.zip")
        with open(zip_path, "wb") as f:
            f.write(response.content)

        print(f"[{run_id}] Unzipping to {tmpdir}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("unzipped_project")  # keep unzipped path static for downstream use

def push_to_github(repo, run_id):
    repo_path = "unzipped_project"
    print(f"[{run_id}] Initializing Git repo at {repo_path}")

    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    subprocess.run(["git", "remote", "add", "origin", repo], cwd=repo_path, check=True)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", f"Initial commit from DAG {run_id}"], cwd=repo_path, check=True)
    subprocess.run(["git", "push", "-u", "origin", "master", "--force"], cwd=repo_path, check=True)

def deploy_to_vercel(project_name, run_id):
    print(f"[{run_id}] Triggering Vercel deployment for {project_name}")
    vercel_url = f"https://api.vercel.com/v13/deployments"
    headers = {"Authorization": f"Bearer {VERCEL_ACCESS_TOKEN}"}
    payload = {
        "name": project_name,
        "gitSource": {
            "type": "github"
        }
    }
    response = requests.post(vercel_url, json=payload, headers=headers)
    if response.status_code != 201:
        raise Exception(f"Vercel deployment failed: {response.status_code} - {response.text}")

def notify_telegram(message, bot_token, chat_id):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    if not response.ok:
        print(f"Telegram notification failed: {response.text}")

def update_supabase_status(run_id, status, supabase_url, supabase_key):
    url = f"{supabase_url}/rest/v1/deploy_status"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "run_id": run_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    }
    response = requests.post(url, json=payload, headers=headers)
    if not response.ok:
        print(f"Supabase status update failed: {response.status_code}, {response.text}")

# --- DAG Definition ---
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
    "depends_on_past": False,
    'retries': 1,
}

with DAG(
    'supabase_to_vercel_pipeline',
    default_args=default_args,
    description='Unzip Supabase file, push to Github, deploy to Vercel',
    schedule=None,
    catchup=False,
) as dag:
    unzip_sb_storage_file = PythonOperator(
        task_id='unzip_file',
        python_callable=with_notification(unzip_file, 'Unzipping project'),
        op_kwargs={'url': '{{ dag_run.conf["url"] }}', 'run_id': '{{ dag_run.run_id }}'},
    )

    github_push_code = PythonOperator(
        task_id='push_to_github',
        python_callable=with_notification(push_to_github, 'Pushing code to GitHub'),
        op_kwargs={'repo': '{{ dag_run.conf["repo"] }}', 'run_id': '{{ dag_run.run_id }}'},
    )

    vercel_deploy_task = PythonOperator(
        task_id='deploy_to_vercel',
        python_callable=with_notification(deploy_to_vercel, 'Deploying to Vercel'),
        op_kwargs={'project_name': '{{ dag_run.conf["project_name"] }}', 'run_id': '{{ dag_run.run_id }}'},
    )

    unzip_sb_storage_file.set_downstream(github_push_code)
    github_push_code.set_downstream(vercel_deploy_task) 