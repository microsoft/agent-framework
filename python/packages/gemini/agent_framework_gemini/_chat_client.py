# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import logging
import sys
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, ClassVar, Generic, cast
from uuid import uuid4

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    BaseChatClient,
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FinishReasonLiteral,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    Message,
    ResponseStream,
    UsageDetails,
    validate_tool_mode,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework.observability import ChatTelemetryLayer
from google import genai
from google.auth.credentials import Credentials
from google.genai import types
from pydantic import BaseModel

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

logger = logging.getLogger("agent_framework.gemini")

__all__ = [
    "GeminiChatClient",
    "GeminiChatOptions",
    "GeminiSettings",
    "GoogleGeminiSettings",
    "RawGeminiChatClient",
    "ThinkingConfig",
]

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)


# region Options & Settings


class ThinkingConfig(TypedDict, total=False):
    """Extended thinking configuration for Gemini models.

    Attributes:
        include_thoughts: Whether to include thought summaries in the response. Thought summaries
            are condensed representations of the model's internal reasoning and appear as response
            parts where ``part.thought`` is ``True``. Note: the framework currently excludes
            thought parts from ``ChatResponse.contents`` and does not surface them as output.
        thinking_budget: Token budget for Gemini 2.5 models. Set to ``0`` to disable
            thinking or ``-1`` to enable a dynamic budget.
        thinking_level: Thinking level for Gemini 2.5 models and later. One of
            ``ThinkingLevel.THINKING_LEVEL_UNSPECIFIED`` (default), ``ThinkingLevel.MINIMAL``,
            ``ThinkingLevel.LOW``, ``ThinkingLevel.MEDIUM``, or ``ThinkingLevel.HIGH``.
    """

    include_thoughts: bool
    thinking_budget: int
    thinking_level: types.ThinkingLevel


class GeminiChatOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """Google Gemini API-specific chat options.

    Extends ``ChatOptions`` with Gemini-specific fields. Standard options are mapped to their
    ``GenerateContentConfig`` equivalents; Gemini-specific fields are declared below.

    Only text output is supported for now. Other modalities may be added later.

    See: https://ai.google.dev/api/generate-content#generationconfig

    Inherited fields from ``ChatOptions``:
        model: Model to use for this call (e.g. ``"gemini-2.5-flash"``).
        temperature: Controls randomness. Higher values produce more varied output.
        max_tokens: Maximum number of tokens to generate (``maxOutputTokens``).
        top_p: Nucleus sampling cutoff. Only tokens within the top-p probability mass are considered.
        stop: One or more sequences that stop generation when encountered (``stopSequences``).
        seed: Fixed seed for reproducible outputs.
        frequency_penalty: Reduces repetition by penalising tokens that appear frequently.
        presence_penalty: Reduces repetition by penalising tokens that have already appeared.
        tools: Function tools the model may call. Accepts ``FunctionTool`` instances, plain callables,
            or ``types.Tool`` objects returned by ``get_code_interpreter_tool``, ``get_web_search_tool``,
            ``get_mcp_tool``, ``get_file_search_tool``, or ``get_maps_grounding_tool``.
        tool_choice: How the model picks a tool. One of ``'auto'``, ``'none'``, or ``'required'``.
        response_format: Pydantic model type for structured JSON output. The response text is
            parsed into the model and exposed via ``ChatResponse.value``.
        instructions: Extra system-level instructions prepended to the system message.

    Not supported, and passing these raises a type error:
        - ``logit_bias``
        - ``allow_multiple_tool_calls``
        - ``store``
        - ``user``
        - ``metadata``
        - ``conversation_id``
    """

    # Gemini's GenerationConfig options
    response_schema: dict[str, Any]
    """Raw JSON schema dict for structured output (alternative to ``response_format``).
    Sets ``response_mime_type`` to ``'application/json'`` and passes the schema directly."""

    top_k: int
    """Top-K sampling: limits token selection to the K most probable tokens."""

    thinking_config: ThinkingConfig
    """Extended thinking configuration. See ``ThinkingConfig`` for available fields."""

    # Unsupported base options. Override with None to indicate not supported
    logit_bias: None  # type: ignore[misc]
    """Not supported in the Gemini API."""

    allow_multiple_tool_calls: None  # type: ignore[misc]
    """Not supported. Gemini handles parallel tool calls automatically."""

    store: None  # type: ignore[misc]
    """Not supported in the Gemini API."""

    user: None  # type: ignore[misc]
    """Not supported in the Gemini API."""

    metadata: None  # type: ignore[misc]
    """Not supported in the Gemini API."""

    conversation_id: None  # type: ignore[misc]
    """Not supported in the Gemini API."""


GeminiChatOptionsT = TypeVar("GeminiChatOptionsT", bound=TypedDict, default="GeminiChatOptions", covariant=True)  # type: ignore[valid-type]


class GeminiSettings(TypedDict, total=False):
    """Gemini configuration settings loaded from environment or .env files."""

    api_key: SecretString | None
    model: str | None


class GoogleGeminiSettings(TypedDict, total=False):
    """Google SDK configuration settings loaded from ``GOOGLE_*`` environment variables."""

    api_key: SecretString | None
    model: str | None
    genai_use_vertexai: bool | None
    cloud_project: str | None
    cloud_location: str | None


# endregion


_GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"
_VERTEX_AI_BASE_URL = "https://aiplatform.googleapis.com"


def _resolve_vertexai_mode(client: genai.Client, *, fallback: bool | None = None) -> bool:
    """Resolve whether a client targets Vertex AI, preferring the instantiated SDK client state."""
    api_client = getattr(client, "_api_client", None)
    vertexai = getattr(api_client, "vertexai", None)
    if isinstance(vertexai, bool):
        return vertexai
    return bool(fallback)


def _resolve_service_url(client: genai.Client, *, vertexai: bool) -> str:
    """Resolve the base service URL from the instantiated SDK client, with a stable fallback."""
    api_client = getattr(client, "_api_client", None)
    http_options = getattr(api_client, "_http_options", None)
    base_url = getattr(http_options, "base_url", None)
    if isinstance(base_url, str) and base_url:
        return base_url.rstrip("/")
    return _VERTEX_AI_BASE_URL if vertexai else _GEMINI_API_BASE_URL


def _validate_client_auth_configuration(
    *,
    vertexai: bool | None,
    api_key: SecretString | None,
    project: str | None,
    location: str | None,
    credentials: Credentials | None,
) -> None:
    """Validate supported auth combinations before instantiating the SDK client."""
    if vertexai is not True:
        if api_key is None:
            raise ValueError(
                "Gemini client requires an API key when Vertex AI is not enabled. "
                "Set GOOGLE_API_KEY or GEMINI_API_KEY, or pass api_key explicitly."
            )
        return

    if api_key is not None or credentials is not None or (project and location):
        return

    if project or location:
        raise ValueError(
            "Gemini client requires both GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION "
            "when Vertex AI is enabled without an API key."
        )

    raise ValueError(
        "Gemini client requires Vertex AI credentials or configuration when Vertex AI is enabled. "
        "Provide GOOGLE_API_KEY for Vertex AI express mode, pass credentials, or set "
        "GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION."
    )


# Keys mapping to a different GenerateContentConfig field name
_OPTION_TRANSLATIONS: dict[str, str] = {
    "max_tokens": "max_output_tokens",
    "stop": "stop_sequences",
}

# Keys handled with dedicated logic, not via the generic passthrough
_OPTION_EXPLICIT_KEYS: frozenset[str] = frozenset({
    "tools",
    "tool_choice",
    "response_format",
    "response_schema",
    "thinking_config",
})

# Keys consumed upstream and not forwarded to GenerateContentConfig
_OPTION_CONSUMED_KEYS: frozenset[str] = frozenset({
    "model",
    "instructions",
})

_OPTION_EXCLUDE_KEYS: frozenset[str] = _OPTION_EXPLICIT_KEYS | _OPTION_CONSUMED_KEYS

_FINISH_REASON_MAP: dict[str, FinishReasonLiteral] = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "LANGUAGE": "content_filter",
    "BLOCKLIST": "content_filter",
    "PROHIBITED_CONTENT": "content_filter",
    "SPII": "content_filter",
    "IMAGE_SAFETY": "content_filter",
    "IMAGE_PROHIBITED_CONTENT": "content_filter",
    "IMAGE_RECITATION": "content_filter",
    "MALFORMED_FUNCTION_CALL": "tool_calls",
    "UNEXPECTED_TOOL_CALL": "tool_calls",
}


class RawGeminiChatClient(
    BaseChatClient[GeminiChatOptionsT],
    Generic[GeminiChatOptionsT],
):
    """A raw Gemini chat client for Gemini Developer API or Vertex AI.

    Use this when you want full control over the request pipeline. For instance, to opt out of
    telemetry, use custom middleware, or compose your own layers. If you want the full-featured
    client with batteries included, use `GeminiChatClient` instead.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "gcp.gemini"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        vertexai: bool | None = None,
        project: str | None = None,
        location: str | None = None,
        credentials: Credentials | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        client: genai.Client | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Create a raw Gemini chat client.

        Args:
            api_key: Gemini Developer API key. Falls back to environment settings, preferring
                ``GOOGLE_API_KEY`` over ``GEMINI_API_KEY``.
            model: Default model identifier. Falls back to environment settings, preferring
                ``GOOGLE_MODEL`` over ``GEMINI_MODEL``.
            vertexai: Whether to use Vertex AI endpoints. Falls back to environment settings,
                using ``GOOGLE_GENAI_USE_VERTEXAI`` when not passed explicitly.
            project: Google Cloud project ID for Vertex AI. Falls back to environment settings,
                using ``GOOGLE_CLOUD_PROJECT`` when not passed explicitly.
            location: Vertex AI location. Falls back to environment settings, preferring
                using ``GOOGLE_CLOUD_LOCATION`` when not passed explicitly.
            credentials: Google Cloud credentials for Vertex AI. When omitted, the SDK can use
                Application Default Credentials.
            env_file_path: Path to a ``.env`` file for credential loading.
            env_file_encoding: Encoding for the ``.env`` file.
            client: Pre-built ``genai.Client`` instance. When provided, connector auth settings are not required.
            additional_properties: Extra properties stored on the client instance.
        """
        settings = load_settings(
            GeminiSettings,
            env_prefix="GEMINI_",
            api_key=api_key,
            model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        google_settings = load_settings(
            GoogleGeminiSettings,
            env_prefix="GOOGLE_",
            api_key=api_key,
            model=model,
            genai_use_vertexai=vertexai,
            cloud_project=project,
            cloud_location=location,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        configured_vertexai = google_settings.get("genai_use_vertexai")
        if client:
            self._genai_client = client
        else:
            resolved_key = google_settings.get("api_key") or settings.get("api_key")
            resolved_project = google_settings.get("cloud_project")
            resolved_location = google_settings.get("cloud_location")
            _validate_client_auth_configuration(
                vertexai=configured_vertexai,
                api_key=resolved_key,
                project=resolved_project,
                location=resolved_location,
                credentials=credentials,
            )

            client_kwargs: dict[str, Any] = {
                "http_options": {"headers": {"x-goog-api-client": AGENT_FRAMEWORK_USER_AGENT}},
            }
            if configured_vertexai is not None:
                client_kwargs["vertexai"] = configured_vertexai

            if resolved_key is not None and (
                configured_vertexai is not True
                or (credentials is None and not (resolved_project and resolved_location))
            ):
                client_kwargs["api_key"] = resolved_key.get_secret_value()

            if configured_vertexai is True and resolved_project:
                client_kwargs["project"] = resolved_project

            if configured_vertexai is True and resolved_location:
                client_kwargs["location"] = resolved_location
            if configured_vertexai is True and credentials is not None:
                client_kwargs["credentials"] = credentials

            self._genai_client = genai.Client(**client_kwargs)

        self._vertexai = _resolve_vertexai_mode(self._genai_client, fallback=configured_vertexai)
        self._service_url = _resolve_service_url(self._genai_client, vertexai=self._vertexai)
        self.model = google_settings.get("model") or settings.get("model")

        super().__init__(additional_properties=additional_properties)

    @staticmethod
    def get_code_interpreter_tool() -> types.Tool:
        """Create a code execution tool.

        Pass the returned tool to the ``tools`` list of an agent or ``ChatOptions``.

        Returns:
            A ``types.Tool`` configured for sandboxed code execution.
        """
        return types.Tool(code_execution=types.ToolCodeExecution())

    @staticmethod
    def get_web_search_tool(
        *,
        search_types: types.SearchTypes | None = None,
        blocking_confidence: types.PhishBlockThreshold | None = None,
        exclude_domains: list[str] | None = None,
        time_range_filter: types.Interval | None = None,
    ) -> types.Tool:
        """Create a Google Search grounding tool.

        Pass the returned tool to the ``tools`` list of an agent or ``ChatOptions``.

        Args:
            search_types: Controls which search types are enabled (web search, image search).
            blocking_confidence: Block sites at or above this phishing confidence level.
                Not supported in Gemini API.
            exclude_domains: List of domains to exclude from search results. Not supported in Gemini API.
            time_range_filter: Restrict results to a specific time range. Not supported in Vertex AI.

        Returns:
            A ``types.Tool`` configured for Google Search grounding.
        """
        return types.Tool(
            google_search=types.GoogleSearch(
                search_types=search_types,
                blocking_confidence=blocking_confidence,
                exclude_domains=exclude_domains,
                time_range_filter=time_range_filter,
            )
        )

    @staticmethod
    def get_mcp_tool(url: str, *, name: str | None = None, **kwargs: Any) -> types.Tool:
        """Create an MCP (Model Context Protocol) server tool.

        Pass the returned tool to the ``tools`` list of an agent or ``ChatOptions``.

        Args:
            url: The URL of the MCP server's streamable HTTP endpoint.
            name: Optional display name for the MCP server.
            **kwargs: Additional kwargs passed to ``StreamableHttpTransport``. Supported fields
                include ``headers``, ``timeout``, ``sse_read_timeout``, and ``terminate_on_close``.

        Returns:
            A ``types.Tool`` configured for the given MCP server.
        """
        return types.Tool(
            mcp_servers=[
                types.McpServer(
                    name=name,
                    streamable_http_transport=types.StreamableHttpTransport(url=url, **kwargs),
                )
            ]
        )

    @staticmethod
    def get_file_search_tool(
        *,
        file_search_store_names: list[str] | None = None,
        top_k: int | None = None,
        metadata_filter: str | None = None,
    ) -> types.Tool:
        """Create a file search tool backed by a Gemini file search store.

        Pass the returned tool to the ``tools`` list of an agent or ``ChatOptions``.

        Args:
            file_search_store_names: Resource names of the file search stores to query.
                Example: ``["fileSearchStores/my-file-search-store-123"]``.
            top_k: Maximum number of retrieval chunks to return.
            metadata_filter: CEL expression to filter retrieval results by metadata.
                See https://google.aip.dev/160 for syntax.

        Returns:
            A ``types.Tool`` configured for file search retrieval.
        """
        return types.Tool(
            file_search=types.FileSearch(
                file_search_store_names=file_search_store_names,
                top_k=top_k,
                metadata_filter=metadata_filter,
            )
        )

    @staticmethod
    def get_maps_grounding_tool(
        *,
        enable_widget: bool | None = None,
        auth_config: types.AuthConfig | None = None,
    ) -> types.Tool:
        """Create a Google Maps grounding tool.

        Pass the returned tool to the ``tools`` list of an agent or ``ChatOptions``.

        Args:
            enable_widget: Return a widget context token in ``GroundingMetadata`` so callers
                can render a Google Maps widget with geospatial context.
            auth_config: Authentication config to access the Maps API. Only API key is
                supported. Not supported in Gemini API.

        Returns:
            A ``types.Tool`` configured for Google Maps grounding.
        """
        return types.Tool(google_maps=types.GoogleMaps(enable_widget=enable_widget, auth_config=auth_config))

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:

            async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                validated = await self._validate_options(options)
                model, contents, config = self._prepare_request(messages, validated)
                async for chunk in await self._genai_client.aio.models.generate_content_stream(  # pyright: ignore[reportUnknownMemberType]
                    model=model,
                    contents=contents,  # type: ignore[arg-type]
                    config=config,
                ):
                    yield self._process_chunk(chunk)

            return self._build_response_stream(_stream(), response_format=options.get("response_format"))

        async def _get_response() -> ChatResponse:
            validated = await self._validate_options(options)
            model, contents, config = self._prepare_request(messages, validated)
            raw = await self._genai_client.aio.models.generate_content(model=model, contents=contents, config=config)  # type: ignore[arg-type]
            return self._process_generate_response(raw, response_format=validated.get("response_format"))

        return _get_response()

    @override
    def service_url(self) -> str:
        """Return the base URL of the configured Gemini or Vertex AI service.

        Returns:
            The resolved service base URL.
        """
        return self._service_url

    # region Request preparation

    def _prepare_request(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
    ) -> tuple[str, list[types.Content], types.GenerateContentConfig]:
        """Resolve the model ID, convert messages to Gemini contents, and build the generation config.

        Call this after awaiting ``_validate_options`` so that tools and other options are
        fully normalized before the request is assembled.

        Args:
            messages: The conversation history as framework Message objects.
            options: Validated and normalized chat options.

        Returns:
            A tuple of the resolved model, the Gemini contents list, and the generation config.

        Raises:
            ValueError: If no model is set on the options or the client instance.
        """
        model = options.get("model") or self.model
        if not model:
            raise ValueError("Gemini model is required. Set via model parameter or GEMINI_MODEL environment variable.")

        system_instruction, contents = self._prepare_gemini_messages(messages)
        if call_instructions := options.get("instructions"):
            system_instruction = (
                f"{call_instructions}\n{system_instruction}" if system_instruction else call_instructions
            )

        return model, contents, self._prepare_config(options, system_instruction)

    def _prepare_gemini_messages(self, messages: Sequence[Message]) -> tuple[str | None, list[types.Content]]:
        """Convert framework messages to Gemini contents and extract system instruction.

        Args:
            messages: The full conversation history as framework Message objects.

        Returns:
            A tuple of (system_instruction_text, contents_list). System messages are extracted
            into the instruction string; tool results are grouped into user-role content blocks.
        """
        system_parts: list[str] = []
        contents: list[types.Content] = []
        # Maps call_id to function name so function_result parts can include the required name field.
        call_id_to_name: dict[str, str] = {}
        # Accumulated functionResponse parts from consecutive tool messages.
        pending_tool_parts: list[types.Part] = []

        def flush_pending_tool_parts() -> None:
            if pending_tool_parts:
                contents.append(types.Content(role="user", parts=list(pending_tool_parts)))
                pending_tool_parts.clear()

        for message in messages:
            if message.role == "system":
                if message.text:
                    system_parts.append(message.text)
                continue

            if message.role == "tool":
                for content in message.contents:
                    part = self._convert_function_result(content, call_id_to_name)
                    if part is not None:
                        pending_tool_parts.append(part)
                continue

            # Non-tool message — flush any accumulated tool parts first.
            flush_pending_tool_parts()

            parts = self._convert_message_contents(message.contents, call_id_to_name)
            if not parts:
                continue

            role = "model" if message.role == "assistant" else "user"
            contents.append(types.Content(role=role, parts=parts))

        flush_pending_tool_parts()

        system_instruction = "\n".join(system_parts) if system_parts else None
        return system_instruction, contents

    def _convert_message_contents(
        self,
        message_contents: Sequence[Content],
        call_id_to_name: dict[str, str],
    ) -> list[types.Part]:
        """Convert framework Content objects to Gemini Part objects, tracking function call IDs.

        Args:
            message_contents: The content items of a single framework message.
            call_id_to_name: Mutable mapping updated with any function call ID-to-name pairs found.

        Returns:
            A list of Gemini Part objects representing the message contents.
        """
        parts: list[types.Part] = []
        for content in message_contents:
            match content.type:
                case "text":
                    parts.append(types.Part(text=content.text or ""))
                case "function_call":
                    call_id = content.call_id or self._generate_tool_call_id()
                    if content.name:
                        call_id_to_name[call_id] = content.name
                    function_call = types.FunctionCall(
                        id=call_id,
                        name=content.name or "",
                        args=content.parse_arguments() or {},
                    )
                    raw_part = content.raw_representation
                    if isinstance(raw_part, types.Part) and raw_part.function_call is not None:
                        parts.append(raw_part.model_copy(update={"function_call": function_call}, deep=True))
                    else:
                        parts.append(types.Part(function_call=function_call))
                case _:
                    logger.debug("Skipping unsupported content type for Gemini: %s", content.type)
        return parts

    def _convert_function_result(
        self,
        content: Content,
        call_id_to_name: dict[str, str],
    ) -> types.Part | None:
        """Convert a function_result Content to a Gemini FunctionResponse Part.

        Args:
            content: The framework Content object, expected to be of type ``function_result``.
            call_id_to_name: Mapping of call IDs to function names, used to resolve the required name field.

        Returns:
            A Gemini Part containing a FunctionResponse, or None if the content type is not
            ``function_result`` or the call ID cannot be resolved.
        """
        if content.type != "function_result":
            return None

        name = call_id_to_name.get(content.call_id or "")
        if not name:
            logger.warning(
                "Skipping function_result: no matching function_call found for call_id=%r",
                content.call_id,
            )
            return None

        response = self._coerce_to_dict(content.result)
        return types.Part(
            function_response=types.FunctionResponse(
                id=content.call_id,
                name=name,
                response=response,
            )
        )

    @staticmethod
    def _coerce_to_dict(value: Any) -> dict[str, Any]:
        """Ensure a tool result value is a dict as required by Gemini's FunctionResponse.

        Args:
            value: The raw tool result. May be a dict, JSON string, plain string, None, or any other value.

        Returns:
            A dict representation of the value. JSON strings are parsed; all other non-dict values
            are wrapped as ``{"result": <str(value)>}``.
        """
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return cast(dict[str, Any], parsed)
            except (json.JSONDecodeError, ValueError):
                pass
            return {"result": value}
        if value is None:
            return {"result": ""}
        return {"result": str(value)}

    def _prepare_config(
        self,
        options: Mapping[str, Any],
        system_instruction: str | None,
    ) -> types.GenerateContentConfig:
        """Build a ``types.GenerateContentConfig`` from the resolved chat options.

        Note: ``_OPTION_TRANSLATIONS`` keys are renamed, ``_OPTION_EXCLUDE_KEYS`` are skipped, and all
        remaining keys are forwarded as-is, allowing new Gemini parameters to be adopted without
        framework changes.

        Args:
            options: Resolved chat options mapping, typically a ``GeminiChatOptions`` dict.
            system_instruction: Combined system instruction text, or None if absent.

        Returns:
            A fully populated ``GenerateContentConfig`` ready to pass to the Gemini API.
        """
        kwargs: dict[str, Any] = {}

        if system_instruction:
            kwargs["system_instruction"] = system_instruction

        for key, value in options.items():
            if key in _OPTION_EXCLUDE_KEYS or value is None:
                continue
            kwargs[_OPTION_TRANSLATIONS.get(key, key)] = value

        if options.get("response_format") or options.get("response_schema"):
            kwargs["response_mime_type"] = "application/json"
        if schema := options.get("response_schema"):
            kwargs["response_schema"] = schema
        if tools := self._prepare_tools(options):
            kwargs["tools"] = tools
        if tool_config := self._prepare_tool_config(options.get("tool_choice")):
            kwargs["tool_config"] = tool_config
        if thinking_config := options.get("thinking_config"):
            thinking_config_kwargs = {k: v for k, v in thinking_config.items() if v is not None}
            if thinking_config_kwargs:
                kwargs["thinking_config"] = types.ThinkingConfig(**thinking_config_kwargs)

        return types.GenerateContentConfig(**kwargs)

    def _prepare_tools(self, options: Mapping[str, Any]) -> list[types.Tool] | None:
        """Translate the framework tool list into Gemini API tool objects.

        The Gemini API does not accept framework ``FunctionTool`` objects directly.
        This method acts as the translation boundary between the two type systems.
        It handles two kinds of entries in ``options["tools"]``:

        - ``FunctionTool``: a framework abstraction for a callable with a name,
          description, and JSON schema. Translated to ``types.FunctionDeclaration``
          (Gemini's equivalent) and grouped into a single ``types.Tool``, which is
          how the Gemini API expects function declarations to be passed.
        - ``types.Tool``: already in Gemini's native format (e.g. built-in tools
          such as search or code execution). Passed through unchanged. Use the
          ``get_*_tool`` factory methods on this class to produce these.

        Args:
            options: Resolved chat options whose ``tools`` entry may contain
                ``FunctionTool`` instances, plain callables, or ``types.Tool`` objects.

        Returns:
            A non-empty list of ``types.Tool`` objects ready for the Gemini API,
            or ``None`` if no tools are configured.
        """
        tools_option: list[Any] = options.get("tools") or []

        result: list[types.Tool] = []

        # Translate framework FunctionTool objects to Gemini API FunctionDeclaration objects
        declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters=tool.parameters(),  # type: ignore[arg-type]
            )
            for tool in tools_option
            if isinstance(tool, FunctionTool)
        ]
        if declarations:
            result.append(types.Tool(function_declarations=declarations))

        # Objects of type types.Tool are already in Gemini's native format
        result.extend(tool for tool in tools_option if isinstance(tool, types.Tool))

        return result or None

    def _prepare_tool_config(self, tool_choice: Any) -> types.ToolConfig | None:
        """Build a Gemini ``ToolConfig`` from the framework ``tool_choice`` value.

        Args:
            tool_choice: Raw ``tool_choice`` value from options (string, dict, or None).

        Returns:
            A ``types.ToolConfig`` with the appropriate ``FunctionCallingConfig``, or None
            if no ``tool_choice`` is set or the mode is unsupported.
        """
        tool_mode = validate_tool_mode(tool_choice)
        if not tool_mode:
            return None

        match tool_mode.get("mode"):
            case "auto":
                function_calling_mode, allowed_names = types.FunctionCallingConfigMode.AUTO, None
            case "none":
                function_calling_mode, allowed_names = types.FunctionCallingConfigMode.NONE, None
            case "required":
                function_calling_mode = types.FunctionCallingConfigMode.ANY
                name = tool_mode.get("required_function_name")
                allowed_names = [name] if name else None
            case unknown_mode:
                logger.warning("Unsupported tool_choice mode for Gemini: %s", unknown_mode)
                return None

        function_calling_kwargs: dict[str, Any] = {"mode": function_calling_mode}
        if allowed_names:
            function_calling_kwargs["allowed_function_names"] = allowed_names

        return types.ToolConfig(function_calling_config=types.FunctionCallingConfig(**function_calling_kwargs))

    # endregion

    # region Response parsing

    def _process_generate_response(
        self,
        response: types.GenerateContentResponse,
        *,
        response_format: type[BaseModel] | None = None,
    ) -> ChatResponse:
        """Convert a Gemini generate_content response to a framework ChatResponse.

        Args:
            response: The raw ``GenerateContentResponse`` from the Gemini API.
            response_format: Optional Pydantic model type for structured output parsing.
                When provided, the response text is parsed into the given model and
                made available via ``ChatResponse.value``.

        Returns:
            A ``ChatResponse`` with parsed messages, usage details, finish reason, and model ID.
        """
        candidate = response.candidates[0] if response.candidates else None
        parts: list[types.Part] = (candidate.content.parts or []) if candidate and candidate.content else []
        contents = self._parse_parts(parts)
        return ChatResponse(
            response_id=None,
            messages=[Message(role="assistant", contents=contents, raw_representation=candidate)],
            usage_details=self._parse_usage(response.usage_metadata),
            model=response.model_version or self.model,
            finish_reason=self._map_finish_reason(
                candidate.finish_reason.name if candidate and candidate.finish_reason else None
            ),
            response_format=response_format,
            raw_representation=response,
        )

    def _process_chunk(self, chunk: types.GenerateContentResponse) -> ChatResponseUpdate:
        """Convert a single streaming chunk to a framework ChatResponseUpdate.

        Usage details are attached only to the final chunk, identified by a non-None finish reason.

        Args:
            chunk: A streaming ``GenerateContentResponse`` chunk from the Gemini API.

        Returns:
            A ``ChatResponseUpdate`` with parsed contents, finish reason, and model ID.
        """
        candidate = chunk.candidates[0] if chunk.candidates else None
        parts: list[types.Part] = (candidate.content.parts or []) if candidate and candidate.content else []
        contents = self._parse_parts(parts)

        finish_reason = self._map_finish_reason(
            candidate.finish_reason.name if candidate and candidate.finish_reason else None
        )

        # Attach usage to the final chunk only (when finish_reason is set).
        if finish_reason and (usage := self._parse_usage(chunk.usage_metadata)):
            contents.append(Content.from_usage(usage_details=usage))

        return ChatResponseUpdate(
            contents=contents,
            model=chunk.model_version,
            finish_reason=finish_reason,
            raw_representation=chunk,
        )

    def _parse_parts(self, parts: Sequence[types.Part]) -> list[Content]:
        """Convert Gemini response parts to framework Content objects, skipping thought/reasoning parts.

        Args:
            parts: Sequence of ``types.Part`` objects from a Gemini response candidate.

        Returns:
            A list of framework ``Content`` objects (text, function_call, or function_result).
        """
        contents: list[Content] = []
        for part in parts:
            if part.thought:
                continue
            if part.text is not None:
                contents.append(Content.from_text(text=part.text, raw_representation=part))
            elif part.function_call is not None:
                function_call = part.function_call
                if function_call.id:
                    call_id = function_call.id
                else:
                    call_id = self._generate_tool_call_id()
                    logger.debug("function_call missing id; generated fallback call_id=%r", call_id)
                contents.append(
                    Content.from_function_call(
                        call_id=call_id,
                        name=function_call.name or "",
                        arguments=function_call.args or {},
                        raw_representation=part,
                    )
                )
            elif part.function_response is not None:
                function_response = part.function_response
                contents.append(
                    Content.from_function_result(
                        call_id=function_response.id or self._generate_tool_call_id(),
                        result=function_response.response,
                        raw_representation=part,
                    )
                )
            elif part.executable_code is not None:
                if part.executable_code.code:
                    contents.append(Content.from_text(text=part.executable_code.code, raw_representation=part))
            elif part.code_execution_result is not None:
                if part.code_execution_result.output:
                    contents.append(Content.from_text(text=part.code_execution_result.output, raw_representation=part))
            else:
                logger.debug("Skipping unsupported response part from Gemini")
        return contents

    def _parse_usage(self, usage: types.GenerateContentResponseUsageMetadata | None) -> UsageDetails | None:
        """Extract token usage counts from Gemini usage metadata.

        Args:
            usage: The ``GenerateContentResponseUsageMetadata`` from the API response, or None.

        Returns:
            A ``UsageDetails`` dict with available token counts, or None if no usage data is present.
        """
        if not usage:
            return None
        details: UsageDetails = {}
        if (v := usage.prompt_token_count) is not None:
            details["input_token_count"] = v
        if (v := usage.candidates_token_count) is not None:
            details["output_token_count"] = v
        if (v := usage.total_token_count) is not None:
            details["total_token_count"] = v
        return details or None

    def _map_finish_reason(self, reason: str | None) -> FinishReasonLiteral | None:
        """Map a Gemini finish reason string to the framework's FinishReasonLiteral.

        Args:
            reason: The finish reason name from the Gemini API (e.g. ``"STOP"``), or None.

        Returns:
            The corresponding ``FinishReasonLiteral``, or None if the reason is absent or unmapped.
        """
        if not reason:
            return None
        return _FINISH_REASON_MAP.get(reason)

    # endregion

    @staticmethod
    def _generate_tool_call_id() -> str:
        """Generate a unique fallback ID for tool calls that lack one.

        Returns:
            A unique string in the format ``tool-call-<uuid_hex>``.
        """
        return f"tool-call-{uuid4().hex}"


class GeminiChatClient(
    FunctionInvocationLayer[GeminiChatOptionsT],
    ChatMiddlewareLayer[GeminiChatOptionsT],
    ChatTelemetryLayer[GeminiChatOptionsT],
    RawGeminiChatClient[GeminiChatOptionsT],
    Generic[GeminiChatOptionsT],
):
    """Gemini chat client for Gemini Developer API or Vertex AI with function invocation, middleware, and telemetry.

    This is the recommended client for most use cases. It builds on ``RawGeminiChatClient``
    and adds:

    - **Function invocation**: automatically calls ``FunctionTool`` implementations and feeds
      results back to the model until it produces a final text response.
    - **Middleware**: a composable chain for cross-cutting concerns (logging, retries, etc.).
    - **Telemetry**: OpenTelemetry traces and metrics emitted for every request.

    Use ``RawGeminiChatClient`` instead when you need full control over the request pipeline
    and want to opt out of one or more of these layers.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        vertexai: bool | None = None,
        project: str | None = None,
        location: str | None = None,
        credentials: Credentials | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        client: genai.Client | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    ) -> None:
        """Create a Gemini chat client.

        Args:
            api_key: Gemini Developer API key. Falls back to environment settings, preferring
                ``GOOGLE_API_KEY`` over ``GEMINI_API_KEY``.
            model: Default model identifier. Falls back to environment settings, preferring
                ``GOOGLE_MODEL`` over ``GEMINI_MODEL``.
            vertexai: Whether to use Vertex AI endpoints. Falls back to ``GOOGLE_GENAI_USE_VERTEXAI``.
            project: Google Cloud project ID for Vertex AI. Falls back to ``GOOGLE_CLOUD_PROJECT``.
            location: Vertex AI location. Falls back to ``GOOGLE_CLOUD_LOCATION``.
            credentials: Google Cloud credentials for Vertex AI. When omitted, the SDK can use
                Application Default Credentials.
            env_file_path: Path to a ``.env`` file for credential loading.
            env_file_encoding: Encoding for the ``.env`` file.
            client: Pre-built ``genai.Client`` instance. When provided, connector auth settings are not required.
            additional_properties: Extra properties stored on the client instance.
            middleware: Optional middleware chain applied to every call.
            function_invocation_configuration: Optional configuration for the function invocation loop.
        """
        super().__init__(
            api_key=api_key,
            model=model,
            vertexai=vertexai,
            project=project,
            location=location,
            credentials=credentials,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            client=client,
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )
