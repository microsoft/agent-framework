# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import Awaitable, Callable, MutableMapping, Sequence
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.beta.assistant import Assistant
from pydantic import BaseModel, SecretStr, ValidationError

from .._agents import ChatAgent
from .._memory import ContextProvider
from .._middleware import Middleware
from .._tools import AIFunction, ToolProtocol
from .._types import ChatOptions
from ..exceptions import ServiceInitializationError
from ._assistants_client import OpenAIAssistantsClient
from ._shared import OpenAISettings, from_assistant_tools, to_assistant_tools

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


__all__ = ["OpenAIAssistantProvider"]

_ToolsType = (
    ToolProtocol
    | Callable[..., Any]
    | MutableMapping[str, Any]
    | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
)


class OpenAIAssistantProvider:
    """Provider for creating ChatAgent instances from OpenAI Assistants API.

    This provider allows you to create, retrieve, and wrap OpenAI Assistants
    as ChatAgent instances for use in the agent framework.

    Examples:
        Basic usage with automatic client creation:

        .. code-block:: python

            from agent_framework.openai import OpenAIAssistantProvider

            # Uses OPENAI_API_KEY environment variable
            provider = OpenAIAssistantProvider()

            # Create a new assistant
            agent = await provider.create_agent(
                name="MyAssistant",
                model="gpt-4",
                instructions="You are a helpful assistant.",
                tools=[my_function],
            )

            result = await agent.run("Hello!")

        Using an existing client:

        .. code-block:: python

            from openai import AsyncOpenAI
            from agent_framework.openai import OpenAIAssistantProvider

            client = AsyncOpenAI()
            provider = OpenAIAssistantProvider(client)

            # Get an existing assistant by ID
            agent = await provider.get_agent(
                assistant_id="asst_123",
                tools=[my_function],  # Provide implementations for function tools
            )

        Wrapping an SDK Assistant object:

        .. code-block:: python

            # Fetch assistant directly via SDK
            assistant = await client.beta.assistants.retrieve("asst_123")

            # Wrap without additional HTTP call
            agent = provider.as_agent(assistant, tools=[my_function])
    """

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        *,
        api_key: str | SecretStr | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the OpenAI Assistant Provider.

        Args:
            client: An existing AsyncOpenAI client to use. If not provided,
                a new client will be created using the other parameters.

        Keyword Args:
            api_key: OpenAI API key. Can also be set via OPENAI_API_KEY env var.
            org_id: OpenAI organization ID. Can also be set via OPENAI_ORG_ID env var.
            base_url: Base URL for the OpenAI API. Can also be set via OPENAI_BASE_URL env var.
            env_file_path: Path to .env file for configuration.
            env_file_encoding: Encoding of the .env file.

        Raises:
            ServiceInitializationError: If no client is provided and API key is missing.

        Examples:
            .. code-block:: python

                # Using environment variables
                provider = OpenAIAssistantProvider()

                # Using explicit API key
                provider = OpenAIAssistantProvider(api_key="sk-...")

                # Using existing client
                client = AsyncOpenAI()
                provider = OpenAIAssistantProvider(client)
        """
        self._client: AsyncOpenAI | None = client
        self._should_close_client: bool = client is None

        if client is None:
            # Load settings and create client
            try:
                settings = OpenAISettings(
                    api_key=api_key,  # type: ignore[reportArgumentType]
                    org_id=org_id,
                    base_url=base_url,
                    env_file_path=env_file_path,
                    env_file_encoding=env_file_encoding,
                )
            except ValidationError as ex:
                raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

            if not settings.api_key:
                raise ServiceInitializationError(
                    "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
                )

            # Get API key value
            api_key_value: str | Callable[[], str | Awaitable[str]] | None
            if isinstance(settings.api_key, SecretStr):
                api_key_value = settings.api_key.get_secret_value()
            else:
                api_key_value = settings.api_key

            # Create client
            client_args: dict[str, Any] = {"api_key": api_key_value}
            if settings.org_id:
                client_args["organization"] = settings.org_id
            if settings.base_url:
                client_args["base_url"] = settings.base_url

            self._client = AsyncOpenAI(**client_args)

    async def __aenter__(self) -> "Self":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the provider and clean up resources.

        If the provider created its own client, it will be closed.
        If an external client was provided, it will not be closed.
        """
        if self._should_close_client and self._client is not None:
            await self._client.close()

    async def create_agent(
        self,
        *,
        name: str,
        model: str,
        instructions: str | None = None,
        description: str | None = None,
        tools: _ToolsType | None = None,
        response_format: type[BaseModel] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        metadata: dict[str, str] | None = None,
        # ChatAgent options
        middleware: Sequence[Middleware] | None = None,
        context_provider: ContextProvider | None = None,
        **kwargs: Any,
    ) -> ChatAgent:
        """Create a new assistant on OpenAI and return a ChatAgent.

        This method creates a new assistant on the OpenAI service and wraps it
        in a ChatAgent instance. The assistant will persist on OpenAI until deleted.

        Keyword Args:
            name: The name of the assistant (required).
            model: The model ID to use, e.g., "gpt-4", "gpt-4o" (required).
            instructions: System instructions for the assistant.
            description: A description of the assistant.
            tools: Tools available to the assistant. Can include:
                - AIFunction instances or callables decorated with @ai_function
                - HostedCodeInterpreterTool for code execution
                - HostedFileSearchTool for vector store search
                - Raw tool dictionaries
            response_format: A Pydantic model class for structured output responses.
            temperature: Sampling temperature (0-2).
            top_p: Nucleus sampling probability.
            metadata: Metadata to attach to the assistant (max 16 key-value pairs).
            middleware: Middleware for the ChatAgent.
            context_provider: Context provider for the ChatAgent.
            **kwargs: Additional arguments passed to the ChatAgent.

        Returns:
            A ChatAgent instance wrapping the created assistant.

        Raises:
            ServiceInitializationError: If assistant creation fails.

        Examples:
            .. code-block:: python

                provider = OpenAIAssistantProvider()

                # Create with function tools
                agent = await provider.create_agent(
                    name="WeatherBot",
                    model="gpt-4",
                    instructions="You are a helpful weather assistant.",
                    tools=[get_weather],
                )

                # Create with code interpreter
                from agent_framework import HostedCodeInterpreterTool

                agent = await provider.create_agent(
                    name="CodeHelper",
                    model="gpt-4",
                    tools=[HostedCodeInterpreterTool()],
                )
        """
        # Normalize tools using ChatOptions
        normalized_tools = ChatOptions(tools=tools).tools if tools else None
        api_tools = to_assistant_tools(normalized_tools) if normalized_tools else []

        # Build assistant creation parameters
        create_params: dict[str, Any] = {
            "model": model,
            "name": name,
        }

        if instructions is not None:
            create_params["instructions"] = instructions
        if description is not None:
            create_params["description"] = description
        if api_tools:
            create_params["tools"] = api_tools
        if temperature is not None:
            create_params["temperature"] = temperature
        if top_p is not None:
            create_params["top_p"] = top_p
        if metadata is not None:
            create_params["metadata"] = metadata

        # Handle response format
        if response_format is not None:
            create_params["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_format.__name__,
                    "schema": response_format.model_json_schema(),
                    "strict": True,
                },
            }

        # Create the assistant
        if not self._client:
            raise ServiceInitializationError("OpenAI client is not initialized.")

        assistant = await self._client.beta.assistants.create(**create_params)

        # Create ChatAgent
        return self._create_chat_agent_from_assistant(
            assistant=assistant,
            tools=list(normalized_tools) if normalized_tools else None,
            instructions=instructions,
            middleware=middleware,
            context_provider=context_provider,
            response_format=response_format,
            **kwargs,
        )

    async def get_agent(
        self,
        assistant_id: str,
        *,
        tools: _ToolsType | None = None,
        instructions: str | None = None,
        middleware: Sequence[Middleware] | None = None,
        context_provider: ContextProvider | None = None,
        **kwargs: Any,
    ) -> ChatAgent:
        """Retrieve an existing assistant by ID and return a ChatAgent.

        This method fetches an existing assistant from OpenAI by its ID
        and wraps it in a ChatAgent instance.

        Args:
            assistant_id: The ID of the assistant to retrieve (e.g., "asst_123").

        Keyword Args:
            tools: Function tools to make available. IMPORTANT: If the assistant
                was created with function tools, you MUST provide matching
                implementations here. Hosted tools (code_interpreter, file_search)
                are automatically included.
            instructions: Override the assistant's instructions (optional).
            middleware: Middleware for the ChatAgent.
            context_provider: Context provider for the ChatAgent.
            **kwargs: Additional arguments passed to the ChatAgent.

        Returns:
            A ChatAgent instance wrapping the retrieved assistant.

        Raises:
            ServiceInitializationError: If the assistant cannot be retrieved.
            ValueError: If required function tools are missing.

        Examples:
            .. code-block:: python

                provider = OpenAIAssistantProvider()

                # Get assistant without function tools
                agent = await provider.get_agent(assistant_id="asst_123")

                # Get assistant with function tools
                agent = await provider.get_agent(
                    assistant_id="asst_456",
                    tools=[get_weather, search_database],  # Implementations required!
                )
        """
        # Fetch the assistant
        if not self._client:
            raise ServiceInitializationError("OpenAI client is not initialized.")

        assistant = await self._client.beta.assistants.retrieve(assistant_id)

        # Use as_agent to wrap it
        return self.as_agent(
            assistant=assistant,
            tools=tools,
            instructions=instructions,
            middleware=middleware,
            context_provider=context_provider,
            **kwargs,
        )

    def as_agent(
        self,
        assistant: Assistant,
        *,
        tools: _ToolsType | None = None,
        instructions: str | None = None,
        middleware: Sequence[Middleware] | None = None,
        context_provider: ContextProvider | None = None,
        **kwargs: Any,
    ) -> ChatAgent:
        """Wrap an existing SDK Assistant object as a ChatAgent.

        This method does NOT make any HTTP calls. It simply wraps an already-
        fetched Assistant object in a ChatAgent.

        Args:
            assistant: The OpenAI Assistant SDK object to wrap.

        Keyword Args:
            tools: Function tools to make available. If the assistant has
                function tools defined, you MUST provide matching implementations.
                Hosted tools (code_interpreter, file_search) are automatically included.
            instructions: Override the assistant's instructions (optional).
            middleware: Middleware for the ChatAgent.
            context_provider: Context provider for the ChatAgent.
            **kwargs: Additional arguments passed to the ChatAgent.

        Returns:
            A ChatAgent instance wrapping the assistant.

        Raises:
            ValueError: If required function tools are missing.

        Examples:
            .. code-block:: python

                client = AsyncOpenAI()
                provider = OpenAIAssistantProvider(client)

                # Fetch assistant via SDK
                assistant = await client.beta.assistants.retrieve("asst_123")

                # Wrap without additional HTTP call
                agent = provider.as_agent(
                    assistant,
                    tools=[my_function],
                    instructions="Custom instructions override",
                )
        """
        # Validate that required function tools are provided
        self._validate_function_tools(assistant.tools or [], tools)

        # Merge hosted tools with user-provided function tools
        merged_tools = self._merge_tools(assistant.tools or [], tools)

        # Create ChatAgent
        return self._create_chat_agent_from_assistant(
            assistant=assistant,
            tools=merged_tools,
            instructions=instructions,
            middleware=middleware,
            context_provider=context_provider,
            **kwargs,
        )

    def _validate_function_tools(
        self,
        assistant_tools: list[Any],
        provided_tools: _ToolsType | None,
    ) -> None:
        """Validate that required function tools are provided.

        Args:
            assistant_tools: Tools defined on the assistant.
            provided_tools: Tools provided by the user.

        Raises:
            ValueError: If a required function tool is missing.
        """
        # Get function tool names from assistant
        required_functions: set[str] = set()
        for tool in assistant_tools:
            if (
                hasattr(tool, "type")
                and tool.type == "function"
                and hasattr(tool, "function")
                and hasattr(tool.function, "name")
            ):
                required_functions.add(tool.function.name)

        if not required_functions:
            return  # No function tools required

        # Get provided function names using ChatOptions normalization
        provided_functions: set[str] = set()
        if provided_tools is not None:
            normalized = ChatOptions(tools=provided_tools).tools
            if normalized:
                for tool in normalized:
                    if isinstance(tool, AIFunction):
                        provided_functions.add(tool.name)
                    elif isinstance(tool, MutableMapping) and "function" in tool:
                        func_spec = tool.get("function", {})
                        if isinstance(func_spec, dict):
                            func_dict = cast(dict[str, Any], func_spec)
                            if "name" in func_dict:
                                provided_functions.add(str(func_dict["name"]))

        # Check for missing functions
        missing = required_functions - provided_functions
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(
                f"Assistant requires function tool(s) '{missing_list}' but no implementation was provided. "
                f"Please pass the function implementation(s) in the 'tools' parameter."
            )

    def _merge_tools(
        self,
        assistant_tools: list[Any],
        user_tools: _ToolsType | None,
    ) -> list[ToolProtocol | MutableMapping[str, Any]]:
        """Merge hosted tools from assistant with user-provided function tools.

        Args:
            assistant_tools: Tools defined on the assistant.
            user_tools: Tools provided by the user.

        Returns:
            A list of all tools (hosted tools + user function implementations).
        """
        merged: list[ToolProtocol | MutableMapping[str, Any]] = []

        # Add hosted tools from assistant using shared conversion
        hosted_tools = from_assistant_tools(assistant_tools)
        merged.extend(hosted_tools)

        # Add user-provided tools (normalized via ChatOptions)
        if user_tools is not None:
            normalized_user_tools = ChatOptions(tools=user_tools).tools
            if normalized_user_tools:
                merged.extend(normalized_user_tools)

        return merged

    def _create_chat_agent_from_assistant(
        self,
        assistant: Assistant,
        tools: list[ToolProtocol | MutableMapping[str, Any]] | None,
        instructions: str | None,
        middleware: Sequence[Middleware] | None,
        context_provider: ContextProvider | None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatAgent:
        """Create a ChatAgent from an Assistant.

        Args:
            assistant: The OpenAI Assistant object.
            tools: Tools for the agent.
            instructions: Instructions override.
            middleware: Middleware for the agent.
            context_provider: Context provider for the agent.
            response_format: Response format (Pydantic model for structured output).
            **kwargs: Additional arguments for ChatAgent.

        Returns:
            A configured ChatAgent instance.
        """
        # Create the chat client with the assistant
        chat_client = OpenAIAssistantsClient(
            model_id=assistant.model,
            assistant_id=assistant.id,
            assistant_name=assistant.name,
            assistant_description=assistant.description,
            async_client=self._client,
        )

        # Use instructions from assistant if not overridden
        final_instructions = instructions if instructions is not None else assistant.instructions

        # Create and return ChatAgent
        return ChatAgent(
            chat_client=chat_client,
            id=assistant.id,
            name=assistant.name,
            description=assistant.description,
            instructions=final_instructions,
            tools=tools if tools else None,
            middleware=middleware,
            context_provider=context_provider,
            response_format=response_format,
            **kwargs,
        )
