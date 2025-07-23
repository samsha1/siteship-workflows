from datetime import datetime
import os
import zipfile
import requests
import tempfile
import time
import logging
from airflow.sdk import dag, task, DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.models import Variable
from github import Github
from github.InputGitTreeElement import InputGitTreeElement
from twilio.rest import Client as TwilioClient


# --- Airflow Variables ---
TELEGRAM_BOT_TOKEN = Variable.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = Variable.get("TELEGRAM_CHAT_ID")
SUPABASE_URL = Variable.get("SUPABASE_URL")
SUPABASE_KEY = Variable.get("SUPABASE_KEY")
VERCEL_ACCESS_TOKEN = Variable.get("VERCEL_ACCESS_TOKEN")
VERCEL_GITHUB_REPO = Variable.get("VERCEL_GITHUB_REPO", default_var=None)
VERCEL_TEAM = Variable.get("VERCEL_TEAM", default_var=None)
# Your Account SID and Auth Token from console.twilio.com
TWILIO_ACCOUNT_SID = Variable.get("TWILIO_SID", default_var=None)
TWILIO_AUTH_TOKEN  = Variable.get("TWILIO_AUTH_TOKEN", default_var=None)
TWILIO_PRD_PHONE_NUM = Variable.get("TWILIO_PHONE_NUM", default_var=None)
TWILIO_SANDBOX_PHONE_NUM = Variable.get("TWILIO_SANDBOX_PHONE_NUM", default_var=None)


# --- Logging Setup ---
logger = logging.getLogger(__name__)

VERCEL_HEADERS = {
    "Authorization": f"Bearer {VERCEL_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}



twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# --- Notification and Status Wrapper ---
def with_notification(task_func, status_text, message_to):
    """_summary_

    Args:
        task_func (Function): _function to wrap with notifications and status updates_
        status_text (str): _text to display in notifications and status updates_

    Returns:
        function: _wrapper function that adds notification and status update logic
    """
    def wrapper(*args, **kwargs):
        notify_twilio_whatsapp(f"🚀 Step started: {status_text}", message_to)
        # update_supabase_status(kwargs['run_id'], status_text, SUPABASE_URL, SUPABASE_KEY)
        result = task_func(*args, **kwargs)
        notify_twilio_whatsapp(f"✅ Step completed: {status_text}", message_to)
        # update_supabase_status(kwargs['run_id'], f"{status_text} completed", SUPABASE_URL, SUPABASE_KEY)
        return result
    return wrapper

# --- Functions Implementation ---
def unzip_file(url, run_id):
    
    """ Downloads a zip file from a supabase storageURL and unzips it to a temporary directory.

    Args:
        url (str): The URL of the zip file to download.
        run_id (str): The run ID for logging and tracking.

    Raises:
        Exception: If the download fails or the zip file cannot be extracted.
    """
    logger.info(f"[{run_id}] Downloading file from {url}")
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed to download zip file. Status: {response.status_code}")

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "project.zip")
        with open(zip_path, "wb") as f:
            f.write(response.content)

        logger.info(f"[{run_id}] Unzipping to {tmpdir}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("unzipped_project")  # keep unzipped path static for downstream use

def push_to_github(branch: str, files: list[dict], github_token: str, repo_name: str):
    """
        Push files to GitHub by creating a new branch with a commit.
        :param branch: New branch name (e.g., "feature/my-branch")
        :param files: List of dicts with 'path' and 'content'
        :param github_token: GitHub personal access token
        :param repo_name: Repository name in 'owner/repo' format
    """
    g = Github(github_token)
    repo = g.get_repo(repo_name)

    # Get default branch ref (e.g., main)
    default_branch = repo.default_branch
    ref = repo.get_git_ref(f"heads/{default_branch}")
    latest_commit = repo.get_git_commit(ref.object.sha)
    base_tree = latest_commit.tree

    # Create blobs and tree elements
    elements = []
    for file in files:
        blob = repo.create_git_blob(file['content'], 'utf-8')
        elements.append(InputGitTreeElement(
            path=file['path'],
            mode='100644',
            type='blob',
            sha=blob.sha
        ))

    # Create new tree and commit
    new_tree = repo.create_git_tree(elements, base_tree)
    new_commit = repo.create_git_commit(f"Deploy {branch}", new_tree, [latest_commit])
    
    # Create new branch ref
    repo.create_git_ref(ref=f"refs/heads/{branch}", sha=new_commit.sha)
    logger.info(f"✅ Created new branch '{branch}' with commit {new_commit.sha}")


def deploy_to_vercel(branch: str, project_name: str, username: str) -> str:
    """_summary_

    Args:
        branch (str): _branch name to deploy_
        project_name (str): _project name to deploy_
        username (str): _username for Vercel account_

    Returns:
        str: _deployment URL if successful, empty string otherwise_
    """
    # Step 1: Create deployment
    url = "https://api.vercel.com/v13/deployments"
    payload = {
        "name": project_name,
        "target": "production",
        "gitSource": {
            "type": "github",
            "repo": VERCEL_GITHUB_REPO,
            "ref": branch,
            "org": username
        }
    }
    if VERCEL_TEAM:
        url += f"?teamId={VERCEL_TEAM}"

    logger.info(f"Creating deployment for branch: {branch}")
    response = requests.post(url, headers=VERCEL_HEADERS, json=payload)
    response.raise_for_status()
    deployment = response.json()

    deployment_id = deployment["id"]
    logger.info(f"Deployment created: ID {deployment_id}, status {deployment['status']}")

    # Step 2: Poll for deployment status
    status = deployment["status"]
    deployment_url = None

    while status in ["INITIALIZING", "BUILDING", "QUEUED"]:
        time.sleep(5)
        status_resp = requests.get(
            f"https://api.vercel.com/v13/deployments/{deployment_id}",
            headers=VERCEL_HEADERS,
            timeout=600
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()
        status = status_data["status"]
        deployment_url = status_data["url"]
        logger.info(f"Deployment status: {status}")

    # Step 3: Assign alias
    if status == "READY":
        logger.info(f"Deployment successful: https://{deployment_url}")

        alias = f"{branch}-{username}.vercel.app"
        alias_resp = requests.post(
            f"https://api.vercel.com/v2/deployments/{deployment_id}/aliases",
            headers=VERCEL_HEADERS,
            json={"alias": alias},
            timeout=600
        )
        alias_resp.raise_for_status()
        logger.info(f"Alias assigned: {alias}")
        return f"https://{alias}"
    else:
        logger.info(f"Deployment failed: status {status}")
        return ""

def notify_twilio_whatsapp(message, to_number):
    """ Sends a WhatsApp message using Twilio.

    Args:
        message (string): Message to send
        to_number (string): Phone number to send the message to, (e.g., +1234567890)
    """
    msg = twilio_client.messages.create(
        body=message,
        from_=TWILIO_SANDBOX_PHONE_NUM,
        to=to_number
    )
    if 'sid' not in msg:
        logger.info(f"Whatsapp notification failed: {msg}")

# def update_supabase_status(run_id, status, supabase_url, supabase_key):
#     url = f"{supabase_url}/rest/v1/deploy_status"
#     headers = {
#         "apikey": supabase_key,
#         "Authorization": f"Bearer {supabase_key}",
#         "Content-Type": "application/json"
#     }
#     payload = {
#         "run_id": run_id,
#         "status": status,
#         "timestamp": datetime.utcnow().isoformat()
#     }
    
#     response = requests.post(url, json=payload, headers=headers)
#     if not response.ok:
#         logger.info(f"Supabase status update failed: {response.status_code}, {response.text}")

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
        python_callable=with_notification(unzip_file, 'Unzipping project', message_to=TWILIO_PRD_PHONE_NUM),
        op_kwargs={'url': '{{ dag_run.conf["url"] }}', 'run_id': '{{ dag_run.run_id }}'},
    )

    github_push_code = PythonOperator(
        task_id='push_to_github',
        python_callable=with_notification(push_to_github, 'Pushing code to GitHub', message_to=TWILIO_PRD_PHONE_NUM),
        op_kwargs={'repo': '{{ dag_run.conf["repo"] }}', 'run_id': '{{ dag_run.run_id }}'},
    )

    vercel_deploy_task = PythonOperator(
        task_id='deploy_to_vercel',
        python_callable=with_notification(deploy_to_vercel, 'Deploying to Vercel', message_to=TWILIO_PRD_PHONE_NUM),
        op_kwargs={'project_name': '{{ dag_run.conf["project_name"] }}', 'run_id': '{{ dag_run.run_id }}'},
    )

    unzip_sb_storage_file.set_downstream([github_push_code,vercel_deploy_task])  # Unzip must complete before pushing to GitHub and deploying to Vercel
