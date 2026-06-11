"""Unit tests for the Bedrock Client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from llm.bedrock_client import BedrockClient


def _make_bedrock_response(content_text: str) -> dict:
    """Create a mock Bedrock API response."""
    body = json.dumps({
        "content": [{"text": content_text}],
    }).encode()
    mock_body = MagicMock()
    mock_body.read.return_value = body
    return {"body": mock_body}


class TestBedrockClientInit:
    """Tests for BedrockClient initialization."""

    @patch("llm.bedrock_client.boto3.client")
    def test_creates_bedrock_runtime_client(self, mock_boto3_client):
        client = BedrockClient(region="ap-south-1", model_id="anthropic.claude-3-sonnet-20240229-v1:0")
        mock_boto3_client.assert_called_once_with("bedrock-runtime", region_name="ap-south-1")
        assert client.model_id == "anthropic.claude-3-sonnet-20240229-v1:0"


class TestBedrockClientInvoke:
    """Tests for BedrockClient.invoke."""

    @patch("llm.bedrock_client.boto3.client")
    def test_successful_json_response(self, mock_boto3_client):
        mock_runtime = MagicMock()
        mock_boto3_client.return_value = mock_runtime
        mock_runtime.invoke_model.return_value = _make_bedrock_response(
            json.dumps({"verdict": "buy", "target": 100})
        )

        client = BedrockClient("ap-south-1", "test-model")
        result = client.invoke("system", "user")

        assert result == {"verdict": "buy", "target": 100}
        mock_runtime.invoke_model.assert_called_once()

    @patch("llm.bedrock_client.boto3.client")
    def test_json_wrapped_in_code_fences(self, mock_boto3_client):
        mock_runtime = MagicMock()
        mock_boto3_client.return_value = mock_runtime
        mock_runtime.invoke_model.return_value = _make_bedrock_response(
            '```json\n{"key": "value"}\n```'
        )

        client = BedrockClient("ap-south-1", "test-model")
        result = client.invoke("system", "user")

        assert result == {"key": "value"}

    @patch("llm.bedrock_client.boto3.client")
    def test_list_response_wrapped_in_items(self, mock_boto3_client):
        mock_runtime = MagicMock()
        mock_boto3_client.return_value = mock_runtime
        mock_runtime.invoke_model.return_value = _make_bedrock_response(
            json.dumps([{"name": "A"}, {"name": "B"}])
        )

        client = BedrockClient("ap-south-1", "test-model")
        result = client.invoke("system", "user")

        assert result == {"items": [{"name": "A"}, {"name": "B"}]}

    @patch("llm.bedrock_client.boto3.client")
    def test_invalid_json_returns_empty_dict(self, mock_boto3_client):
        mock_runtime = MagicMock()
        mock_boto3_client.return_value = mock_runtime
        mock_runtime.invoke_model.return_value = _make_bedrock_response(
            "This is not valid JSON at all"
        )

        client = BedrockClient("ap-south-1", "test-model")
        result = client.invoke("system", "user")

        assert result == {}

    @patch("llm.bedrock_client.boto3.client")
    def test_throttling_retries_with_backoff(self, mock_boto3_client):
        from botocore.exceptions import ClientError

        mock_runtime = MagicMock()
        mock_boto3_client.return_value = mock_runtime

        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        mock_runtime.invoke_model.side_effect = [
            ClientError(error_response, "InvokeModel"),
            ClientError(error_response, "InvokeModel"),
            _make_bedrock_response(json.dumps({"result": "ok"})),
        ]

        client = BedrockClient("ap-south-1", "test-model")
        with patch("llm.bedrock_client.time.sleep"):
            result = client.invoke("system", "user")

        assert result == {"result": "ok"}
        assert mock_runtime.invoke_model.call_count == 3

    @patch("llm.bedrock_client.boto3.client")
    def test_throttling_exhausts_retries(self, mock_boto3_client):
        from botocore.exceptions import ClientError

        mock_runtime = MagicMock()
        mock_boto3_client.return_value = mock_runtime

        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        mock_runtime.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        client = BedrockClient("ap-south-1", "test-model")
        with patch("llm.bedrock_client.time.sleep"):
            result = client.invoke("system", "user")

        assert result == {}
        assert mock_runtime.invoke_model.call_count == 4  # 1 initial + 3 retries

    @patch("llm.bedrock_client.boto3.client")
    def test_non_throttle_client_error_no_retry(self, mock_boto3_client):
        from botocore.exceptions import ClientError

        mock_runtime = MagicMock()
        mock_boto3_client.return_value = mock_runtime

        error_response = {"Error": {"Code": "ValidationException", "Message": "Bad request"}}
        mock_runtime.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        client = BedrockClient("ap-south-1", "test-model")
        result = client.invoke("system", "user")

        assert result == {}
        assert mock_runtime.invoke_model.call_count == 1

    @patch("llm.bedrock_client.boto3.client")
    def test_unexpected_exception_returns_empty(self, mock_boto3_client):
        mock_runtime = MagicMock()
        mock_boto3_client.return_value = mock_runtime
        mock_runtime.invoke_model.side_effect = RuntimeError("Connection lost")

        client = BedrockClient("ap-south-1", "test-model")
        result = client.invoke("system", "user")

        assert result == {}
