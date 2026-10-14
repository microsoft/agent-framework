# Copyright (c) Microsoft. All rights reserved.

"""Native Responses workflow projection, with durable output preceding publication."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, aclosing
from contextvars import ContextVar
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from typing import Any, cast

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    ChatResponse,
    ChatResponseUpdate,
    CheckpointStorage,
    Content,
    FinishReason,
    Message,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
    WorkflowEvent,
)
from anyio import CancelScope
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses._id_generator import IdGenerator
from azure.ai.agentserver.responses.aio import ResponseEventStream
from azure.ai.agentserver.responses.models import CreateResponse, ResponseObject, ResponseStreamEvent
from azure.ai.agentserver.responses.streaming._checkpoint import ResponseCheckpointEvent
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route, Router
from starlette.types import Send

from ._request import (
    HostedResponseRequest,
    OptionsHook,
    WorkflowTurn,
    prepare_response_options,
    response_run_options,
    validate_request_options,
)
from ._responses import (
    _HOSTED_PROVIDER_USAGE_KEY,  # pyright: ignore[reportPrivateUsage]
    _agent_response_updates,  # pyright: ignore[reportPrivateUsage]
    _item_to_message,  # pyright: ignore[reportPrivateUsage]
    _OutputItemTracker,  # pyright: ignore[reportPrivateUsage]
    _SignalledIterator,  # pyright: ignore[reportPrivateUsage]
)
from ._scope import FoundryRequestScope
from ._state_store import CheckpointStoreProvider, ContextScopedStoreProvider
from ._workflow_source import WorkflowResolver, WorkflowSource, prepare_workflow_kwargs, workflow_agents
from ._workflow_state import HostedWorkflowRun, WorkflowConflictError

logger = logging.getLogger(__name__)


@dataclass
class _NativeStreamLifetime:
    events: _SignalledIterator[ResponseStreamEvent | ResponseCheckpointEvent] | None = None


_NATIVE_STREAM_LIFETIME: ContextVar[_NativeStreamLifetime | None] = ContextVar(
    "foundry_native_responses_stream_lifetime", default=None
)


class _NativeWorkflowStreamingResponse(StreamingResponse):
    """Close native work and the SDK's public body iterator in its owning streaming task."""

    def __init__(self, response: StreamingResponse, *, keep_alive: bool) -> None:
        super().__init__(
            response.body_iterator,
            status_code=response.status_code,
            media_type=response.media_type,
            background=response.background,
        )
        self.raw_headers = list(response.raw_headers)
        self._lifetime = _NativeStreamLifetime()
        self._keep_alive = keep_alive

    async def stream_response(self, send: Send) -> None:
        token = _NATIVE_STREAM_LIFETIME.set(self._lifetime)
        try:
            await super().stream_response(send)
        finally:
            with CancelScope(shield=True):
                if self._keep_alive:
                    close = getattr(self.body_iterator, "aclose", None)
                    if callable(close):
                        result = close()
                        if inspect.isawaitable(result):
                            await result
                try:
                    if self._lifetime.events is not None:
                        await self._lifetime.events.aclose()
                finally:
                    async for _ in self.body_iterator:
                        pass
            _NATIVE_STREAM_LIFETIME.reset(token)


class _WorkflowRequestError(ValueError):
    """A neutral, actionable native protocol validation error."""


def _wire_value(value: Any) -> Any:
    """Encode explicit data types without arbitrary to_dict, repr, or private provider tokens."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (AgentResponse, ChatResponse)):
        return {
            "messages": [_wire_value(message) for message in value.messages],
            "usage_details": _wire_value(value.usage_details),
            "finish_reason": value.finish_reason,
        }
    if isinstance(value, (AgentResponseUpdate, ChatResponseUpdate)):
        return {"contents": [_wire_value(content) for content in value.contents], "finish_reason": value.finish_reason}
    if isinstance(value, (Content, Message)):
        return _wire_value(value.to_dict())
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _wire_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, Any], value)
        if any(not isinstance(key, str) for key in mapping):
            raise TypeError("Workflow JSON output keys must be strings.")
        return {key: _wire_value(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple)):
        return [_wire_value(item) for item in cast(list[Any] | tuple[Any, ...], value)]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("The workflow output is not a supported JSON or framework data type.")


def _snapshot(stream: ResponseEventStream) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(_wire_value(stream.response), allow_nan=False)))


async def _load_replies(request: HostedResponseRequest, run: HostedWorkflowRun) -> dict[str, Any]:
    items = await request.get_input_items()
    if not run.pending_requests or not items:
        raise _WorkflowRequestError("Workflow replies require an exact pending stored checkpoint.")
    replies: dict[str, Any] = {}
    for input_item in items:
        item = cast(Mapping[str, Any], input_item)
        if item.get("type") == "mcp_approval_response":
            wire_id, decision = item.get("approval_request_id"), item.get("approve")
            if not isinstance(wire_id, str) or type(decision) is not bool:
                raise _WorkflowRequestError("An approval reply requires its exact ID and a boolean decision.")
            request_id = run.approvals.get(wire_id)
            pending = run.pending_requests.get(request_id) if request_id is not None else None
            if (
                pending is None
                or not isinstance(pending.data, Content)
                or pending.data.type != "function_approval_request"
            ):
                raise _WorkflowRequestError("The approval is unavailable in this exact pending checkpoint.")
            response = pending.data.to_function_approval_response(decision)
        elif item.get("type") in ("function_call_output", "computer_call_output"):
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or not call_id:
                raise _WorkflowRequestError("A workflow reply requires its pending call ID.")
            request_id = run.approvals.get(call_id)
            if request_id is None or request_id not in run.pending_requests:
                raise _WorkflowRequestError("A reply must match its wire ID in the exact pending workflow checkpoint.")
            pending = run.pending_requests[request_id]
            if isinstance(pending.data, Content) and pending.data.type == "function_approval_request":
                raise _WorkflowRequestError("An approval cannot be replaced by a function result.")
            if item.get("type") == "computer_call_output":
                message = await _item_to_message(input_item)
                if len(message.contents) != 1:
                    raise _WorkflowRequestError(
                        "A computer reply requires a typed screenshot and safety acknowledgement."
                    )
                response = message.contents[0]
                if not isinstance(pending.data, Content) or pending.data.type != "computer_tool_call":
                    raise _WorkflowRequestError("The computer reply has no matching pending computer request.")
                response.call_id = pending.data.call_id
            elif (
                pending.response_type is Content
                and isinstance(pending.data, Content)
                and pending.data.type == "function_call"
            ):
                if not pending.data.call_id:
                    raise _WorkflowRequestError("The pending function call has no valid correlation ID.")
                response = Content.from_function_result(pending.data.call_id, result=item.get("output"))
            else:
                response = item.get("output")
                if isinstance(response, str) and pending.response_type not in (str, Content):
                    try:
                        response = json.loads(response)
                    except json.JSONDecodeError as exc:
                        raise _WorkflowRequestError("A typed workflow reply must contain valid JSON.") from exc
        else:
            raise _WorkflowRequestError("Pending workflow replies cannot be mixed with new input.")
        if request_id is None or request_id in replies:
            raise _WorkflowRequestError("Duplicate workflow replies are not allowed.")
        replies[request_id] = response
    if set(replies) != set(run.pending_requests):
        raise _WorkflowRequestError("Answer exactly the complete pending workflow request batch.")
    validated = run.validate_turn(WorkflowTurn(responses=replies))
    return dict(validated.responses or {})


class _CheckpointApprovals:
    """Collect wire aliases in the same per-response pair as the pending checkpoint."""

    def __init__(self, checkpoint: WorkflowCheckpoint | None, aliases: dict[str, str]) -> None:
        self.pending = checkpoint.pending_request_info_events if checkpoint is not None else {}
        self.aliases = aliases

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        matches = [
            request_id
            for request_id, event in self.pending.items()
            if isinstance(event.data, Content) and event.data.to_dict() == request.to_dict()
        ]
        if len(matches) != 1 or matches[0] in self.aliases.values():
            raise _WorkflowRequestError("Approval output must match one unique request in the exact pause checkpoint.")
        self.aliases[approval_request_id] = matches[0]

    async def load_approval_request(self, approval_request_id: str) -> Content:
        request_id = self.aliases.get(approval_request_id)
        event = self.pending.get(request_id) if request_id is not None else None
        if event is None or not isinstance(event.data, Content):
            raise _WorkflowRequestError("The approval is unavailable in this pending checkpoint.")
        return event.data


async def _project(
    event: WorkflowEvent[Any],
    stream: ResponseEventStream,
    tracker: _OutputItemTracker,
    approvals: _CheckpointApprovals,
) -> list[ResponseStreamEvent]:
    updates: list[AgentResponseUpdate] = []
    if event.type == "request_info":
        wire_id = IdGenerator.new_id("call", str(stream.response["id"]))
        if isinstance(event.data, Content) and event.data.type == "function_approval_request":
            content = event.data
        elif isinstance(event.data, Content) and event.data.type in ("function_call", "computer_tool_call"):
            content = Content.from_dict(event.data.to_dict())
            content.call_id = wire_id
            approvals.aliases[wire_id] = event.request_id
        else:
            content = Content.from_function_call(
                wire_id,
                "request_info",
                arguments={"request_id": wire_id, "request": _wire_value(event.data)},
            )
            approvals.aliases[wire_id] = event.request_id
            if isinstance(event.data, Content) and event.data.type == "oauth_consent_request":
                updates.append(AgentResponseUpdate(contents=[event.data]))
        updates.append(AgentResponseUpdate(contents=[content]))
    elif event.type in ("output", "intermediate", "data"):
        data = event.data
        if isinstance(data, (AgentResponse, ChatResponse)):
            updates = _agent_response_updates(
                AgentResponse(
                    messages=data.messages,
                    usage_details=data.usage_details,
                    finish_reason=FinishReason(data.finish_reason) if data.finish_reason is not None else None,
                ),
                str(stream.response["id"]),
            )
        elif isinstance(data, (AgentResponseUpdate, ChatResponseUpdate)):
            updates = [
                AgentResponseUpdate(
                    contents=list(data.contents),
                    role=data.role,
                    message_id=data.message_id,
                    finish_reason=FinishReason(data.finish_reason) if data.finish_reason is not None else None,
                )
            ]
        elif isinstance(data, Message):
            updates = _agent_response_updates(AgentResponse(messages=[data]), str(stream.response["id"]))
        elif isinstance(data, list) and data and all(isinstance(item, Message) for item in cast(list[Any], data)):
            updates = _agent_response_updates(
                AgentResponse(messages=cast(list[Message], data)), str(stream.response["id"])
            )
        elif isinstance(data, Content):
            updates = [AgentResponseUpdate(contents=[data], message_id=uuid.uuid4().hex)]
        elif isinstance(data, str):
            updates = [AgentResponseUpdate(contents=[Content.from_text(data)], message_id=uuid.uuid4().hex)]
        else:
            value = _wire_value(data)
            json.dumps(value, allow_nan=False)
            events = list(tracker.close())
            events.extend([item async for item in stream.output_item_structured_outputs(value)])
            return events
    events: list[ResponseStreamEvent] = []
    for update in updates:
        events.extend([item async for item in tracker.handle_update(update, approval_storage=approvals)])
    return events


class NativeResponsesWorkflow:
    """The native-only adapter; ordinary agents and legacy wrapper machinery remain separate."""

    def __init__(
        self,
        source: WorkflowSource[HostedResponseRequest],
        parser: Callable[[HostedResponseRequest], WorkflowTurn[Any] | Awaitable[WorkflowTurn[Any]]],
        *,
        config: AgentConfig,
        checkpoint_store_provider: ContextScopedStoreProvider[CheckpointStorage],
        prepare_options: OptionsHook | None,
        resilient_background: bool,
        allowed_oauth_consent_origins: frozenset[str] | None,
    ) -> None:
        self.resolver = WorkflowResolver(source)
        self.parser = parser
        self.config = config
        self.checkpoint_store_provider = checkpoint_store_provider
        self.options_hook = prepare_options
        self.resilient_background = resilient_background
        self.allowed_origins = allowed_oauth_consent_origins

    def bind_streaming_route(self, router: Router, *, prefix: str, keep_alive: bool) -> None:
        """Adapt only the native POST route's public StreamingResponse cleanup lifetime."""
        path = f"/{prefix.strip('/')}/responses" if prefix.strip("/") else "/responses"
        for index, route in enumerate(router.routes):
            if not isinstance(route, Route) or route.path != path or "POST" not in (route.methods or ()):
                continue
            endpoint = cast(Callable[[Request], Awaitable[Response]], route.endpoint)

            async def native_endpoint(
                request: Request, handler: Callable[[Request], Awaitable[Response]] = endpoint
            ) -> Response:
                response = await handler(request)
                if isinstance(response, StreamingResponse):
                    return _NativeWorkflowStreamingResponse(response, keep_alive=keep_alive)
                return response

            router.routes[index] = Route(
                route.path,
                endpoint=native_endpoint,
                methods=list(route.methods or ()),
                name=route.name,
                include_in_schema=route.include_in_schema,
            )
            return
        raise RuntimeError("The native Responses streaming route is unavailable.")

    async def response_events(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncGenerator[ResponseStreamEvent | ResponseCheckpointEvent]:
        """Keep factory, resources, and native generator cleanup in one persistent task."""
        lifetime = _NATIVE_STREAM_LIFETIME.get()
        inner = self.handle_response(request, context, cancellation_signal)
        if lifetime is None or request.get("background") is True:
            async with aclosing(inner):
                async for event in inner:
                    yield event
            return
        events = _SignalledIterator(inner)
        lifetime.events = events
        async with aclosing(events):
            async for event in events:
                yield event

    async def handle_response(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncGenerator[ResponseStreamEvent | ResponseCheckpointEvent]:
        """Validate, run, pair, close owned resources, and only then publish terminal success."""
        stream = ResponseEventStream(response_id=context.response_id, request=request)
        run: HostedWorkflowRun | None = None
        phase = "preparation"
        completed = False
        preserve_for_recovery = False
        resources: AsyncExitStack | None = None
        sequence = 0

        def wire(event: ResponseStreamEvent) -> ResponseStreamEvent:
            nonlocal sequence
            payload = dict(event)
            payload["sequence_number"] = sequence
            sequence += 1
            return cast(ResponseStreamEvent, payload)

        async def abort() -> bool:
            if run is None:
                return True
            try:
                await run.abort()
            except Exception as exc:
                logger.error("Native workflow abort persistence failed (%s).", type(exc).__name__)
                return False
            return True

        try:
            platform_context = get_request_context()
            scope = FoundryRequestScope.from_context(
                self.config, platform_context, local_session_id=context.response_id
            )
            hosted = HostedResponseRequest(request, context, scope, response_run_options(request))
            await prepare_response_options(hosted, self.options_hook)
            validate_request_options(hosted.options)
            workflow = await self.resolver.resolve(hosted)
            resources = AsyncExitStack()
            await resources.__aenter__()
            for agent in workflow_agents(workflow):
                if isinstance(agent, AbstractAsyncContextManager):
                    await resources.enter_async_context(agent)
            resilient = (
                self.resilient_background and request.get("background") is True and request.get("store") is not False
            )
            if context.is_recovery and not resilient:
                raise _WorkflowRequestError("Native workflow recovery requires a stored resilient background response.")
            if not self.resolver.is_factory and (
                context.is_recovery
                or context.conversation_id is not None
                or request.get("previous_response_id") is not None
            ):
                raise _WorkflowRequestError("Native workflow continuation requires a fresh request-aware factory.")
            phase = "scoped continuation"
            run = await HostedWorkflowRun.prepare(
                workflow,
                scope=scope,
                response_id=context.response_id,
                config=self.config,
                platform_context=platform_context,
                checkpoint_store_provider=self.checkpoint_store_provider,
                previous_response_id=request.get("previous_response_id"),
                conversation_id=context.conversation_id,
                stored=request.get("store") is not False,
                recovery=context.is_recovery,
                fresh_factory=self.resolver.is_factory,
            )
            if context.is_recovery and run.snapshot is not None:
                if run.snapshot.get("id") != context.response_id:
                    raise _WorkflowRequestError("The recovered output does not match this exact outer response.")
                stream = ResponseEventStream(
                    response_id=context.response_id, response=cast(ResponseObject, run.snapshot)
                )
            yield wire(stream.emit_created())
            yield wire(stream.emit_in_progress())
            hosted._set_workflow_responses(lambda: _load_replies(hosted, run))  # pyright: ignore[reportPrivateUsage]
            phase = "input parsing"
            turn = run.recovery_turn() if context.is_recovery else self.parser(hosted)
            if inspect.isawaitable(turn):
                turn = await turn
            phase = "input validation"
            turn = run.validate_turn(turn)
            if (
                run.stored
                and turn.input is not None
                and isinstance(self.checkpoint_store_provider, CheckpointStoreProvider)
            ):
                try:
                    self.checkpoint_store_provider.validate_checkpoint_value(turn.input)
                except WorkflowCheckpointException as exc:
                    raise _WorkflowRequestError(
                        "Stored native workflow input uses an application type that is not checkpoint-allowlisted. "
                        'Configure CheckpointStoreProvider(allowed_checkpoint_types=["module:qualname"]).'
                    ) from exc
            client_kwargs, function_kwargs = prepare_workflow_kwargs(
                workflow,
                turn,
                scope,
                options=hosted.options,
                stored=run.stored,
                fresh_factory=self.resolver.is_factory,
            )
            if cancellation_signal.is_set():
                return
            await run.claim()
            aliases = dict(run.approvals) if context.is_recovery else {}
            represented_pending: set[str] = set(run.pending_requests) if context.is_recovery else set()
            buffered: list[WorkflowEvent[Any]] = []
            tracker = _OutputItemTracker(stream, self.allowed_origins)

            async def flush(checkpoint_id: str | None) -> list[ResponseStreamEvent]:
                nonlocal stream, tracker, aliases
                checkpoint = await run.get_checkpoint(checkpoint_id) if run.stored else None
                pending = checkpoint.pending_request_info_events if checkpoint is not None else {}
                next_aliases = {key: value for key, value in aliases.items() if value in pending}
                draft = ResponseEventStream(
                    response_id=context.response_id, response=cast(ResponseObject, _snapshot(stream))
                )
                draft.emit_created()
                draft.emit_in_progress()
                next_tracker = _OutputItemTracker(draft, self.allowed_origins)
                approval_projection = _CheckpointApprovals(checkpoint, next_aliases)
                events: list[ResponseStreamEvent] = []
                for event in buffered:
                    events.extend(await _project(event, draft, next_tracker, approval_projection))
                events.extend(next_tracker.close())
                draft.internal_metadata[_HOSTED_PROVIDER_USAGE_KEY] = next_tracker.usage_details
                await run.stage(_snapshot(draft), approvals=next_aliases, checkpoint_id=checkpoint_id)
                stream, tracker, aliases = draft, next_tracker, next_aliases
                buffered.clear()
                return events

            async def checkpoint_stamp() -> str | None:  # ruff: ignore[unused-async]
                return run.checkpoint_id

            phase = "execution"
            if not run.has_completed_output:
                iterator = _SignalledIterator(
                    run.events(turn, client_kwargs=client_kwargs, function_invocation_kwargs=function_kwargs),
                    context.shutdown,
                    cancellation_signal,
                    stamp=checkpoint_stamp,
                )
                async with aclosing(iterator):
                    async for event in iterator:
                        if event.type == "request_info" and event.request_id not in represented_pending:
                            if not self.resolver.is_factory:
                                raise _WorkflowRequestError(
                                    "A pausing native workflow requires a fresh request-aware factory."
                                )
                            buffered.append(event)
                        elif event.type in ("output", "intermediate", "data"):
                            buffered.append(event)
                        elif event.type == "superstep_started" and run.stored and run.snapshot is None:
                            await run.stage(_snapshot(stream), checkpoint_id=iterator.stamp)
                            if resilient:
                                yield stream.checkpoint()
                        elif event.type == "superstep_completed":
                            for output_event in await flush(iterator.stamp):
                                yield wire(output_event)
                            if resilient:
                                yield stream.checkpoint()
                if iterator.signalled:
                    if context.shutdown.is_set() and resilient and run.snapshot is not None:
                        preserve_for_recovery = True
                        await context.exit_for_recovery()
                    if cancellation_signal.is_set():
                        await abort()
                        return
                    raise _WorkflowRequestError("The workflow stopped without a recoverable background pair.")
            if cancellation_signal.is_set():
                await abort()
                return
            phase = "final output persistence"
            if buffered:
                for event in await flush(run.checkpoint_id):
                    yield wire(event)
            terminal = (
                stream.emit_incomplete(reason=tracker.incomplete_reason, usage=tracker.usage)
                if tracker.oauth_consent_requested or tracker.incomplete_reason is not None
                else stream.emit_completed(usage=tracker.usage)
            )
            await run.commit(_snapshot(stream))
            completed = True
            yield wire(terminal)
        except (asyncio.CancelledError, GeneratorExit):
            if not preserve_for_recovery:
                await abort()
            raise
        except Exception as exc:
            preserve_for_recovery = False
            logger.error("Native Responses workflow failed during %s (%s).", phase, type(exc).__name__)
            persisted_abort = await abort()
            message = (
                str(exc)
                if isinstance(exc, (_WorkflowRequestError, WorkflowConflictError))
                else f"Native workflow {phase} failed. Validate the typed input and current scoped continuation, "
                "or start a fresh workflow lineage."
            )
            if not persisted_abort:
                message = "Workflow persistence failed; start a fresh workflow lineage and inspect the host logs."
            if sequence == 0:
                yield wire(stream.emit_created())
                yield wire(stream.emit_in_progress())
            yield wire(stream.emit_failed(message=message))
        finally:
            try:
                if not completed and not preserve_for_recovery:
                    await abort()
            finally:
                if resources is not None:
                    await resources.aclose()
