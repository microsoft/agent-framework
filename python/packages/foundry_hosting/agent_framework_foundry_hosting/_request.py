# Copyright (c) Microsoft. All rights reserved.

"""Request-scoped Responses options and a view for developer hooks."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, cast

from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse, Item

from ._scope import FoundryRequestScope

UnsupportedOptions: TypeAlias = Literal["ignore", "warn", "error"]

_HOST_CONTROLLED_FIELDS = frozenset({
    "agent",
    "agent_reference",
    "agent_session_id",
    "background",
    "call_id",
    "continuation_token",
    "conversation",
    "conversation_id",
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


def validate_unsupported_options(mode: str) -> UnsupportedOptions:
    """Reject misspelled unsupported-options policies at host construction."""
    if mode not in ("ignore", "warn", "error"):
        raise ValueError("unsupported_options must be 'ignore', 'warn', or 'error'.")
    return mode
