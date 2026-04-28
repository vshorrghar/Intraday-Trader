"""AWS SES email sender with retry logic.

Sends HTML email reports via boto3 SES client. Retries up to 3 times
with exponential backoff (1s, 2s, 4s) on failure.
"""

from __future__ import annotations

import logging
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def send_email(
    html_body: str,
    subject: str,
    sender: str,
    recipient: str,
    region: str,
) -> bool:
    """Send an HTML email via AWS SES.

    Args:
        html_body: The HTML content of the email.
        subject: Email subject line.
        sender: Verified SES sender email address.
        recipient: Recipient email address.
        region: AWS region for SES (e.g. 'ap-south-1').

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    client = boto3.client("ses", region_name=region)
    max_retries = 3
    backoff_seconds = 1

    for attempt in range(1, max_retries + 2):  # 1 initial + 3 retries = 4 total
        try:
            logger.info("SES send attempt %d/%d for '%s'", attempt, max_retries + 1, subject)
            client.send_email(
                Source=sender,
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
                },
            )
            logger.info("Email sent successfully: '%s'", subject)
            return True
        except (ClientError, Exception) as exc:
            logger.warning("SES attempt %d failed: %s", attempt, exc)
            if attempt > max_retries:
                logger.error("All %d SES attempts exhausted for '%s'", max_retries + 1, subject)
                return False
            time.sleep(backoff_seconds)
            backoff_seconds *= 2

    return False
