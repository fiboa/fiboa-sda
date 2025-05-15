import os
import logging
import random
from urllib.parse import urljoin

import requests
from slack_sdk import WebhookClient
from slack_sdk.http_retry import RateLimitErrorRetryHandler
from tenacity import retry, wait_exponential

logger = logging.getLogger()
logger.setLevel("INFO")

SLACK_WEBHOOK_URL = os.getenv(
    "SLACK_APP_URL",
    None,
)
SOURCE_COOP_URL = os.getenv("SOURCE_COOP_URL", "https://source.coop")
EMOJIS = [
    ":tractor:",
    ":farmer:",
    ":corn:",
    ":strawberry:",
    ":ear_of_rice:",
    ":seedling:",
    ":hatching_chick:",
    ":ladybug:",
    ":sunflower:",
]


@retry(wait=wait_exponential(multiplier=1, min=4, max=10))
def _fetch_repo(repo_name: str):
    """Fetch the repo from source.coop."""
    r = requests.get(
        urljoin(SOURCE_COOP_URL, f"/api/v1/repositories/fiboa/{repo_name}")
    )
    r.raise_for_status()
    resp_json = r.json()
    return resp_json


def _send_slack_notification(repo_name: str, webhook_client: WebhookClient):
    """Send a notification to a slack webhook, indicating a new fiboa dataset is available."""
    repo = _fetch_repo(repo_name)
    repo_meta = repo["meta"]

    formatted_tags = " ".join(sorted([f"`{tag}`" for tag in repo_meta["tags"]]))
    emoji = random.choice(EMOJIS)
    body = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{repo_meta['title']} {emoji}",
                    "emoji": True,
                },
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": formatted_tags}},
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": repo_meta["description"]},
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "source.coop",
                        "emoji": True,
                    },
                    "value": "source.coop",
                    "style": "primary",
                    "url": f"https://source.coop/repositories/fiboa/{repo_name}/description",
                    "action_id": "button-action",
                },
            },
        ]
    }
    print("SENDING BODY - ", body)
    # webhook_client.send(**body)


def handler(event, context):
    rate_limit_handler = RateLimitErrorRetryHandler(max_retry_count=3)
    webhook_client = WebhookClient(
        url=SLACK_WEBHOOK_URL,
        retry_handlers=[rate_limit_handler],
        timeout=10,
    )
    for record in event["Records"]:
        key: str = record["s3"]["object"]["key"]
        if not key.startswith("fiboa/"):
            logger.info(f"Skipping key - {key}")
            continue
        repo_name = key.split("/")[1]
        if key.endswith("README.md"):
            # New source.coop dataset, send slack notification.
            repo_name = key.split("/")[1]
            _send_slack_notification(repo_name, webhook_client)
            logger.info(f"Sent slack notification for {repo_name}")
        elif key.endswith(".parquet"):
            # New fiboa dataset, send to AWS batch.
            pass
        else:
            logger.info(f"Skipping key - {key}")
            continue
