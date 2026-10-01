# Copyright (c) Microsoft. All rights reserved.

"""Foundry request models and per-turn options for protocol hosts."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, cast

from agent_framework import AgentRunInputs, Content, Message
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse, Item

from ._scope import FoundryRequestScope

UnsupportedOptions: TypeAlias = Literal["ignore", "warn", "error"]


@dataclass(frozen=True)
class InvocationRun:
    """Messages, per-turn options, and streaming intent parsed from an Invocations request.

    Args:
        messages: MAF message input for this turn, including typed `Message` or `Content` values.
        options: Caller generation options for this turn, separate from agent defaults.
        stream: Whether to stream framed SSE events rather than return a JSON response.

    Raises:
        TypeError: If the messages, options, or streaming intent have invalid types.
    """

    messages: AgentRunInputs
    options: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any]())
    stream: bool = False

    def __post_init__(self) -> None:
        if not (
            isinstance(self.messages, (str, Content, Message))
            or (
                isinstance(self.messages, Sequence)
                and all(isinstance(message, (str, Content, Message)) for message in self.messages)
            )
        ):
            raise TypeError("InvocationRun.messages must be a string, Content, Message, or a sequence of them.")
        if not isinstance(self.options, Mapping) or any(not isinstance(key, str) for key in self.options):
            raise TypeError("InvocationRun.options must be a mapping with string keys.")
        if not isinstance(self.stream, bool):
            raise TypeError("InvocationRun.stream must be a boolean.")


_HOST_CONTROLLED_FIELDS = frozenset({
    "agent",
    "agent_reference",
    "agent_session_id",
    "background",
    "call_id",
    "continuation_token",
    "conversation",
    "conversation_id",
    "extra_body",
    "input",
    "previous_response_id",
    "response_id",
    "service_session_id",
    "session_id",
    "store",
    "stream",
    "user",
    "user_id",
})
_OPTION_NAMES = {"max_output_tokens": "max_tokens", "parallel_tool_calls": "allow_multiple_tool_calls"}
_NATIVE_FIELDS = frozenset(CreateResponse.__annotations__)


def response_run_options(request: CreateResponse) -> dict[str, Any]:
    """Translate native generation fields, with flattened extra-body values winning collisions."""
    native: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    nested_extra: dict[str, Any] = {}
    for name, value in request.items():
        if value is None or (name == "model" and value == ""):
            continue
        if name == "extra_body":
            if not isinstance(value, Mapping) or any(
                not isinstance(key, str) for key in cast(Mapping[object, object], value)
            ):
                raise TypeError("extra_body must be a mapping of model options.")
            if "extra_body" in value:
                raise ValueError("Nested extra_body is not supported; flatten provider options instead.")
            nested_extra.update(cast(Mapping[str, Any], value))
        elif name in _HOST_CONTROLLED_FIELDS:
            continue
        elif name in _NATIVE_FIELDS:
            native[_OPTION_NAMES.get(name, name)] = value
        else:
            extra[name] = value
    return {
        **native,
        **{name: value for name, value in extra.items() if name not in _HOST_CONTROLLED_FIELDS},
        **{name: value for name, value in nested_extra.items() if name not in _HOST_CONTROLLED_FIELDS},
    }


class HostedResponseRequest:
    """Expose a copied request, trusted scope, and only this turn's input to an options hook."""

    def __init__(
        self,
        request: CreateResponse,
        context: ResponseContext,
        scope: FoundryRequestScope,
        options: Mapping[str, Any],
    ) -> None:
        self.request: Mapping[str, Any] = MappingProxyType(deepcopy(dict(request)))
        self.scope = scope
        self.response_id = context.response_id
        self.conversation_id = context.conversation_id
        self._context = context
        self._options: Mapping[str, Any] = MappingProxyType(dict(options))

    @property
    def options(self) -> Mapping[str, Any]:
        """Return this turn's effective caller options after the hook."""
        return self._options

    def set_options(self, options: Mapping[str, Any]) -> None:
        """Replace the caller options without changing the agent's defaults."""
        self._options = MappingProxyType(dict(options))

    async def get_input_items(self) -> list[Item]:
        """Read only this turn's input items, not earlier conversation history."""
        return list(await self._context.get_input_items())

    async def get_input_text(self) -> str | None:
        """Read this turn's text input, if present."""
        return await self._context.get_input_text()


OptionsHook: TypeAlias = Callable[
    [HostedResponseRequest, dict[str, Any]],
    Mapping[str, Any] | Awaitable[Mapping[str, Any]],
]


async def prepare_response_options(request: HostedResponseRequest, hook: OptionsHook | None) -> None:
    """Apply a synchronous or asynchronous developer hook to a copy of caller options."""
    if hook is None:
        return
    result = hook(request, dict(request.options))
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, Mapping):
        raise TypeError("prepare_options must return a mapping of MAF run options.")
    request.set_options(result)


def validate_request_options(options: Mapping[str, Any]) -> None:
    """Keep hosting identity, storage decisions, and private continuation out of model options."""
    reserved = _HOST_CONTROLLED_FIELDS.intersection(options)
    if reserved:
        raise ValueError(f"prepare_options cannot set host-controlled fields: {', '.join(sorted(reserved))}.")


def validate_default_transport_options(defaults: Mapping[str, Any], *, allow_agent_store: bool) -> None:
    """Reject transport overrides that would bypass the host's inner storage and identity decisions."""
    extra_body = defaults.get("extra_body")
    if extra_body is None:
        return
    if not isinstance(extra_body, Mapping) or any(
        not isinstance(key, str) for key in cast(Mapping[object, object], extra_body)
    ):
        raise TypeError("Agent default extra_body must be a mapping of model options.")
    reserved = _HOST_CONTROLLED_FIELDS.intersection(cast(Mapping[str, Any], extra_body))
    if allow_agent_store:
        reserved -= {"store"}
    if reserved:
        raise ValueError(
            "Agent default extra_body cannot set host-controlled fields: "
            f"{', '.join(sorted(reserved))}. Use explicit agent defaults or history_source='service'."
        )


def validate_unsupported_options(mode: str) -> UnsupportedOptions:
    """Reject misspelled unsupported-options policies at host construction."""
    if mode not in ("ignore", "warn", "error"):
        raise ValueError("unsupported_options must be 'ignore', 'warn', or 'error'.")
    return mode
