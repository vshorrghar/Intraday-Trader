"""S3 report and file uploader for Wealth Builder Pro.

Uploads HTML reports and XLSX files to S3 with date-stamped keys.
Failures are logged and do not block the pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def upload_report(
    html_body: str,
    report_type: str,
    s3_bucket: str,
    region: str,
) -> bool:
    """Upload an HTML report to S3 with a date-stamped key.

    Args:
        html_body: The HTML content to upload.
        report_type: Report identifier (e.g. 'morning_brief', 'eod_report').
        s3_bucket: Target S3 bucket name.
        region: AWS region for S3.

    Returns:
        True on success, False on failure.
    """
    now = datetime.now(IST)
    key = f"reports/{now.strftime('%Y/%m/%d')}/{report_type}_{now.strftime('%Y%m%d_%H%M%S')}.html"
    try:
        client = boto3.client("s3", region_name=region)
        client.put_object(
            Bucket=s3_bucket,
            Key=key,
            Body=html_body.encode("utf-8"),
            ContentType="text/html",
        )
        logger.info("Uploaded report to s3://%s/%s", s3_bucket, key)
        return True
    except (ClientError, Exception) as exc:
        logger.error("Failed to upload report to S3: %s", exc)
        return False


def upload_xlsx(
    file_path: str,
    s3_bucket: str,
    region: str,
) -> bool:
    """Upload an XLSX file to S3 for archival.

    Args:
        file_path: Local path to the XLSX file.
        s3_bucket: Target S3 bucket name.
        region: AWS region for S3.

    Returns:
        True on success, False on failure.
    """
    now = datetime.now(IST)
    filename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    key = f"portfolio/{now.strftime('%Y/%m/%d')}/{filename}"
    try:
        client = boto3.client("s3", region_name=region)
        client.upload_file(file_path, s3_bucket, key)
        logger.info("Uploaded XLSX to s3://%s/%s", s3_bucket, key)
        return True
    except (ClientError, Exception) as exc:
        logger.error("Failed to upload XLSX to S3: %s", exc)
        return False
