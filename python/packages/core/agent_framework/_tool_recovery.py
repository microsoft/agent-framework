# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from math import isfinite
from time import perf_counter, time
from types import TracebackType
from typing import Any, Literal, cast

import msgspec

from ._sessions import AgentSession
from ._types import ChatResponse, ChatResponseUpdate, Content, Message
from .exceptions import ChatClientException, ChatClientInvalidRequestException

BACKGROUND_TOOL_RECOVERY_KEY = "_background_tool_recovery"
_MAX_HANDLED_RESPONSES = 256


class _PendingToolDelivery(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    token: str
    response_id: str
    status: Literal["executing", "ready", "submitting", "indeterminate"]
    calls: dict[str, list[str] | None]
    inputs: list[str]
    prepared_messages: list[str]
    transcript: list[str]
    budget: dict[str, Any]
    errors_in_a_row: int
    usage: dict[str, Any] | None
    tool_choice: Any


class _BackgroundToolState(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    version: Literal[1]
    scope: str
    busy: bool
    handled: list[str]
    pending: _PendingToolDelivery | None


class BackgroundToolRecovery:
    """Retain local execution evidence independently of successful-run history."""

    def __init__(
        self,
        *,
        scope: str,
        session: AgentSession | None,
        authoritative: bool,
        options: Mapping[str, Any],
        messages: Sequence[Message],
    ) -> None:
        self._scope = scope
        self._session = session if authoritative else None
        raw_token = options.get("continuation_token")
        token = cast(Mapping[str, Any], raw_token).get("response_id") if isinstance(raw_token, Mapping) else None
        self._token: str | None = token if isinstance(token, str) else None
        if raw_token is not None and (not isinstance(self._token, str) or not self._token):
            raise ChatClientInvalidRequestException("Background continuation requires a non-empty response_id.")
        self._inputs = [message.to_json() for message in messages]
        self._state: _BackgroundToolState | None = None
        self._response: ChatResponse[Any] | None = None
        self._streamed_delivery = False
        self.resuming = False

    def __enter__(self) -> BackgroundToolRecovery:
        if self._session is None:
            return self
        raw = self._session.state.get(BACKGROUND_TOOL_RECOVERY_KEY)
        if BACKGROUND_TOOL_RECOVERY_KEY not in self._session.state:
            self._state = _BackgroundToolState(version=1, scope=self._scope, busy=False, handled=[], pending=None)
        else:
            try:
                self._state = msgspec.convert(raw, type=_BackgroundToolState, strict=True)
            except (TypeError, ValueError) as exc:
                raise ChatClientInvalidRequestException(
                    "Invalid background tool recovery state; refusing replay."
                ) from exc
        state = self._state
        if state.scope != self._scope:
            raise ChatClientInvalidRequestException("Background recovery belongs to a different provider or model.")
        if state.busy:
            raise ChatClientInvalidRequestException(
                "Another background poll owns this session; concurrent polls are unsafe."
            )
        if state.pending is not None:
            pending = state.pending
            if self._token != pending.token or self._inputs != pending.inputs:
                raise ChatClientInvalidRequestException(
                    "Pending tool results must be recovered with the original token and no new input."
                )
            if pending.status != "ready":
                raise ChatClientException(
                    "Background tool execution or result delivery has an indeterminate outcome. "
                    "Reconcile it with the external service; tools will not be executed again."
                )
            if not pending.calls or any(result is None for result in pending.calls.values()):
                raise ChatClientInvalidRequestException("Incomplete background execution evidence; refusing replay.")
            try:
                for key in ("elapsed_seconds", "paused_at"):
                    value = pending.budget[key]
                    if type(value) not in (int, float) or not isfinite(value) or value < 0:
                        raise ValueError(f"Invalid background budget {key}.")
                for key in ("attempt_count", "total_function_calls"):
                    value = pending.budget[key]
                    if type(value) is not int or value < 0:
                        raise ValueError(f"Invalid background budget {key}.")
                if not pending.prepared_messages or not pending.transcript:
                    raise ValueError("Missing background result transcript.")
                for message in (*pending.prepared_messages, *pending.transcript):
                    Message.from_json(message)
            except (KeyError, TypeError, ValueError) as exc:
                raise ChatClientInvalidRequestException(
                    "Invalid background delivery checkpoint; refusing replay."
                ) from exc
            self.resuming = True
        elif self._token in state.handled:
            raise ChatClientInvalidRequestException("This background token is stale; its tools have already completed.")
        state.busy = True
        self._save()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._state is None:
            return
        pending = self._state.pending
        if pending is not None:
            if exc is None:
                self._remember(pending.token, pending.response_id)
                self._state.pending = None
            elif pending.status == "submitting":
                cause = exc.__cause__ if isinstance(exc, ChatClientException) else exc
                status_code = getattr(cause, "status_code", None)
                pending.status = (
                    "ready" if status_code in (429, 503) and not self._streamed_delivery else "indeterminate"
                )
            elif pending.status != "ready":
                pending.status = "indeterminate"
        self._state.busy = False
        self._save()

    def _save(self) -> None:
        if self._session is not None and self._state is not None:
            self._session.state[BACKGROUND_TOOL_RECOVERY_KEY] = msgspec.to_builtins(self._state)

    def _remember(self, *response_ids: str) -> None:
        if self._state is not None:
            for response_id in response_ids:
                if response_id not in self._state.handled:
                    self._state.handled.append(response_id)

    def restore(
        self, options: dict[str, Any], request_kwargs: dict[str, Any], budget: dict[str, Any]
    ) -> _PendingToolDelivery | None:
        if not self.resuming or self._state is None or self._state.pending is None:
            return None
        pending = self._state.pending
        snapshot = copy.deepcopy(pending.budget)
        elapsed = float(snapshot.pop("elapsed_seconds"))
        paused_at = float(snapshot.pop("paused_at"))
        payload_budget = budget.get("_function_result_payload_budget")
        if isinstance(payload_budget, dict):
            payload_budget = cast(dict[str, Any], payload_budget)
            payload_budget.clear()
            payload_budget.update(snapshot.get("_function_result_payload_budget", {}))
            snapshot["_function_result_payload_budget"] = payload_budget
        budget.clear()
        budget.update(snapshot)
        budget["start_time"] = perf_counter() - elapsed - max(0.0, time() - paused_at)
        options.pop("continuation_token", None)
        options["conversation_id"] = pending.response_id
        options["tool_choice"] = copy.deepcopy(pending.tool_choice)
        request_kwargs["conversation_id"] = pending.response_id
        return pending

    def before_request(self) -> None:
        if self._state is not None and self._state.pending is not None:
            pending = self._state.pending
            if pending.status == "ready":
                pending.status = "submitting"
                self._streamed_delivery = False
                self._save()

    def observe_update(self, update: ChatResponseUpdate) -> None:
        if self._state is not None and self._state.pending is not None and self._state.pending.status == "submitting":
            self._streamed_delivery = True

    def observe_response(self, response: ChatResponse[Any]) -> None:
        if self._state is not None and self._state.pending is not None:
            pending = self._state.pending
            if pending.status == "submitting":
                self._remember(pending.token, pending.response_id)
                self._state.pending = None
                self._save()
        self._response = response

    def start_call(self, function_call: Content) -> bool:
        # Approval/Host resume executes before a new provider response and keeps its existing recovery contract.
        if self._response is None:
            return False
        if self._session is None or self._state is None:
            raise ChatClientInvalidRequestException(
                "Automatic background tools require an explicit AgentSession, reused for every poll."
            )
        if not self._response.response_id:
            raise ChatClientInvalidRequestException("Background tools require a provider response identity.")
        state = self._state
        if len(state.handled) >= _MAX_HANDLED_RESPONSES:
            raise ChatClientInvalidRequestException(
                "Background recovery capacity reached; start a new session instead of forgetting executed tools."
            )
        if state.pending is None:
            state.pending = _PendingToolDelivery(
                token=self._token or self._response.response_id,
                response_id=self._response.response_id,
                status="executing",
                calls={},
                inputs=copy.deepcopy(self._inputs),
                prepared_messages=[],
                transcript=[],
                budget={},
                errors_in_a_row=0,
                usage=None,
                tool_choice=None,
            )
        occurrence_id = function_call.id
        if not occurrence_id or occurrence_id in state.pending.calls:
            raise ChatClientInvalidRequestException(
                "Missing or repeated background tool occurrence; refusing execution."
            )
        state.pending.calls[occurrence_id] = None
        self._save()
        return True

    def complete_call(self, function_call: Content, contents: Sequence[Content]) -> None:
        if self._state is None or self._state.pending is None or function_call.id is None:
            raise RuntimeError("Background tool execution was not claimed.")
        self._state.pending.calls[function_call.id] = [
            msgspec.json.encode(content.to_dict()).decode() for content in contents
        ]
        self._save()

    def checkpoint(
        self,
        *,
        prepared_messages: Sequence[Message],
        transcript: Sequence[Message],
        budget: Mapping[str, Any],
        errors_in_a_row: int,
        usage: Mapping[str, Any] | None,
        options: Mapping[str, Any],
    ) -> None:
        if self._state is None or self._state.pending is None:
            return
        pending = self._state.pending
        if pending.status != "executing" or any(result is None for result in pending.calls.values()):
            raise ChatClientException("Background tool batch did not produce complete execution evidence.")
        # Opaque JSON prevents AgentSession restoration from eagerly rehydrating nested type discriminators.
        pending.prepared_messages = [message.to_json() for message in prepared_messages]
        pending.transcript = [message.to_json() for message in transcript]
        pending.budget = copy.deepcopy(dict(budget))
        pending.errors_in_a_row = errors_in_a_row
        pending.usage = dict(usage) if usage is not None else None
        pending.tool_choice = copy.deepcopy(options.get("tool_choice"))
        pending.status = "ready"
        self._save()
