# Copyright (c) Microsoft. All rights reserved.

"""AGENT-HOOKS-0.1 enforcement middleware for Agent Framework (experimental).

This module implements the `agent-hooks <https://github.com/responsibleai/agent-hooks>`_
control contract as one coherent feature on the framework's native middleware seams:

- ``agent_startup`` / ``input`` / ``output`` / ``agent_shutdown`` ride the agent seam,
- ``pre_model_call`` / ``post_model_call`` ride the chat seam,
- ``pre_tool_call`` / ``post_tool_call`` ride the function seam.

The public entry points are :func:`create_agent_hooks_middleware` (one agent-hooks
session per run) and :func:`create_agent_hooks_middleware_from_emitter` (host-owned
session). Both return a :class:`~agent_framework.MiddlewareBundle`: the three middleware
implementations are deliberately private and travel as one indivisible unit, because
installing only part of them would enforce only part of the control contract. Install
exactly one bundle per agent, placed first in the middleware list: middleware listed
before the bundle runs outside the enforcement boundary (outer position is outer trust)
— e.g. a function middleware placed before the bundle can substitute a tool result that
the tool seam never brackets; the final ``output`` point still guards whatever egresses.

Enforcement semantics (``mode="enforce"``):

- Every interception point is emitted **before** the guarded action runs (pre points) or
  before its result is incorporated (post points). Emission failures inside the SDK
  (interceptor crash/timeout, invalid context) synthesize ``host_error:*`` denies and are
  treated as blocks — the feature never fails open.
- ``transform`` verdicts are written back into the native middleware contexts
  (``messages`` / ``arguments`` / ``results``) through per-point codecs, so the framework
  executes exactly the value the interceptors approved. Content objects are preserved:
  rich (non-text) message content is projected as content dictionaries, never flattened
  to text.
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
- Durable history persistence is gated behind the verdicts: run-end context-provider
  persistence and per-service-call history persistence are deferred (via the run
  persistence gate in ``_sessions.py``) until the ``output`` / ``post_model_call``
  emission permits the content, so denied content never becomes durable and transformed
  content is persisted post-transform. Each persist is gated by its own covering
  verdict: per-service-call history persisted under a permitted ``post_model_call``
  verdict remains durable even if the run's ``output`` is later denied. A mid-run deny
  is conservative in the other direction: the dropped per-service-call persist carries
  that service call's request messages too, so the denied turn's input is not
  persisted either. Only the gated run's own persistence defers: nested and
  middleware-initiated agent runs (sub-agents invoked as tools, agents run by other
  middleware or context providers, even on a shared session) persist inline at their
  own run boundaries — the gate is bound to its run's identity (see the run
  persistence gate in ``_sessions.py``), and the function-invocation layer
  additionally suspends the gate around tool invocations to cover nested agents with
  fully custom run loops. An outer deny therefore never discards fully-permitted
  inner history, and a second sub-agent call within one outer run reads fresh
  history. Residual limitation: an agent whose run loop never stamps a run identity
  (a fully custom ``run()`` implementation) that itself nests another such agent
  outside the tool seam falls back to deferring both — fail-closed, matching the
  pre-ownership behavior.

Streaming is supported **fail-closed by buffering** via
:meth:`ResponseStream.buffered_and_gated`: the model/agent stream is fully consumed
internally, middleware stream hooks are applied to the buffered content, the
``post_model_call`` / ``output`` verdict is applied to the finalized result, and only
then are the (possibly transformed) updates released to the consumer. No partial content
ever egresses ahead of a verdict (spec §12.1/§12.1a ``buffered_output: true``
behaviour), and nothing can rewrite content past the gate.

Known limitation — service-side (hosted) tool execution: tools executed by the model
provider itself (surfaced as informational-only function calls, e.g. hosted MCP or
web-search tools) never pass through the framework's function-invocation seam, so
``pre_tool_call`` / ``post_tool_call`` cannot intercept them. Their calls and outputs
are surfaced faithfully in the ``post_model_call`` content projection (they are part of
the model response), where interceptors can observe and deny/transform the response
that carries them.

Session scoping: by default each agent run is one agent-hooks session (fresh emitter and
sequence, ``agent_startup``/``agent_shutdown`` bracket the run). A host that owns a
longer-lived session constructs its own emitter and builder and installs them via
:func:`create_agent_hooks_middleware_from_emitter`; the middleware then emits only the
per-run points and the host owns the session boundaries.

The ``agent-hooks-sdk`` dependency is optional: importing this module (and the lazy root
exports) works without it, and the factories raise a descriptive ``ModuleNotFoundError``
when the SDK is missing. Install it via ``pip install agent-framework-core[agent-hooks]``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn, cast

from pydantic import BaseModel

from ._feature_stage import ExperimentalFeature, experimental
from ._middleware import (
    AgentContext,
    AgentMiddleware,
    ChatContext,
    ChatMiddleware,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareBundle,
    MiddlewareTermination,
)
from ._serialization import make_json_safe
from ._sessions import (
    _current_run_identity,  # pyright: ignore[reportPrivateUsage]
    _RunPersistenceGate,  # pyright: ignore[reportPrivateUsage]
)
from ._telemetry import FeatureIndex, mark_feature_used
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

logger = logging.getLogger(__name__)

_FRAMEWORK_NAME = "agent-framework"
_HOST_ERROR_PREFIX = "host_error:"
_JCS_SHA256 = "jcs-sha256"
_DEFAULT_TIMEOUT = 5.0

_SDK_MISSING_MESSAGE = (
    "The agent-hooks middleware requires the optional `agent-hooks-sdk` package. "
    "Please install `agent-framework-core[agent-hooks]` (or `agent-hooks-sdk`)."
)

_TRIO_REQUIRED_MESSAGE = (
    "agent-hooks {seam} middleware was invoked without an active agent-hooks run. "
    "The middleware bundle returned by create_agent_hooks_middleware() must be installed "
    "as one unit on an Agent, e.g. Agent(client=..., middleware=[create_agent_hooks_middleware([...])])."
)

_FOREIGN_TRIO_MESSAGE = (
    "agent-hooks {seam} middleware found an active agent-hooks run owned by a different "
    "agent-hooks middleware bundle. Stacking multiple bundles on one agent (or splitting "
    "bundles across agent- and client-level middleware) is not supported: emissions would "
    "silently bind to the wrong emitter. Install exactly one bundle per agent."
)


class _AgentHooksWriteBackError(MiddlewareException):
    """A transform verdict could not be converted back into the native context.

    Raised (and deliberately never caught by this module) so an unappliable transform
    fails the run closed instead of silently proceeding with the untransformed value.
    """


def _require_sdk() -> None:
    """Import the SDK surface this module uses at runtime, with a helpful install hint.

    Only a genuinely missing ``agent_hooks`` package is translated into the
    install-the-extra message; anything else (a broken installation, an incompatible
    SDK version missing symbols, a failing transitive import) propagates unchanged so
    real breakage is not masked as a missing extra.
    """
    try:
        from agent_hooks import (
            AgentContextBuilder,
            EnforcementMode,
            InterceptionBlocked,
            InterceptionEmitter,
        )
    except ModuleNotFoundError as exc:
        if exc.name == "agent_hooks" or (exc.name or "").startswith("agent_hooks."):
            raise ModuleNotFoundError(_SDK_MISSING_MESSAGE) from exc
        raise
    else:
        # Reference the probed surface so the imports are not "unused": the probe's
        # purpose is exactly to verify these symbols resolve.
        del AgentContextBuilder, EnforcementMode, InterceptionBlocked, InterceptionEmitter


# region Run state


@dataclass
class _AgentHooksConfig:
    """Configuration shared by one middleware bundle (one factory call)."""

    interceptors: tuple[tuple[str | None, Interceptor], ...]
    resolver: ApprovalResolver | None
    mode: EnforcementMode | None
    composition: CompositionConfig | None
    identity_provider: str | IdentityProvider | None
    timeout: float | None
    record_sink: Callable[[InterceptionRecord], None] | None
    emitter: InterceptionEmitter | None
    builder: AgentContextBuilder | None


@dataclass
class _RunState:
    """Per-run enforcement state shared by the middleware trio via a ContextVar."""

    emitter: InterceptionEmitter
    builder: AgentContextBuilder
    session_scoped: bool
    config: _AgentHooksConfig
    halted: BaseException | None = None


_RUN_STATE: ContextVar[_RunState | None] = ContextVar("agent_framework_agent_hooks_run_state", default=None)


# endregion

# region Wire building blocks (framework values <-> AGENT-HOOKS wire JSON)


def _wire_equal(left: Any, right: Any) -> bool:
    """Type-aware equality for wire JSON values (the codecs' untouched-target checks).

    Python's ``==`` equates ``1 == True`` and ``0 == False``, so a transform that
    swaps a value between bool and number would look untouched and be silently
    dropped (the untransformed native value would proceed — fail-open for the
    transform). Bool-ness is therefore compared explicitly at every nesting level.
    """
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        left_map = cast("Mapping[Any, Any]", left)
        right_map = cast("Mapping[Any, Any]", right)
        if left_map.keys() != right_map.keys():
            return False
        return all(_wire_equal(item, right_map[key]) for key, item in left_map.items())
    left_is_sequence = isinstance(left, Sequence) and not isinstance(left, (str, bytes, bytearray))
    right_is_sequence = isinstance(right, Sequence) and not isinstance(right, (str, bytes, bytearray))
    if left_is_sequence and right_is_sequence:
        left_items = cast("Sequence[Any]", left)
        right_items = cast("Sequence[Any]", right)
        if len(left_items) != len(right_items):
            return False
        return all(_wire_equal(left_item, right_item) for left_item, right_item in zip(left_items, right_items))
    return bool(left == right)


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
    return [cast("dict[str, Any]", make_json_safe(content.to_dict())) for content in contents]


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


def _looks_like_message_dicts(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    items = cast("list[Any]", value)
    return bool(items) and all(isinstance(item, Mapping) and "content" in item for item in items)


def _write_back_message_list(
    originals: Sequence[Message],
    before: Sequence[Mapping[str, Any]],
    after: Any,
    *,
    point: str,
) -> list[Message]:
    """Convert a transformed wire message list back into framework messages.

    The transformed list is authoritative. Entries are matched to original messages by
    projection identity rather than list position, so a removal or insertion in the
    middle does not shift content onto the wrong original:

    - An entry equal to an (unconsumed) original's projection reuses that original
      untouched; originals skipped over were removed by the transform.
    - A changed entry mutates the next unconsumed original in place only when that
      original's projection is not preserved later in the transformed list (i.e. it was
      modified, not shifted) and its role is unchanged. At the ``input`` seam this
      in-place mutation lets caller-held message objects adopt the transform; at the
      chat seam the outgoing messages are framework-rebuilt copies, so the mutation
      affects only the guarded request (enforcement is unaffected either way).
    - Anything else (insertions, role changes) becomes a new ``Message``.
    """
    if not isinstance(after, list):
        raise _AgentHooksWriteBackError(f"agent-hooks {point} transform must produce a list of messages.")
    after_items: list[Mapping[str, Any]] = []
    for item in cast("list[Any]", after):
        if not isinstance(item, Mapping) or "content" not in item:
            raise _AgentHooksWriteBackError(f"agent-hooks {point} transform produced a message without role/content.")
        after_items.append(cast("Mapping[str, Any]", item))

    before_dicts = [dict(projection) for projection in before]
    result: list[Message] = []
    cursor = 0
    for index, item in enumerate(after_items):
        item_dict = dict(item)
        match_index = next(
            (position for position in range(cursor, len(originals)) if _wire_equal(before_dicts[position], item_dict)),
            None,
        )
        if match_index is not None:
            result.append(originals[match_index])
            cursor = match_index + 1
            continue
        if cursor < len(originals):
            candidate_projection = before_dicts[cursor]
            preserved_later = any(_wire_equal(dict(later), candidate_projection) for later in after_items[index + 1 :])
            role = str(item.get("role") or "user")
            if not preserved_later and role == str(candidate_projection.get("role")):
                message = originals[cursor]
                cursor += 1
                message.contents = _wire_to_contents(item.get("content"), point=point)
                result.append(message)
                continue
        result.append(Message(str(item.get("role") or "user"), _wire_to_contents(item.get("content"), point=point)))
    return result


def _arguments_to_wire(arguments: Any) -> dict[str, Any]:
    """Project tool-call arguments as the spec's ``args`` object."""
    if arguments is None:
        return {}
    if isinstance(arguments, BaseModel):
        return {str(key): make_json_safe(item) for key, item in arguments.model_dump().items()}
    if isinstance(arguments, Mapping):
        return {str(key): make_json_safe(item) for key, item in cast("Mapping[Any, Any]", arguments).items()}
    if isinstance(arguments, str):
        with contextlib.suppress(ValueError):
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return cast("dict[str, Any]", parsed)
        return {"raw_arguments": arguments}
    return {"raw_arguments": str(arguments)}


def _usage_to_wire(usage_details: Any) -> dict[str, int] | None:
    if not isinstance(usage_details, Mapping):
        return None
    usage = {
        str(key): item
        for key, item in cast("Mapping[Any, Any]", usage_details).items()
        if isinstance(item, int) and not isinstance(item, bool)
    }
    return usage or None


# endregion

# region Interception-point codecs
#
# One codec per interception point owns both directions of the wire conversion:
# ``to_wire`` projects the native framework value into the spec's payload, and
# ``write_back`` converts the (possibly transformed) wire target back into the native
# value. Every ``write_back`` implements the same rule exactly once per point: a wire
# value the interceptors left untouched maps back to the untouched native value — only
# genuine transforms modify native state, and an untranslatable transform raises
# ``_AgentHooksWriteBackError`` (fail closed) rather than being dropped.


class _InputCodec:
    """``input``: the run's input messages <-> the spec's input payload."""

    @staticmethod
    def message_to_wire(message: Message) -> dict[str, Any]:
        """Project one input message with the spec's input role mapping."""
        return {"role": _input_role(message.role), "content": _contents_to_wire(message.contents)}

    @classmethod
    def to_wire(cls, messages: Sequence[Message]) -> dict[str, Any]:
        """Project run input per the spec's ``input`` payload schema.

        A single plain-text message projects as its content string (so string-matching
        perimeter guards fire); multi-message or rich input projects as a list of
        per-message ``{"role", "content"}`` objects (roles mapped onto the spec's input
        role enum) whose contents are strings when plain.
        """
        if len(messages) == 1:
            return {"content": _contents_to_wire(messages[0].contents), "role": _input_role(messages[0].role)}
        return {"content": [cls.message_to_wire(message) for message in messages], "role": "user"}

    @classmethod
    def write_back(cls, messages: list[Message], before: Mapping[str, Any], after: Any) -> None:
        """Write a transformed ``input`` target back into the run's message list."""
        if after is None or _wire_equal(after, before):
            return
        if not isinstance(after, Mapping):
            raise _AgentHooksWriteBackError("agent-hooks input transform must produce an input object target.")
        after_map = cast("Mapping[str, Any]", after)
        after_role = after_map.get("role")
        if after_role != before.get("role"):
            # The role field is per-message only for single-message input; for
            # multi-message input the top-level role is synthetic and a transform
            # against it is ambiguous.
            if len(messages) != 1 or not isinstance(after_role, str):
                raise _AgentHooksWriteBackError(
                    "agent-hooks input transform changed the input role in a way that cannot be written back."
                )
            messages[0].role = after_role
        after_content = after_map.get("content")
        if _wire_equal(after_content, before.get("content")):
            return
        if len(messages) == 1 and not _looks_like_message_dicts(after_content):
            messages[0].contents = _wire_to_contents(after_content, point="input")
            return
        before_list = [cls.message_to_wire(message) for message in messages]
        messages[:] = _write_back_message_list(list(messages), before_list, after_content, point="input")


class _ModelRequestCodec:
    """``pre_model_call``: the outgoing request messages <-> the spec's messages list."""

    @staticmethod
    def to_wire(messages: Sequence[Message]) -> list[dict[str, Any]]:
        return _messages_to_wire(messages)

    @staticmethod
    def write_back(
        messages: Sequence[Message], before: Sequence[Mapping[str, Any]], after: Any
    ) -> list[Message] | None:
        """Return the transformed message list, or None when the target is untouched."""
        if _wire_equal(after, list(before)):
            return None
        return _write_back_message_list(list(messages), before, after, point="pre_model_call")


class _ModelResponseCodec:
    """``post_model_call``: the assembled chat response <-> the spec's response payload.

    Host-executed tool calls ride ``tool_calls`` (they drive the function seam);
    service-executed (informational-only) tool calls are part of the model response
    itself and are surfaced in ``content`` so hosted tool activity is interceptable
    here even though the function seam never sees it.
    """

    @staticmethod
    def content_to_wire(messages: Sequence[Message]) -> str | list[dict[str, Any]] | None:
        """Project the response content (everything except host-executed tool calls)."""
        parts: list[dict[str, Any]] = []
        for message in messages:
            visible = [
                content for content in message.contents if content.type != "function_call" or content.informational_only
            ]
            if not visible:
                continue
            parts.append({"role": _role_str(message.role), "content": _contents_to_wire(visible)})
        if not parts:
            return None
        if len(parts) == 1 and isinstance(parts[0]["content"], str):
            return parts[0]["content"]
        return parts

    @staticmethod
    def tool_calls_to_wire(messages: Sequence[Message]) -> list[dict[str, Any]]:
        """Project the host-executed tool calls (the ones the function seam will bracket)."""
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

    @classmethod
    def to_wire(cls, response: ChatResponse[Any]) -> dict[str, Any]:
        return {
            "content": cls.content_to_wire(response.messages),
            "tool_calls": cls.tool_calls_to_wire(response.messages),
            "finish_reason": _finish_reason_str(response.finish_reason),
        }

    @classmethod
    def write_back(cls, response: ChatResponse[Any], before: Mapping[str, Any], after: Any) -> bool:
        """Write a transformed ``post_model_call`` target back into the chat response."""
        if after is None or _wire_equal(after, before):
            return False
        if not isinstance(after, Mapping):
            raise _AgentHooksWriteBackError("agent-hooks post_model_call transform must produce a response object.")
        after_map = cast("Mapping[str, Any]", after)
        changed = False
        after_finish = after_map.get("finish_reason")
        if after_finish != before.get("finish_reason"):
            if not isinstance(after_finish, str):
                raise _AgentHooksWriteBackError(
                    "agent-hooks post_model_call transform must keep finish_reason a string."
                )
            response.finish_reason = cast(Any, after_finish)
            changed = True
        after_calls = after_map.get("tool_calls")
        if not _wire_equal(after_calls, before.get("tool_calls")):
            changed = cls._write_back_tool_calls(response, after_calls) or changed
        after_content = after_map.get("content")
        if not _wire_equal(after_content, before.get("content")):
            cls._write_back_content(response, after_content)
            changed = True
        return changed

    @staticmethod
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
                wire_name = wire.get("name")
                if not isinstance(wire_name, str) or not wire_name:
                    raise _AgentHooksWriteBackError(
                        "agent-hooks post_model_call transform must keep each tool call's name a non-empty string."
                    )
                if wire_name != str(content.name):
                    content.name = wire_name
                    changed = True
                wire_args = wire.get("args")
                if not isinstance(wire_args, Mapping):
                    raise _AgentHooksWriteBackError(
                        "agent-hooks post_model_call transform must keep each tool call's args an object."
                    )
                if not _wire_equal(_arguments_to_wire(content.arguments), dict(cast("Mapping[str, Any]", wire_args))):
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
                    arguments={
                        str(key): item for key, item in cast("Mapping[Any, Any]", call.get("args") or {}).items()
                    },
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

    @staticmethod
    def _write_back_content(response: ChatResponse[Any], after_content: Any) -> None:
        """Rebuild the response's visible content from a transformed ``response.content`` value."""
        calls = [
            content
            for message in response.messages
            for content in message.contents
            if content.type == "function_call" and not content.informational_only
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


class _ToolArgumentsCodec:
    """``pre_tool_call``: the native tool arguments <-> the spec's args object."""

    @staticmethod
    def to_wire(arguments: Any) -> dict[str, Any]:
        return _arguments_to_wire(arguments)

    @staticmethod
    def write_back(arguments: Any, before: Mapping[str, Any], after: Any) -> tuple[Any, dict[str, Any]]:
        """Merge a transformed ``args`` target back onto the native arguments.

        Returns ``(native_arguments, effective_wire_args)``. Only the keys the
        transform actually changed (or added/removed) are taken from the wire value;
        untouched keys keep their original native values, so non-JSON-native argument
        values (bytes, rich objects) survive a transform that did not touch them.
        """
        if not isinstance(after, Mapping):
            raise _AgentHooksWriteBackError("agent-hooks pre_tool_call transform must produce an arguments object.")
        effective = {str(key): item for key, item in cast("Mapping[Any, Any]", after).items()}
        if _wire_equal(effective, dict(before)):
            return arguments, effective
        if isinstance(arguments, BaseModel):
            native: dict[str, Any] = {name: getattr(arguments, name) for name in type(arguments).model_fields}
        elif isinstance(arguments, Mapping):
            native = {str(key): item for key, item in cast("Mapping[Any, Any]", arguments).items()}
        else:
            native = {}
        merged = {key: item for key, item in native.items() if key in effective}
        for key, item in effective.items():
            if key not in before or not _wire_equal(before[key], item):
                merged[key] = item
        return merged, effective


class _ToolResultCodec:
    """``post_tool_call``: the native tool result <-> the spec's result value."""

    @staticmethod
    def to_wire(value: Any) -> Any:
        """Project a tool result faithfully, unwrapping framework ``Content`` containers.

        Text content projects as its text, ``function_result`` content projects as its
        canonical ``result`` value, and any other content projects as its full content
        dictionary — never as ``str(Content)`` reprs.
        """
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        if isinstance(value, list) and len(cast("list[Any]", value)) == 1 and isinstance(value[0], Content):
            # The canonical single-content result (e.g. the default parser's wrapped
            # text) projects as the content's value itself, matching what the model sees.
            return _ToolResultCodec.to_wire(value[0])
        if isinstance(value, Content):
            if value.type == "text":
                return value.text or ""
            if value.type == "function_result":
                if value.result is not None:
                    return _ToolResultCodec.to_wire(value.result)
                if value.items is not None:
                    return [_ToolResultCodec.to_wire(item) for item in value.items]
                return None
            return make_json_safe(value.to_dict())
        if isinstance(value, Mapping):
            return {str(key): _ToolResultCodec.to_wire(item) for key, item in cast("Mapping[Any, Any]", value).items()}
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            return [_ToolResultCodec.to_wire(item) for item in cast("Sequence[Any]", value)]
        return make_json_safe(value)

    @staticmethod
    def write_back(original: Any, before: Any, after: Any) -> Any:
        """Convert a transformed ``post_tool_call`` value back into the native result shape.

        A wire value the interceptors left untouched maps back to the untouched native
        result (the codec region's shared rule, applied here like in the other five
        codecs). When the original result is the framework's canonical
        ``list[Content]`` and the transformed value is shape-compatible, the Content
        wrappers are preserved; otherwise the transformed wire value becomes the
        result as-is (the function invocation layer serializes arbitrary JSON-native
        results faithfully).
        """
        if _wire_equal(after, before):
            return original
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
                    if _wire_equal(_ToolResultCodec.to_wire(content), item):
                        rebuilt.append(content)
                    elif content.type == "text" and isinstance(item, str):
                        rebuilt.append(Content.from_text(item))
                    else:
                        return after_items
                return rebuilt
        return cast(Any, after)


class _OutputCodec:
    """``output``: the final agent response <-> the spec's output payload."""

    @staticmethod
    def to_wire(response: AgentResponse[Any]) -> str | list[dict[str, Any]]:
        """Project the run output: a single plain-text message as a string, else per-message objects."""
        parts = _messages_to_wire(response.messages)
        if len(parts) == 1 and isinstance(parts[0]["content"], str):
            return parts[0]["content"]
        return parts

    @staticmethod
    def write_back(response: AgentResponse[Any], before_content: Any, after: Any) -> bool:
        """Write a transformed ``output`` target back into the agent response. Returns whether it changed."""
        if after is None:
            return False
        if not isinstance(after, Mapping):
            raise _AgentHooksWriteBackError("agent-hooks output transform must produce an output object target.")
        after_content = cast("Mapping[str, Any]", after).get("content")
        if _wire_equal(after_content, before_content):
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


# endregion

# region Enforcement helpers


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
    """Project the registered tool names for ``agent_startup`` (spec ``tools_registered``)."""
    from ._tools import _get_tool_name, normalize_tools  # type: ignore[reportPrivateUsage]

    tools: Any = context.tools if context.tools is not None else getattr(context.agent, "tools", None)
    if tools is None:
        return []
    try:
        normalized = normalize_tools(tools)
    except Exception:
        logger.warning("agent-hooks could not normalize the run's tools for the agent_startup projection.")
        return []
    names: list[str] = []
    for item in normalized:
        name = _get_tool_name(item)
        names.append(name if name else type(item).__name__)
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
    """Route an unexpected failure inside the enforcement layer through the fail-closed halt path.

    The function-invocation loop converts arbitrary exceptions raised by function
    middleware into tool-error results and keeps running; for a failure of the
    enforcement layer itself (projection bug, emitter fault) that would fail open —
    the failure would vanish from the audit trail and the run would continue unguarded.
    Instead the loop is stopped via ``MiddlewareTermination`` (its only loud escape) and
    the agent middleware re-raises the failure to the caller at the run boundary.
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


# endregion

# region Middleware implementations (private: the bundle is one coherent feature)


# eq=False keeps identity semantics (and hashability): the middleware pipeline caches
# compare middleware tuples with ==, and value-equality would let a pipeline cached for
# one bundle be reused for a field-equal fresh bundle, conflating their run states.
@dataclass(eq=False)
class _AgentHooksMiddlewareBase:
    """Shared base carrying the bundle's config (also enables ownership checks)."""

    _config: _AgentHooksConfig

    def _shares_config(self, config: _AgentHooksConfig) -> bool:
        """Whether this middleware was created by the same factory call as ``config``."""
        return self._config is config


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
        before = _InputCodec.to_wire(context.messages)
        outcome: EmitOutcome = await state.emitter.emit(
            state.builder.input(content=before["content"], role=before["role"])
        )
        _InputCodec.write_back(context.messages, before, outcome.target)

    async def _emit_output(self, state: _RunState, response: AgentResponse[Any]) -> bool:
        """Emit ``output`` over the assembled response; apply output transforms."""
        before_content = _OutputCodec.to_wire(response)
        outcome: EmitOutcome = await state.emitter.emit(state.builder.output(content=before_content))
        return _OutputCodec.write_back(response, before_content, outcome.target)

    async def _emit_shutdown(self, state: _RunState, reason: str) -> None:
        """Best-effort ``agent_shutdown`` (per-run sessions only; blocks there are record-only)."""
        if state.session_scoped:
            return
        try:
            await state.emitter.emit_unchecked(state.builder.agent_shutdown(reason=reason))
        except Exception:
            logger.warning(
                "agent-hooks failed to emit agent_shutdown (reason=%r); the session trail is incomplete.",
                reason,
                exc_info=True,
            )

    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        from agent_hooks import InterceptionBlocked

        state = self._new_run_state(context)
        if context.stream:
            await self._process_streaming(context, call_next, state)
            return

        token = _RUN_STATE.set(state)
        shutdown_reason = "completed"
        try:
            gate = _RunPersistenceGate()
            # Hand the gate to the pipeline's final handler via the context: the run
            # it starts adopts the gate and binds it to its own identity, so only that
            # run's persistence defers (middleware-initiated runs persist inline).
            context._run_persistence_gate = gate  # pyright: ignore[reportPrivateUsage]
            try:
                await self._emit_run_start(context, state)
                termination: MiddlewareTermination | None = None
                with gate:
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
                # The verdict permitted the content (or nothing egresses): release the
                # persistence the run deferred behind the gate. A deny above drops it
                # instead, so denied content never becomes durable.
                await gate.flush()
                if termination is not None:
                    raise termination
            except InterceptionBlocked:
                gate.drop()
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

        Ownership of the session trail passes to the gated stream only once it is
        installed as the run result; every earlier exit (pre-run deny, middleware
        exception, unguardable result) still closes the trail with ``agent_shutdown``.
        """
        token = _RUN_STATE.set(state)
        # Pessimistic default: any exit before the gated stream takes ownership closes
        # the trail as an error; ``None`` means ownership was handed off.
        shutdown_reason: str | None = "error"
        try:
            gate_handle = _RunPersistenceGate()
            # Hand the gate to the pipeline's final handler via the context (see the
            # non-streaming branch): the run it starts binds the gate to its identity.
            context._run_persistence_gate = gate_handle  # pyright: ignore[reportPrivateUsage]
            await self._emit_run_start(context, state)
            termination: MiddlewareTermination | None = None
            # The gate covers the pipeline descent too, exactly like the non-streaming
            # branch: a middleware that drains an attempt's stream in-pipeline (e.g. a
            # retry that discards a successful attempt) issues that attempt's run-end
            # persistence here, and it must defer behind the final verdict — the
            # attempt's identity is an accepted owner via the claim ticket. The gate
            # is then re-entered (sequential reuse) around the released stream's
            # consumption in _consume, and flushed/dropped exactly once by its gate.
            with gate_handle:
                try:
                    await call_next()
                except MiddlewareTermination as exc:
                    termination = exc
            inner = context.result
            if inner is None and termination is not None:
                if state.halted is not None:
                    # The enforcement layer itself failed: strand the deferred
                    # persistence (fail-closed) and surface the halt.
                    raise state.halted
                # Terminated without a result: nothing will egress, so the no-egress
                # termination is a permitted outcome. Release the persistence the
                # drained in-pipeline work deferred — history of model calls that
                # really happened and passed their own verdicts — mirroring the
                # non-streaming branch's flush-before-re-raise.
                await gate_handle.flush()
                shutdown_reason = "completed"
                raise termination
            if not isinstance(inner, ResponseStream):
                raise MiddlewareException(
                    "agent-hooks streaming enforcement requires a ResponseStream agent result; "
                    f"got {type(inner).__name__}."
                )
            context.result = self._gated_agent_stream(
                state, cast("ResponseStream[AgentResponseUpdate, AgentResponse[Any]]", inner), gate_handle
            )
            # The gated stream now owns the shutdown emission.
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

    def _gated_agent_stream(
        self,
        state: _RunState,
        inner: ResponseStream[AgentResponseUpdate, AgentResponse[Any]],
        gate_handle: _RunPersistenceGate,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Guard a streaming run with a fail-closed buffered gate.

        The run is fully consumed (with the run state and the persistence gate active),
        middleware stream hooks are applied by the combinator before the verdict, the
        ``output`` verdict is applied to the finalized response, and deferred
        persistence is released only after the verdict permits. The combinator owns the
        no-divergence rule: a transformed output (or any applied stream hooks)
        re-derives the released updates from the verdicted response.
        """

        async def _consume() -> tuple[Sequence[AgentResponseUpdate], AgentResponse[Any]]:
            run_token = _RUN_STATE.set(state)
            try:
                with gate_handle:
                    final = await inner.get_final_response()
            except asyncio.CancelledError:
                await self._emit_shutdown(state, "cancelled")
                raise
            except BaseException:
                await self._emit_shutdown(state, "error")
                raise
            finally:
                _RUN_STATE.reset(run_token)
            return list(inner.updates), final

        async def _gate(
            _updates: list[AgentResponseUpdate], final: AgentResponse[Any]
        ) -> tuple[AgentResponse[Any], bool]:
            from agent_hooks import InterceptionBlocked

            try:
                if state.halted is not None:
                    raise state.halted
                if not isinstance(final, AgentResponse):
                    raise MiddlewareException(
                        f"agent-hooks cannot guard a streamed run result of type {type(final).__name__}; "
                        "the output interception point was not emitted."
                    )
                transformed = await self._emit_output(state, final)
                await gate_handle.flush()
                await self._emit_shutdown(state, "completed")
                return final, transformed
            except InterceptionBlocked:
                gate_handle.drop()
                await self._emit_shutdown(state, "error")
                raise
            except asyncio.CancelledError:
                await self._emit_shutdown(state, "cancelled")
                raise
            except BaseException:
                await self._emit_shutdown(state, "error")
                raise

        return cast(
            "ResponseStream[AgentResponseUpdate, AgentResponse[Any]]",
            cast(Any, ResponseStream).buffered_and_gated(
                consume=_consume, gate=_gate, rederive=_agent_updates_from_response
            ),
        )


class _AgentHooksChatMiddleware(_AgentHooksMiddlewareBase, ChatMiddleware):
    """Model bracket: ``pre_model_call`` and ``post_model_call``."""

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        from agent_hooks import InterceptionBlocked

        state = _RUN_STATE.get()
        if state is None:
            raise MiddlewareException(_TRIO_REQUIRED_MESSAGE.format(seam="chat"))
        if not self._shares_config(state.config):
            # A different bundle's agent middleware owns the innermost run state
            # (stacked bundles, or a bundle split across agent- and client-level
            # middleware): binding to it would silently misroute emissions.
            raise MiddlewareException(_FOREIGN_TRIO_MESSAGE.format(seam="chat"))

        options = context.options or {}
        model_id = str(options.get("model") or type(context.client).__name__)
        before = _ModelRequestCodec.to_wire(context.messages)
        outcome: EmitOutcome = await state.emitter.emit(
            state.builder.pre_model_call(model_id=model_id, messages=before)
        )
        transformed_messages = _ModelRequestCodec.write_back(context.messages, before, outcome.target)
        if transformed_messages is not None:
            context.messages = transformed_messages

        termination: MiddlewareTermination | None = None
        gate = _RunPersistenceGate()
        # The chat seam runs inside its run's identity scope, so the gate binds to the
        # current run immediately: only this run's per-service-call persists defer.
        gate.bind_owner(_current_run_identity())
        with gate:
            try:
                await call_next()
            except MiddlewareTermination as exc:
                # A chat middleware short-circuited with a substituted result; whatever
                # was substituted still flows into the agent loop, so it is guarded below.
                termination = exc

        result = context.result
        if isinstance(result, ResponseStream):
            context.result = self._gated_chat_stream(
                state, model_id, cast("ResponseStream[ChatResponseUpdate, ChatResponse[Any]]", result), gate
            )
        elif isinstance(result, ChatResponse):
            try:
                await self._emit_post_model_call(state, model_id, result)
            except InterceptionBlocked:
                # §6.1: the denied response must not be incorporated (and the deferred
                # per-service-call persistence for it is dropped, never executed).
                gate.drop()
                context.result = None
                raise
            await gate.flush()
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
        before = _ModelResponseCodec.to_wire(response)
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
        return _ModelResponseCodec.write_back(response, before, outcome.target)

    def _gated_chat_stream(
        self,
        state: _RunState,
        model_id: str,
        inner: ResponseStream[ChatResponseUpdate, ChatResponse[Any]],
        gate_handle: _RunPersistenceGate,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Guard a streaming model call with a fail-closed buffered gate.

        Spec §12.1: the complete response is assembled before ``post_model_call`` is
        emitted, and nothing (updates or tool calls) is released beforehand. A deny
        raises before any update egresses, and per-service-call history persistence
        deferred by the run persistence gate is released only after the verdict
        permits. The combinator owns the no-divergence rule: a transformed response
        (or any applied stream hooks) re-derives the released updates from it.
        """

        async def _consume() -> tuple[Sequence[ChatResponseUpdate], ChatResponse[Any]]:
            with gate_handle:
                response = await inner.get_final_response()
            return list(inner.updates), response

        async def _gate(_updates: list[ChatResponseUpdate], final: ChatResponse[Any]) -> tuple[ChatResponse[Any], bool]:
            from agent_hooks import InterceptionBlocked

            if not isinstance(final, ChatResponse):
                raise MiddlewareException(
                    f"agent-hooks cannot guard a streamed chat result of type {type(final).__name__}; "
                    "the post_model_call interception point was not emitted."
                )
            try:
                changed = await self._emit_post_model_call(state, model_id, final)
            except InterceptionBlocked:
                # §6.1: the deferred per-service-call persistence for the denied
                # response is dropped, never executed.
                gate_handle.drop()
                raise
            await gate_handle.flush()
            return final, changed

        return cast(
            "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]",
            cast(Any, ResponseStream).buffered_and_gated(
                consume=_consume, gate=_gate, rederive=_chat_updates_from_response
            ),
        )


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
            # No run state means the bundle's agent middleware never ran. A plain
            # exception raised here would be converted into a tool error by the
            # function-invocation loop and the run would continue unguarded (fail
            # open); MiddlewareTermination is the only loud escape: the tool is never
            # dispatched and the loop stops.
            message = _TRIO_REQUIRED_MESSAGE.format(seam="function")
            context.result = {"error": message}
            raise MiddlewareTermination(message)
        if not self._shares_config(state.config):
            # A different bundle owns the innermost run state (stacked bundles):
            # binding to it would silently misroute emissions. Halt the run
            # fail-closed (the loop swallows plain exceptions, so route through the
            # halt path).
            _halt_on_enforcement_failure(
                state, context, MiddlewareException(_FOREIGN_TRIO_MESSAGE.format(seam="function")), "pre_tool_call"
            )

        try:
            raw_call_id = context.metadata.get("call_id")
            call_id = str(raw_call_id) if raw_call_id else uuid.uuid4().hex
            name = str(getattr(context.function, "name", context.function))
            args = _ToolArgumentsCodec.to_wire(context.arguments)
            outcome: EmitOutcome = await state.emitter.emit(
                state.builder.pre_tool_call(call_id=call_id, name=name, args=args)
            )
            arguments, effective = _ToolArgumentsCodec.write_back(context.arguments, args, outcome.target)
            if arguments is not context.arguments:
                # The transform rewrote (some of) the arguments: execute the approved
                # values, keeping untouched keys' original native values.
                context.arguments = arguments
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

        if _is_approval_request(context.result):
            # Framework approval control flow on the normal return path (a middleware
            # set an approval request and returned): the tool has not run, so there is
            # no result to bracket — pass the control object through un-emitted, exactly
            # like the termination branch above. The approved replay re-enters through
            # pre_tool_call.
            return

        try:
            value = _ToolResultCodec.to_wire(context.result)
            outcome = await state.emitter.emit(
                state.builder.post_tool_call(call_id=call_id, name=name, args=args, value=value)
            )
            context.result = _ToolResultCodec.write_back(context.result, value, outcome.target)
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

# region Public factories


@experimental(feature_id=ExperimentalFeature.AGENT_HOOKS)
def create_agent_hooks_middleware(
    interceptors: Sequence[Interceptor] | Mapping[str, Interceptor],
    *,
    resolver: ApprovalResolver | None = None,
    mode: EnforcementMode | str = "enforce",
    composition: CompositionConfig | None = None,
    identity_provider: str | IdentityProvider | None = _JCS_SHA256,
    timeout: float | None = _DEFAULT_TIMEOUT,
    record_sink: Callable[[InterceptionRecord], None] | None = None,
) -> MiddlewareBundle:
    """Build the AGENT-HOOKS-0.1 enforcement middleware for an :class:`~agent_framework.Agent`.

    The returned bundle emits every applicable interception point of the agent-hooks
    control contract and enforces the combined verdicts fail-closed: denies block the
    guarded action (a run-level deny raises :class:`agent_hooks.InterceptionBlocked` to
    the caller; a tool-seam deny surfaces a tool error to the model), transforms are
    written back into the framework's messages, arguments, and results so execution uses
    exactly the values the interceptors approved, streaming runs are buffered and only
    released after the ``output`` verdict permits, and durable history persistence is
    deferred until the covering verdict permits the content. When middleware retries a
    run, every attempt's persistence stays behind the one final verdict; note that
    ``post_model_call`` is the content-complete audit point — a discarded attempt's
    response passes its own ``post_model_call`` verdict but never reaches ``output``.

    Every agent run is one agent-hooks session: a fresh ``InterceptionEmitter`` and
    ``AgentContextBuilder`` pair is created per run and ``agent_startup`` /
    ``agent_shutdown`` bracket the run. To scope one session across multiple runs, see
    :func:`create_agent_hooks_middleware_from_emitter`. Use ``record_sink`` to observe
    interception records.

    Composition order:
        Pass the bundle as one element of ``Agent(middleware=[...])``, placed first
        (outermost), and install exactly one bundle per agent (stacked bundles are
        rejected fail-closed). Middleware listed before the bundle runs outside the
        enforcement boundary: a function middleware placed before it, for example, can
        substitute a tool result that the tool seam never brackets, and stream hooks
        registered by outer-position middleware are applied to buffered streaming
        content ahead of the verdict, granting that middleware pre-verdict *read*
        access (its rewrites remain covered by the verdict, and nothing egresses to
        the caller before the verdict). Outer position is outer trust — the final
        ``output`` point still guards whatever egresses.

    Args:
        interceptors: The agent-hooks interceptors to register, either as a sequence or
            as a mapping of registration name to interceptor (names appear on the
            records' verdict summaries). At least one interceptor is required.

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

    Returns:
        The middleware bundle to pass (as one element) to ``Agent(middleware=...)``.

    Raises:
        ModuleNotFoundError: If the optional ``agent-hooks-sdk`` package is not
            installed.
        ValueError: If no interceptors are provided.

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
                middleware=[create_agent_hooks_middleware([EgressGuard()])],
            )
    """
    _require_sdk()
    from agent_hooks import EnforcementMode

    named: list[tuple[str | None, Interceptor]]
    if isinstance(interceptors, Mapping):
        named = [(str(name), interceptor) for name, interceptor in interceptors.items()]
    else:
        named = [(None, interceptor) for interceptor in interceptors]
    if not named:
        raise ValueError(
            "create_agent_hooks_middleware requires at least one interceptor (an emitter with "
            "zero interceptors fails closed on every emission)."
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
    return _build_bundle(config)


@experimental(feature_id=ExperimentalFeature.AGENT_HOOKS)
def create_agent_hooks_middleware_from_emitter(
    emitter: InterceptionEmitter,
    builder: AgentContextBuilder,
) -> MiddlewareBundle:
    """Build the agent-hooks middleware bundle around a host-owned session.

    Use this form when your host scopes one agent-hooks session across multiple agent
    runs (shared ``sequence``, stateful interceptors, one approval ledger): construct
    and configure the ``InterceptionEmitter`` (interceptors, resolver, mode,
    composition, identity provider, timeout, record sink) and the matching
    ``AgentContextBuilder`` yourself and pass them here. The middleware then emits only
    the per-run points (``input`` through ``output``) on your emitter, and your host
    owns the ``agent_startup`` / ``agent_shutdown`` session boundaries.

    Enforcement semantics and composition-order requirements are identical to
    :func:`create_agent_hooks_middleware`.

    Args:
        emitter: The host-owned, fully configured ``InterceptionEmitter``.
        builder: The host-owned ``AgentContextBuilder`` matching ``emitter``.

    Returns:
        The middleware bundle to pass (as one element) to ``Agent(middleware=...)``.

    Raises:
        ModuleNotFoundError: If the optional ``agent-hooks-sdk`` package is not
            installed.
        ValueError: If ``emitter`` or ``builder`` is missing.
    """
    _require_sdk()
    if not emitter or not builder:
        raise ValueError("create_agent_hooks_middleware_from_emitter requires both an emitter and a builder.")
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
    return _build_bundle(config)


def _build_bundle(config: _AgentHooksConfig) -> MiddlewareBundle:
    mark_feature_used(FeatureIndex.CORE_AGENT_HOOKS)
    return MiddlewareBundle([
        _AgentHooksAgentMiddleware(config),
        _AgentHooksChatMiddleware(config),
        _AgentHooksFunctionMiddleware(config),
    ])


# endregion
