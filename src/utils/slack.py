import logging

import requests
from slack_sdk.webhook import WebhookClient

from src.configs.env import APP_ENVIRONMENT


def send_slack_notification(text: str):
    try:
        # Portfolio version: Use environment variables for sensitive information
        import os
        url = os.getenv("SLACK_API_URL", "https://slack-api.example.com/openapi/slack/message/channel")
        token = os.getenv("SLACK_API_TOKEN", "")
        channel = os.getenv("SLACK_CHANNEL_DEV", "CHANNEL_DEV")
        if APP_ENVIRONMENT.upper() == "PROD":
            channel = os.getenv("SLACK_CHANNEL_PROD", "CHANNEL_PROD")
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        urls = f"{url}?token={token}&channel={channel}&text={text}"

        response = requests.post(urls, headers=headers)
        if response.status_code != 200:
            raise Exception(response.text)
        return response
    except Exception as e:
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, f"send_webhook_message > Exception:{e}")


def send_slack_alert(text: str):
    try:
        # Portfolio version: Use environment variables for sensitive information
        import os
        url = os.getenv("SLACK_API_URL", "https://slack-api.example.com/openapi/slack/message/channel")
        token = os.getenv("SLACK_API_TOKEN", "")
        channel = os.getenv("SLACK_CHANNEL_DEV", "CHANNEL_DEV")
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        urls = f"{url}?token={token}&channel={channel}&text={text}"

        response = requests.post(urls, headers=headers)
        if response.status_code != 200:
            raise Exception(response.text)
        return response
    except Exception as e:
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, f"send_webhook_message > Exception:{e}")


def send_webhook_message(text: str):
    """Portfolio version: Use environment variables for webhook URL and proxy settings"""
    import os
    url = os.getenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
    try:
        if APP_ENVIRONMENT == "DEV":
            proxy = os.getenv("SLACK_PROXY_DEV", None)
            webhook = WebhookClient(url, proxy=proxy) if proxy else WebhookClient(url)
            response = webhook.send(text=f"[DEV] {text}")
        elif APP_ENVIRONMENT == "PROD":
            proxy = os.getenv("SLACK_PROXY_PROD", None)
            webhook = WebhookClient(url, proxy=proxy) if proxy else WebhookClient(url)
            response = webhook.send(text=f"[PROD] {text}")
        else:
            # Local development
            url = os.getenv("SLACK_WEBHOOK_URL_LOCAL", url)
            webhook = WebhookClient(url)
            response = webhook.send(text=f"[LOCAL] {text}")
        if response.status_code != 200:
            raise Exception(response.body)
        return response
    except Exception as e:
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, f"send_webhook_message > Exception:{e}")


def send_slack_msg_load(msg):
    import json
    import os
    import sys

    import requests

    # Portfolio version: Use environment variables for webhook URL
    url = os.getenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
    slack_data = {
        "text": msg,
        "short": "false",
    }
    # Portfolio version: Use environment variables for proxy settings
    proxy_url = os.getenv("SLACK_PROXY_URL", None)
    proxies = None
    if proxy_url:
        proxies = {
            "http": f"http://{proxy_url}",
            "https": f"http://{proxy_url}",
        }

    byte_length = str(sys.getsizeof(slack_data))
    headers = {"Content-Type": "application/json", "Content-Length": byte_length}

    response = requests.post(
        url,
        data=json.dumps(slack_data),
        headers=headers,
        proxies=proxies,
        verify=False,
        timeout=5,
    )
    if response.status_code != 200:
        print(response.status_code, response.text)
