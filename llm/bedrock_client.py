"""AWS Bedrock client for Claude Sonnet invocations.

Provides a wrapper around boto3 bedrock-runtime that handles prompt formatting,
JSON response parsing, timeout handling, and exponential backoff retries for throttling.
"""

from __future__ import annotations

import json
import logging
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class BedrockClient:
    """Client for invoking Claude Sonnet via AWS Bedrock."""

    def __init__(self, region: str, model_id: str):
        """Initialize boto3 Bedrock runtime client.

        Args:
            region: AWS region (e.g. 'ap-south-1').
            model_id: Bedrock model identifier (e.g. 'anthropic.claude-3-sonnet-20240229-v1:0').
        """
        self.model_id = model_id
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=boto3.session.Config(read_timeout=300, connect_timeout=10),
        )

    def invoke(self, system_prompt: str, user_prompt: str) -> dict:
        """Send prompt to Claude Sonnet via Bedrock and return parsed JSON response.

        Retries up to 3 times with exponential backoff on throttling errors.
        Returns an empty dict on unrecoverable failures or invalid JSON.

        Args:
            system_prompt: System-level instruction for Claude.
            user_prompt: User-level prompt with data and questions.

        Returns:
            Parsed JSON dict from Claude's response, or empty dict on failure.
        """
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16384,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
        })

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=body,
                )

                response_body = json.loads(response["body"].read())
                text_content = response_body["content"][0]["text"]
                return self._parse_json_response(text_content)

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                last_error = e

                if error_code in ("ThrottlingException", "TooManyRequestsException"):
                    if attempt < MAX_RETRIES:
                        wait_time = BASE_BACKOFF_SECONDS * (2 ** attempt)
                        logger.warning(
                            "Bedrock throttled (attempt %d/%d), retrying in %.1fs",
                            attempt + 1, MAX_RETRIES + 1, wait_time,
                        )
                        time.sleep(wait_time)
                        continue

                logger.error("Bedrock API error: %s", e)
                return {}

            except Exception as e:
                logger.error("Bedrock invocation failed: %s", e)
                return {}

        logger.error("Bedrock max retries exhausted. Last error: %s", last_error)
        return {}

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """Extract and parse JSON from Claude's text response.

        Handles markdown code fences and truncated JSON responses.
        """
        cleaned = text.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) >= 3:
                cleaned = "\n".join(lines[1:-1]).strip()

        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
            if isinstance(result, list):
                return {"items": result}
            return {}
        except json.JSONDecodeError:
            # Try to repair truncated JSON by closing open brackets
            repaired = cleaned
            open_braces = repaired.count("{") - repaired.count("}")
            open_brackets = repaired.count("[") - repaired.count("]")

            # Truncate at last complete item (find last }, or ])
            last_complete = max(repaired.rfind("}"), repaired.rfind("]"))
            if last_complete > 0:
                repaired = repaired[:last_complete + 1]
                # Re-count after truncation
                open_braces = repaired.count("{") - repaired.count("}")
                open_brackets = repaired.count("[") - repaired.count("]")

            repaired += "]" * open_brackets + "}" * open_braces

            try:
                result = json.loads(repaired)
                logger.warning("Repaired truncated JSON response (closed %d braces, %d brackets)",
                             open_braces, open_brackets)
                if isinstance(result, dict):
                    return result
                if isinstance(result, list):
                    return {"items": result}
            except json.JSONDecodeError:
                pass

            logger.error("Failed to parse JSON from LLM response: %.200s", cleaned)
            return {}
