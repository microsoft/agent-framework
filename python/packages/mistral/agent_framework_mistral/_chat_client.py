# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, ClassVar, Generic, Literal, cast

import httpx
from agent_framework import (
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
from agent_framework._telemetry import get_user_agent, mark_feature_used
from agent_framework._types import prepend_instructions_to_messages
from agent_framework.exceptions import (
    ChatClientException,
    ChatClientInvalidAuthException,
    ChatClientInvalidRequestException,
    ChatClientInvalidResponseException,
)
from agent_framework.observability import ChatTelemetryLayer
from pydantic import BaseModel

from ._feature_usage import FeatureIndex

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

logger = logging.getLogger("agent_framework.mistral")

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)


# region Options & Settings


class MistralChatOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """Mistral AI-specific chat options.

    Extends ``ChatOptions`` with Mistral-specific fields. Standard options are mapped to their
    Mistral chat-completion equivalents; Mistral-specific fields are declared below.

    See: https://docs.mistral.ai/api/#tag/chat

    Inherited fields from ``ChatOptions``:
        model: Model to use for this call (e.g. ``"mistral-large-latest"``).
        temperature: Controls randomness. Higher values produce more varied output.
        max_tokens: Maximum number of tokens to generate.
        top_p: Nucleus sampling cutoff.
        stop: One or more sequences that stop generation when encountered.
        seed: Fixed seed for reproducible outputs, translates to ``random_seed``.
        frequency_penalty: Reduces repetition by penalising frequent tokens.
        presence_penalty: Reduces repetition by penalising tokens already present.
        tools: Function tools the model may call.
        tool_choice: How the model picks a tool. One of ``'auto'``, ``'none'``, or ``'required'``.
        allow_multiple_tool_calls: Translates to ``parallel_tool_calls``.
        response_format: Pydantic model type or JSON schema mapping for structured JSON output.
            The response text is parsed and exposed via ``ChatResponse.value``.
        instructions: Extra system-level instructions prepended to the system message.
        metadata: Arbitrary key/value metadata attached to the request.

    Not supported, and passing these raises a type error:
        - ``logit_bias``
        - ``store``
        - ``user``
        - ``conversation_id``
    """

    safe_prompt: bool
    """Whether to inject a safety prompt before all conversations."""

    prompt_mode: str
    """Toggle between reasoning mode and no system prompt (e.g. ``"reasoning"``)."""

    prediction: dict[str, Any]
    """Predicted output to optimize response time when large parts of the response are known."""

    guardrails: list[dict[str, Any]]
    """Guardrail configurations applied to the request."""

    prompt_cache_key: str
    """Cache key shared by requests with the same prompt prefix."""

    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"]
    """Effort level for models that support reasoning."""

    # Unsupported base options. Override with None to indicate not supported
    logit_bias: None  # type: ignore[misc]
    """Not supported in the Mistral API."""

    store: None  # type: ignore[misc]
    """Not supported in the Mistral API."""

    user: None  # type: ignore[misc]
    """Not supported in the Mistral API."""

    conversation_id: None  # type: ignore[misc]
    """Not supported in the Mistral API."""


MistralChatOptionsT = TypeVar("MistralChatOptionsT", bound=TypedDict, default="MistralChatOptions", covariant=True)  # type: ignore[valid-type]


class MistralSettings(TypedDict, total=False):
    """Mistral AI chat settings.

    Fields:
        api_key: Mistral API key. Resolved from ``MISTRAL_API_KEY``.
        chat_model: Chat model name. Resolved from ``MISTRAL_CHAT_MODEL``.
        server_url: Optional server URL override. Resolved from ``MISTRAL_SERVER_URL``.
    """

    api_key: SecretString | None
    chat_model: str | None
    server_url: str | None


# endregion

_MISTRAL_API_BASE_URL = "https://api.mistral.ai"
_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_SSE_DATA_PREFIX = "data:"
_SSE_DONE = "[DONE]"

# Keys mapping to a different Mistral chat-completion parameter name
_OPTION_TRANSLATIONS: dict[str, str] = {
    "seed": "random_seed",
    "allow_multiple_tool_calls": "parallel_tool_calls",
}

# Keys handled with dedicated logic, not via the generic passthrough
_OPTION_EXPLICIT_KEYS: frozenset[str] = frozenset(
    {
        "tools",
        "tool_choice",
        "response_format",
    }
)

# Keys consumed upstream and not forwarded to the Mistral API
_OPTION_CONSUMED_KEYS: frozenset[str] = frozenset(
    {
        "model",
        "instructions",
    }
)

_OPTION_EXCLUDE_KEYS: frozenset[str] = _OPTION_EXPLICIT_KEYS | _OPTION_CONSUMED_KEYS

_FINISH_REASON_MAP: dict[str, FinishReasonLiteral] = {
    "stop": "stop",
    "length": "length",
    "model_length": "length",
    "tool_calls": "tool_calls",
}

# La Plateforme requires tool call IDs to be exactly 9 alphanumeric characters.
_MISTRAL_TOOL_CALL_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]{9}$")


def _sanitize_tool_call_id(call_id: str) -> str:
    """Return a Mistral-compatible tool call ID, deterministically derived when needed."""
    if _MISTRAL_TOOL_CALL_ID_PATTERN.match(call_id):
        return call_id
    return hashlib.sha256(call_id.encode("utf-8")).hexdigest()[:9]


def _tool_call_id_of(tool_call: Mapping[str, Any]) -> str:
    """Return the wire tool call ID, treating null/"null" placeholders as missing."""
    call_id = tool_call.get("id")
    if isinstance(call_id, str) and call_id and call_id != "null":
        return call_id
    return ""


def _function_call_content(tool_call: Mapping[str, Any]) -> Content:
    function: Mapping[str, Any] = tool_call.get("function") or {}
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        normalized_arguments: str | dict[str, Any] = arguments
    elif isinstance(arguments, dict):
        normalized_arguments = cast("dict[str, Any]", arguments)
    else:
        normalized_arguments = str(cast(object, arguments))
    return Content.from_function_call(
        call_id=_tool_call_id_of(tool_call),
        name=function.get("name") or "",
        arguments=normalized_arguments,
        raw_representation=tool_call,
    )


class _StreamedToolCalls:
    """Correlates streamed tool-call fragments by ``(choice index, tool-call index)``.

    Mistral may interleave fragments of parallel calls and omit ``id`` on
    continuations, so a call is only emitted once it is complete: when its
    choice finishes, when its index is reused by a new call, or at stream end.
    """

    def __init__(self) -> None:
        self._pending: dict[tuple[int, int | str], dict[str, Any]] = {}
        self._auto_key_count = 0

    def add(self, choice_index: int, fragment: Mapping[str, Any]) -> list[Content]:
        """Fold a fragment into its pending call; returns calls completed by an index reuse."""
        flushed: list[Content] = []
        key = self._key_for(choice_index, fragment)
        pending = self._pending.get(key)
        if pending is not None:
            fragment_id = _tool_call_id_of(fragment)
            if fragment_id and (pending_id := _tool_call_id_of(pending)) and pending_id != fragment_id:
                flushed.append(_function_call_content(self._pending.pop(key)))
                pending = None
        if pending is None:
            self._pending[key] = {**fragment, "function": dict(fragment.get("function") or {})}
        else:
            self._merge(pending, fragment)
        return flushed

    def flush_choice(self, choice_index: int) -> list[Content]:
        keys = [key for key in self._pending if key[0] == choice_index]
        return [_function_call_content(self._pending.pop(key)) for key in keys]

    def flush_all(self) -> list[Content]:
        contents = [_function_call_content(pending) for pending in self._pending.values()]
        self._pending.clear()
        return contents

    def _key_for(self, choice_index: int, fragment: Mapping[str, Any]) -> tuple[int, int | str]:
        index = fragment.get("index")
        if isinstance(index, int):
            return (choice_index, index)
        if fragment_id := _tool_call_id_of(fragment):
            for key, pending in self._pending.items():
                if key[0] == choice_index and _tool_call_id_of(pending) == fragment_id:
                    return key
        else:
            for key in reversed(self._pending):
                if key[0] == choice_index:
                    return key
        self._auto_key_count += 1
        return (choice_index, f"auto-{self._auto_key_count}")

    @staticmethod
    def _merge(pending: dict[str, Any], fragment: Mapping[str, Any]) -> None:
        if fragment_id := _tool_call_id_of(fragment):
            pending["id"] = fragment_id
        function: Mapping[str, Any] = fragment.get("function") or {}
        pending_function: dict[str, Any] = pending["function"]
        if (name := function.get("name")) and not pending_function.get("name"):
            pending_function["name"] = name
        new_arguments = function.get("arguments")
        old_arguments = pending_function.get("arguments")
        if new_arguments is None:
            return
        if isinstance(old_arguments, str) and isinstance(new_arguments, str):
            pending_function["arguments"] = old_arguments + new_arguments
        elif isinstance(old_arguments, dict) and isinstance(new_arguments, dict):
            cast("dict[str, Any]", old_arguments).update(cast("dict[str, Any]", new_arguments))
        else:
            pending_function["arguments"] = new_arguments


class RawMistralChatClient(
    BaseChatClient[MistralChatOptionsT],
    Generic[MistralChatOptionsT],
):
    """A raw Mistral AI chat client.

    Talks to the Mistral REST API directly over HTTP; the ``mistralai`` SDK is not required.

    Use this when you want full control over the request pipeline. For instance, to opt out of
    telemetry, use custom middleware, or compose your own layers. If you want the full-featured
    client with batteries included, use `MistralChatClient` instead.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "mistralai"

    INJECTABLE: ClassVar[set[str]] = {"client"}

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        server_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Create a raw Mistral AI chat client.

        Keyword Args:
            model: The Mistral chat model to use (e.g. "mistral-large-latest").
                Can also be set via environment variable ``MISTRAL_CHAT_MODEL``.
            api_key: Mistral API key. Defaults to ``MISTRAL_API_KEY`` environment variable.
            server_url: Optional server URL override. Defaults to ``MISTRAL_SERVER_URL``
                environment variable, or the Mistral default.
            client: Optional pre-configured ``httpx.AsyncClient``. When provided, api_key is
                not required and the client is expected to carry its own auth headers and
                base URL.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Path to ``.env`` file for settings.
            env_file_encoding: Encoding for ``.env`` file.
        """
        mistral_settings = load_settings(
            MistralSettings,
            env_prefix="MISTRAL_",
            required_fields=[] if client is not None else ["api_key"],
            api_key=api_key,
            chat_model=model,
            server_url=server_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.model = mistral_settings.get("chat_model")
        self.server_url = mistral_settings.get("server_url")
        self._owns_client = client is None

        if client is not None:
            self.client = client
            if self.server_url is None:
                client_base_url = str(client.base_url).rstrip("/")
                self.server_url = client_base_url or None
        else:
            resolved_api_key: SecretString = mistral_settings["api_key"]  # type: ignore[assignment]
            self.client = httpx.AsyncClient(
                base_url=self.server_url or _MISTRAL_API_BASE_URL,
                headers={
                    "Authorization": f"Bearer {resolved_api_key.get_secret_value()}",
                    "User-Agent": get_user_agent(),
                    "Accept": "application/json",
                },
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )

        super().__init__(additional_properties=additional_properties)

    async def close(self) -> None:
        """Close the internally created HTTP client."""
        if self._owns_client:
            await self.client.aclose()

    @override
    def service_url(self) -> str:
        """Get the URL of the service."""
        return self.server_url or _MISTRAL_API_BASE_URL

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
                request = self._prepare_request(messages, validated, **kwargs)
                request["stream"] = True
                mark_feature_used(FeatureIndex.MISTRAL)
                tool_calls = _StreamedToolCalls()
                try:
                    async with self.client.stream("POST", _CHAT_COMPLETIONS_PATH, json=request) as response:
                        await self._raise_for_status(response)
                        async for line in response.aiter_lines():
                            chunk = self._parse_sse_line(line)
                            if chunk is not None:
                                yield self._parse_chunk(chunk, tool_calls)
                    if remaining := tool_calls.flush_all():
                        yield ChatResponseUpdate(contents=remaining, role="assistant")
                except ChatClientException:
                    raise
                except Exception as ex:
                    raise ChatClientException(
                        f"Mistral streaming chat request failed: {ex}",
                        inner_exception=ex,
                    ) from ex

            return self._build_response_stream(_stream(), response_format=options.get("response_format"))

        async def _get_response() -> ChatResponse:
            validated = await self._validate_options(options)
            request = self._prepare_request(messages, validated, **kwargs)
            mark_feature_used(FeatureIndex.MISTRAL)
            try:
                response = await self.client.post(_CHAT_COMPLETIONS_PATH, json=request)
                await self._raise_for_status(response)
            except ChatClientException:
                raise
            except Exception as ex:
                raise ChatClientException(f"Mistral chat request failed: {ex}", inner_exception=ex) from ex
            try:
                raw_payload = response.json()
                if not isinstance(raw_payload, Mapping):
                    raise ChatClientInvalidResponseException("Mistral chat response must be a JSON object.")
                payload = cast("Mapping[str, Any]", raw_payload)
                return self._parse_response(payload, response_format=validated.get("response_format"))
            except ChatClientException:
                raise
            except Exception as ex:
                raise ChatClientInvalidResponseException(
                    f"Mistral chat response was invalid: {ex}",
                    inner_exception=ex,
                ) from ex

        return _get_response()

    @staticmethod
    async def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        body = (await response.aread()).decode("utf-8", errors="replace")
        message = f"Mistral chat request failed with status {response.status_code}: {body[:2000]}"
        if response.status_code in (401, 403):
            raise ChatClientInvalidAuthException(message)
        if response.status_code < 500:
            raise ChatClientInvalidRequestException(message)
        raise ChatClientException(message)

    @staticmethod
    def _parse_sse_line(line: str) -> dict[str, Any] | None:
        """Parse one server-sent-events line into a completion chunk, or None to skip."""
        line = line.strip()
        if not line.startswith(_SSE_DATA_PREFIX):
            return None
        data = line[len(_SSE_DATA_PREFIX) :].strip()
        if not data or data == _SSE_DONE:
            return None
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as ex:
            raise ChatClientInvalidResponseException(
                "Mistral streaming chat response contained malformed SSE data.",
                inner_exception=ex,
            ) from ex
        if not isinstance(parsed, dict):
            raise ChatClientInvalidResponseException("Mistral streaming chat SSE data must be a JSON object.")
        return cast("dict[str, Any]", parsed)

    # region Request preparation

    def _prepare_request(
        self, messages: Sequence[Message], options: Mapping[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Build the JSON body for a Mistral chat-completion request.

        Args:
            messages: The conversation history as framework Message objects.
            options: Validated and normalized chat options.
            kwargs: Additional keyword arguments merged into the request body.

        Returns:
            The request body for ``POST /v1/chat/completions``.

        Raises:
            ValueError: If no model is set on the options or the client instance.
        """
        model = options.get("model") or self.model
        if not model:
            raise ValueError(
                "Mistral model is required. Set via model parameter or MISTRAL_CHAT_MODEL environment variable."
            )

        if instructions := options.get("instructions"):
            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")

        request: dict[str, Any] = {
            "model": model,
            "messages": self._prepare_mistral_messages(messages),
        }

        for key, value in options.items():
            if key in _OPTION_EXCLUDE_KEYS or value is None:
                continue
            request[_OPTION_TRANSLATIONS.get(key, key)] = value

        if tools := self._prepare_tools(options.get("tools")):
            request["tools"] = tools
        if (tool_choice := self._prepare_tool_choice(options.get("tool_choice"))) is not None:
            request["tool_choice"] = tool_choice
        if (response_format := self._prepare_response_format(options.get("response_format"))) is not None:
            request["response_format"] = response_format

        request.update(kwargs)
        return request

    def _prepare_mistral_messages(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        mistral_messages: list[dict[str, Any]] = []
        for message in messages:
            match message.role:
                case "system":
                    if message.text:
                        mistral_messages.append({"role": "system", "content": message.text})
                case "user":
                    mistral_messages.append(self._format_user_message(message))
                case "assistant":
                    mistral_messages.append(self._format_assistant_message(message))
                case "tool":
                    mistral_messages.extend(self._format_tool_messages(message))
                case _:
                    logger.debug("Skipping unsupported message role for Mistral: %s", message.role)
        return mistral_messages

    def _format_user_message(self, message: Message) -> dict[str, Any]:
        chunks: list[dict[str, Any]] = []
        text_only = True
        for content in message.contents:
            match content.type:
                case "text":
                    chunks.append({"type": "text", "text": content.text or ""})
                case "data" | "uri":
                    chunk = self._convert_data_or_uri_content(content)
                    if chunk is not None:
                        chunks.append(chunk)
                        text_only = False
                case _:
                    logger.debug("Skipping unsupported user content type for Mistral: %s", content.type)

        if text_only:
            return {"role": "user", "content": message.text}
        return {"role": "user", "content": chunks}

    def _convert_data_or_uri_content(self, content: Content) -> dict[str, Any] | None:
        """Convert a ``data`` or ``uri`` Content to a Mistral content chunk.

        Images become ``image_url`` chunks (data URIs are passed through as-is).
        PDF documents referenced by external URI become ``document_url`` chunks.
        """
        uri = content.uri
        if not uri:
            logger.warning("Skipping %s content for Mistral: missing uri", content.type)
            return None

        if content.has_top_level_media_type("image"):
            return {"type": "image_url", "image_url": uri}

        if content.type == "uri" and content.media_type == "application/pdf":
            return {"type": "document_url", "document_url": uri}

        logger.warning(
            "Skipping unsupported %s content for Mistral: media_type=%s",
            content.type,
            content.media_type,
        )
        return None

    def _format_assistant_message(self, message: Message) -> dict[str, Any]:
        tool_calls: list[dict[str, Any]] = []
        for content in message.contents:
            if content.type == "function_call":
                arguments = content.arguments if isinstance(content.arguments, (str, Mapping)) else "{}"
                if isinstance(arguments, Mapping):
                    arguments = dict(arguments)
                tool_calls.append(
                    {
                        "id": _sanitize_tool_call_id(content.call_id or ""),
                        "type": "function",
                        "function": {"name": content.name or "", "arguments": arguments},
                    }
                )
        formatted: dict[str, Any] = {"role": "assistant", "content": message.text or None}
        if tool_calls:
            formatted["tool_calls"] = tool_calls
        return formatted

    def _format_tool_messages(self, message: Message) -> list[dict[str, Any]]:
        tool_messages: list[dict[str, Any]] = []
        for content in message.contents:
            if content.type != "function_result":
                continue
            if content.items:
                text_parts = [c.text or "" for c in content.items if c.type == "text"]
                if any(c.type in ("data", "uri") for c in content.items):
                    logger.warning(
                        "Mistral does not support rich content (images, audio) in tool results. "
                        "Rich content items will be omitted."
                    )
                result_text = "\n".join(text_parts)
            else:
                result_text = self._result_to_text(content.result)
            tool_message: dict[str, Any] = {
                "role": "tool",
                "content": result_text,
                "tool_call_id": _sanitize_tool_call_id(content.call_id or ""),
            }
            if name := getattr(content, "name", None):
                tool_message["name"] = name
            tool_messages.append(tool_message)
        return tool_messages

    @staticmethod
    def _result_to_text(result: Any) -> str:
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result)
        except (TypeError, ValueError):
            return str(result)

    def _prepare_tools(self, tools: Sequence[Any] | None) -> list[Any] | None:
        """Translate the framework tool list into Mistral API tool definitions.

        ``FunctionTool`` instances are translated to Mistral function definitions; plain
        mappings are passed through unchanged.
        """
        if not tools:
            return None
        prepared: list[Any] = []
        for tool in tools:
            if isinstance(tool, FunctionTool):
                prepared.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": tool.parameters(),
                        },
                    }
                )
            else:
                prepared.append(tool)
        return prepared or None

    def _prepare_tool_choice(self, tool_choice: Any) -> Any | None:
        """Build the Mistral ``tool_choice`` value from the framework ``tool_choice`` option."""
        tool_mode = validate_tool_mode(tool_choice)
        if not tool_mode:
            return None

        match tool_mode.get("mode"):
            case "auto":
                if "allowed_tools" in tool_mode:
                    logger.warning("Mistral does not support restricting auto tool choice to specific tools.")
                return "auto"
            case "none":
                return "none"
            case "required":
                if name := tool_mode.get("required_function_name"):
                    return {"type": "function", "function": {"name": name}}
                return "required"
            case unknown_mode:
                logger.warning("Unsupported tool_choice mode for Mistral: %s", unknown_mode)
                return None

    def _prepare_response_format(self, response_format: Any) -> dict[str, Any] | None:
        """Build a Mistral ``response_format`` object from the framework option.

        Supports Pydantic model types, raw JSON schema mappings, response-format envelopes
        (``{"type": "json_object"}`` / ``{"type": "json_schema", "json_schema": {...}}``),
        and the string ``"json"``.
        """
        if response_format is None:
            return None

        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": response_format.__name__,
                    "schema": response_format.model_json_schema(),
                    "strict": True,
                },
            }

        if isinstance(response_format, str):
            if response_format in ("json", "json_object"):
                return {"type": "json_object"}
            logger.warning("Unsupported response_format string for Mistral: %s", response_format)
            return None

        if isinstance(response_format, Mapping):
            mapping: dict[str, Any] = dict(cast("Mapping[str, Any]", response_format))
            format_type = mapping.get("type")
            if format_type == "json_object":
                return {"type": "json_object"}
            if format_type == "json_schema":
                json_schema: dict[str, Any] = dict(mapping.get("json_schema") or {})
                prepared_schema: dict[str, Any] = {
                    "name": json_schema.get("name", "response"),
                    "schema": json_schema.get("schema") or json_schema.get("schema_definition") or {},
                }
                if (strict := json_schema.get("strict")) is not None:
                    prepared_schema["strict"] = strict
                return {"type": "json_schema", "json_schema": prepared_schema}
            # A raw JSON schema mapping
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": str(mapping.get("title", "response")),
                    "schema": mapping,
                    "strict": True,
                },
            }

        type_name = type(cast(object, response_format)).__name__
        logger.warning("Unsupported response_format for Mistral: %s", type_name)
        return None

    # endregion

    # region Response parsing

    def _parse_response(
        self,
        response: Mapping[str, Any],
        *,
        response_format: Any | None = None,
    ) -> ChatResponse:
        """Convert a Mistral chat-completion response payload to a framework ChatResponse."""
        choices = cast("Sequence[Mapping[str, Any]]", response.get("choices") or ())
        choice: Mapping[str, Any] = choices[0] if choices else {}
        message: Mapping[str, Any] = choice.get("message") or {}
        contents = self._parse_message_contents(message)
        finish_reason: FinishReasonLiteral | None = None
        if reason := choice.get("finish_reason"):
            finish_reason = _FINISH_REASON_MAP.get(str(reason))
        return ChatResponse(
            response_id=response.get("id"),
            messages=[Message(role="assistant", contents=contents, raw_representation=choice or None)],
            usage_details=self._parse_usage(response.get("usage")),
            model=response.get("model") or self.model,
            created_at=self._format_created_at(response.get("created")),
            finish_reason=finish_reason,
            response_format=response_format,
            raw_representation=response,
        )

    def _parse_chunk(self, chunk: Mapping[str, Any], tool_calls: _StreamedToolCalls) -> ChatResponseUpdate:
        """Convert a Mistral streaming completion chunk to a framework ChatResponseUpdate.

        Tool-call fragments are folded into ``tool_calls`` keyed by (choice, index) and
        emitted as complete calls when their choice finishes.
        """
        contents: list[Content] = []
        finish_reason: FinishReasonLiteral | None = None
        choices = cast("Sequence[Mapping[str, Any]]", chunk.get("choices") or ())
        for choice in choices:
            choice_index = index if isinstance(index := choice.get("index"), int) else 0
            delta: Mapping[str, Any] = choice.get("delta") or {}
            contents.extend(self._parse_content_chunks(delta))
            for fragment in cast("Sequence[Mapping[str, Any]]", delta.get("tool_calls") or ()):
                contents.extend(tool_calls.add(choice_index, fragment))
            if reason := choice.get("finish_reason"):
                contents.extend(tool_calls.flush_choice(choice_index))
                if finish_reason is None:
                    finish_reason = _FINISH_REASON_MAP.get(str(reason))
        if usage := self._parse_usage(chunk.get("usage")):
            contents.append(Content.from_usage(usage_details=usage, raw_representation=chunk))
        return ChatResponseUpdate(
            contents=contents,
            role="assistant",
            response_id=chunk.get("id"),
            model=chunk.get("model"),
            created_at=self._format_created_at(chunk.get("created")),
            finish_reason=finish_reason,
            raw_representation=chunk,
        )

    def _parse_message_contents(self, message: Mapping[str, Any]) -> list[Content]:
        contents = self._parse_content_chunks(message)
        tool_calls = cast("Sequence[Mapping[str, Any]]", message.get("tool_calls") or ())
        contents.extend(_function_call_content(tool_call) for tool_call in tool_calls)
        return contents

    def _parse_content_chunks(self, message: Mapping[str, Any]) -> list[Content]:
        contents: list[Content] = []
        content = message.get("content")
        if isinstance(content, str):
            if content:
                contents.append(Content.from_text(text=content))
        elif content:
            for chunk in cast("Sequence[Mapping[str, Any]]", content):
                chunk_type = chunk.get("type")
                if chunk_type == "text":
                    if text := chunk.get("text"):
                        contents.append(Content.from_text(text=text, raw_representation=chunk))
                elif chunk_type == "thinking":
                    if reasoning := self._thinking_to_text(chunk):
                        contents.append(Content.from_text_reasoning(text=reasoning, raw_representation=chunk))
                else:
                    logger.debug("Skipping unsupported response chunk from Mistral: %s", chunk_type)
        return contents

    @staticmethod
    def _format_created_at(created: Any) -> str | None:
        if not isinstance(created, (int, float)):
            return None
        return datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def _thinking_to_text(chunk: Mapping[str, Any]) -> str:
        thinking = chunk.get("thinking")
        if isinstance(thinking, str):
            return thinking
        if isinstance(thinking, Sequence):
            return "".join(
                part.get("text") or ""
                for part in cast("Sequence[Mapping[str, Any]]", thinking)
                if isinstance(part, Mapping)
            )
        return ""

    def _parse_usage(self, usage: Mapping[str, Any] | None) -> UsageDetails | None:
        if not usage:
            return None
        details: UsageDetails = {}
        if (value := usage.get("prompt_tokens")) is not None:
            details["input_token_count"] = value
        if (value := usage.get("completion_tokens")) is not None:
            details["output_token_count"] = value
        if (value := usage.get("total_tokens")) is not None:
            details["total_token_count"] = value
        return details or None

    # endregion


class MistralChatClient(
    FunctionInvocationLayer[MistralChatOptionsT],
    ChatMiddlewareLayer[MistralChatOptionsT],
    ChatTelemetryLayer[MistralChatOptionsT],
    RawMistralChatClient[MistralChatOptionsT],
    Generic[MistralChatOptionsT],
):
    """Mistral AI chat client with function invocation, middleware, and telemetry support.

    This is the recommended client for most use cases. It builds on ``RawMistralChatClient``
    and adds:

    - **Function invocation**: automatically calls ``FunctionTool`` implementations and feeds
      results back to the model until it produces a final text response.
    - **Middleware**: a composable chain for cross-cutting concerns (logging, retries, etc.).
    - **Telemetry**: OpenTelemetry traces and metrics emitted for every request.

    Use ``RawMistralChatClient`` instead when you need full control over the request pipeline
    and want to opt out of one or more of these layers.

    Examples:
        .. code-block:: python

            from agent_framework_mistral import MistralChatClient

            # Using environment variables
            # Set MISTRAL_API_KEY=your-key
            # Set MISTRAL_CHAT_MODEL=mistral-large-latest
            client = MistralChatClient()

            # Or passing parameters directly
            client = MistralChatClient(
                model="mistral-large-latest",
                api_key="your-api-key",
            )

            response = await client.get_response("Hello!")
            print(response.text)
            await client.close()
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        server_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Create a Mistral AI chat client.

        Keyword Args:
            model: The Mistral chat model to use (e.g. "mistral-large-latest").
                Can also be set via environment variable ``MISTRAL_CHAT_MODEL``.
            api_key: Mistral API key. Defaults to ``MISTRAL_API_KEY`` environment variable.
            server_url: Optional server URL override. Defaults to ``MISTRAL_SERVER_URL``
                environment variable, or the Mistral default.
            client: Optional pre-configured ``httpx.AsyncClient``. When provided, api_key is
                not required and the client is expected to carry its own auth headers and
                base URL.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional middleware chain applied to every call.
            function_invocation_configuration: Optional configuration for the function invocation loop.
            env_file_path: Path to ``.env`` file for settings.
            env_file_encoding: Encoding for ``.env`` file.
        """
        super().__init__(
            model=model,
            api_key=api_key,
            server_url=server_url,
            client=client,
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
