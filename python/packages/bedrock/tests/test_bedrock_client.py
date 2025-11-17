# Copyright (c) Microsoft. All rights reserved.
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import ChatMessage, ChatOptions, Role, TextContent, ai_function
from agent_framework.exceptions import ServiceInitializationError
from agent_framework_bedrock import BedrockClient, BedrockSettings
from agent_framework_bedrock._chat_client import ModelProvider


class TestBedrockSettings:
    """Tests for BedrockSettings class."""

    def test_bedrock_settings_init_with_bearer_token(self, bedrock_unit_test_env):  # type: ignore
        """Test BedrockSettings initialization with bearer token."""
        settings = BedrockSettings()

        assert settings.bearer_token_bedrock is not None
        assert settings.bearer_token_bedrock.get_secret_value() == "test-bearer-token-12345"
        assert settings.region_name == "us-east-1"
        assert settings.chat_model_id == "anthropic.claude-3-5-sonnet-20241022-v2:0"

    def test_bedrock_settings_init_with_parameters(self):
        """Test BedrockSettings initialization with direct parameters."""
        settings = BedrockSettings(
            bearer_token_bedrock="custom-token",
            region_name="us-west-2",
            chat_model_id="amazon.titan-text-premier-v1:0",
        )

        assert settings.bearer_token_bedrock is not None
        assert settings.bearer_token_bedrock.get_secret_value() == "custom-token"
        assert settings.region_name == "us-west-2"
        assert settings.chat_model_id == "amazon.titan-text-premier-v1:0"

    def test_bedrock_settings_with_aws_credentials(self):
        """Test BedrockSettings with standard AWS credentials."""
        settings = BedrockSettings(
            aws_access_key_id="test-access-key",
            aws_secret_access_key="test-secret-key",
            aws_session_token="test-session-token",
        )

        assert settings.aws_access_key_id is not None
        assert settings.aws_access_key_id.get_secret_value() == "test-access-key"
        assert settings.aws_secret_access_key is not None
        assert settings.aws_secret_access_key.get_secret_value() == "test-secret-key"


class TestBedrockClientInitialization:
    """Tests for BedrockClient initialization."""

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_client_init_with_bearer_token(self, mock_boto3_client, bedrock_unit_test_env):  # type: ignore
        """Test BedrockClient initialization with bearer token."""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        client = BedrockClient()

        assert client.bedrock_client is not None
        assert client.model_id == "anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert client.use_converse_api is True
        assert client.region_name == "us-east-1"

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_client_init_with_custom_parameters(self, mock_boto3_client):
        """Test BedrockClient initialization with custom parameters."""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        client = BedrockClient(
            bearer_token="custom-token",
            region_name="us-west-2",
            model_id="amazon.titan-text-premier-v1:0",
            use_converse_api=False,
        )

        assert client.model_id == "amazon.titan-text-premier-v1:0"
        assert client.use_converse_api is False
        assert client.region_name == "us-west-2"

    def test_client_init_with_existing_boto3_client(self, mock_bedrock_client):  # type: ignore
        """Test BedrockClient initialization with existing boto3 client."""
        client = BedrockClient(
            bedrock_client=mock_bedrock_client, model_id="anthropic.claude-3-5-sonnet-20241022-v2:0"
        )

        assert client.bedrock_client is mock_bedrock_client
        assert client.model_id == "anthropic.claude-3-5-sonnet-20241022-v2:0"

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_client_init_missing_model_id_uses_env(self, mock_boto3_client, bedrock_unit_test_env):  # type: ignore
        """Test that missing model ID uses environment variable."""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        client = BedrockClient()

        assert client.model_id == "anthropic.claude-3-5-sonnet-20241022-v2:0"


class TestModelDetection:
    """Tests for model provider detection."""

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_detect_anthropic_provider(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test detection of Anthropic models."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        # Test various Anthropic model IDs
        assert client._detect_model_provider("anthropic.claude-3-5-sonnet-20241022-v2:0") == ModelProvider.ANTHROPIC
        assert client._detect_model_provider("anthropic.claude-3-haiku-20240307-v1:0") == ModelProvider.ANTHROPIC
        assert (
            client._detect_model_provider("us.anthropic.claude-sonnet-4-5-20250929-v1:0") == ModelProvider.ANTHROPIC
        )

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_detect_titan_provider(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test detection of Amazon Titan models."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        assert client._detect_model_provider("amazon.titan-text-premier-v1:0") == ModelProvider.AMAZON_TITAN
        assert client._detect_model_provider("amazon.titan-text-express-v1") == ModelProvider.AMAZON_TITAN

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_detect_unknown_provider(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test detection of unknown models."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        assert client._detect_model_provider("unknown-model-id") == ModelProvider.UNKNOWN

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_get_anthropic_capabilities(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test getting capabilities for Anthropic models."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        capabilities = client._get_model_capabilities(ModelProvider.ANTHROPIC)

        assert capabilities["supports_tools"] is True
        assert capabilities["supports_streaming"] is True
        assert capabilities["supports_images"] is True
        assert capabilities["max_tokens_default"] == 4096

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_get_titan_capabilities(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test getting capabilities for Titan models."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        capabilities = client._get_model_capabilities(ModelProvider.AMAZON_TITAN)

        assert capabilities["supports_tools"] is False
        assert capabilities["supports_streaming"] is True
        assert capabilities["supports_images"] is False
        assert capabilities["max_tokens_default"] == 3072


class TestMessageConversion:
    """Tests for message conversion to Bedrock format."""

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_convert_simple_messages(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test conversion of simple text messages."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        messages = [
            ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")]),
            ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="Hi there!")]),
        ]

        conversation_messages, system_messages = client._convert_messages_to_bedrock_format(messages)

        assert len(conversation_messages) == 2
        assert conversation_messages[0]["role"] == "user"
        assert conversation_messages[0]["content"][0]["text"] == "Hello"
        assert conversation_messages[1]["role"] == "assistant"
        assert conversation_messages[1]["content"][0]["text"] == "Hi there!"
        assert len(system_messages) == 0

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_convert_messages_with_system(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test conversion of messages with system message."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        messages = [
            ChatMessage(role=Role.SYSTEM, contents=[TextContent(text="You are a helpful assistant")]),
            ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")]),
        ]

        conversation_messages, system_messages = client._convert_messages_to_bedrock_format(messages)

        assert len(conversation_messages) == 1
        assert len(system_messages) == 1
        assert system_messages[0]["text"] == "You are a helpful assistant"


class TestToolConversion:
    """Tests for tool conversion to Bedrock format."""

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_convert_ai_function_to_tool(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test conversion of AIFunction to Bedrock tool format."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        @ai_function
        def get_weather(location: str) -> str:
            """Get weather for a location."""
            return f"Weather in {location}"

        tool_config = client._convert_tools_to_bedrock_format([get_weather])

        assert tool_config is not None
        assert "tools" in tool_config
        assert len(tool_config["tools"]) == 1

        tool_spec = tool_config["tools"][0]["toolSpec"]
        assert tool_spec["name"] == "get_weather"
        assert "Get weather for a location" in tool_spec["description"]
        assert "inputSchema" in tool_spec
        assert "json" in tool_spec["inputSchema"]

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_convert_tool_choice_auto(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test conversion of 'auto' tool choice."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        tool_choice = client._convert_tool_choice("auto")

        assert tool_choice == {"auto": {}}

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_convert_tool_choice_required(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test conversion of 'required' tool choice."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        tool_choice = client._convert_tool_choice("required")

        assert tool_choice == {"any": {}}

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_convert_tool_choice_none(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test conversion of 'none' tool choice."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        tool_choice = client._convert_tool_choice("none")

        assert tool_choice is None


class TestResponseProcessing:
    """Tests for processing Bedrock responses."""

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_process_converse_response(self, mock_boto3_client, mock_bedrock_client, mock_converse_response):  # type: ignore
        """Test processing of Converse API response."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        chat_response = client._process_converse_response(
            mock_converse_response, "anthropic.claude-3-5-sonnet-20241022-v2:0"
        )

        assert chat_response.response_id == "test-request-id-123"
        assert len(chat_response.messages) == 1
        assert chat_response.messages[0].role == Role.ASSISTANT
        assert len(chat_response.messages[0].contents) == 1
        assert chat_response.messages[0].contents[0].text == "Hello! I'm here to help. How can I assist you today?"
        assert chat_response.usage_details.input_token_count == 10
        assert chat_response.usage_details.output_token_count == 15
        assert chat_response.usage_details.total_token_count == 25

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_process_converse_response_with_tools(  # type: ignore
        self, mock_boto3_client, mock_bedrock_client, mock_converse_response_with_tools
    ):
        """Test processing of Converse API response with tool use."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        chat_response = client._process_converse_response(
            mock_converse_response_with_tools, "anthropic.claude-3-5-sonnet-20241022-v2:0"
        )

        assert len(chat_response.messages[0].contents) == 2
        # First content is text
        assert chat_response.messages[0].contents[0].text == "Let me check the weather for you."
        # Second content is function call
        assert hasattr(chat_response.messages[0].contents[1], "call_id")
        assert chat_response.messages[0].contents[1].name == "get_weather"
        assert chat_response.messages[0].contents[1].arguments == {"location": "San Francisco"}

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_parse_usage(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test parsing of usage information."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        usage = {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150}

        usage_details = client._parse_usage(usage)

        assert usage_details.input_token_count == 100
        assert usage_details.output_token_count == 50
        assert usage_details.total_token_count == 150

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_parse_usage_empty(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test parsing of empty usage information."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        usage_details = client._parse_usage(None)

        assert usage_details.input_token_count == 0
        assert usage_details.output_token_count == 0
        assert usage_details.total_token_count == 0


class TestRequestCreation:
    """Tests for creating Bedrock API requests."""

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_create_converse_request_basic(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test creation of basic Converse API request."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]
        chat_options = ChatOptions(temperature=0.7, max_tokens=1024)

        request = client._create_converse_request(
            messages, chat_options, "anthropic.claude-3-5-sonnet-20241022-v2:0"
        )

        assert request["modelId"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert len(request["messages"]) == 1
        assert request["messages"][0]["role"] == "user"
        assert request["inferenceConfig"]["temperature"] == 0.7
        assert request["inferenceConfig"]["maxTokens"] == 1024

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_create_converse_request_with_tools(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test creation of Converse API request with tools."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        @ai_function
        def get_weather(location: str) -> str:
            """Get weather."""
            return "sunny"

        messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="What's the weather?")])]
        chat_options = ChatOptions(tools=[get_weather])

        request = client._create_converse_request(
            messages, chat_options, "anthropic.claude-3-5-sonnet-20241022-v2:0"
        )

        assert "toolConfig" in request
        assert "tools" in request["toolConfig"]
        assert len(request["toolConfig"]["tools"]) == 1
        assert request["toolConfig"]["tools"][0]["toolSpec"]["name"] == "get_weather"


class TestStreamProcessing:
    """Tests for processing streaming responses."""

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_process_stream_event_message_start(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test processing of messageStart stream event."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        event = {"messageStart": {"role": "assistant"}}

        update = client._process_stream_event(event, "test-model")

        assert update is not None
        assert update.role == Role.ASSISTANT

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_process_stream_event_content_delta(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test processing of contentBlockDelta stream event."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        event = {"contentBlockDelta": {"delta": {"text": "Hello"}, "contentBlockIndex": 0}}

        update = client._process_stream_event(event, "test-model")

        assert update is not None
        assert len(update.contents) == 1
        assert update.contents[0].text == "Hello"

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_process_stream_event_metadata(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test processing of metadata stream event."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        event = {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}}}

        update = client._process_stream_event(event, "test-model")

        assert update is not None
        assert len(update.contents) == 1
        assert hasattr(update.contents[0], "details")

    @patch("agent_framework_bedrock._chat_client.boto3.client")
    def test_process_stream_event_message_stop(self, mock_boto3_client, mock_bedrock_client):  # type: ignore
        """Test processing of messageStop stream event."""
        client = BedrockClient(bedrock_client=mock_bedrock_client, model_id="test-model")

        event = {"messageStop": {"stopReason": "end_turn"}}

        update = client._process_stream_event(event, "test-model")

        assert update is not None
        assert update.finish_reason is not None
