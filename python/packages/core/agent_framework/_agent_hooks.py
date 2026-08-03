# Copyright (c) Microsoft. All rights reserved.

"""AGENT-HOOKS-0.1 enforcement middleware for Agent Framework (experimental).

This module implements the `agent-hooks <https://github.com/responsibleai/agent-hooks>`_
control contract as one coherent feature on the framework's native middleware seams:

- ``agent_startup`` / ``input`` / ``output`` / ``agent_shutdown`` ride the agent seam,
- ``pre_model_call`` / ``post_model_call`` ride the chat seam,
- ``pre_tool_call`` / ``post_tool_call`` ride the function seam.

The single public entry point is :func:`agent_hooks_middleware`, which returns the three
middleware objects as one unit. The implementations are deliberately private: installing
only part of the trio would enforce only part of the control contract. Install exactly
one trio per agent, placed first in the middleware list: middleware listed before the
trio runs outside the enforcement boundary (outer position is outer trust) — e.g. a
function middleware placed before the trio can substitute a tool result that the tool
seam never brackets; the final ``output`` point still guards whatever egresses.

Enforcement semantics (``mode="enforce"``):

- Every interception point is emitted **before** the guarded action runs (pre points) or
  before its result is incorporated (post points). Emission failures inside the SDK
  (interceptor crash/timeout, invalid context) synthesize ``host_error:*`` denies and are
  treated as blocks — the feature never fails open.
- ``transform`` verdicts are written back into the native middleware contexts
  (``messages`` / ``arguments`` / ``result``), so the framework executes exactly the
  value the interceptors approved. Content objects are preserved: rich (non-text)
  message content is projected as content dictionaries, never flattened to text.
- A ``deny`` at ``input``, ``pre_model_call``, ``post_model_call``, or ``output``
  terminates the run: :class:`agent_hooks.InterceptionBlocked` propagates to the caller
  of :meth:`Agent.run` (for streaming runs, it is raised when the stream is consumed).
- A ``deny`` at ``pre_tool_call`` / ``post_tool_call`` blocks the tool call: the tool is
  not executed (or its result is discarded) and a tool-error payload is surfaced to the
  model so the agent loop can continue, per the spec's block-propagation rules. A
  ``host_error:*`` deny at the tool seam additionally halts the run (the enforcement
  layer itself failed, so continuing would be unreliable).
- Framework middleware short-circuits (``MiddlewareTermination``) are guarded: a result
  substituted by another middleware still passes ``output`` / ``post_model_call`` /
  ``post_tool_call`` before it egresses or enters the transcript.
- The agent middleware verifies at run start that its chat and function siblings are
  installed with it (the trio is created together by the factory), results the feature
  cannot project are rejected loudly, and unexpected failures inside the enforcement
  layer itself halt the run instead of degrading into tool errors.

Streaming is supported **fail-closed by buffering**: the model/agent stream is fully
consumed internally, ``post_model_call`` / ``output`` verdicts are applied to the
assembled response, and only then are the (possibly transformed) updates released to the
consumer. No partial content ever egresses ahead of a verdict (spec §12.1/§12.1a
``buffered_output: true`` behaviour).

Session scoping: by default each agent run is one agent-hooks session (fresh emitter and
sequence, ``agent_startup``/``agent_shutdown`` bracket the run). A host that owns a
longer-lived session can pass its own ``emitter`` and ``builder``; the middleware then
emits only the per-run points and the host owns the session boundaries.

The ``agent-hooks-sdk`` dependency is optional: importing this module (and the lazy root
export) works without it, and :func:`agent_hooks_middleware` raises a descriptive
``ModuleNotFoundError`` when the SDK is missing. Install it via
``pip install agent-framework-core[agent-hooks]``.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, NoReturn, TypeVar, cast

from pydantic import BaseModel

from ._feature_stage import ExperimentalFeature, experimental
from ._middleware import (
    AgentContext,
    AgentMiddleware,
    ChatContext,
    ChatMiddleware,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareTermination,
    MiddlewareTypes,
)
from ._types import (
    AgentResponse,
    AgentResponseUpdate,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
)
from .exceptions import MiddlewareException

if TYPE_CHECKING:
    from agent_hooks import (
        AgentContextBuilder,
        ApprovalResolver,
        CompositionConfig,
        EmitOutcome,
        EnforcementMode,
        IdentityProvider,
        InterceptionBlocked,
        InterceptionEmitter,
        InterceptionRecord,
        Interceptor,
    )

_UpdateT = TypeVar("_UpdateT")

_FRAMEWORK_NAME = "agent-framework"
_HOST_ERROR_PREFIX = "host_error:"
_JCS_SHA256 = "jcs-sha256"
_DEFAULT_TIMEOUT = 5.0

_SDK_MISSING_MESSAGE = (
    "agent_hooks_middleware requires the optional `agent-hooks-sdk` package. "
    "Please install `agent-framework-core[agent-hooks]` (or `agent-hooks-sdk`)."
)

_TRIO_REQUIRED_MESSAGE = (
    "agent-hooks {seam} middleware was invoked without an active agent-hooks run. "
    "The middleware returned by agent_hooks_middleware() must be installed together "
    "on an Agent, e.g. Agent(client=..., middleware=agent_hooks_middleware([...]))."
)

_SIBLINGS_REQUIRED_MESSAGE = (
    "agent-hooks agent middleware could not find its chat and function middleware "
    "siblings in this run's effective middleware. The middleware returned by "
    "agent_hooks_middleware() must be installed together on an Agent, e.g. "
    "Agent(client=..., middleware=agent_hooks_middleware([...]))."
)

_FOREIGN_TRIO_MESSAGE = (
    "agent-hooks {seam} middleware found an active agent-hooks run owned by a different "
    "agent_hooks_middleware() trio. Stacking multiple trios on one agent (or splitting "
    "trios across agent- and client-level middleware) is not supported: emissions would "
    "silently bind to the wrong emitter. Install exactly one trio per agent."
)


class _AgentHooksWriteBackError(MiddlewareException):
    """A transform verdict could not be converted back into the native context.

    Raised (and deliberately never caught by this module) so an unappliable transform
    fails the run closed instead of silently proceeding with the untransformed value.
    """


# region Run state


@dataclass
class _RunState:
    """Per-run enforcement state shared by the middleware trio via a ContextVar."""

    emitter: InterceptionEmitter
    builder: AgentContextBuilder
    session_scoped: bool
    config: _AgentHooksConfig
    halted: BaseException | None = None


_RUN_STATE: ContextVar[_RunState | None] = ContextVar("agent_framework_agent_hooks_run_state", default=None)


@dataclass
class _AgentHooksConfig:
    """Configuration shared by one middleware trio (one factory call)."""

    interceptors: tuple[tuple[str | None, Interceptor], ...]
    resolver: ApprovalResolver | None
    mode: EnforcementMode | None
    composition: CompositionConfig | None
    identity_provider: str | IdentityProvider | None
    timeout: float | None
    record_sink: Callable[[InterceptionRecord], None] | None
    emitter: InterceptionEmitter | None
    builder: AgentContextBuilder | None


# endregion

# region Wire projections (framework objects -> AGENT-HOOKS wire JSON)


def _json_safe(value: Any) -> Any:
    """Best-effort projection of an arbitrary Python value into JSON-native values.

    The SDK's own marshalling guard still fails closed on anything this misses
    (``host_error:context_invalid``), so this is a fidelity aid, not a safety gate.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Content):
        return _json_safe(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in cast("Mapping[Any, Any]", value).items()}
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, Sequence):
        return [_json_safe(item) for item in cast("Sequence[Any]", value)]
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump())
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        with contextlib.suppress(Exception):
            return _json_safe(to_dict())
    return str(value)


def _role_str(role: Any) -> str:
    return str(getattr(role, "value", role) or "user")


def _input_role(role: Any) -> str:
    """Map a framework role onto the spec's input role enum (user | system | external)."""
    value = _role_str(role)
    return value if value in ("user", "system") else "external"


def _finish_reason_str(finish_reason: Any) -> str:
    return str(getattr(finish_reason, "value", finish_reason) or "stop")


def _contents_to_wire(contents: Sequence[Content]) -> str | list[dict[str, Any]]:
    """Project message contents faithfully: plain text as a string, rich content as dicts."""
    if len(contents) == 1 and contents[0].type == "text":
        return contents[0].text or ""
    return [cast("dict[str, Any]", _json_safe(content.to_dict())) for content in contents]


def _message_to_wire(message: Message) -> dict[str, Any]:
    return {"role": _role_str(message.role), "content": _contents_to_wire(message.contents)}


def _messages_to_wire(messages: Sequence[Message]) -> list[dict[str, Any]]:
    return [_message_to_wire(message) for message in messages]


def _wire_to_contents(value: Any, *, point: str) -> list[Content]:
    """Decode a transformed wire content value back into framework Content objects."""
    if value is None:
        return []
    if isinstance(value, str):
        return [Content.from_text(value)]
    if isinstance(value, Mapping):
        items: list[Any] = [value]
    elif isinstance(value, Sequence):
        items = list(cast("Sequence[Any]", value))
    else:
        raise _AgentHooksWriteBackError(f"agent-hooks {point} transform produced an unsupported content value type.")
    contents: list[Content] = []
    for item in items:
        if isinstance(item, str):
            contents.append(Content.from_text(item))
            continue
        if isinstance(item, Mapping) and "type" in item:
            try:
                contents.append(Content.from_dict(cast("Mapping[str, Any]", item)))
                continue
            except Exception as exc:
                raise _AgentHooksWriteBackError(
                    f"agent-hooks {point} transform produced an undecodable content item."
                ) from exc
        raise _AgentHooksWriteBackError(f"agent-hooks {point} transform produced an unsupported content item.")
    return contents


def _write_back_message_list(
    originals: Sequence[Message],
    before: Sequence[Mapping[str, Any]],
    after: Any,
    *,
    point: str,
) -> list[Message]:
    """Convert a transformed wire message list back into framework messages.

    Unchanged messages keep their original ``Message`` object (identity, ids, and
    non-projected metadata). Changed messages are mutated in place when the role
    matches (so shared conversation history adopts the transform) and rebuilt
    otherwise. The transformed list is authoritative: added or removed messages are
    reflected as-is.
    """
    if not isinstance(after, list):
        raise _AgentHooksWriteBackError(f"agent-hooks {point} transform must produce a list of messages.")
    result: list[Message] = []
    for index, item in enumerate(cast("list[Any]", after)):
        if not isinstance(item, Mapping) or "content" not in item:
            raise _AgentHooksWriteBackError(f"agent-hooks {point} transform produced a message without role/content.")
        wire_message = cast("Mapping[str, Any]", item)
        role = str(wire_message.get("role") or "user")
        if index < len(before) and dict(wire_message) == dict(before[index]):
            result.append(originals[index])
            continue
        if index < len(originals) and role == str(before[index].get("role")):
            message = originals[index]
            message.contents = _wire_to_contents(wire_message.get("content"), point=point)
            result.append(message)
            continue
        result.append(Message(role, _wire_to_contents(wire_message.get("content"), point=point)))
    return result


def _input_message_to_wire(message: Message) -> dict[str, Any]:
    """Project one input message with the spec's input role mapping."""
    return {"role": _input_role(message.role), "content": _contents_to_wire(message.contents)}


def _input_messages_to_wire(messages: Sequence[Message]) -> list[dict[str, Any]]:
    return [_input_message_to_wire(message) for message in messages]


def _input_to_wire(messages: Sequence[Message]) -> dict[str, Any]:
    """Project run input per the spec's ``input`` payload schema.

    A single plain-text message projects as its content string (so string-matching
    perimeter guards fire); multi-message or rich input projects as a list of
    per-message ``{"role", "content"}`` objects (roles mapped onto the spec's input
    role enum) whose contents are strings when plain.
    """
    if len(messages) == 1:
        return {"content": _contents_to_wire(messages[0].contents), "role": _input_role(messages[0].role)}
    return {"content": _input_messages_to_wire(messages), "role": "user"}


def _looks_like_message_dicts(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    items = cast("list[Any]", value)
    return bool(items) and all(isinstance(item, Mapping) and "content" in item for item in items)


def _apply_input_write_back(messages: list[Message], before: Mapping[str, Any], after: Any) -> None:
    """Write a transformed ``input`` target back into the run's message list."""
    if after is None or after == before:
        return
    if not isinstance(after, Mapping):
        raise _AgentHooksWriteBackError("agent-hooks input transform must produce an input object target.")
    after_map = cast("Mapping[str, Any]", after)
    after_role = after_map.get("role")
    if after_role != before.get("role"):
        # The role field is per-message only for single-message input; for multi-message
        # input the top-level role is synthetic and a transform against it is ambiguous.
        if len(messages) != 1 or not isinstance(after_role, str):
            raise _AgentHooksWriteBackError(
                "agent-hooks input transform changed the input role in a way that cannot be written back."
            )
        messages[0].role = after_role
    after_content = after_map.get("content")
    if after_content == before.get("content"):
        return
    if len(messages) == 1 and not _looks_like_message_dicts(after_content):
        messages[0].contents = _wire_to_contents(after_content, point="input")
        return
    before_list = _input_messages_to_wire(messages)
    messages[:] = _write_back_message_list(list(messages), before_list, after_content, point="input")


def _arguments_to_wire(arguments: Any) -> dict[str, Any]:
    """Project tool-call arguments as the spec's ``args`` object."""
    if arguments is None:
        return {}
    if isinstance(arguments, BaseModel):
        return {str(key): _json_safe(item) for key, item in arguments.model_dump().items()}
    if isinstance(arguments, Mapping):
        return {str(key): _json_safe(item) for key, item in cast("Mapping[Any, Any]", arguments).items()}
    if isinstance(arguments, str):
        with contextlib.suppress(ValueError):
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return cast("dict[str, Any]", parsed)
        return {"raw_arguments": arguments}
    return {"raw_arguments": str(arguments)}


def _tool_calls_to_wire(messages: Sequence[Message]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for message in messages:
        for content in message.contents:
            if content.type == "function_call" and not content.informational_only:
                calls.append({
                    "id": str(content.call_id or ""),
                    "name": str(content.name or ""),
                    "args": _arguments_to_wire(content.arguments),
                })
    return calls


def _response_content_to_wire(messages: Sequence[Message]) -> str | list[dict[str, Any]] | None:
    """Project a model response's non-tool-call content (tool calls ride ``tool_calls``)."""
    parts: list[dict[str, Any]] = []
    for message in messages:
        visible = [content for content in message.contents if content.type != "function_call"]
        if not visible:
            continue
        parts.append({"role": _role_str(message.role), "content": _contents_to_wire(visible)})
    if not parts:
        return None
    if len(parts) == 1 and isinstance(parts[0]["content"], str):
        return parts[0]["content"]
    return parts


def _usage_to_wire(usage_details: Any) -> dict[str, int] | None:
    if not isinstance(usage_details, Mapping):
        return None
    usage = {
        str(key): item
        for key, item in cast("Mapping[Any, Any]", usage_details).items()
        if isinstance(item, int) and not isinstance(item, bool)
    }
    return usage or None


def _tool_result_to_wire(value: Any) -> Any:
    """Project a tool result faithfully, unwrapping framework ``Content`` containers.

    Text content projects as its text, ``function_result`` content projects as its
    canonical ``result`` value, and any other content projects as its full content
    dictionary — never as ``str(Content)`` reprs.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list) and len(cast("list[Any]", value)) == 1 and isinstance(value[0], Content):
        # The canonical single-content result (e.g. the default parser's wrapped text)
        # projects as the content's value itself, matching what the model sees.
        return _tool_result_to_wire(value[0])
    if isinstance(value, Content):
        if value.type == "text":
            return value.text or ""
        if value.type == "function_result":
            if value.result is not None:
                return _tool_result_to_wire(value.result)
            if value.items is not None:
                return [_tool_result_to_wire(item) for item in value.items]
            return None
        return _json_safe(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _tool_result_to_wire(item) for key, item in cast("Mapping[Any, Any]", value).items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_tool_result_to_wire(item) for item in cast("Sequence[Any]", value)]
    return _json_safe(value)


def _apply_tool_result_write_back(original: Any, after: Any) -> Any:
    """Convert a transformed ``post_tool_call`` value back into the native result shape.

    When the original result is the framework's canonical ``list[Content]`` and the
    transformed value is shape-compatible, the Content wrappers are preserved;
    otherwise the transformed wire value becomes the result as-is (the function
    invocation layer serializes arbitrary JSON-native results faithfully).
    """
    if (
        isinstance(original, list)
        and original
        and all(isinstance(item, Content) for item in cast("list[Any]", original))
    ):
        original_contents = cast("list[Content]", original)
        if isinstance(after, str) and len(original_contents) == 1 and original_contents[0].type == "text":
            return [Content.from_text(after)]
        after_items = cast("list[Any]", after) if isinstance(after, list) else None
        if after_items is not None and len(after_items) == len(original_contents):
            rebuilt: list[Content] = []
            for content, item in zip(original_contents, after_items):
                if _tool_result_to_wire(content) == item:
                    rebuilt.append(content)
                elif content.type == "text" and isinstance(item, str):
                    rebuilt.append(Content.from_text(item))
                else:
                    return after_items
            return rebuilt
    return cast(Any, after)


def _agent_output_to_wire(response: AgentResponse) -> str | list[dict[str, Any]]:
    """Project the run output: a single plain-text message as a string, else per-message objects."""
    parts = _messages_to_wire(response.messages)
    if len(parts) == 1 and isinstance(parts[0]["content"], str):
        return parts[0]["content"]
    return parts


def _apply_output_write_back(response: AgentResponse, before_content: Any, after: Any) -> bool:
    """Write a transformed ``output`` target back into the agent response. Returns whether it changed."""
    if after is None:
        return False
    if not isinstance(after, Mapping):
        raise _AgentHooksWriteBackError("agent-hooks output transform must produce an output object target.")
    after_content = cast("Mapping[str, Any]", after).get("content")
    if after_content == before_content:
        return False
    originals = list(response.messages)
    if isinstance(after_content, str):
        if len(originals) == 1:
            originals[0].contents = _wire_to_contents(after_content, point="output")
        else:
            response.messages = [Message("assistant", [after_content])]
        return True
    if after_content is None:
        response.messages = []
        return True
    before_list = _messages_to_wire(originals)
    response.messages = _write_back_message_list(originals, before_list, after_content, point="output")
    return True


def _write_back_tool_calls(response: ChatResponse[Any], after_calls: Any) -> bool:
    """Reconcile transformed ``tool_calls`` with the response's function-call contents."""
    if not isinstance(after_calls, list):
        raise _AgentHooksWriteBackError("agent-hooks post_model_call transform must keep tool_calls a list.")
    wire_calls: list[Mapping[str, Any]] = []
    for item in cast("list[Any]", after_calls):
        if not isinstance(item, Mapping) or "id" not in item or "name" not in item:
            raise _AgentHooksWriteBackError(
                "agent-hooks post_model_call transform produced a tool call without id/name."
            )
        wire_calls.append(cast("Mapping[str, Any]", item))
    calls_by_id = {str(call["id"]): call for call in wire_calls}
    consumed: set[str] = set()
    changed = False
    for message in response.messages:
        kept: list[Content] = []
        for content in message.contents:
            if content.type != "function_call" or content.informational_only:
                kept.append(content)
                continue
            wire = calls_by_id.get(str(content.call_id))
            if wire is None:
                changed = True  # the transform dropped this tool call
                continue
            consumed.add(str(content.call_id))
            wire_args = wire.get("args")
            if isinstance(wire_args, Mapping) and _arguments_to_wire(content.arguments) != dict(
                cast("Mapping[str, Any]", wire_args)
            ):
                content.arguments = {str(key): item for key, item in cast("Mapping[Any, Any]", wire_args).items()}
                changed = True
            kept.append(content)
        if len(kept) != len(message.contents):
            message.contents = kept
    added = [call for call in wire_calls if str(call["id"]) not in consumed]
    if added:
        contents = [
            Content.from_function_call(
                str(call["id"]),
                str(call["name"]),
                arguments={str(key): item for key, item in cast("Mapping[Any, Any]", call.get("args") or {}).items()},
            )
            for call in added
        ]
        target = next((m for m in reversed(response.messages) if _role_str(m.role) == "assistant"), None)
        if target is not None:
            target.contents = [*target.contents, *contents]
        else:
            response.messages.append(Message("assistant", contents))
        changed = True
    return changed


def _write_back_response_content(response: ChatResponse[Any], after_content: Any) -> None:
    """Rebuild the response's visible content from a transformed ``response.content`` value."""
    calls = [
        content for message in response.messages for content in message.contents if content.type == "function_call"
    ]
    base: list[Message]
    if after_content is None:
        base = []
    elif isinstance(after_content, str):
        base = [Message("assistant", [after_content])]
    elif isinstance(after_content, list):
        base = []
        for item in cast("list[Any]", after_content):
            if not isinstance(item, Mapping) or "content" not in item:
                raise _AgentHooksWriteBackError(
                    "agent-hooks post_model_call transform produced content without role/content."
                )
            wire_message = cast("Mapping[str, Any]", item)
            base.append(
                Message(
                    str(wire_message.get("role") or "assistant"),
                    _wire_to_contents(wire_message.get("content"), point="post_model_call"),
                )
            )
    else:
        raise _AgentHooksWriteBackError("agent-hooks post_model_call transform produced unsupported content.")
    if calls:
        if base and _role_str(base[-1].role) == "assistant":
            base[-1].contents = [*base[-1].contents, *calls]
        else:
            base.append(Message("assistant", calls))
    response.messages = base


def _apply_response_write_back(response: ChatResponse[Any], before: Mapping[str, Any], after: Any) -> bool:
    """Write a transformed ``post_model_call`` target back into the chat response."""
    if after is None or after == before:
        return False
    if not isinstance(after, Mapping):
        raise _AgentHooksWriteBackError("agent-hooks post_model_call transform must produce a response object.")
    after_map = cast("Mapping[str, Any]", after)
    changed = False
    after_finish = after_map.get("finish_reason")
    if after_finish != before.get("finish_reason"):
        if not isinstance(after_finish, str):
            raise _AgentHooksWriteBackError("agent-hooks post_model_call transform must keep finish_reason a string.")
        response.finish_reason = cast(Any, after_finish)
        changed = True
    after_calls = after_map.get("tool_calls")
    if after_calls != before.get("tool_calls"):
        changed = _write_back_tool_calls(response, after_calls) or changed
    after_content = after_map.get("content")
    if after_content != before.get("content"):
        _write_back_response_content(response, after_content)
        changed = True
    return changed


def _chat_updates_from_response(response: ChatResponse[Any]) -> list[ChatResponseUpdate]:
    """Re-derive stream updates from a (transformed) assembled chat response."""
    updates = [
        ChatResponseUpdate(
            contents=list(message.contents),
            role=cast(Any, message.role),
            author_name=message.author_name,
            message_id=message.message_id,
            response_id=response.response_id,
            model=response.model,
        )
        for message in response.messages
    ]
    if not updates:
        updates = [ChatResponseUpdate(role="assistant", response_id=response.response_id)]
    updates[-1].finish_reason = response.finish_reason
    return updates


def _agent_updates_from_response(response: AgentResponse[Any]) -> list[AgentResponseUpdate]:
    """Re-derive stream updates from a (transformed) assembled agent response."""
    updates = [
        AgentResponseUpdate(
            contents=list(message.contents),
            role=message.role,
            author_name=message.author_name,
            message_id=message.message_id,
            response_id=response.response_id,
        )
        for message in response.messages
    ]
    if not updates:
        updates = [AgentResponseUpdate(role="assistant", response_id=response.response_id)]
    return updates


def _tool_names(context: AgentContext) -> list[str]:
    tools: Any = context.tools if context.tools is not None else getattr(context.agent, "tools", None)
    if tools is None:
        return []
    items: Sequence[Any] = (
        cast("Sequence[Any]", tools) if isinstance(tools, Sequence) and not isinstance(tools, (str, bytes)) else [tools]
    )
    names: list[str] = []
    for item in items:
        name = getattr(item, "name", None) or getattr(item, "__name__", None)
        names.append(str(name) if name else type(item).__name__)
    return names


def _is_host_error(record: InterceptionRecord) -> bool:
    return bool(record.verdict.reason and record.verdict.reason.startswith(_HOST_ERROR_PREFIX))


def _blocked_tool_result(point: str, record: InterceptionRecord) -> dict[str, Any]:
    """Tool-error payload surfaced to the model for a blocked tool call (no target content)."""
    payload: dict[str, Any] = {
        "error": f"Tool call blocked by agent-hooks at {point}.",
        "reason": record.verdict.reason or "deny",
    }
    if record.verdict.message:
        payload["message"] = record.verdict.message
    return payload


def _is_approval_request(result: Any) -> bool:
    """Whether a function result is the framework's approval-request control object."""
    return isinstance(result, Content) and result.type == "function_approval_request"


def _halt_on_enforcement_failure(
    state: _RunState, context: FunctionInvocationContext, exc: BaseException, point: str
) -> NoReturn:
    """Route an unexpected failure inside the enforcement layer through the halt path.

    The function-invocation loop converts arbitrary exceptions raised by function
    middleware into tool-error results and keeps running; for a failure of the
    enforcement layer itself (projection bug, emitter fault) that would fail open —
    the failure would vanish from the audit trail while the run continued. Instead:
    the loop is stopped via ``MiddlewareTermination`` (its only loud escape) and the
    agent middleware re-raises the failure to the caller at the run boundary.
    """
    message = f"agent-hooks {point} enforcement failed: {type(exc).__name__}"
    context.result = {"error": message}
    if isinstance(exc, MiddlewareException):
        failure: BaseException = exc
    else:
        failure = MiddlewareException(message)
        failure.__cause__ = exc
    state.halted = failure
    raise MiddlewareTermination(message) from exc


# eq=False keeps identity semantics (and hashability): the middleware pipeline caches
# compare middleware tuples with ==, and value-equality would let a pipeline cached for
# one trio be reused for a field-equal fresh trio, breaking the identity-based sibling
# verification on the second run.
@dataclass(eq=False)
class _AgentHooksMiddlewareBase:
    """Shared base carrying the trio's config (also enables sibling identity checks)."""

    _config: _AgentHooksConfig

    def _shares_config(self, config: _AgentHooksConfig) -> bool:
        """Whether this middleware was created by the same factory call as ``config``."""
        return self._config is config


class _ReplayAsyncIterator(Generic[_UpdateT]):
    """Async iterator that replays a buffered list of updates."""

    def __init__(self, updates: Sequence[_UpdateT]) -> None:
        self._iterator = iter(updates)

    def __aiter__(self) -> _ReplayAsyncIterator[_UpdateT]:
        return self

    async def __anext__(self) -> _UpdateT:
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration from None


# endregion

# region Middleware implementations (private: the trio is one coherent feature)


class _AgentHooksAgentMiddleware(_AgentHooksMiddlewareBase, AgentMiddleware):
    """Run bracket: ``agent_startup``, ``input``, ``output``, ``agent_shutdown``."""

    def _new_run_state(self, context: AgentContext) -> _RunState:
        config = self._config
        if config.emitter is not None and config.builder is not None:
            return _RunState(emitter=config.emitter, builder=config.builder, session_scoped=True, config=config)
        from agent_hooks import AgentContextBuilder, InterceptionEmitter

        agent = context.agent
        agent_name = getattr(agent, "name", None)
        agent_id = str(getattr(agent, "id", None) or agent_name or "agent")
        builder = AgentContextBuilder(
            agent_id=agent_id,
            framework=_FRAMEWORK_NAME,
            session_id=uuid.uuid4().hex,
            agent_name=str(agent_name) if agent_name else None,
        )
        kwargs: dict[str, Any] = {
            "resolver": config.resolver,
            "timeout": config.timeout,
            "composition": config.composition,
            "identity_provider": config.identity_provider,
        }
        if config.mode is not None:
            kwargs["mode"] = config.mode
        emitter = InterceptionEmitter(**kwargs)
        for name, interceptor in config.interceptors:
            emitter.register(interceptor, name)
        if config.record_sink is not None:
            emitter.set_record_sink(config.record_sink)
        return _RunState(emitter=emitter, builder=builder, session_scoped=False, config=config)

    async def _emit_run_start(self, context: AgentContext, state: _RunState) -> None:
        """Emit ``agent_startup`` (per-run sessions) and ``input``; apply input transforms."""
        if not state.session_scoped:
            await state.emitter.emit(state.builder.agent_startup(tools_registered=_tool_names(context)))
        before = _input_to_wire(context.messages)
        outcome: EmitOutcome = await state.emitter.emit(
            state.builder.input(content=before["content"], role=before["role"])
        )
        _apply_input_write_back(context.messages, before, outcome.target)

    async def _emit_output(self, state: _RunState, response: AgentResponse[Any]) -> bool:
        """Emit ``output`` over the assembled response; apply output transforms."""
        before_content = _agent_output_to_wire(response)
        outcome: EmitOutcome = await state.emitter.emit(state.builder.output(content=before_content))
        return _apply_output_write_back(response, before_content, outcome.target)

    async def _emit_shutdown(self, state: _RunState, reason: str) -> None:
        """Best-effort ``agent_shutdown`` (per-run sessions only; blocks there are record-only)."""
        if state.session_scoped:
            return
        with contextlib.suppress(Exception):
            await state.emitter.emit_unchecked(state.builder.agent_shutdown(reason=reason))

    def _verify_siblings(self, context: AgentContext) -> None:
        """Fail closed unless the chat and function siblings from this trio are installed.

        The trio is created together by the factory, so the siblings are located by
        identity of the shared config. The agent seam sees the combined chat/function
        middleware for the run in ``context.client_kwargs["middleware"]`` (the agent
        layer assembles it there before building the context).
        """
        installed = context.client_kwargs.get("middleware")
        candidates = cast("Sequence[Any]", installed) if isinstance(installed, Sequence) else ()
        has_chat = any(
            isinstance(item, _AgentHooksChatMiddleware) and item._shares_config(self._config) for item in candidates
        )
        has_function = any(
            isinstance(item, _AgentHooksFunctionMiddleware) and item._shares_config(self._config) for item in candidates
        )
        if not (has_chat and has_function):
            raise MiddlewareException(_SIBLINGS_REQUIRED_MESSAGE)

    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        from agent_hooks import InterceptionBlocked

        self._verify_siblings(context)
        state = self._new_run_state(context)
        if context.stream:
            await self._process_streaming(context, call_next, state)
            return

        token = _RUN_STATE.set(state)
        shutdown_reason = "completed"
        try:
            try:
                await self._emit_run_start(context, state)
                termination: MiddlewareTermination | None = None
                try:
                    await call_next()
                except MiddlewareTermination as exc:
                    # A middleware short-circuited the run; any substituted result
                    # still egresses to the caller, so it passes the output point.
                    termination = exc
                if state.halted is not None:
                    raise state.halted
                result = context.result
                if isinstance(result, AgentResponse):
                    await self._emit_output(state, result)
                elif result is not None:
                    raise MiddlewareException(
                        f"agent-hooks cannot guard a run result of type {type(result).__name__}; "
                        "the output interception point was not emitted."
                    )
                if termination is not None:
                    raise termination
            except InterceptionBlocked:
                shutdown_reason = "error"
                context.result = None
                raise
            except asyncio.CancelledError:
                shutdown_reason = "cancelled"
                raise
            except MiddlewareTermination:
                # Deliberate short-circuit: the result (if any) was guarded above.
                raise
            except BaseException:
                shutdown_reason = "error"
                raise
        finally:
            await self._emit_shutdown(state, shutdown_reason)
            _RUN_STATE.reset(token)

    async def _process_streaming(
        self, context: AgentContext, call_next: Callable[[], Awaitable[None]], state: _RunState
    ) -> None:
        """Streaming run setup (executed lazily on the first pull of the outer stream).

        Ownership of the session trail passes to the guarded stream only once it is
        installed as the run result; every earlier exit (pre-run deny, middleware
        exception, unguardable result) still closes the trail with ``agent_shutdown``.
        """
        token = _RUN_STATE.set(state)
        # Pessimistic default: any exit before the guarded stream takes ownership
        # closes the trail as an error; ``None`` means ownership was handed off.
        shutdown_reason: str | None = "error"
        try:
            await self._emit_run_start(context, state)
            termination: MiddlewareTermination | None = None
            try:
                await call_next()
            except MiddlewareTermination as exc:
                termination = exc
            inner = context.result
            if inner is None and termination is not None:
                # Terminated without a result: nothing will egress.
                shutdown_reason = "completed"
                raise termination
            if not isinstance(inner, ResponseStream):
                raise MiddlewareException(
                    "agent-hooks streaming enforcement requires a ResponseStream agent result; "
                    f"got {type(inner).__name__}."
                )
            context.result = cast(
                "ResponseStream[AgentResponseUpdate, AgentResponse[Any]]",
                cast(Any, ResponseStream).from_awaitable(
                    self._guarded_agent_stream(
                        state, cast("ResponseStream[AgentResponseUpdate, AgentResponse[Any]]", inner)
                    )
                ),
            )
            # The guarded stream now owns the shutdown emission.
            shutdown_reason = None
            if termination is not None:
                # A middleware substituted its own stream: it is guarded, and the
                # termination still short-circuits the rest of the pipeline.
                raise termination
        except asyncio.CancelledError:
            shutdown_reason = "cancelled"
            raise
        finally:
            if shutdown_reason is not None:
                await self._emit_shutdown(state, shutdown_reason)
            _RUN_STATE.reset(token)

    async def _guarded_agent_stream(
        self,
        state: _RunState,
        inner: ResponseStream[AgentResponseUpdate, AgentResponse[Any]],
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Consume the run fully, apply the ``output`` verdict, then release buffered updates.

        Fail-closed streamed egress: no update is released to the consumer before the
        ``output`` emission permits, and a transformed output replaces the buffered
        updates entirely.
        """
        from agent_hooks import InterceptionBlocked

        token = _RUN_STATE.set(state)
        shutdown_reason = "completed"
        transformed = False
        final: AgentResponse[Any]
        try:
            try:
                final = await inner.get_final_response()
                if state.halted is not None:
                    raise state.halted
                if not isinstance(final, AgentResponse):
                    raise MiddlewareException(
                        f"agent-hooks cannot guard a streamed run result of type {type(final).__name__}; "
                        "the output interception point was not emitted."
                    )
                transformed = await self._emit_output(state, final)
            except InterceptionBlocked:
                shutdown_reason = "error"
                raise
            except asyncio.CancelledError:
                shutdown_reason = "cancelled"
                raise
            except BaseException:
                shutdown_reason = "error"
                raise
        finally:
            await self._emit_shutdown(state, shutdown_reason)
            _RUN_STATE.reset(token)

        updates = _agent_updates_from_response(final) if transformed else list(inner.updates)

        def _finalize(_: Sequence[AgentResponseUpdate]) -> AgentResponse[Any]:
            return final

        return ResponseStream(_ReplayAsyncIterator(updates), finalizer=_finalize)


class _AgentHooksChatMiddleware(_AgentHooksMiddlewareBase, ChatMiddleware):
    """Model bracket: ``pre_model_call`` and ``post_model_call``."""

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        from agent_hooks import InterceptionBlocked

        state = _RUN_STATE.get()
        if state is None:
            raise MiddlewareException(_TRIO_REQUIRED_MESSAGE.format(seam="chat"))
        if not self._shares_config(state.config):
            # A different trio's agent middleware owns the innermost run state (stacked
            # trios, or a trio split across agent- and client-level middleware): binding
            # to it would silently misroute emissions. Fail closed instead.
            raise MiddlewareException(_FOREIGN_TRIO_MESSAGE.format(seam="chat"))

        options = context.options or {}
        model_id = str(options.get("model") or type(context.client).__name__)
        before = _messages_to_wire(context.messages)
        outcome: EmitOutcome = await state.emitter.emit(
            state.builder.pre_model_call(model_id=model_id, messages=before)
        )
        if outcome.target != before:
            context.messages = _write_back_message_list(
                list(context.messages), before, outcome.target, point="pre_model_call"
            )

        termination: MiddlewareTermination | None = None
        try:
            await call_next()
        except MiddlewareTermination as exc:
            # A chat middleware short-circuited with a substituted result; whatever
            # was substituted still flows into the agent loop, so it is guarded below.
            termination = exc

        result = context.result
        if isinstance(result, ResponseStream):
            context.result = cast(
                "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]",
                cast(Any, ResponseStream).from_awaitable(
                    self._guarded_chat_stream(
                        state, model_id, cast("ResponseStream[ChatResponseUpdate, ChatResponse[Any]]", result)
                    )
                ),
            )
        elif isinstance(result, ChatResponse):
            try:
                await self._emit_post_model_call(state, model_id, result)
            except InterceptionBlocked:
                # §6.1: the denied response must not be incorporated.
                context.result = None
                raise
        elif result is not None:
            raise MiddlewareException(
                f"agent-hooks cannot guard a chat result of type {type(result).__name__}; "
                "the post_model_call interception point was not emitted."
            )
        elif context.stream and termination is None:
            raise MiddlewareException("agent-hooks streaming enforcement requires a ResponseStream chat result.")
        if termination is not None:
            raise termination

    async def _emit_post_model_call(self, state: _RunState, model_id: str, response: ChatResponse[Any]) -> bool:
        """Emit ``post_model_call`` over the assembled response; apply transforms. Returns whether changed."""
        before: dict[str, Any] = {
            "content": _response_content_to_wire(response.messages),
            "tool_calls": _tool_calls_to_wire(response.messages),
            "finish_reason": _finish_reason_str(response.finish_reason),
        }
        outcome: EmitOutcome = await state.emitter.emit(
            state.builder.post_model_call(
                model_id=str(response.model or model_id),
                content=before["content"],
                tool_calls=before["tool_calls"],
                finish_reason=before["finish_reason"],
                usage=_usage_to_wire(response.usage_details),
                request_id=response.response_id,
            )
        )
        return _apply_response_write_back(response, before, outcome.target)

    async def _guarded_chat_stream(
        self,
        state: _RunState,
        model_id: str,
        inner: ResponseStream[ChatResponseUpdate, ChatResponse[Any]],
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Assemble the streamed response, apply the ``post_model_call`` verdict, then replay.

        Spec §12.1: the complete response is assembled before ``post_model_call`` is
        emitted, and nothing (updates or tool calls) is released beforehand. A deny
        raises before any update egresses.
        """
        response = await inner.get_final_response()
        if not isinstance(response, ChatResponse):
            raise MiddlewareException(
                f"agent-hooks cannot guard a streamed chat result of type {type(response).__name__}; "
                "the post_model_call interception point was not emitted."
            )
        changed = await self._emit_post_model_call(state, model_id, response)
        updates = _chat_updates_from_response(response) if changed else list(inner.updates)

        def _finalize(_: Sequence[ChatResponseUpdate]) -> ChatResponse[Any]:
            return response

        return ResponseStream(_ReplayAsyncIterator(updates), finalizer=_finalize)


class _AgentHooksFunctionMiddleware(_AgentHooksMiddlewareBase, FunctionMiddleware):
    """Tool bracket: ``pre_tool_call`` and ``post_tool_call``."""

    def _block(
        self, state: _RunState, context: FunctionInvocationContext, exc: InterceptionBlocked, point: str
    ) -> None:
        """Enforce a tool-seam deny: surface a tool error and, on host errors, halt the run."""
        context.result = _blocked_tool_result(point, exc.result)
        self._maybe_halt(state, exc, point)

    def _maybe_halt(self, state: _RunState, exc: InterceptionBlocked, point: str) -> None:
        record: InterceptionRecord = exc.result
        if _is_host_error(record):
            # The enforcement layer itself failed (interceptor crash/timeout, invalid
            # context): continuing the loop would run unguarded. Halt the run; the
            # agent middleware re-raises the block to the caller.
            state.halted = exc
            raise MiddlewareTermination(
                f"agent-hooks {point} failed closed: {record.verdict.reason}",
            ) from exc

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        from agent_hooks import InterceptionBlocked

        state = _RUN_STATE.get()
        if state is None:
            # No run state means the trio was split. A plain exception raised here
            # would be converted into a tool error by the function-invocation loop
            # and the run would continue unguarded (fail open); MiddlewareTermination
            # is the only loud escape: the tool is never dispatched and the loop stops.
            message = _TRIO_REQUIRED_MESSAGE.format(seam="function")
            context.result = {"error": message}
            raise MiddlewareTermination(message)
        if not self._shares_config(state.config):
            # A different trio owns the innermost run state (stacked trios): binding to
            # it would silently misroute emissions. Halt the run fail-closed (the loop
            # swallows plain exceptions, so route through the halt path).
            _halt_on_enforcement_failure(
                state, context, MiddlewareException(_FOREIGN_TRIO_MESSAGE.format(seam="function")), "pre_tool_call"
            )

        try:
            raw_call_id = context.metadata.get("call_id")
            call_id = str(raw_call_id) if raw_call_id else uuid.uuid4().hex
            name = str(getattr(context.function, "name", context.function))
            args = _arguments_to_wire(context.arguments)
            outcome: EmitOutcome = await state.emitter.emit(
                state.builder.pre_tool_call(call_id=call_id, name=name, args=args)
            )
            target = outcome.target
            if not isinstance(target, Mapping):
                raise _AgentHooksWriteBackError("agent-hooks pre_tool_call transform must produce an arguments object.")
            effective = {str(key): item for key, item in cast("Mapping[Any, Any]", target).items()}
            if effective != args:
                # The transform rewrote the arguments: execute the approved value.
                context.arguments = dict(effective)
                args = effective
        except InterceptionBlocked as exc:
            # §6.2: the tool is not dispatched and no post_tool_call is emitted.
            self._block(state, context, exc, "pre_tool_call")
            return
        except (MiddlewareTermination, asyncio.CancelledError):
            raise
        except BaseException as exc:
            _halt_on_enforcement_failure(state, context, exc, "pre_tool_call")

        termination: MiddlewareTermination | None = None
        try:
            await call_next()
        except MiddlewareTermination as exc:
            if state.halted is not None or _is_approval_request(context.result):
                # Our own halt path, or framework approval control flow (the tool did
                # not run; an approved replay re-enters through pre_tool_call).
                raise
            # A middleware short-circuited with a substituted result; that result
            # still enters the transcript, so it is bracketed below.
            termination = exc
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            # The invocation errored: the contract still brackets it (is_error=True).
            # Only the exception type name crosses the boundary (spec §6.3/§14).
            try:
                await state.emitter.emit(
                    state.builder.post_tool_call(
                        call_id=call_id, name=name, args=args, value=type(exc).__name__, is_error=True
                    )
                )
            except InterceptionBlocked as blocked:
                # A policy deny over an already-errored call changes nothing (the
                # result is discarded either way); a host error still halts the run.
                self._maybe_halt(state, blocked, "post_tool_call")
            except asyncio.CancelledError:
                raise
            except BaseException as emit_exc:
                _halt_on_enforcement_failure(state, context, emit_exc, "post_tool_call")
            raise

        try:
            value = _tool_result_to_wire(context.result)
            outcome = await state.emitter.emit(
                state.builder.post_tool_call(call_id=call_id, name=name, args=args, value=value)
            )
            if outcome.target != value:
                context.result = _apply_tool_result_write_back(context.result, outcome.target)
        except InterceptionBlocked as exc:
            # §6.1: the result must be discarded as if the call had errored.
            self._block(state, context, exc, "post_tool_call")
        except (MiddlewareTermination, asyncio.CancelledError):
            raise
        except BaseException as exc:
            _halt_on_enforcement_failure(state, context, exc, "post_tool_call")
        if termination is not None:
            raise termination


# endregion

# region Public factory


@experimental(feature_id=ExperimentalFeature.AGENT_HOOKS)
def agent_hooks_middleware(
    interceptors: Sequence[Interceptor] | Mapping[str, Interceptor] | None = None,
    *,
    resolver: ApprovalResolver | None = None,
    mode: EnforcementMode | str = "enforce",
    composition: CompositionConfig | None = None,
    identity_provider: str | IdentityProvider | None = _JCS_SHA256,
    timeout: float | None = _DEFAULT_TIMEOUT,
    record_sink: Callable[[InterceptionRecord], None] | None = None,
    emitter: InterceptionEmitter | None = None,
    builder: AgentContextBuilder | None = None,
) -> list[MiddlewareTypes]:
    """Build the AGENT-HOOKS-0.1 middleware trio for an :class:`~agent_framework.Agent`.

    The returned middleware emit every applicable interception point of the agent-hooks
    control contract and enforce the combined verdicts fail-closed: denies block the
    guarded action (a run-level deny raises :class:`agent_hooks.InterceptionBlocked` to
    the caller; a tool-seam deny surfaces a tool error to the model), and transforms are
    written back into the framework's messages, arguments, and results so execution uses
    exactly the values the interceptors approved. Streaming runs are buffered and only
    released after the ``output`` verdict permits.

    The three middleware form one coherent feature and must be installed together;
    always pass the returned list as a whole to ``Agent(middleware=...)``, and install
    exactly one trio per agent (stacked trios are rejected fail-closed).

    Composition order:
        Place the trio first (outermost) in the middleware list. Middleware listed
        before the trio runs outside the enforcement boundary: a function middleware
        placed before the trio, for example, can substitute a tool result that the
        tool seam never brackets. Outer position is outer trust — the final
        ``output`` point still guards whatever egresses to the caller.

    Session scoping:
        By default every agent run is one agent-hooks session: a fresh
        ``InterceptionEmitter``/``AgentContextBuilder`` pair is created per run and
        ``agent_startup``/``agent_shutdown`` bracket the run. To scope one session
        across multiple runs (shared ``sequence``, stateful interceptors, one approval
        ledger), construct and own the emitter and builder yourself and pass them via
        ``emitter=``/``builder=``; the middleware then emits only the per-run points
        (``input`` through ``output``) and your host emits the session boundaries.
        Use ``record_sink`` (or your own emitter) to observe interception records.

    Args:
        interceptors: The agent-hooks interceptors to register, either as a sequence or
            as a mapping of registration name to interceptor (names appear on the
            records' verdict summaries). Required unless ``emitter`` is supplied.

    Keyword Args:
        resolver: Optional approval resolver consulted for liftable denies.
        mode: ``"enforce"`` (default) honours verdicts; ``"evaluate_only"`` records
            them without acting.
        composition: Composition profile and knobs; ``None`` uses the SDK default
            (``sequential/first_deny``, ``on_approval: stop``).
        identity_provider: ``"jcs-sha256"`` (default), a custom
            :class:`agent_hooks.IdentityProvider`, or ``None`` for identity-unbound
            records.
        timeout: Per-interceptor/resolver timeout in seconds (spec RECOMMENDED 5.0).
        record_sink: Optional callable receiving every interception record.
        emitter: A host-owned ``InterceptionEmitter`` for session-scoped enforcement.
            Must be provided together with ``builder``; the emitter's own
            configuration (interceptors, resolver, mode, ...) then governs and the
            per-run configuration parameters must be left at their defaults.
        builder: The host-owned ``AgentContextBuilder`` matching ``emitter``.

    Returns:
        The middleware list to pass to ``Agent(middleware=...)``.

    Raises:
        ModuleNotFoundError: If the optional ``agent-hooks-sdk`` package is not
            installed.
        ValueError: If the configuration is inconsistent (no interceptors in per-run
            mode, ``emitter``/``builder`` not provided together, or per-run parameters
            combined with a host-owned emitter).

    Examples:
        .. code-block:: python

            from agent_framework import Agent
            from agent_hooks import ALLOW, Verdict


            class EgressGuard:
                def intercept(self, context):
                    if "secret" in str(context.get("target")):
                        return Verdict.deny(reason="egress_blocked")
                    return ALLOW


            agent = Agent(
                client=client,
                name="assistant",
                middleware=agent_hooks_middleware([EgressGuard()]),
            )
    """
    try:
        from agent_hooks import EnforcementMode
    except ImportError as exc:  # pragma: no cover - exercised via tests with import hooks
        raise ModuleNotFoundError(_SDK_MISSING_MESSAGE) from exc

    if (emitter is None) != (builder is None):
        raise ValueError("agent_hooks_middleware requires `emitter` and `builder` to be provided together.")

    if emitter is not None:
        conflicting = [
            param_name
            for param_name, value in (
                ("interceptors", interceptors),
                ("resolver", resolver),
                ("composition", composition),
                ("record_sink", record_sink),
            )
            if value is not None
        ]
        if (mode.value if isinstance(mode, EnforcementMode) else str(mode)) != "enforce":
            conflicting.append("mode")
        if identity_provider != _JCS_SHA256:
            conflicting.append("identity_provider")
        if timeout != _DEFAULT_TIMEOUT:
            conflicting.append("timeout")
        if conflicting:
            raise ValueError(
                "agent_hooks_middleware received a host-owned `emitter`; the emitter's own configuration "
                f"governs, so these parameters must be left at their defaults: {', '.join(sorted(conflicting))}."
            )
        # Host-owned session: only the emitter/builder pair is retained — the emitter's
        # own configuration governs, so the per-run knobs are not stored at all.
        config = _AgentHooksConfig(
            interceptors=(),
            resolver=None,
            mode=None,
            composition=None,
            identity_provider=None,
            timeout=None,
            record_sink=None,
            emitter=emitter,
            builder=builder,
        )
    else:
        named: list[tuple[str | None, Interceptor]]
        if isinstance(interceptors, Mapping):
            named = [(str(name), interceptor) for name, interceptor in interceptors.items()]
        else:
            named = [(None, interceptor) for interceptor in interceptors or []]
        if not named:
            raise ValueError(
                "agent_hooks_middleware requires at least one interceptor (an emitter with zero "
                "interceptors fails closed on every emission)."
            )
        config = _AgentHooksConfig(
            interceptors=tuple(named),
            resolver=resolver,
            mode=EnforcementMode(mode) if isinstance(mode, str) else mode,
            composition=composition,
            identity_provider=identity_provider,
            timeout=timeout,
            record_sink=record_sink,
            emitter=None,
            builder=None,
        )

    return [
        _AgentHooksAgentMiddleware(config),
        _AgentHooksChatMiddleware(config),
        _AgentHooksFunctionMiddleware(config),
    ]


# endregion
