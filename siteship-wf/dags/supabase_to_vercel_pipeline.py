from datetime import datetime
import requests
import time
import logging
import os
import zipfile
import io
from functools import wraps
from airflow.decorators import dag, task
from airflow.models import Variable
from github import Github
from github.InputGitTreeElement import InputGitTreeElement
from twilio.rest import Client as TwilioClient
# from _scproxy import _get_proxy_settings


# --- Logging Setup ---
logger = logging.getLogger(__name__)
os.environ['NO_PROXY'] = '*'  # Disable proxy for requests
# _get_proxy_settings()

# --- Airflow Variables ---
TELEGRAM_BOT_TOKEN = Variable.get("TELEGRAM_BOT_TOKEN", default_var=None)
TELEGRAM_CHAT_ID = Variable.get("TELEGRAM_CHAT_ID", default_var=None)
SUPABASE_URL = Variable.get("SUPABASE_URL")
SUPABASE_KEY = Variable.get("SUPABASE_KEY")
VERCEL_ACCESS_TOKEN = Variable.get("VERCEL_ACCESS_TOKEN")
VERCEL_GITHUB_REPO = Variable.get("VERCEL_GITHUB_REPO", default_var=None)
VERCEL_TEAM = Variable.get("VERCEL_TEAM", default_var=None)
TWILIO_ACCOUNT_SID = Variable.get("TWILIO_ACCOUNT_SID", default_var=None)
TWILIO_AUTH_TOKEN = Variable.get("TWILIO_AUTH_TOKEN", default_var=None)
TWILIO_PRD_PHONE_NUM = Variable.get("TWILIO_PHONE_NUM", default_var=None)
TWILIO_SANDBOX_PHONE_NUM = Variable.get("TWILIO_SANDBOX_PHONE_NUM", default_var=None)
GITHUB_REPO = Variable.get("GITHUB_REPO")
GITHUB_ACCESS_TOKEN = Variable.get("GITHUB_ACCESS_TOKEN")
MESSAGE_TO = Variable.get("NOTIFICATION_PHONE")  # Configurable phone number


HTTP_PROXIES = {
    'http':None,
    'https':None
}


# --- Notification Wrapper ---
def with_notification(status_text, message_to):
    """Decorator to add notification and status update logic."""
    def decorator(task_func):
        @wraps(task_func)
        def wrapper(*args, **kwargs):
            notify_twilio_whatsapp(f"🚀 Step started: {status_text}", message_to)
            try:
                result = task_func(*args, **kwargs)
                notify_twilio_whatsapp(f"✅ Step completed: {status_text}", message_to)
                return result
            except Exception as e:
                notify_twilio_whatsapp(f"❌ Step failed: {status_text} - {str(e)}", message_to)
                raise
        return wrapper
    return decorator

# --- Task Functions ---
@task()
@with_notification("Unzipping code files", MESSAGE_TO)
def unzip_file(file_url: str, username: str, extract_to: str = "/tmp/code") -> str:
    """Downloads a zip file from Supabase storage and unzips it to a temporary directory."""
    logger.info(f"Downloading file from {file_url} for user {username}")
    # HTTP_PROXIES = {
    #     "http": 'http://materialisting:11ZoYAiymG5qOupH_country-Sweden_session-s5TQunQ4@proxy.packetstream.io:31112',
    #     "https": 'http://materialisting:11ZoYAiymG5qOupH_country-Sweden_session-s5TQunQ4@proxy.packetstream.io:31112'
    # }
    temp_dir = f"{extract_to}/{username}"
    os.makedirs(temp_dir, exist_ok=True)
    os.environ['NO_PROXY'] = '*'  # Disable proxy for requests
    response = requests.get(file_url, timeout=30)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
        zip_ref.extractall(temp_dir)

    logger.info(f"Unzipped files to {temp_dir}")
    return temp_dir

@task()
@with_notification("Pushing code to GitHub", MESSAGE_TO)
def push_to_github(unzipped_file_dir: str, username: str) -> str:
    """Pushes files to GitHub by creating a new branch with a commit."""
    g = Github(GITHUB_ACCESS_TOKEN)
    repo = g.get_repo(GITHUB_REPO)

    # Create a unique branch name
    branch = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    logger.info(f"Creating branch {branch}")

    # Get default branch ref
    default_branch = repo.default_branch
    ref = repo.get_git_ref(f"heads/{default_branch}")
    latest_commit = repo.get_git_commit(ref.object.sha)
    base_tree = latest_commit.tree

    # Create blobs and tree elements
    elements = []
    for root, _, files in os.walk(unzipped_file_dir):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            rel_path = os.path.relpath(file_path, unzipped_file_dir)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            blob = repo.create_git_blob(content, "utf-8")
            elements.append(InputGitTreeElement(
                path=rel_path,
                mode="100644",
                type="blob",
                sha=blob.sha
            ))

    # Create new tree and commit
    new_tree = repo.create_git_tree(elements, base_tree)
    new_commit = repo.create_git_commit(f"Deploy {branch}", new_tree, [latest_commit])
    repo.create_git_ref(ref=f"refs/heads/{branch}", sha=new_commit.sha)
    logger.info(f"Created branch '{branch}' with commit {new_commit.sha}")
    return branch

@task()
@with_notification("Deploying to Vercel", MESSAGE_TO)
def deploy_to_vercel(branch: str, project_name: str, username: str) -> str:
    """Deploys a branch to Vercel and returns the deployment URL."""
    url = "https://api.vercel.com/v6/deployments"
    payload = {
        "name": project_name,
        "target": "production",
        "gitSource": {
            "type": "github",
            "repo": VERCEL_GITHUB_REPO,
            "ref": branch,
            "org": 'samsha1'
        }
    }
    logger.info(f"Payload for Vercel deployment: {payload}")
    if VERCEL_TEAM:
        url += f"?teamId={VERCEL_TEAM}"
    VERCEL_HEADERS = {
        "Authorization": f"Bearer {VERCEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    logger.info(f"Creating deployment for branch: {branch}")
    response = requests.post(url, headers=VERCEL_HEADERS, json=payload,timeout=60, proxies=HTTP_PROXIES, allow_redirects=True)
    # response.raise_for_status()
    deployment = response.json()
    logger.info(f"Vercel response status code: {deployment}")

    deployment_id = deployment["id"]
    logger.info(f"Deployment created: ID {deployment_id}, status {deployment['readyState']}")

    # Poll for deployment status
    status = deployment["readyState"]
    deployment_url = None
    while status in ["INITIALIZING", "BUILDING", "QUEUED"]:
        time.sleep(5)
        status_resp = requests.get(
            f"https://api.vercel.com/v6/deployments/{deployment_id}",
            headers=VERCEL_HEADERS,
            timeout=120,
            proxies=HTTP_PROXIES, allow_redirects=True
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()
        status = status_data.get("readyState")
        deployment_url = status_data.get("url")
        logger.info(f"Deployment status: {status}")

    if status == "READY":
        logger.info(f"Deployment successful: https://{deployment_url}")
        alias = f"{branch}-{username}.vercel.app"
        alias_resp = requests.post(
            f"https://api.vercel.com/v6/deployments/{deployment_id}/aliases",
            headers=VERCEL_HEADERS,
            json={"alias": alias},
            timeout=120,
            proxies=HTTP_PROXIES, allow_redirects=True
        )
        alias_resp.raise_for_status()
        logger.info(f"Alias assigned: {alias}")
        return f"https://{alias}"
    else:
        logger.error(f"Deployment failed: status {status}")
        raise ValueError(f"Deployment failed with status {status}")

def notify_twilio_whatsapp(message: str, to_number: str):
    """Sends a WhatsApp message using Twilio."""
    try:
        twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info(f"Sending WhatsApp message to {to_number}: {message}")
        msg = twilio_client.messages.create(
            body=message,
            from_=f"whatsapp:{TWILIO_SANDBOX_PHONE_NUM}",
            to=f"whatsapp:{to_number}"
        )
        logger.info(f"WhatsApp message sent with SID: {msg.sid}")
        return msg.sid
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {str(e)}")
        raise

# --- DAG Definition ---
@dag(
    dag_id="supabase_to_vercel_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    default_args={
        "owner": "airflow",
        "depends_on_past": False,
        "retries": 1,
    },
    description="Unzip Supabase file, push to GitHub, deploy to Vercel",
)
def supabase_to_vercel_pipeline():
    # Extract DAG run configuration
    conf = {"url": "{{ dag_run.conf['url'] }}", "username": "{{ dag_run.conf['username'] }}", "project_name": "{{ dag_run.conf['project_name'] }}"}
    
    # Task instances
    unzipped_dir = unzip_file(file_url=conf["url"], username=conf["username"])
    branch = push_to_github(unzipped_file_dir=unzipped_dir, username=conf["username"])
    deploy_to_vercel(branch=branch, project_name=conf["project_name"], username=conf["username"])

# Instantiate the DAG
supabase_to_vercel_pipeline()