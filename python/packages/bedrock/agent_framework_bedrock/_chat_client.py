# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from collections.abc import AsyncIterable, Callable, MutableSequence, Sequence
from enum import Enum
from typing import Any, ClassVar, Final, TypeVar

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AIFunction,
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Contents,
    DataContent,
    FinishReason,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    ToolProtocol,
    UsageContent,
    UsageDetails,
    get_logger,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_observability
from pydantic import SecretStr, ValidationError

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError as e:
    raise ImportError(
        "boto3 and botocore are required for AWS Bedrock integration. "
        "Install them with: pip install boto3 botocore"
    ) from e

logger = get_logger("agent_framework.bedrock")

BEDROCK_DEFAULT_MAX_TOKENS: Final[int] = 4096
BEDROCK_DEFAULT_REGION: Final[str] = "us-east-1"

ROLE_MAP: dict[Role, str] = {
    Role.USER: "user",
    Role.ASSISTANT: "assistant",
    Role.SYSTEM: "user",  # System messages handled separately in Bedrock
    Role.TOOL: "user",  # Tool results sent as user messages
}

FINISH_REASON_MAP: dict[str, FinishReason] = {
    "end_turn": FinishReason.STOP,
    "tool_use": FinishReason.TOOL_CALLS,
    "max_tokens": FinishReason.LENGTH,
    "stop_sequence": FinishReason.STOP,
    "content_filtered": FinishReason.CONTENT_FILTER,
}


class ModelProvider(Enum):
    """Supported model providers in AWS Bedrock."""

    ANTHROPIC = "anthropic"
    AMAZON_TITAN = "amazon.titan"
    AI21 = "ai21"
    COHERE = "cohere"
    META = "meta"
    MISTRAL = "mistral"
    UNKNOWN = "unknown"


class BedrockSettings(AFBaseSettings):
    """AWS Bedrock settings.

    The settings are first loaded from environment variables with the prefix 'AWS_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        bearer_token_bedrock: The AWS bearer token for Bedrock authentication.
        region_name: AWS region name (default: us-east-1).
        chat_model_id: The Bedrock model ID to use.
        aws_access_key_id: AWS access key ID for standard authentication.
        aws_secret_access_key: AWS secret access key for standard authentication.
        aws_session_token: AWS session token for temporary credentials.
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework_bedrock import BedrockSettings

            # Using environment variables
            # Set AWS_BEARER_TOKEN_BEDROCK=your_bearer_token
            # AWS_REGION_NAME=us-east-1
            # AWS_CHAT_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

            # Or passing parameters directly
            settings = BedrockSettings(
                bearer_token_bedrock="your_bearer_token",
                chat_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0"
            )

            # Or loading from a .env file
            settings = BedrockSettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "AWS_"

    bearer_token_bedrock: SecretStr | None = None
    region_name: str | None = BEDROCK_DEFAULT_REGION
    chat_model_id: str | None = None
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_session_token: SecretStr | None = None


TBedrockClient = TypeVar("TBedrockClient", bound="BedrockClient")


@use_function_invocation
@use_observability
@use_chat_middleware
class BedrockClient(BaseChatClient):
    """AWS Bedrock Chat client.

    Supports both Converse API (recommended) and InvokeModel API for accessing
    foundation models on AWS Bedrock.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "aws-bedrock"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        bearer_token: str | None = None,
        region_name: str | None = None,
        model_id: str | None = None,
        bedrock_client: Any | None = None,
        use_converse_api: bool = True,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_session_token: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an AWS Bedrock client.

        Keyword Args:
            bearer_token: The AWS bearer token for Bedrock authentication.
            region_name: AWS region name (default: us-east-1).
            model_id: The ID of the Bedrock model to use.
            bedrock_client: An existing boto3 bedrock-runtime client to use. If not provided, one will be created.
            use_converse_api: Whether to use Converse API (True) or InvokeModel API (False). Default: True.
            aws_access_key_id: AWS access key ID for standard authentication.
            aws_secret_access_key: AWS secret access key for standard authentication.
            aws_session_token: AWS session token for temporary credentials.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            kwargs: Additional keyword arguments passed to the parent class.

        Examples:
            .. code-block:: python

                from agent_framework_bedrock import BedrockClient

                # Using bearer token
                client = BedrockClient(
                    bearer_token="your-bearer-token",
                    region_name="us-east-1",
                    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
                )

                # Using standard AWS credentials
                client = BedrockClient(
                    aws_access_key_id="your-access-key",
                    aws_secret_access_key="your-secret-key",
                    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
                )

                # Using environment variables
                client = BedrockClient()

                # Passing in an existing boto3 client
                import boto3
                bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')
                client = BedrockClient(
                    bedrock_client=bedrock,
                    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
                )
        """
        try:
            bedrock_settings = BedrockSettings(
                bearer_token_bedrock=bearer_token,  # type: ignore[arg-type]
                region_name=region_name,
                chat_model_id=model_id,
                aws_access_key_id=aws_access_key_id,  # type: ignore[arg-type]
                aws_secret_access_key=aws_secret_access_key,  # type: ignore[arg-type]
                aws_session_token=aws_session_token,  # type: ignore[arg-type]
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Bedrock settings.", ex) from ex

        if bedrock_client is None:
            bedrock_client = self._create_bedrock_client(bedrock_settings)

        # Initialize parent
        super().__init__(**kwargs)

        # Initialize instance variables
        self.bedrock_client = bedrock_client
        self.model_id = bedrock_settings.chat_model_id
        self.use_converse_api = use_converse_api
        self.region_name = bedrock_settings.region_name

        # Track current tool use for streaming
        self._current_tool_use: dict[str, Any] = {}
        self._last_tool_name: str | None = None

    def _create_bedrock_client(self, settings: BedrockSettings) -> Any:
        """Create and configure boto3 bedrock-runtime client.

        Priority order:
        1. Bearer token (AWS_BEARER_TOKEN_BEDROCK)
        2. Standard AWS credentials (access key/secret key)
        3. Default boto3 credential chain

        Args:
            settings: BedrockSettings with authentication configuration.

        Returns:
            Configured boto3 bedrock-runtime client.

        Raises:
            ServiceInitializationError: If client creation fails.
        """
        try:
            import os

            # Priority 1: Bearer token
            if settings.bearer_token_bedrock:
                logger.info("Using bearer token for Bedrock authentication")
                # Set the AWS_BEARER_TOKEN_BEDROCK environment variable
                # boto3 automatically detects and uses this for authentication
                os.environ['AWS_BEARER_TOKEN_BEDROCK'] = settings.bearer_token_bedrock.get_secret_value()

            # Priority 2: Standard AWS credentials
            elif settings.aws_access_key_id and settings.aws_secret_access_key:
                logger.info("Using AWS access key/secret for Bedrock authentication")
                # Set credentials as environment variables for boto3
                os.environ['AWS_ACCESS_KEY_ID'] = settings.aws_access_key_id.get_secret_value()
                os.environ['AWS_SECRET_ACCESS_KEY'] = settings.aws_secret_access_key.get_secret_value()
                if settings.aws_session_token:
                    os.environ['AWS_SESSION_TOKEN'] = settings.aws_session_token.get_secret_value()

            # Priority 3: Default boto3 credential chain (environment, ~/.aws/credentials, instance profile)
            else:
                logger.info("Using default AWS credential chain for Bedrock authentication")

            # Create boto3 client - it will automatically use credentials from environment
            return boto3.client(
                service_name="bedrock-runtime",
                region_name=settings.region_name or BEDROCK_DEFAULT_REGION,
            )

        except NoCredentialsError as ex:
            raise ServiceInitializationError(
                "AWS credentials not found. Set via 'bearer_token', 'aws_access_key_id/aws_secret_access_key', "
                "or configure AWS credentials via environment variables or ~/.aws/credentials file."
            ) from ex
        except Exception as ex:
            raise ServiceInitializationError(f"Failed to create Bedrock client: {ex}") from ex

    def _detect_model_provider(self, model_id: str) -> ModelProvider:
        """Detect model provider from model ID.

        Args:
            model_id: The Bedrock model ID.

        Returns:
            ModelProvider enum value.

        Examples:
            - anthropic.claude-3-5-sonnet-20241022-v2:0 -> ANTHROPIC
            - amazon.titan-text-premier-v1:0 -> AMAZON_TITAN
            - us.anthropic.claude-sonnet-4-5-20250929-v1:0 -> ANTHROPIC (inference profile)
        """
        # Handle inference profile format (region.provider.model)
        model_id_lower = model_id.lower()

        for provider in ModelProvider:
            if provider.value in model_id_lower:
                return provider

        return ModelProvider.UNKNOWN

    def _get_model_capabilities(self, provider: ModelProvider) -> dict[str, Any]:
        """Get capabilities for model provider.

        Args:
            provider: The detected ModelProvider.

        Returns:
            Dictionary of model capabilities.
        """
        capabilities = {
            ModelProvider.ANTHROPIC: {
                "supports_tools": True,
                "supports_streaming": True,
                "supports_images": True,
                "supports_documents": True,
                "max_tokens_default": 4096,
            },
            ModelProvider.AMAZON_TITAN: {
                "supports_tools": False,
                "supports_streaming": True,
                "supports_images": False,
                "supports_documents": False,
                "max_tokens_default": 3072,
            },
            ModelProvider.AI21: {
                "supports_tools": False,
                "supports_streaming": True,
                "supports_images": False,
                "supports_documents": False,
                "max_tokens_default": 2048,
            },
            ModelProvider.COHERE: {
                "supports_tools": True,
                "supports_streaming": True,
                "supports_images": False,
                "supports_documents": False,
                "max_tokens_default": 2048,
            },
            ModelProvider.META: {
                "supports_tools": False,
                "supports_streaming": True,
                "supports_images": False,
                "supports_documents": False,
                "max_tokens_default": 2048,
            },
            ModelProvider.MISTRAL: {
                "supports_tools": True,
                "supports_streaming": True,
                "supports_images": False,
                "supports_documents": False,
                "max_tokens_default": 2048,
            },
        }

        return capabilities.get(
            provider,
            {
                "supports_tools": False,
                "supports_streaming": True,
                "supports_images": False,
                "supports_documents": False,
                "max_tokens_default": 1024,
            },
        )

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get response using AWS Bedrock Converse or InvokeModel API.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            kwargs: Additional keyword arguments.

        Returns:
            ChatResponse with the model's response.

        Raises:
            ServiceError: If the API call fails.
        """
        model_id = chat_options.model_id or self.model_id
        if not model_id:
            raise ValueError("Model ID is required. Set via 'model_id' parameter or AWS_CHAT_MODEL_ID.")

        if self.use_converse_api:
            return await self._get_converse_response(messages, chat_options, model_id, **kwargs)
        else:
            return await self._get_invoke_model_response(messages, chat_options, model_id, **kwargs)

    async def _get_converse_response(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get response using Bedrock Converse API.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Returns:
            ChatResponse with the model's response.
        """
        request_params = self._create_converse_request(messages, chat_options, model_id, **kwargs)

        try:
            # Use asyncio.to_thread since boto3 is synchronous
            response = await asyncio.to_thread(self.bedrock_client.converse, **request_params)
            return self._process_converse_response(response, model_id)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"Bedrock Converse API error [{error_code}]: {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Bedrock Converse API: {e}")
            raise

    async def _get_invoke_model_response(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get response using Bedrock InvokeModel API.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Returns:
            ChatResponse with the model's response.
        """
        request_params = self._create_invoke_model_request(messages, chat_options, model_id, **kwargs)

        try:
            response = await asyncio.to_thread(self.bedrock_client.invoke_model, **request_params)
            response_body = json.loads(response["body"].read())
            return self._process_invoke_model_response(response_body, model_id, response)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"Bedrock InvokeModel API error [{error_code}]: {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Bedrock InvokeModel API: {e}")
            raise

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Stream response using AWS Bedrock ConverseStream or InvokeModelWithResponseStream API.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            kwargs: Additional keyword arguments.

        Yields:
            ChatResponseUpdate with incremental response updates.

        Raises:
            ServiceError: If the API call fails.
        """
        model_id = chat_options.model_id or self.model_id
        if not model_id:
            raise ValueError("Model ID is required. Set via 'model_id' parameter or AWS_CHAT_MODEL_ID.")

        if self.use_converse_api:
            async for chunk in self._stream_converse_response(messages, chat_options, model_id, **kwargs):
                yield chunk
        else:
            async for chunk in self._stream_invoke_model_response(messages, chat_options, model_id, **kwargs):
                yield chunk

    async def _stream_converse_response(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Stream response using Bedrock ConverseStream API.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Yields:
            ChatResponseUpdate with incremental response updates.
        """
        request_params = self._create_converse_request(messages, chat_options, model_id, **kwargs)

        try:
            response_stream = await asyncio.to_thread(self.bedrock_client.converse_stream, **request_params)

            # Process stream events
            stream = response_stream.get("stream", [])
            for event in stream:
                if chunk := self._process_stream_event(event, model_id):
                    yield chunk

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"Bedrock ConverseStream API error [{error_code}]: {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Bedrock ConverseStream API: {e}")
            raise

    async def _stream_invoke_model_response(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Stream response using Bedrock InvokeModelWithResponseStream API.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Yields:
            ChatResponseUpdate with incremental response updates.
        """
        request_params = self._create_invoke_model_request(messages, chat_options, model_id, **kwargs)

        try:
            response_stream = await asyncio.to_thread(
                self.bedrock_client.invoke_model_with_response_stream, **request_params
            )

            # Process stream events
            stream = response_stream.get("body", [])
            for event in stream:
                if chunk := self._process_invoke_stream_event(event, model_id):
                    yield chunk

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"Bedrock InvokeModelWithResponseStream API error [{error_code}]: {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Bedrock InvokeModelWithResponseStream API: {e}")
            raise

    def _create_converse_request(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create Converse API request parameters.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Returns:
            Dictionary of request parameters for Converse API.
        """
        # Convert messages to Bedrock format
        conversation_messages, system_messages = self._convert_messages_to_bedrock_format(messages)

        # Build request
        request: dict[str, Any] = {
            "modelId": model_id,
            "messages": conversation_messages,
        }

        # Add system messages if present
        if system_messages:
            request["system"] = system_messages

        # Add inference configuration
        inference_config: dict[str, Any] = {}
        if chat_options.max_tokens:
            inference_config["maxTokens"] = chat_options.max_tokens
        else:
            # Use default based on model provider
            provider = self._detect_model_provider(model_id)
            capabilities = self._get_model_capabilities(provider)
            inference_config["maxTokens"] = capabilities["max_tokens_default"]

        if chat_options.temperature is not None:
            inference_config["temperature"] = chat_options.temperature

        if chat_options.top_p is not None:
            inference_config["topP"] = chat_options.top_p

        if chat_options.stop:
            if isinstance(chat_options.stop, str):
                inference_config["stopSequences"] = [chat_options.stop]
            else:
                inference_config["stopSequences"] = list(chat_options.stop)

        if inference_config:
            request["inferenceConfig"] = inference_config

        # Add tool configuration
        if tool_config := self._convert_tools_to_bedrock_format(chat_options.tools):
            if tool_choice := self._convert_tool_choice(chat_options.tool_choice):
                tool_config["toolChoice"] = tool_choice
            request["toolConfig"] = tool_config

        return request

    def _create_invoke_model_request(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create InvokeModel API request parameters.

        Different models require different request formats.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Returns:
            Dictionary of request parameters for InvokeModel API.
        """
        provider = self._detect_model_provider(model_id)

        if provider == ModelProvider.ANTHROPIC:
            return self._create_anthropic_invoke_request(messages, chat_options, model_id, **kwargs)
        elif provider == ModelProvider.AMAZON_TITAN:
            return self._create_titan_invoke_request(messages, chat_options, model_id, **kwargs)
        else:
            # Generic fallback - try Converse API format
            return self._create_generic_invoke_request(messages, chat_options, model_id, **kwargs)

    def _create_anthropic_invoke_request(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create InvokeModel request for Anthropic Claude models.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Returns:
            Dictionary of request parameters.
        """
        # Convert messages
        conversation_messages, system_messages = self._convert_messages_to_bedrock_format(messages)

        # Build body
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": conversation_messages,
            "max_tokens": chat_options.max_tokens or 4096,
        }

        # Add system message if present
        if system_messages:
            body["system"] = " ".join([msg["text"] for msg in system_messages])

        if chat_options.temperature is not None:
            body["temperature"] = chat_options.temperature

        if chat_options.top_p is not None:
            body["top_p"] = chat_options.top_p

        if chat_options.stop:
            if isinstance(chat_options.stop, str):
                body["stop_sequences"] = [chat_options.stop]
            else:
                body["stop_sequences"] = list(chat_options.stop)

        # Add tools if present
        if chat_options.tools:
            if tool_config := self._convert_tools_to_bedrock_format(chat_options.tools):
                body["tools"] = tool_config.get("tools", [])

        return {
            "modelId": model_id,
            "body": json.dumps(body),
            "contentType": "application/json",
            "accept": "application/json",
        }

    def _create_titan_invoke_request(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create InvokeModel request for Amazon Titan models.

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Returns:
            Dictionary of request parameters.
        """
        # Titan uses a different format
        # Combine all messages into a single prompt
        prompt = ""
        for msg in messages:
            if msg.role == Role.USER:
                prompt += f"User: {msg.text}\n"
            elif msg.role == Role.ASSISTANT:
                prompt += f"Bot: {msg.text}\n"
            elif msg.role == Role.SYSTEM:
                prompt = f"{msg.text}\n\n{prompt}"

        prompt += "Bot:"

        body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": chat_options.max_tokens or 3072,
                "temperature": chat_options.temperature or 0.7,
                "topP": chat_options.top_p or 0.9,
            },
        }

        if chat_options.stop:
            if isinstance(chat_options.stop, str):
                body["textGenerationConfig"]["stopSequences"] = [chat_options.stop]
            else:
                body["textGenerationConfig"]["stopSequences"] = list(chat_options.stop)

        return {
            "modelId": model_id,
            "body": json.dumps(body),
            "contentType": "application/json",
            "accept": "application/json",
        }

    def _create_generic_invoke_request(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        model_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create generic InvokeModel request (fallback).

        Args:
            messages: List of chat messages.
            chat_options: Options for the chat completion.
            model_id: The Bedrock model ID.
            kwargs: Additional keyword arguments.

        Returns:
            Dictionary of request parameters.
        """
        # Use Converse API format as generic fallback
        conversation_messages, system_messages = self._convert_messages_to_bedrock_format(messages)

        body: dict[str, Any] = {
            "messages": conversation_messages,
            "max_tokens": chat_options.max_tokens or 1024,
        }

        if system_messages:
            body["system"] = system_messages

        if chat_options.temperature is not None:
            body["temperature"] = chat_options.temperature

        return {
            "modelId": model_id,
            "body": json.dumps(body),
            "contentType": "application/json",
            "accept": "application/json",
        }

    def _convert_messages_to_bedrock_format(
        self, messages: MutableSequence[ChatMessage]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Convert ChatMessage list to Bedrock format.

        Bedrock Converse API expects:
        - System messages as separate 'system' parameter
        - User/assistant messages in 'messages' list
        - Each message has 'role' and 'content' list

        Args:
            messages: List of ChatMessage objects.

        Returns:
            Tuple of (conversation_messages, system_messages).
        """
        system_messages: list[dict[str, Any]] = []
        conversation_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == Role.SYSTEM:
                # System messages handled separately
                system_messages.append({"text": msg.text or ""})
            else:
                # Convert message contents
                conversation_messages.append(
                    {"role": ROLE_MAP[msg.role], "content": self._convert_contents(msg.contents)}
                )

        return conversation_messages, system_messages

    def _convert_contents(self, contents: Sequence[Contents]) -> list[dict[str, Any]]:
        """Convert content objects to Bedrock format.

        Bedrock content types:
        - text: {'text': '...'}
        - image: {'image': {'format': 'png', 'source': {'bytes': b'...'}}}
        - toolUse: {'toolUse': {'toolUseId': '...', 'name': '...', 'input': {...}}}
        - toolResult: {'toolResult': {'toolUseId': '...', 'content': [...]}}

        Args:
            contents: List of content objects.

        Returns:
            List of Bedrock-formatted content blocks.
        """
        bedrock_contents: list[dict[str, Any]] = []

        for content in contents:
            if isinstance(content, TextContent):
                bedrock_contents.append({"text": content.text})

            elif isinstance(content, DataContent):
                # Handle image data
                if content.has_top_level_media_type("image"):
                    # Determine image format from media type
                    image_format = "png"  # default
                    if content.media_type:
                        if "jpeg" in content.media_type or "jpg" in content.media_type:
                            image_format = "jpeg"
                        elif "gif" in content.media_type:
                            image_format = "gif"
                        elif "webp" in content.media_type:
                            image_format = "webp"

                    # Get bytes from data URI
                    import base64

                    image_bytes = base64.b64decode(content.get_data_bytes_as_str())

                    bedrock_contents.append(
                        {"image": {"format": image_format, "source": {"bytes": image_bytes}}}
                    )
                else:
                    logger.debug(f"Ignoring unsupported data content media type: {content.media_type}")

            elif isinstance(content, FunctionCallContent):
                # Track for later use
                self._last_tool_name = content.name
                bedrock_contents.append(
                    {
                        "toolUse": {
                            "toolUseId": content.call_id,
                            "name": content.name,
                            "input": content.arguments if isinstance(content.arguments, dict) else {},
                        }
                    }
                )

            elif isinstance(content, FunctionResultContent):
                # Tool result content
                result_contents = []
                if isinstance(content.result, str):
                    result_contents = [{"text": content.result}]
                elif isinstance(content.result, dict):
                    result_contents = [{"json": content.result}]
                else:
                    result_contents = [{"text": str(content.result)}]

                bedrock_contents.append(
                    {"toolResult": {"toolUseId": content.call_id, "content": result_contents}}
                )

        return bedrock_contents

    def _convert_tools_to_bedrock_format(
        self, tools: list[ToolProtocol | dict[str, Any] | Callable[..., Any]] | None
    ) -> dict[str, Any] | None:
        """Convert framework tools to Bedrock toolConfig.

        Args:
            tools: List of tools to convert.

        Returns:
            Dictionary with 'tools' list, or None if no tools.
        """
        if not tools:
            return None

        tool_specs: list[dict[str, Any]] = []

        for tool in tools:
            if isinstance(tool, AIFunction):
                tool_specs.append(
                    {
                        "toolSpec": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "inputSchema": {"json": tool.parameters()},
                        }
                    }
                )
            elif isinstance(tool, dict):
                # Pass through pre-formatted tools
                tool_specs.append(tool)

        return {"tools": tool_specs} if tool_specs else None

    def _convert_tool_choice(self, tool_mode: Any) -> dict[str, Any] | None:
        """Convert framework tool choice to Bedrock format.

        Framework: 'auto', 'required', 'none'
        Bedrock: {'auto': {}}, {'any': {}}, or None

        Args:
            tool_mode: Framework tool mode.

        Returns:
            Bedrock tool choice configuration or None.
        """
        if tool_mode is None or tool_mode == "auto":
            return {"auto": {}}
        elif tool_mode == "required":
            return {"any": {}}
        elif tool_mode == "none":
            return None

        # Default to auto
        return {"auto": {}}

    def _process_converse_response(self, response: dict[str, Any], model_id: str) -> ChatResponse:
        """Process Converse API response.

        Args:
            response: Raw response from Converse API.
            model_id: The model ID used.

        Returns:
            ChatResponse object.
        """
        message_data = response["output"]["message"]

        return ChatResponse(
            response_id=response["ResponseMetadata"]["RequestId"],
            messages=[
                ChatMessage(
                    role=Role.ASSISTANT,
                    contents=self._parse_bedrock_contents(message_data["content"]),
                    raw_representation=message_data,
                )
            ],
            usage_details=self._parse_usage(response.get("usage")),
            model_id=model_id,
            finish_reason=self._map_stop_reason(response.get("stopReason")),
            raw_response=response,
        )

    def _process_invoke_model_response(
        self, response_body: dict[str, Any], model_id: str, full_response: dict[str, Any]
    ) -> ChatResponse:
        """Process InvokeModel API response.

        Args:
            response_body: Parsed JSON response body.
            model_id: The model ID used.
            full_response: Full response including metadata.

        Returns:
            ChatResponse object.
        """
        provider = self._detect_model_provider(model_id)

        if provider == ModelProvider.ANTHROPIC:
            # Anthropic format
            content = response_body.get("content", [])
            usage = response_body.get("usage", {})
            stop_reason = response_body.get("stop_reason")

            return ChatResponse(
                response_id=full_response["ResponseMetadata"]["RequestId"],
                messages=[
                    ChatMessage(
                        role=Role.ASSISTANT,
                        contents=self._parse_bedrock_contents(content),
                        raw_representation=response_body,
                    )
                ],
                usage_details=UsageDetails(
                    input_token_count=usage.get("input_tokens", 0),
                    output_token_count=usage.get("output_tokens", 0),
                    total_token_count=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                ),
                model_id=model_id,
                finish_reason=self._map_stop_reason(stop_reason),
                raw_response=full_response,
            )

        elif provider == ModelProvider.AMAZON_TITAN:
            # Titan format
            results = response_body.get("results", [{}])
            output_text = results[0].get("outputText", "") if results else ""
            input_token_count = response_body.get("inputTextTokenCount", 0)

            return ChatResponse(
                response_id=full_response["ResponseMetadata"]["RequestId"],
                messages=[
                    ChatMessage(
                        role=Role.ASSISTANT,
                        contents=[TextContent(text=output_text)],
                        raw_representation=response_body,
                    )
                ],
                usage_details=UsageDetails(
                    input_token_count=input_token_count,
                    output_token_count=0,  # Titan doesn't provide output token count
                    total_token_count=input_token_count,
                ),
                model_id=model_id,
                finish_reason=FinishReason.STOP,
                raw_response=full_response,
            )

        else:
            # Generic fallback
            text = response_body.get("completion", "") or response_body.get("text", "") or str(response_body)

            return ChatResponse(
                response_id=full_response["ResponseMetadata"]["RequestId"],
                messages=[
                    ChatMessage(
                        role=Role.ASSISTANT,
                        contents=[TextContent(text=text)],
                        raw_representation=response_body,
                    )
                ],
                usage_details=UsageDetails(input_token_count=0, output_token_count=0, total_token_count=0),
                model_id=model_id,
                finish_reason=FinishReason.STOP,
                raw_response=full_response,
            )

    def _parse_bedrock_contents(self, content_list: list[dict[str, Any]]) -> list[Contents]:
        """Parse Bedrock content blocks to framework Contents.

        Args:
            content_list: List of Bedrock content blocks.

        Returns:
            List of framework Contents objects.
        """
        contents: list[Contents] = []

        for block in content_list:
            if "text" in block:
                contents.append(TextContent(text=block["text"], raw_representation=block))

            elif "toolUse" in block:
                tool_use = block["toolUse"]
                self._last_tool_name = tool_use["name"]
                contents.append(
                    FunctionCallContent(
                        call_id=tool_use["toolUseId"],
                        name=tool_use["name"],
                        arguments=tool_use.get("input", {}),
                        raw_representation=block,
                    )
                )

            elif "toolResult" in block:
                tool_result = block["toolResult"]
                # Extract text from content
                result_text = ""
                if "content" in tool_result:
                    for content in tool_result["content"]:
                        if "text" in content:
                            result_text += content["text"]

                contents.append(
                    FunctionResultContent(
                        call_id=tool_result["toolUseId"],
                        name=self._last_tool_name or "unknown",
                        result=result_text or tool_result.get("content"),
                        raw_representation=block,
                    )
                )

        return contents

    def _parse_usage(self, usage: dict[str, Any] | None) -> UsageDetails:
        """Parse usage information from Bedrock response.

        Args:
            usage: Usage dictionary from Bedrock.

        Returns:
            UsageDetails object.
        """
        if not usage:
            return UsageDetails(input_token_count=0, output_token_count=0, total_token_count=0)

        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)
        total_tokens = usage.get("totalTokens", input_tokens + output_tokens)

        return UsageDetails(input_token_count=input_tokens, output_token_count=output_tokens, total_token_count=total_tokens)

    def _map_stop_reason(self, stop_reason: str | None) -> FinishReason:
        """Map Bedrock stop reason to framework FinishReason.

        Args:
            stop_reason: Bedrock stop reason string.

        Returns:
            FinishReason enum value.
        """
        if not stop_reason:
            return FinishReason.STOP

        return FINISH_REASON_MAP.get(stop_reason, FinishReason.STOP)

    def _process_stream_event(self, event: dict[str, Any], model_id: str) -> ChatResponseUpdate | None:
        """Process ConverseStream events.

        Event types:
        - messageStart: Initial metadata
        - contentBlockStart: Start of content block
        - contentBlockDelta: Incremental content
        - contentBlockStop: End of content block
        - messageStop: End of message
        - metadata: Token usage and metrics

        Args:
            event: Stream event from ConverseStream.
            model_id: The model ID used.

        Returns:
            ChatResponseUpdate or None if event should be skipped.
        """
        # Event has single key indicating type
        if not event:
            return None

        event_type = list(event.keys())[0]
        event_data = event[event_type]

        if event_type == "messageStart":
            return ChatResponseUpdate(
                role=Role.ASSISTANT,
                contents=[],
                raw_response=event,
            )

        elif event_type == "contentBlockStart":
            # Track starting content block
            block_data = event_data.get("start", {})
            if "toolUse" in block_data:
                tool_use = block_data["toolUse"]
                self._current_tool_use = tool_use
                self._last_tool_name = tool_use.get("name")
                return ChatResponseUpdate(
                    contents=[
                        FunctionCallContent(
                            call_id=tool_use["toolUseId"], name=tool_use["name"], arguments={}, raw_representation=event
                        )
                    ],
                    raw_response=event,
                )
            return None

        elif event_type == "contentBlockDelta":
            # Process incremental updates
            delta = event_data.get("delta", {})

            if "text" in delta:
                return ChatResponseUpdate(
                    contents=[TextContent(text=delta["text"], raw_representation=event)], raw_response=event
                )

            elif "toolUse" in delta:
                # Incremental tool use input
                tool_use_delta = delta["toolUse"]
                if self._current_tool_use:
                    return ChatResponseUpdate(
                        contents=[
                            FunctionCallContent(
                                call_id=self._current_tool_use["toolUseId"],
                                name=self._current_tool_use.get("name", ""),
                                arguments=tool_use_delta.get("input", {}),
                                raw_representation=event,
                            )
                        ],
                        raw_response=event,
                    )

        elif event_type == "contentBlockStop":
            # End of content block
            return None

        elif event_type == "metadata":
            # Usage information
            usage = event_data.get("usage", {})
            usage_details = self._parse_usage(usage)
            return ChatResponseUpdate(
                contents=[UsageContent(details=usage_details, raw_representation=event)], raw_response=event
            )

        elif event_type == "messageStop":
            # Final event
            return ChatResponseUpdate(
                finish_reason=self._map_stop_reason(event_data.get("stopReason")), raw_response=event
            )

        return None

    def _process_invoke_stream_event(self, event: dict[str, Any], model_id: str) -> ChatResponseUpdate | None:
        """Process InvokeModelWithResponseStream events.

        Args:
            event: Stream event from InvokeModelWithResponseStream.
            model_id: The model ID used.

        Returns:
            ChatResponseUpdate or None if event should be skipped.
        """
        # InvokeModel streaming has provider-specific formats
        provider = self._detect_model_provider(model_id)

        if "chunk" in event:
            chunk_data = json.loads(event["chunk"]["bytes"])

            if provider == ModelProvider.ANTHROPIC:
                # Anthropic streaming format
                event_type = chunk_data.get("type")

                if event_type == "content_block_delta":
                    delta = chunk_data.get("delta", {})
                    if "text" in delta:
                        return ChatResponseUpdate(
                            contents=[TextContent(text=delta["text"], raw_representation=event)], raw_response=event
                        )

                elif event_type == "message_stop":
                    return ChatResponseUpdate(finish_reason=FinishReason.STOP, raw_response=event)

            elif provider == ModelProvider.AMAZON_TITAN:
                # Titan streaming format
                if "outputText" in chunk_data:
                    return ChatResponseUpdate(
                        contents=[TextContent(text=chunk_data["outputText"], raw_representation=event)],
                        raw_response=event,
                    )

        return None
