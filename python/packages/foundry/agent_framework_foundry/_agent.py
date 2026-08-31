# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Foundry Agent for connecting to pre-configured agents in Foundry.

This module provides ``RawFoundryAgent`` and ``FoundryAgent`` — Agent subclasses
that connect to existing PromptAgents or HostedAgents in Foundry. Use
``FoundryAgent`` for the recommended experience with full middleware and telemetry.
"""

from __future__ import annotations

import logging
import sys
import warnings
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, cast

from agent_framework import (
    AgentMiddlewareLayer,
    AgentResponseUpdate,
    AgentSession,
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    ContextProvider,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    Message,
    RawAgent,
    load_settings,
)
from agent_framework._compaction import CompactionStrategy, TokenizerProtocol
from agent_framework._telemetry import IS_TELEMETRY_ENABLED, get_user_agent
from agent_framework.observability import AgentTelemetryLayer, ChatTelemetryLayer
from agent_framework_openai._chat_client import OpenAIChatOptions, RawOpenAIChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from agent_framework_foundry._oauth_helpers import try_parse_oauth_consent_event

from ._feature_usage import (
    FeatureIndex,
    create_feature_usage_policy,
    create_foundry_feature_usage_http_client,
)
from ._tools import _sanitize_foundry_response_tool  # pyright: ignore[reportPrivateUsage]

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover

if TYPE_CHECKING:
    from agent_framework import (
        Agent,
        AgentRunInputs,
        MiddlewareTypes,
        ToolTypes,
    )
    from agent_framework._agents import _RunContext  # pyright: ignore[reportPrivateUsage]

logger: logging.Logger = logging.getLogger("agent_framework.foundry")


AzureTokenProvider = Callable[[], str | Awaitable[str]]
AzureCredentialTypes = TokenCredential | AsyncTokenCredential


class FoundryAgentSettings(TypedDict, total=False):
    """Settings for Microsoft FoundryAgentClient resolved from args and environment.

    Keyword Args:
        project_endpoint: The Foundry project endpoint URL.
            Can be set via environment variable FOUNDRY_PROJECT_ENDPOINT.
        agent_name: The name of the Foundry agent to connect to.
            Can be set via environment variable FOUNDRY_AGENT_NAME.
        agent_version: The version of the Foundry agent (for PromptAgents).
            Can be set via environment variable FOUNDRY_AGENT_VERSION.
    """

    project_endpoint: str | None
    agent_name: str | None
    agent_version: str | None


FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY = "foundry_hosted_agent_session_id"


class FoundryAgentOptions(OpenAIChatOptions, total=False):
    """Microsoft Foundry agent-specific chat options.

    Extends ``OpenAIChatOptions`` with hosted-agent session configuration used by
    ``FoundryAgent`` / ``RawFoundryAgent``.

    Keyword Args:
        extra_body: Additional request body values sent to the Responses API.
        isolation_key: Deprecated. This option no longer has any effect.
    """

    extra_body: dict[str, Any]
    isolation_key: str


FoundryAgentOptionsT = TypeVar(
    "FoundryAgentOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="FoundryAgentOptions",
    covariant=True,
)


def _merge_extra_body(extra_body: Any | None, *, additions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Normalize and merge provider-specific extra_body values."""
    if extra_body is None:
        merged: dict[str, Any] = {}
    elif isinstance(extra_body, Mapping):
        merged = dict(cast(Mapping[str, Any], extra_body))
    else:
        raise TypeError(f"extra_body must be a mapping when provided, got {type(extra_body).__name__}.")

    if additions:
        merged.update(additions)
    return merged


def _extract_foundry_hosted_agent_session_id(response: Any) -> str | None:
    """Extract a Foundry hosted-agent session ID from a service response."""
    agent_session_id = getattr(response, "agent_session_id", None)
    return agent_session_id if isinstance(agent_session_id, str) and agent_session_id else None


def _build_agent_reference(agent_name: str, agent_version: str | None) -> dict[str, str]:
    """Build the Responses API ``agent_reference`` payload for non-preview Foundry agent calls.

    Used for both Prompt Agents and HostedAgents on the ``allow_preview=False`` code path —
    the preview branch instead injects identity via ``project_client.get_openai_client(agent_name=...)``.
    """
    ref: dict[str, str] = {"name": agent_name, "type": "agent_reference"}
    if agent_version:
        ref["version"] = agent_version
    return ref


class RawFoundryAgentChatClient(
    RawOpenAIChatClient[FoundryAgentOptionsT],
    Generic[FoundryAgentOptionsT],
):
    """Raw Microsoft Foundry Agent chat client for connecting to pre-configured agents in Foundry.

    Connects to existing PromptAgents or HostedAgents via the Responses API.
    Does not create or delete agents — the agent must already exist in Foundry.

    This is a raw client without function invocation, chat middleware, or telemetry layers.
    Tools passed in options are validated (only ``FunctionTool`` allowed) but **not invoked** —
    the function invocation loop is handled by ``_FoundryAgentChatClient`` or a custom subclass
    that includes ``FunctionInvocationLayer``.

    Use this class as an extension point when building a custom client with specific middleware
    layers via subclassing::

        from agent_framework._tools import FunctionInvocationLayer
        from agent_framework.foundry import RawFoundryAgentChatClient


        class MyClient(FunctionInvocationLayer, RawFoundryAgentChatClient):
            pass


        agent = FoundryAgent(..., client_type=MyClient)
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.foundry"
    _FEATURE_USAGE_INDEX: ClassVar[int | None] = FeatureIndex.FOUNDRY_AGENT

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        credential: AzureCredentialTypes | None = None,
        project_client: AIProjectClient | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize a raw Foundry Agent client.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
                Can also be set via environment variable FOUNDRY_PROJECT_ENDPOINT.
            agent_name: The name of the Foundry agent to connect to.
                Can also be set via environment variable FOUNDRY_AGENT_NAME.
            agent_version: The version of the agent (required for PromptAgents, optional for HostedAgents).
                Can also be set via environment variable FOUNDRY_AGENT_VERSION.
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            default_headers: Additional HTTP headers for requests made through the OpenAI client.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            instruction_role: The role to use for 'instruction' messages.
            compaction_strategy: Optional per-client compaction override.
            tokenizer: Optional tokenizer for compaction strategies.
            additional_properties: Additional properties stored on the client instance.
            timeout: HTTP timeout in seconds for requests. When not provided, the
                OpenAI SDK default is used (connect: 5s, total: 600s).
        """
        settings = load_settings(
            FoundryAgentSettings,
            env_prefix="FOUNDRY_",
            project_endpoint=project_endpoint,
            agent_name=agent_name,
            agent_version=agent_version,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        resolved_endpoint = settings.get("project_endpoint")
        agent_name_setting = settings.get("agent_name")
        self.agent_version: str | None = settings.get("agent_version")
        self.allow_preview = allow_preview or False

        if not agent_name_setting:
            raise ValueError(
                "Agent name is required. Set via 'agent_name' parameter or 'FOUNDRY_AGENT_NAME' environment variable."
            )
        self.agent_name = agent_name_setting

        # Create or use provided project client
        self._should_close_client = False
        if project_client is not None:
            self.project_client = project_client
        else:
            if not resolved_endpoint:
                raise ValueError(
                    "Either 'project_endpoint' or 'project_client' is required. "
                    "Set project_endpoint via parameter or 'FOUNDRY_PROJECT_ENDPOINT' environment variable."
                )
            if not credential:
                raise ValueError("Azure credential is required when using project_endpoint without a project_client.")
            project_client_kwargs: dict[str, Any] = {
                "endpoint": resolved_endpoint,
                "credential": credential,
                "per_retry_policies": [create_feature_usage_policy()],
            }
            if IS_TELEMETRY_ENABLED:
                project_client_kwargs["user_agent"] = get_user_agent()
            if allow_preview is not None:
                project_client_kwargs["allow_preview"] = allow_preview
            self.project_client = AIProjectClient(**project_client_kwargs)
            self._should_close_client = True

        openai_client_kwargs: dict[str, Any] = {}
        if default_headers:
            openai_client_kwargs["default_headers"] = dict(default_headers)
        if self._should_close_client:
            openai_client_kwargs["http_client"] = create_foundry_feature_usage_http_client()
        if allow_preview:
            openai_client_kwargs["agent_name"] = self.agent_name
        openai_client = self.project_client.get_openai_client(**openai_client_kwargs)
        if timeout is not None:
            openai_client = openai_client.with_options(timeout=timeout)
        super().__init__(
            async_client=openai_client,
            default_headers=default_headers,
            instruction_role=instruction_role,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
        )
        self.model = ""  # Foundry agents resolve model server-side; ignore env vars (issue #7272).

    @override
    def as_agent(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: FoundryAgentOptionsT | Mapping[str, Any] | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        require_per_service_call_history_persistence: bool = False,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: Mapping[str, Any] | None = None,
    ) -> Agent[FoundryAgentOptionsT]:
        """Create a FoundryAgent that reuses this client's Foundry configuration."""
        function_tools = cast(
            FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None,
            tools,
        )

        return cast(
            "Agent[FoundryAgentOptionsT]",
            FoundryAgent(
                project_client=self.project_client,
                agent_name=self.agent_name,
                agent_version=self.agent_version,
                tools=function_tools,
                context_providers=context_providers,
                middleware=middleware,
                require_per_service_call_history_persistence=require_per_service_call_history_persistence,
                client_type=cast(type[RawFoundryAgentChatClient], self.__class__),
                id=id,
                name=self.agent_name if name is None else name,
                description=description,
                instructions=instructions,
                default_options=default_options,
                function_invocation_configuration=function_invocation_configuration,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                additional_properties=additional_properties,
            ),
        )

    @override
    async def _prepare_options(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Prepare options for the Responses API and validate client-side tools."""
        caller_requested_encrypted_reasoning = "reasoning.encrypted_content" in (options.get("include") or [])
        prepared_options = dict(options)
        if prepared_options.pop("isolation_key", None) is not None:
            warnings.warn(
                "The 'isolation_key' option is deprecated and no longer has any effect.",
                DeprecationWarning,
                stacklevel=2,
            )

        # Validate tools — only FunctionTool allowed
        tools = options.get("tools", [])
        if tools:
            for tool_item in tools:
                if not isinstance(tool_item, FunctionTool):
                    raise TypeError(
                        f"Only FunctionTool objects are accepted for Foundry agents, "
                        f"got {type(tool_item).__name__}. Other tool types (MCPTool, dict schemas, "
                        f"hosted tools) must be defined on the Foundry agent definition in the service."
                    )

        # Prepare messages: extract system/developer messages as instructions
        prepared_messages, _instructions = self._prepare_messages_for_azure_ai(messages)

        # Call parent prepare_options (OpenAI Responses API format)
        run_options = await super()._prepare_options(prepared_messages, prepared_options, **kwargs)

        # Foundry Agent deployments can reject the OpenAI client's automatic encrypted-reasoning
        # opt-in even when the configured model otherwise supports reasoning. Preserve an explicit
        # caller request, but do not add this provider capability implicitly.
        if not caller_requested_encrypted_reasoning and isinstance(run_options.get("include"), list):
            include = [item for item in run_options["include"] if item != "reasoning.encrypted_content"]
            if include:
                run_options["include"] = include
            else:
                run_options.pop("include")

        # Apply Azure AI schema transforms
        if "input" in run_options and isinstance(run_options["input"], list):
            run_options["input"] = self._transform_input_for_azure_ai(cast(list[dict[str, Any]], run_options["input"]))

        # Merge caller-supplied extra_body with any agent-specific request payload.
        extra_body = _merge_extra_body(run_options.pop("extra_body", None))
        agent_session_id = extra_body.get("agent_session_id")
        # Non-preview Prompt/Hosted Agent calls need agent_reference in the request body to
        # tell the Responses API which Foundry agent (and version) is in use, since ``model``
        # is stripped below. The preview path injects the reference via the OpenAI client kwarg
        # ``agent_name`` instead, so skip there. See issue #5582.
        if not self.allow_preview:
            extra_body.setdefault("agent_reference", _build_agent_reference(self.agent_name, self.agent_version))
            should_strip_model = agent_session_id is not None or (
                options.get("conversation_id") is None and not options.get("model")
            )
            if should_strip_model:
                run_options.pop("model", None)
        if extra_body:
            run_options["extra_body"] = extra_body

        # Strip tool fields from the request body. This client always targets a pre-provisioned
        # Foundry agent (agent_name is required), and the service rejects requests that carry both
        # an agent reference and tool declarations with HTTP 400 "Not allowed when agent is
        # specified." (issue #5130). The agent already owns its tool schema server-side; any
        # FunctionTools passed here are used only for client-side dispatch by the function
        # invocation layer. This must run on both the non-preview path (agent injected via
        # ``agent_reference`` in extra_body) and the preview path (agent injected via the OpenAI
        # client kwarg ``agent_name``) — both specify an agent, so neither may send tools.
        stripped_tools = run_options.pop("tools", None)
        run_options.pop("tool_choice", None)
        run_options.pop("parallel_tool_calls", None)
        if stripped_tools:
            logger.warning(
                "Foundry agent '%s' was provided tools, but tool declarations cannot be sent when an "
                "agent is specified; they are omitted from the request and used only for client-side "
                "function dispatch. Define tool schemas on the Foundry agent definition in the service.",
                self.agent_name,
            )

        return run_options

    @override
    def _parse_response_from_openai(
        self,
        response: Any,
        options: dict[str, Any],
    ) -> Any:
        parsed_response = super()._parse_response_from_openai(response, options)
        if agent_session_id := _extract_foundry_hosted_agent_session_id(response):
            parsed_response.additional_properties["agent_session_id"] = agent_session_id
        return parsed_response

    @override
    def _parse_chunk_from_openai(
        self,
        event: Any,
        options: dict[str, Any],
        function_call_ids: dict[int, tuple[str, str]],
        seen_reasoning_delta_item_ids: set[str] | None = None,
    ) -> ChatResponseUpdate:
        """Parse streaming events while preserving hosted-agent session state."""
        update = try_parse_oauth_consent_event(event, self.model)
        if update is None:
            update = super()._parse_chunk_from_openai(
                event,
                options,
                function_call_ids,
                seen_reasoning_delta_item_ids,
            )
        if agent_session_id := _extract_foundry_hosted_agent_session_id(getattr(event, "response", None)):
            if update.additional_properties is None:
                update.additional_properties = {}
            update.additional_properties["agent_session_id"] = agent_session_id
        return update

    @override
    def _check_model_presence(self, options: dict[str, Any]) -> None:
        """Skip model check — model is configured on the Foundry agent."""
        pass

    @override
    def _prepare_tools_for_openai(
        self,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
    ) -> list[Any]:
        response_tools = super()._prepare_tools_for_openai(tools)
        return [_sanitize_foundry_response_tool(tool_item) for tool_item in response_tools]

    def _prepare_messages_for_azure_ai(self, messages: Sequence[Message]) -> tuple[list[Message], str | None]:
        """Extract system/developer messages as instructions for Azure AI.

        Foundry agents may not support system/developer messages directly.
        Instead, extract them as instructions to prepend.
        """
        prepared: list[Message] = []
        instructions_parts: list[str] = []
        for msg in messages:
            if msg.role in ("system", "developer"):
                if msg.text:
                    instructions_parts.append(msg.text)
            else:
                prepared.append(msg)
        instructions = "\n".join(instructions_parts) if instructions_parts else None
        return prepared, instructions

    def _transform_input_for_azure_ai(self, input_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform input items to match Azure AI Projects expected schema.

        Azure AI Projects 'create responses' API expects 'type' at item level
        and 'annotations' for output_text content items.
        """
        transformed: list[dict[str, Any]] = []
        for item in input_items:
            new_item: dict[str, Any] = dict(item)

            if "role" in new_item and "type" not in new_item:
                new_item["type"] = "message"

            if (content := new_item.get("content")) and isinstance(content, list):
                new_content: list[Any] = []
                for content_item in content:  # type: ignore[union-attr]
                    if isinstance(content_item, MutableMapping):
                        if content_item.get("type") == "output_text" and "annotations" not in content_item:  # type: ignore[operator]
                            content_item["annotations"] = []
                        new_content.append(content_item)
                    else:
                        new_content.append(content_item)
                new_item["content"] = new_content

            transformed.append(new_item)

        return transformed

    async def close(self) -> None:
        """Close the project client if we created it."""
        if self._should_close_client:
            await self.project_client.close()


class _FoundryAgentChatClient(
    FunctionInvocationLayer[FoundryAgentOptionsT],
    ChatMiddlewareLayer[FoundryAgentOptionsT],
    ChatTelemetryLayer[FoundryAgentOptionsT],
    RawFoundryAgentChatClient[FoundryAgentOptionsT],
    Generic[FoundryAgentOptionsT],
):
    """Microsoft Foundry Agent client with middleware, telemetry, and function invocation support.

    Connects to existing PromptAgents or HostedAgents in Foundry.

    Examples:
        .. code-block:: python

            from agent_framework import Agent
            from agent_framework.foundry import FoundryAgent
            from azure.identity import AzureCliCredential

            client = FoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-prompt-agent",
                agent_version="1",
                credential=AzureCliCredential(),
            )

            agent = Agent(client=client, tools=[my_function_tool])
            result = await agent.run("Hello!")
    """

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        credential: AzureCredentialTypes | None = None,
        project_client: AIProjectClient | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: (Sequence[ChatAndFunctionMiddlewareTypes] | None) = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize a Foundry Agent client with full middleware support.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
            agent_name: The name of the Foundry agent to connect to.
            agent_version: The version of the agent (for PromptAgents).
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            default_headers: Additional HTTP headers for requests made through the OpenAI client.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            instruction_role: The role to use for 'instruction' messages.
            compaction_strategy: Optional per-client compaction override.
            tokenizer: Optional tokenizer for compaction strategies.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional sequence of middleware.
            function_invocation_configuration: Optional function invocation configuration.
            timeout: HTTP timeout in seconds for requests. When not provided, the
                OpenAI SDK default is used (connect: 5s, total: 600s).
        """
        super().__init__(
            project_endpoint=project_endpoint,
            agent_name=agent_name,
            agent_version=agent_version,
            credential=credential,
            project_client=project_client,
            allow_preview=allow_preview,
            default_headers=default_headers,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            instruction_role=instruction_role,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            timeout=timeout,
        )

    @override
    def _update_function_invocation_continuation_state(
        self,
        kwargs: dict[str, Any],
        response: ChatResponse[Any],
        *,
        session: AgentSession | None,
        options: dict[str, Any] | None = None,
    ) -> None:
        super()._update_function_invocation_continuation_state(
            kwargs,
            response,
            session=session,
            options=options,
        )
        agent_session_id = response.additional_properties.get("agent_session_id")
        if not isinstance(agent_session_id, str) or not agent_session_id:
            return
        # Persist the ID for later runs and inject it into the current options because function
        # invocation can make another service call before the agent prepares a new run context.
        if session is not None:
            session.state[FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY] = agent_session_id
        if options is not None:
            extra_body = _merge_extra_body(options.get("extra_body"))
            extra_body["agent_session_id"] = agent_session_id
            options["extra_body"] = extra_body


class RawFoundryAgent(
    RawAgent[FoundryAgentOptionsT],
):
    """Raw Microsoft Foundry Agent without agent-level middleware or telemetry.

    Connects to an existing PromptAgent or HostedAgent in Foundry.
    For full middleware and telemetry support, use :class:`FoundryAgent`.

    Examples:
        .. code-block:: python

            from agent_framework.foundry import RawFoundryAgent
            from azure.identity import AzureCliCredential

            agent = RawFoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-prompt-agent",
                agent_version="1",
                credential=AzureCliCredential(),
            )
            result = await agent.run("Hello!")
    """

    service_session_state_keys: ClassVar[frozenset[str]] = frozenset({FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY})

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        credential: AzureCredentialTypes | None = None,
        project_client: AIProjectClient | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        client_type: type[RawFoundryAgentChatClient] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        default_options: FoundryAgentOptionsT | Mapping[str, Any] | None = None,
        require_per_service_call_history_persistence: bool = False,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize a Foundry Agent.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
                Can also be set via environment variable FOUNDRY_PROJECT_ENDPOINT.
            agent_name: The name of the Foundry agent to connect to.
                Can also be set via environment variable FOUNDRY_AGENT_NAME.
            agent_version: The version of the agent (required for PromptAgents, optional for HostedAgents).
                Can also be set via environment variable FOUNDRY_AGENT_VERSION.
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            default_headers: Additional HTTP headers for requests made through the OpenAI client.
            tools: Function tools to provide to the agent. Only ``FunctionTool`` objects are accepted.
            context_providers: Optional context providers for injecting dynamic context.
            middleware: Optional agent-level middleware.
            client_type: Custom client class to use (must be a subclass of ``RawFoundryAgentChatClient``).
                Defaults to ``_FoundryAgentChatClient`` (full client middleware).
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            id: Optional local agent identifier.
            name: Optional display name for the local agent wrapper.
            description: Optional local description for the local agent wrapper.
            instructions: Optional instructions for the local agent wrapper.
            default_options: Default chat options for the local agent wrapper.
            require_per_service_call_history_persistence: Whether to require per-service-call
                chat history persistence when using local history providers.
            function_invocation_configuration: Optional function invocation configuration override.
            compaction_strategy: Optional agent-level in-run compaction override.
            tokenizer: Optional agent-level tokenizer override.
            additional_properties: Additional properties stored on the local agent wrapper.
            timeout: HTTP timeout in seconds for requests. When not provided, the
                OpenAI SDK default is used (connect: 5s, total: 600s).
        """
        # Create the client
        actual_client_type = client_type or _FoundryAgentChatClient
        if not issubclass(actual_client_type, RawFoundryAgentChatClient):
            raise TypeError(
                f"client_type must be a subclass of RawFoundryAgentChatClient, got {actual_client_type.__name__}"
            )

        client_kwargs: dict[str, Any] = {
            "project_endpoint": project_endpoint,
            "agent_name": agent_name,
            "agent_version": agent_version,
            "credential": credential,
            "project_client": project_client,
            "allow_preview": allow_preview,
            "default_headers": default_headers,
            "env_file_path": env_file_path,
            "env_file_encoding": env_file_encoding,
            "timeout": timeout,
        }
        if function_invocation_configuration is not None:
            if not issubclass(actual_client_type, FunctionInvocationLayer):
                raise TypeError(
                    "function_invocation_configuration requires a FunctionInvocationLayer-based client_type."
                )
            client_kwargs["function_invocation_configuration"] = function_invocation_configuration

        client = actual_client_type(**client_kwargs)

        super().__init__(
            client=client,  # type: ignore[arg-type]
            instructions=instructions,
            id=id,
            name=name or agent_name,
            description=description,
            tools=tools,
            default_options=cast(FoundryAgentOptionsT | None, default_options),
            context_providers=context_providers,
            middleware=middleware,
            require_per_service_call_history_persistence=require_per_service_call_history_persistence,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=dict(additional_properties) if additional_properties is not None else None,
        )

    async def create_conversation(self, *, session_id: str | None = None) -> AgentSession:
        """Create a project-level Foundry conversation session.

        This creates a server-side conversation through the Foundry project's OpenAI
        client and returns an ``AgentSession`` configured to continue that
        conversation.

        Keyword Args:
            session_id: Optional local session ID (generated if not provided).

        Returns:
            A new ``AgentSession`` whose ``service_session_id`` is the created
            Foundry conversation ID.
        """
        client = cast(RawFoundryAgentChatClient, self.client)
        conversation = await client.client.conversations.create()
        return self.get_session(service_session_id=conversation.id, session_id=session_id)

    @override
    async def _prepare_run_context(
        self,
        *,
        messages: AgentRunInputs | None,
        session: AgentSession | None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
        options: Mapping[str, Any] | None,
        compaction_strategy: CompactionStrategy | None,
        tokenizer: TokenizerProtocol | None,
        function_invocation_kwargs: Mapping[str, Any] | None,
        client_kwargs: Mapping[str, Any] | None,
    ) -> _RunContext:
        runtime_options = dict(options) if options else {}
        agent_session_id = session.state.get(FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY) if session is not None else None
        if isinstance(agent_session_id, str) and agent_session_id:
            extra_body = _merge_extra_body(self.default_options.get("extra_body"))
            extra_body.update(_merge_extra_body(runtime_options.get("extra_body")))
            extra_body.setdefault("agent_session_id", agent_session_id)
            runtime_options["extra_body"] = extra_body

        return await super()._prepare_run_context(
            messages=messages,
            session=session,
            tools=tools,
            options=runtime_options,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=client_kwargs,
        )

    @override
    def _update_session_from_chat_response(
        self,
        session: AgentSession | None,
        response: ChatResponse[Any],
    ) -> None:
        super()._update_session_from_chat_response(session, response)
        agent_session_id = response.additional_properties.get("agent_session_id")
        if session is not None and isinstance(agent_session_id, str) and agent_session_id:
            session.state[FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY] = agent_session_id

    @override
    def _update_session_from_chat_response_update(
        self,
        session: AgentSession | None,
        update: AgentResponseUpdate,
    ) -> None:
        super()._update_session_from_chat_response_update(session, update)
        agent_session_id = (
            update.additional_properties.get("agent_session_id") if update.additional_properties is not None else None
        )
        if session is not None and isinstance(agent_session_id, str) and agent_session_id:
            session.state[FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY] = agent_session_id

    async def configure_azure_monitor(
        self,
        enable_sensitive_data: bool = False,
        **kwargs: Any,
    ) -> None:
        """Setup observability with Azure Monitor (Microsoft Foundry integration).

        This method configures Azure Monitor for telemetry collection using the
        connection string from the Foundry project client (accessed via the internal client).

        Args:
            enable_sensitive_data: Enable sensitive data logging (prompts, responses).
                Should only be enabled in development/test environments. Default is False.
            **kwargs: Additional arguments passed to configure_azure_monitor().

        Raises:
            ImportError: If azure-monitor-opentelemetry-exporter is not installed.
        """
        from agent_framework.observability import (
            OBSERVABILITY_SETTINGS,
            create_metric_views,
            create_resource,
            enable_instrumentation,
        )
        from azure.core.exceptions import ResourceNotFoundError

        if OBSERVABILITY_SETTINGS.is_user_disabled:
            logger.info(
                "FoundryAgent.configure_azure_monitor(): Skipping setup because instrumentation was "
                "explicitly disabled via disable_instrumentation(). Call enable_instrumentation(force=True) "
                "to re-enable, then re-invoke configure_azure_monitor()."
            )
            return

        client = self.client
        if not isinstance(client, RawFoundryAgentChatClient):
            raise TypeError("configure_azure_monitor requires a RawFoundryAgentChatClient-based client.")

        try:
            conn_string = await client.project_client.telemetry.get_application_insights_connection_string()
        except ResourceNotFoundError:
            logger.warning(
                "No Application Insights connection string found for the Foundry project. "
                "Please ensure Application Insights is configured in your project, "
                "or call configure_otel_providers() manually with custom exporters."
            )
            return

        try:
            from azure.monitor.opentelemetry import configure_azure_monitor  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "azure-monitor-opentelemetry is required for Azure Monitor integration. "
                "Install it with: pip install azure-monitor-opentelemetry"
            ) from exc

        if "resource" not in kwargs:
            kwargs["resource"] = create_resource()

        configure_azure_monitor(
            connection_string=conn_string,
            views=create_metric_views(),
            **kwargs,
        )

        enable_instrumentation(enable_sensitive_data=enable_sensitive_data)


class FoundryAgent(  # type: ignore[misc]
    AgentMiddlewareLayer,
    AgentTelemetryLayer,
    RawFoundryAgent[FoundryAgentOptionsT],
):
    """Microsoft Foundry Agent with full middleware and telemetry support.

    Connects to an existing PromptAgent or HostedAgent in Foundry.
    This is the recommended class for production use.

    Examples:
        .. code-block:: python

            from agent_framework.foundry import FoundryAgent
            from azure.identity import AzureCliCredential

            # Connect to a PromptAgent
            agent = FoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-prompt-agent",
                agent_version="1.0",
                credential=AzureCliCredential(),
                tools=[my_function_tool],
            )
            result = await agent.run("Hello!")

            # Connect to a HostedAgent (no version needed)
            agent = FoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-hosted-agent",
                credential=AzureCliCredential(),
            )

            # Custom client (e.g., raw client without client middleware)
            agent = FoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-agent",
                credential=AzureCliCredential(),
                client_type=RawFoundryAgentChatClient,
            )
    """

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        credential: AzureCredentialTypes | None = None,
        project_client: AIProjectClient | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        client_type: type[RawFoundryAgentChatClient] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        default_options: FoundryAgentOptionsT | Mapping[str, Any] | None = None,
        require_per_service_call_history_persistence: bool = False,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize a Foundry Agent with full middleware and telemetry.

        ``FoundryAgent`` supports both PromptAgents and HostedAgents. PromptAgents
        typically provide ``agent_version`` directly. HostedAgents can omit
        ``agent_version`` and, when they need preview-only session APIs, should
        opt in with ``allow_preview=True`` when this class creates the underlying
        ``AIProjectClient``. If you pass ``project_client`` explicitly, it must
        already be configured for preview APIs before being passed to
        ``FoundryAgent``.

        For HostedAgents, the service creates an agent session when the first
        request does not specify one. The agent stores that infrastructure ID in
        ``AgentSession.state["foundry_hosted_agent_session_id"]`` and sends it through
        ``extra_body`` on later requests. ``AgentSession.service_session_id``
        remains the conversation continuation handle.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
            agent_name: The name of the Foundry agent to connect to.
            agent_version: The version of the agent (for PromptAgents).
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
                Set this to ``True`` for HostedAgents that need preview APIs.
            default_headers: Additional HTTP headers for requests made through the OpenAI client.
            tools: Function tools to provide to the agent. Only ``FunctionTool`` objects are accepted.
            context_providers: Optional context providers.
            middleware: Optional agent-level middleware.
            client_type: Custom client class (must subclass ``RawFoundryAgentChatClient``).
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            id: Optional local agent identifier.
            name: Optional display name for the local agent wrapper.
            description: Optional local description for the local agent wrapper.
            instructions: Optional instructions for the local agent wrapper.
            default_options: Default chat options for the local agent wrapper.
                ``FoundryAgentOptions`` can include ``extra_body`` when working
                with HostedAgents.
            require_per_service_call_history_persistence: Whether to require per-service-call
                chat history persistence when using local history providers.
            function_invocation_configuration: Optional function invocation configuration override.
            compaction_strategy: Optional agent-level in-run compaction override.
            tokenizer: Optional agent-level tokenizer override.
            additional_properties: Additional properties stored on the local agent wrapper.
            timeout: HTTP timeout in seconds for requests. When not provided, the
                OpenAI SDK default is used (connect: 5s, total: 600s).
        """
        super().__init__(
            project_endpoint=project_endpoint,
            agent_name=agent_name,
            agent_version=agent_version,
            credential=credential,
            project_client=project_client,
            allow_preview=allow_preview,
            default_headers=default_headers,
            tools=tools,
            context_providers=context_providers,
            middleware=middleware,
            client_type=client_type,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            id=id,
            name=name,
            description=description,
            instructions=instructions,
            default_options=default_options,
            require_per_service_call_history_persistence=require_per_service_call_history_persistence,
            function_invocation_configuration=function_invocation_configuration,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
            timeout=timeout,
        )
