from datetime import datetime
import requests
import zipfile
import io
import os
import shutil
from airflow.sdk import dag, task
from github import Github
from github.InputGitTreeElement import InputGitTreeElement
from twilio.rest import Client as TwilioClient

# --- Task Functions ---
@task
def unzip_file(**kwargs) -> str:
    """Download and unzip a file from Supabase to a temporary directory."""
    conf = kwargs['dag_run'].conf
    file_url = conf.get('url', 'https://default-url.com')
    username = conf.get('username', 'default_user')
    temp_dir = f"/tmp/code/{username}"
    os.makedirs(temp_dir, exist_ok=True)
    response = requests.get(file_url, timeout=30)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
        zip_ref.extractall(temp_dir)
    return temp_dir

@task
def push_to_github(unzipped_file_dir: str, **kwargs) -> str:
    """Push files to a new GitHub branch."""
    conf = kwargs['dag_run'].conf
    username = conf.get('username', 'default_user')
    github_token = os.getenv("GITHUB_ACCESS_TOKEN")
    repo_name = os.getenv("GITHUB_REPO")
    g = Github(github_token)
    repo = g.get_repo(repo_name)
    branch = f"{username}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    ref = repo.get_git_ref(f"heads/{repo.default_branch}")
    latest_commit = repo.get_git_commit(ref.object.sha)
    base_tree = latest_commit.tree
    elements = []
    for root, _, files in os.walk(unzipped_file_dir):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            rel_path = os.path.relpath(file_path, unzipped_file_dir)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                blob = repo.create_git_blob(content, "utf-8")
                elements.append(InputGitTreeElement(path=rel_path, mode="100644", type="blob", sha=blob.sha))
            except UnicodeDecodeError:
                continue
    new_tree = repo.create_git_tree(elements, base_tree)
    new_commit = repo.create_git_commit(f"Deploy {branch}", new_tree, [latest_commit])
    repo.create_git_ref(ref=f"refs/heads/{branch}", sha=new_commit.sha)
    return branch

@task
def deploy_to_vercel(branch: str, **kwargs) -> str:
    """Deploy a GitHub branch to Vercel."""
    conf = kwargs['dag_run'].conf
    project_name = conf.get('project_name', 'default_project')
    vercel_token = os.getenv("VERCEL_ACCESS_TOKEN")
    vercel_repo = os.getenv("VERCEL_GITHUB_REPO")
    url = "https://api.vercel.com/v6/deployments"
    headers = {"Authorization": f"Bearer {vercel_token}", "Content-Type": "application/json"}
    payload = {
        "name": project_name,
        "target": "production",
        "gitSource": {"type": "github", "repo": vercel_repo, "ref": branch, "org": "samsha1"}
    }
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    deployment = response.json()
    deployment_id = deployment["id"]
    status = deployment.get("readyState")
    while status in ["INITIALIZING", "BUILDING", "QUEUED"]:
        response = requests.get(f"https://api.vercel.com/v6/deployments/{deployment_id}", headers=headers, timeout=120)
        response.raise_for_status()
        status = response.json().get("readyState")
    if status == "READY":
        alias = f"{project_name}-{branch}.vercel.app"
        requests.post(f"https://api.vercel.com/v6/deployments/{deployment_id}/aliases", headers=headers, json={"alias": alias}, timeout=120).raise_for_status()
        return f"https://{alias}"
    raise ValueError(f"Deployment failed with status {status}")

@task
def send_final_notification(alias_url: str, **kwargs):
    """Send a WhatsApp notification with the deployment URL."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_SANDBOX_PHONE_NUM")
    to_number = os.getenv("NOTIFICATION_PHONE")
    message = f"🚀 Deployment completed! Your project is live at {alias_url}" if alias_url else "❌ Deployment failed: No URL"
    twilio_client = TwilioClient(account_sid, auth_token)
    twilio_client.messages.create(body=message, from_=f"whatsapp:{from_number}", to=f"whatsapp:{to_number}")

@task
def cleanup_temp_dir(unzipped_dir: str, **kwargs):
    """Clean up temporary directory."""
    shutil.rmtree(unzipped_dir, ignore_errors=True)

# --- DAG Definition ---
@dag(
    dag_id="supabase_to_vercel",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    default_args={"owner": "airflow", "retries": 1},
    description="Unzip Supabase file, push to GitHub, deploy to Vercel",
)
def supabase_to_vercel_pipeline():
    # Task instances (dependencies via >>) >> hey this is your latest code
    # conf ={
    #     "url": "https://yknecccdejmevqjwvwhd.supabase.co/storage/v1/object/public/projects/9779867397267/generated_website/20251101_131839.zip",
    #     "username": "testuser",
    #     "project_name": "testproject"
    # }
    unzipped_dir = unzip_file()
    branch = push_to_github(unzipped_file_dir=unzipped_dir)
    alias_url = deploy_to_vercel(branch=branch)
    send_final_notification(alias_url=alias_url)
    cleanup_temp_dir(unzipped_dir=unzipped_dir)

# Instantiate the DAG
supabase_to_vercel_pipeline()