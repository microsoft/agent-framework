import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from pydantic import BaseModel
from agent_framework_openai import OpenAIChatClient
from agent_framework._types import Message

class OutputStruct(BaseModel):
    city: str

@pytest.mark.asyncio
async def test_response_format_pydantic_model_converted_to_dict():
    """Test that Pydantic model response_format is converted to a dict for the Responses API."""
    mock_async_client = MagicMock()
    mock_async_client.responses = MagicMock()
    mock_stream_ctx = AsyncMock()
    mock_async_client.responses.stream.return_value = mock_stream_ctx
    
    client = OpenAIChatClient(
        model="gpt-4o",
        api_key="fake-key",
        async_client=mock_async_client
    )
    
    messages = [Message(role="user", contents=["Test"])]
    
    # Trigger streaming path
    stream = client._inner_get_response(
        messages=messages,
        options={"response_format": OutputStruct},
        stream=True
    )
    
    async for _ in stream:
        break
        
    # Verify text_format was passed as a dict
    _, kwargs = mock_async_client.responses.stream.call_args
    text_format = kwargs.get("text_format")
    
    assert isinstance(text_format, dict)
    assert text_format["type"] == "json_schema"
    assert text_format["name"] == "OutputStruct"
    assert "schema" in text_format
    assert text_format["strict"] is True
