from datetime import datetime
import requests
import os

# Disable all proxies
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('https_proxy', None)

# Disable SSL verification for requests (and thus PyGithub)
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
import time
import logging
import zipfile
import io
from functools import wraps
from airflow.sdk import dag, task
from airflow.models import Variable
from airflow.providers.github.operators.github import GithubOperator
# from twilio.rest import Client as TwilioClient
# from _scproxy import _get_proxy_settings


# --- Logging Setup ---
logger = logging.getLogger(__name__)
# _get_proxy_settings()

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





# --- Notification Wrapper ---
def with_notification(status_text, message_to='+9779867397267'):
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
@with_notification("Unzipping code files")
def unzip_file(file_url: str, username: str, extract_to: str = "/tmp/code") -> str:
    """Downloads a zip file from Supabase storage and unzips it to a temporary directory."""
    logger.info(f"Downloading file from {file_url} for user {username}")
    os.environ['NO_PROXY'] = '*'  # Disable proxy for requests
    try:
      response = requests.get(file_url, timeout=30,verify=False, allow_redirects=True,proxies={ 'http': None, 'https': None})
      response.raise_for_status()
    except Exception as e:
      logger.error(f"Failed to download file: {e}")
      raise
    temp_dir = f"{extract_to}/{username}"
    os.makedirs(temp_dir, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
        zip_ref.extractall(temp_dir)

    logger.info(f"Unzipped files to {temp_dir}")
    return temp_dir

@task()
@with_notification("Pushing code to GitHub", MESSAGE_TO)
def push_to_github(unzipped_file_dir: str, username: str) -> str:
    """Pushes files to GitHub using GitHubOperator."""
    branch = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    logger.info(f"Pushing files from {unzipped_file_dir} to branch {branch} in repo {GITHUB_REPO}")

    # Initialize local git repository if not already initialized
    repo_path = unzipped_file_dir
    if not os.path.exists(os.path.join(repo_path, '.git')):
        os.system(f"git -C {repo_path} init")
        os.system(f"git -C {repo_path} remote add origin https://github.com/{GITHUB_REPO}.git")
    method_args = {
        "branch": branch,
        "files": [os.path.relpath(os.path.join(root, f), repo_path) for root, _, files in os.walk(repo_path) for f in files],
        "local_path": unzipped_file_dir,
        "repo": GITHUB_REPO,
        "commit_message": f"Deploy {branch}"
    }
    # Use GitHubOperator to commit and push files
    github_op = GithubOperator(
        task_id='push_to_github_internal',
        github_method='create_commit',
        github_conn_id=GITHUB_ACCESS_TOKEN,
        github_method_args=method_args,
    )
    github_op.execute(context={})
    logger.info(f"Created branch '{branch}'")
    return branch

# @task()
# @with_notification("Deploying to Vercel", MESSAGE_TO)
# def deploy_to_vercel(branch: str, project_name: str, username: str) -> str:
#     """Deploys a branch to Vercel and returns the deployment URL."""
#     url = "https://api.vercel.com/v6/deployments"
#     payload = {
#         "name": project_name,
#         "target": "production",
#         "gitSource": {
#             "type": "github",
#             "repo": VERCEL_GITHUB_REPO,
#             "ref": branch,
#             "org": username
#         }
#     }
#     logger.info(f"Payload for Vercel deployment: {payload}")
#     if VERCEL_TEAM:
#         url += f"?teamId={VERCEL_TEAM}"
#     VERCEL_HEADERS = {
#         "Authorization": f"Bearer {VERCEL_ACCESS_TOKEN}",
#         "Content-Type": "application/json"
#     }
#     logger.info(f"Creating deployment for branch: {branch}")
#     response = requests.post(url, headers=VERCEL_HEADERS, json=payload,timeout=60, proxies=HTTP_PROXIES, allow_redirects=True)
    
#     # response.raise_for_status()
#     deployment = response.json()

#     deployment_id = deployment["id"]
#     logger.info(f"Deployment created: ID {deployment_id}, status {deployment['status']}")

#     # Poll for deployment status
#     status = deployment["status"]
#     deployment_url = None
#     while status in ["INITIALIZING", "BUILDING", "QUEUED"]:
#         time.sleep(5)
#         status_resp = requests.get(
#             f"https://api.vercel.com/v6/deployments/{deployment_id}",
#             headers=VERCEL_HEADERS,
#             timeout=120,
#             proxies=HTTP_PROXIES, allow_redirects=True
#         )
#         status_resp.raise_for_status()
#         status_data = status_resp.json()
#         status = status_data["status"]
#         deployment_url = status_data.get("url")
#         logger.info(f"Deployment status: {status}")

#     if status == "READY":
#         logger.info(f"Deployment successful: https://{deployment_url}")
#         alias = f"{branch}-{username}.vercel.app"
#         alias_resp = requests.post(
#             f"https://api.vercel.com/v6/deployments/{deployment_id}/aliases",
#             headers=VERCEL_HEADERS,
#             json={"alias": alias},
#             timeout=120,
#             proxies=HTTP_PROXIES, allow_redirects=True
#         )
#         alias_resp.raise_for_status()
#         logger.info(f"Alias assigned: {alias}")
#         return f"https://{alias}"
#     else:
#         logger.error(f"Deployment failed: status {status}")
#         raise ValueError(f"Deployment failed with status {status}")

def notify_twilio_whatsapp(message: str, to_number: str):
    """Sends a WhatsApp message using Twilio."""
    try:
        # twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info(f"Sending WhatsApp message to {to_number}: {message}")
        # msg = twilio_client.messages.create(
        #     body=message,
        #     from_=f"whatsapp:{TWILIO_SANDBOX_PHONE_NUM}",
        #     to=f"whatsapp:{to_number}"
        # )
        logger.info(f"WhatsApp message sent with SID")
        # return msg.sid
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
    # deploy_to_vercel(branch=branch, project_name=conf["project_name"], username=conf["username"])

# Instantiate the DAG
supabase_to_vercel_pipeline()