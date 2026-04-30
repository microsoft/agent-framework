# Copyright (c) Microsoft. All rights reserved.

"""Executor for the ``HttpRequestAction`` declarative action.

Mirrors the .NET ``HttpRequestExecutor``: dispatches an HTTP request through the
configured :class:`HttpRequestHandler`, parses the response body, and assigns
the parsed body and response headers to the declared state paths.

Security note: response bodies can echo secrets and may be very large. Diagnostic
messages produced for non-2xx responses truncate the body to 256 characters and
collapse CR/LF/TAB to spaces (parity with .NET ``FormatBodyForDiagnostics``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

import httpx
from agent_framework import (
    Message,
    WorkflowContext,
    handler,
)

from ._declarative_base import (
    ActionComplete,
    DeclarativeActionExecutor,
    DeclarativeWorkflowState,
)
from ._errors import DeclarativeActionError
from ._http_handler import HttpRequestHandler, HttpRequestInfo, HttpRequestResult

__all__ = [
    "HTTP_ACTION_EXECUTORS",
    "HttpRequestActionExecutor",
]

logger = logging.getLogger(__name__)

_MAX_BODY_DIAGNOSTIC_LENGTH = 256
_BODY_TRUNCATION_SUFFIX = " \u2026 [truncated]"


# Body discriminator aliases. Long forms match the .NET object-model type
# names so YAML produced by .NET round-trips. Short forms are the .NET YAML
# convention used in test fixtures.
_BODY_KIND_JSON = {"json", "JsonRequestContent"}
_BODY_KIND_RAW = {"raw", "RawRequestContent"}
_BODY_KIND_NONE = {"none", "NoRequestContent"}


def _get_path(action_def: Mapping[str, Any], key: str) -> str | None:
    """Extract a state path from ``response``/``responseHeaders`` field.

    Supports two YAML shapes (matches .NET serialization round-trips):

    - ``response: Local.MyVar`` (plain string).
    - ``response: { path: Local.MyVar }`` (object form).
    """
    value = action_def.get(key)
    if isinstance(value, str):
        return value or None
    if isinstance(value, Mapping):
        path = value.get("path")
        return path if isinstance(path, str) and path else None
    return None


def _format_body_for_diagnostics(body: str | None) -> str:
    """Truncate and sanitise a response body for inclusion in error messages.

    Mirrors the .NET ``FormatBodyForDiagnostics`` helper:

    - Empty/None -> empty string.
    - Replaces CR/LF/TAB with spaces.
    - Truncates to 256 chars with a unicode-ellipsis ``[truncated]`` suffix.
    """
    if not body:
        return ""

    truncated = len(body) > _MAX_BODY_DIAGNOSTIC_LENGTH
    head = body[:_MAX_BODY_DIAGNOSTIC_LENGTH] if truncated else body
    sanitized = head.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return sanitized + _BODY_TRUNCATION_SUFFIX if truncated else sanitized


def _parse_response_body(body: str | None) -> Any:
    """Parse an HTTP response body the same way the .NET executor does.

    JSON-first: if the body parses as JSON, the parsed value is returned. Other
    bodies are returned as the raw string. Empty/None bodies return ``None``.
    """
    if body is None or body == "":
        return None
    try:
        return json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return body


def _format_query_value(value: Any) -> str | None:
    """Format a query-parameter value for URL inclusion.

    Mirrors .NET ``FormatQueryValue``: ``None`` is dropped, ``bool`` becomes
    lower-case ``"true"``/``"false"``, numerics use invariant ``str()``, and
    other values fall through to ``str()``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return str(value)


def _get_messages_path(state: DeclarativeWorkflowState, conversation_id_expr: str | None) -> str | None:
    """Mirror ``InvokeAzureAgentExecutor._get_conversation_messages_path`` semantics.

    Returns a single state path (no double-mirroring): ``Conversation.messages``
    when no conversation id is provided, otherwise
    ``System.conversations.{evaluated_id}.messages``. Returns ``None`` if the
    expression evaluates to an empty string (matches .NET ``GetConversationId``
    behaviour where empty becomes ``null`` and the response is not appended).
    """
    if not conversation_id_expr:
        return None
    evaluated = state.eval_if_expression(conversation_id_expr)
    if evaluated is None or (isinstance(evaluated, str) and not evaluated):
        return None
    return f"System.conversations.{evaluated}.messages"


class HttpRequestActionExecutor(DeclarativeActionExecutor):
    """Executor for the ``HttpRequestAction`` declarative action.

    Dispatches through the supplied :class:`HttpRequestHandler` and:

    - Parses the response body (JSON-first, raw string fall-back).
    - Assigns the parsed body to ``response`` path (if configured).
    - Folds multi-value response headers (comma-joined) and assigns them to
      ``responseHeaders`` path (if configured).
    - On 2xx with non-empty body and a configured ``conversationId``, appends
      an Assistant :class:`agent_framework.Message` to
      ``System.conversations.{id}.messages``.
    - On non-2xx, still publishes ``responseHeaders`` (diagnostic) and raises
      :class:`DeclarativeActionError` with a status-coded message containing a
      truncated/sanitised body preview.

    Transport errors (``httpx.TimeoutException``, ``TimeoutError``,
    ``httpx.HTTPError``) become :class:`DeclarativeActionError`. ``CancelledError``
    is intentionally NOT caught so that workflow cancellation propagates.
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        *,
        id: str | None = None,
        http_request_handler: HttpRequestHandler,
    ) -> None:
        """Create an HTTP request action executor.

        Args:
            action_def: Parsed ``HttpRequestAction`` YAML dict.
            id: Optional executor id (defaults to action id or generated).
            http_request_handler: Handler used to dispatch HTTP requests.
                Required: the builder enforces presence at workflow-build time.
        """
        super().__init__(action_def, id=id)
        self._http_request_handler = http_request_handler

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Execute the HTTP request action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        method = self._get_method(state)
        url = self._get_url(state)
        headers = self._get_headers(state)
        query_parameters = self._get_query_parameters(state)
        body, body_content_type = self._get_body(state)
        timeout_ms = self._get_timeout_ms(state)
        conversation_id_expr = self._action_def.get("conversationId")
        connection_name = self._get_connection_name(state)

        info = HttpRequestInfo(
            method=method,
            url=url,
            headers=headers or {},
            query_parameters=query_parameters or {},
            body=body,
            body_content_type=body_content_type,
            timeout_ms=timeout_ms,
            connection_name=connection_name,
        )

        try:
            result = await self._http_request_handler.send(info)
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise DeclarativeActionError(f"HTTP request to '{url}' timed out.") from exc
        except DeclarativeActionError:
            raise
        except httpx.HTTPError as exc:
            raise DeclarativeActionError(
                f"HTTP request to '{url}' failed: {type(exc).__name__}"
            ) from exc
        except Exception as exc:
            # Custom HttpRequestHandler implementations may raise arbitrary
            # exception types. Wrap them in DeclarativeActionError so workflow
            # error handling stays uniform regardless of transport. Note that
            # ``asyncio.CancelledError`` is a ``BaseException`` (not
            # ``Exception``) and so still propagates unmodified, preserving
            # workflow-cancellation semantics.
            raise DeclarativeActionError(
                f"HTTP request to '{url}' failed: {type(exc).__name__}"
            ) from exc

        if result.is_success_status_code:
            self._assign_response(state, result)
            self._assign_response_headers(state, result)
            self._append_response_to_conversation(state, conversation_id_expr, result.body)
            await ctx.send_message(ActionComplete())
            return

        # Non-success path: still publish headers diagnostically, then raise.
        self._assign_response_headers(state, result)
        body_preview = _format_body_for_diagnostics(result.body)
        if body_preview:
            message = (
                f"HTTP request to '{url}' failed with status code {result.status_code}. "
                f"Body: '{body_preview}'"
            )
        else:
            message = f"HTTP request to '{url}' failed with status code {result.status_code}."
        raise DeclarativeActionError(message)

    # ----- Field resolution ----------------------------------------------------

    def _get_method(self, state: DeclarativeWorkflowState) -> str:
        method = self._action_def.get("method")
        evaluated = state.eval_if_expression(method) if method is not None else None
        if not evaluated:
            return "GET"
        return str(evaluated).upper()

    def _get_url(self, state: DeclarativeWorkflowState) -> str:
        raw = self._action_def.get("url")
        if raw is None:
            raise ValueError("HttpRequestAction requires a 'url' field.")
        evaluated = state.eval_if_expression(raw)
        if not isinstance(evaluated, str) or not evaluated:
            raise ValueError("HttpRequestAction 'url' evaluated to an empty value.")
        return evaluated

    def _get_headers(self, state: DeclarativeWorkflowState) -> dict[str, str] | None:
        raw_headers = self._action_def.get("headers")
        if not isinstance(raw_headers, Mapping) or not raw_headers:
            return None
        result: dict[str, str] = {}
        for key, value in raw_headers.items():
            if not isinstance(key, str) or not key:
                continue
            evaluated = state.eval_if_expression(value)
            if evaluated is None:
                continue
            text = str(evaluated)
            if not text:
                continue
            result[key] = text
        return result or None

    def _get_query_parameters(self, state: DeclarativeWorkflowState) -> dict[str, str] | None:
        raw_params = self._action_def.get("queryParameters")
        if not isinstance(raw_params, Mapping) or not raw_params:
            return None
        result: dict[str, str] = {}
        for key, value in raw_params.items():
            if not isinstance(key, str) or not key or value is None:
                continue
            evaluated = state.eval_if_expression(value)
            formatted = _format_query_value(evaluated)
            if formatted is not None:
                result[key] = formatted
        return result or None

    def _get_body(self, state: DeclarativeWorkflowState) -> tuple[str | None, str | None]:
        raw_body = self._action_def.get("body")
        if raw_body is None:
            return None, None
        if not isinstance(raw_body, Mapping):
            raise ValueError(
                "HttpRequestAction 'body' must be a mapping with a 'kind' field "
                "(json, raw) or omitted entirely."
            )

        kind_value = raw_body.get("kind") or raw_body.get("$kind")
        if kind_value is None:
            raise ValueError(
                "HttpRequestAction 'body' is missing 'kind'. Use 'json', 'raw', "
                "or omit 'body' for no request body."
            )
        if not isinstance(kind_value, str):
            raise ValueError(
                f"HttpRequestAction 'body.kind' must be a string, got {type(kind_value).__name__}."
            )

        if kind_value in _BODY_KIND_NONE:
            return None, None

        if kind_value in _BODY_KIND_JSON:
            content_expr = raw_body.get("content")
            if content_expr is None:
                return None, None
            evaluated = state.eval_if_expression(content_expr)
            try:
                body_text = json.dumps(evaluated, default=str)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"HttpRequestAction 'body.content' could not be serialised as JSON: {exc}"
                ) from exc
            return body_text, "application/json"

        if kind_value in _BODY_KIND_RAW:
            content_expr = raw_body.get("content")
            content_type_expr = raw_body.get("contentType")
            content: str | None = None
            if content_expr is not None:
                evaluated = state.eval_if_expression(content_expr)
                content = None if evaluated is None else str(evaluated)
            content_type: str | None = None
            if content_type_expr is not None:
                ct_eval = state.eval_if_expression(content_type_expr)
                ct_text = None if ct_eval is None else str(ct_eval)
                content_type = ct_text or None
            # Match .NET RawRequestContent semantics: when a raw body is sent
            # without an explicit content type, default to text/plain so the
            # request is interpretable by servers.
            if content is not None and not content_type:
                content_type = "text/plain"
            return content, content_type

        raise ValueError(
            f"HttpRequestAction 'body.kind' has unsupported value '{kind_value}'. "
            "Expected one of: json, raw, JsonRequestContent, RawRequestContent, "
            "NoRequestContent."
        )

    def _get_timeout_ms(self, state: DeclarativeWorkflowState) -> int | None:
        raw = self._action_def.get("requestTimeoutInMilliseconds")
        if raw is None:
            return None
        evaluated = state.eval_if_expression(raw)
        if evaluated is None:
            return None
        try:
            value = int(evaluated)
        except (TypeError, ValueError):
            logger.debug(
                "HttpRequestAction: ignoring non-numeric requestTimeoutInMilliseconds=%r",
                evaluated,
            )
            return None
        return value if value > 0 else None

    def _get_connection_name(self, state: DeclarativeWorkflowState) -> str | None:
        connection = self._action_def.get("connection")
        if not isinstance(connection, Mapping):
            return None
        name_expr = connection.get("name")
        if name_expr is None:
            return None
        evaluated = state.eval_if_expression(name_expr)
        if evaluated is None:
            return None
        text = str(evaluated)
        return text or None

    # ----- Result handling -----------------------------------------------------

    def _assign_response(self, state: DeclarativeWorkflowState, result: HttpRequestResult) -> None:
        path = _get_path(self._action_def, "response")
        if path is None:
            return
        state.set(path, _parse_response_body(result.body))

    def _assign_response_headers(self, state: DeclarativeWorkflowState, result: HttpRequestResult) -> None:
        path = _get_path(self._action_def, "responseHeaders")
        if path is None:
            return
        if not result.headers:
            state.set(path, None)
            return
        # Fold multi-value headers with commas (standard HTTP folding) only at
        # assignment time. The raw multi-value dict on HttpRequestResult.headers
        # is left untouched so callers/tests can inspect duplicates.
        flattened: dict[str, str] = {}
        for key, values in result.headers.items():
            flattened[key] = ",".join(values)
        state.set(path, flattened)

    def _append_response_to_conversation(
        self,
        state: DeclarativeWorkflowState,
        conversation_id_expr: str | None,
        body: str,
    ) -> None:
        if not body:
            return
        messages_path = _get_messages_path(state, conversation_id_expr)
        if messages_path is None:
            return
        # Ensure the conversation entry exists so downstream agents can reference it.
        evaluated_id = messages_path.split(".", 2)[2].rsplit(".", 1)[0]
        conversations: dict[str, Any] = state.get("System.conversations") or {}
        if evaluated_id not in conversations:
            conversations[evaluated_id] = {"id": evaluated_id, "messages": []}
            state.set("System.conversations", conversations)
        message = Message(role="assistant", contents=[body])
        state.append(messages_path, message)


HTTP_ACTION_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "HttpRequestAction": HttpRequestActionExecutor,
}
