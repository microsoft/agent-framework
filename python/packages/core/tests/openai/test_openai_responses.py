from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_framework._types import ChatMessage, Role, TextContent
from agent_framework.openai._responses_client import OpenAIResponsesClient


def create_chat_message(text: str) -> ChatMessage:
    content = TextContent(text=text)
    return ChatMessage(role=Role.USER, contents=[content])


@pytest.mark.asyncio
async def test_store_parameter_not_sent_by_default():
    client = OpenAIResponsesClient(api_key="test-key", model_id="gpt-4o")
    with patch.object(client.client.responses, "create", new_callable=AsyncMock) as mock_create:
        # Create a properly structured mock response
        mock_response = MagicMock()
        mock_response.usage.input_tokens_details.cached_tokens = 10
        mock_response.usage.output_tokens_details.reasoning_tokens = 20
        mock_response.usage.input_tokens_details = mock_response.usage.input_tokens_details
        mock_response.usage.output_tokens_details = mock_response.usage.output_tokens_details
        mock_response.usage = mock_response.usage
        mock_create.return_value = mock_response

        message = create_chat_message("test")
        await client.get_response(messages=[message])

        args, kwargs = mock_create.call_args
        assert "store" not in kwargs


@pytest.mark.asyncio
async def test_store_parameter_explicit_false():
    client = OpenAIResponsesClient(api_key="test-key", model_id="gpt-4o")
    with patch.object(client.client.responses, "create", new_callable=AsyncMock) as mock_create:
        mock_response = MagicMock()
        mock_response.usage.input_tokens_details.cached_tokens = 15
        mock_response.usage.output_tokens_details.reasoning_tokens = 25
        mock_response.usage.input_tokens_details = mock_response.usage.input_tokens_details
        mock_response.usage.output_tokens_details = mock_response.usage.output_tokens_details
        mock_response.usage = mock_response.usage
        mock_create.return_value = mock_response

        message = create_chat_message("test")
        await client.get_response(messages=[message], store=False)

        args, kwargs = mock_create.call_args
        assert kwargs.get("store") is False


@pytest.mark.asyncio
async def test_store_parameter_explicit_true():
    client = OpenAIResponsesClient(api_key="test-key", model_id="gpt-4o")
    with patch.object(client.client.responses, "create", new_callable=AsyncMock) as mock_create:
        mock_response = MagicMock()
        mock_response.usage.input_tokens_details.cached_tokens = 30
        mock_response.usage.output_tokens_details.reasoning_tokens = 40
        mock_response.usage.input_tokens_details = mock_response.usage.input_tokens_details
        mock_response.usage.output_tokens_details = mock_response.usage.output_tokens_details
        mock_response.usage = mock_response.usage
        mock_create.return_value = mock_response

        message = create_chat_message("test")
        await client.get_response(messages=[message], store=True)

        args, kwargs = mock_create.call_args
        assert kwargs.get("store") is True
