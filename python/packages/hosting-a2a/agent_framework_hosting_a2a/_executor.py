# Copyright (c) Microsoft. All rights reserved.

"""Host-routed A2A :class:`AgentExecutor`.

Unlike ``agent_framework_a2a.A2AExecutor`` (which calls ``agent.run`` directly
and manages its own session), :class:`HostAgentExecutor` routes every incoming
A2A request through the host pipeline via :class:`ChannelContext` — so host
session resolution, request metadata, and run/response hooks all apply. The A2A
``context_id`` maps onto :class:`ChannelSession` (caller-supplied session
family).
"""

from __future__ import annotations

import base64
import re
from asyncio import CancelledError
from dataclasses import replace
from typing import Any, cast

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState
from agent_framework import Content
from agent_framework import Message as AFMessage
from agent_framework_hosting import (
    ChannelContext,
    ChannelIdentity,
    ChannelRequest,
    ChannelResponseHook,
    ChannelRunHook,
    ChannelSession,
    logger,
)

try:
    from a2a.helpers import new_task_from_user_message
except ImportError:  # pragma: no cover - older a2a-sdk layout
    from a2a.utils import new_task_from_user_message  # type: ignore[no-redef, attr-defined, import-not-found]

_DATA_URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<data>[A-Za-z0-9+/=]+)$")


def _contents_to_parts(contents: list[Content]) -> list[Part]:
    """Convert Agent Framework contents into A2A parts (text, uri, inline data)."""
    parts: list[Part] = []
    for content in contents:
        if content.type == "text" and content.text:
            parts.append(Part(text=content.text))
        elif content.type == "uri" and content.uri:
            parts.append(Part(url=content.uri, media_type=content.media_type or ""))
        elif content.type == "data" and content.uri:
            match = _DATA_URI_PATTERN.match(content.uri)
            if match is None:
                logger.warning("A2AChannel could not parse data URI; omitted.")
                continue
            parts.append(Part(raw=base64.b64decode(match.group("data")), media_type=content.media_type or ""))
        else:
            logger.warning("A2AChannel does not support content type: %s. Omitted.", content.type)
    return parts


def _value_to_parts(value: Any) -> list[Part]:
    """Convert workflow outputs and fallback values into A2A parts."""
    if isinstance(value, Content):
        return _contents_to_parts([value])
    if isinstance(value, AFMessage):
        return _contents_to_parts(list(value.contents))
    if isinstance(value, str):
        return [Part(text=value)]
    return [Part(text=str(value))]


def _strip_options_hook(request: ChannelRequest, **_: Any) -> ChannelRequest:
    """Default run hook: remove all parsed options before reaching the agent.

    When no custom ``run_hook`` is configured this prevents untrusted A2A
    callers from injecting generation parameters. Supply a custom hook to
    forward or transform specific options.
    """
    return replace(request, options=None)


class HostAgentExecutor(AgentExecutor):
    """A2A executor that drives the hosted target through :class:`ChannelContext`."""

    def __init__(
        self,
        context: ChannelContext,
        *,
        channel_name: str,
        streaming: bool = True,
        run_hook: ChannelRunHook | None = None,
        response_hook: ChannelResponseHook | None = None,
    ) -> None:
        """Bind the executor to the host context.

        Args:
            context: The host-supplied :class:`ChannelContext`.

        Keyword Args:
            channel_name: The owning channel's name (stamped on requests).
            streaming: When ``True`` (default) the target is consumed via
                :meth:`ChannelContext.run_stream` and incremental updates are
                published as A2A task artifacts; otherwise the full reply is
                published as a single working-state message.
            run_hook: Optional :data:`ChannelRunHook` applied to the request.
                When omitted, a default hook that strips all caller-supplied
                options is applied so untrusted A2A callers cannot inject
                generation parameters.
            response_hook: Optional :data:`ChannelResponseHook` applied to the
                originating final response.
        """
        super().__init__()
        self._ctx = context
        self._channel_name = channel_name
        self._streaming = streaming
        self._run_hook: ChannelRunHook = run_hook if run_hook is not None else _strip_options_hook
        self._response_hook = response_hook

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Publish a cancellation event for the in-flight task."""
        if context.context_id is None:
            raise ValueError("Context ID must be provided in the RequestContext")
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id)
        await updater.cancel()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Route an A2A request through the host and publish task events."""
        if context.context_id is None:
            raise ValueError("Context ID must be provided in the RequestContext")
        if context.message is None:
            raise ValueError("Message must be provided in the RequestContext")

        query = context.get_user_input()
        task: Task | None = context.current_task
        if not task:
            task = cast(Task, new_task_from_user_message(context.message))
            await event_queue.enqueue_event(task)

        task_id: str = task.id
        updater = TaskUpdater(event_queue, task_id, context.context_id)
        await updater.submit()

        try:
            await updater.start_work()
            request = self._build_request(query, context, task_id)
            if request.stream:
                await self._run_stream(request, updater, protocol_request=context.message)
            else:
                await self._run(request, updater, protocol_request=context.message)
            await updater.complete()
        except CancelledError:
            await updater.update_status(state=TaskState.TASK_STATE_CANCELED)
        except Exception as exc:
            logger.exception("A2AChannel encountered an error during execution.")
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=updater.new_agent_message([Part(text=str(exc))]),
            )

    def _build_request(self, query: Any, context: RequestContext, task_id: str) -> ChannelRequest:
        """Build the channel-neutral request from the A2A request context."""
        context_id = cast(str, context.context_id)
        return ChannelRequest(
            channel=self._channel_name,
            operation="message.create",
            input=query if isinstance(query, str) else str(query),
            session=ChannelSession(isolation_key=context_id),
            stream=self._streaming,
            identity=ChannelIdentity(channel=self._channel_name, native_id=context_id),
            attributes={"task_id": task_id},
        )

    async def _run(self, request: ChannelRequest, updater: TaskUpdater, *, protocol_request: Any) -> None:
        """Non-streaming: run the target and publish the reply as task messages."""
        result = await self._ctx.run(
            request,
            run_hook=self._run_hook,
            protocol_request=protocol_request,
            response_hook=self._response_hook,
            channel_name=self._channel_name,
        )
        response: Any = result.result
        messages: list[Any] = list(getattr(response, "messages", None) or [])
        get_outputs = cast("Any", getattr(response, "get_outputs", None))
        if callable(get_outputs):
            messages.extend(cast("list[Any]", get_outputs()))
        for message in messages:
            if getattr(message, "role", None) == "user":
                continue
            parts = _value_to_parts(message)
            if parts:
                await updater.update_status(
                    state=TaskState.TASK_STATE_WORKING,
                    message=updater.new_agent_message(parts=parts),
                )

    async def _run_stream(self, request: ChannelRequest, updater: TaskUpdater, *, protocol_request: Any) -> None:
        """Streaming: publish incremental updates as task artifacts."""
        stream_artifact_id = f"{request.attributes.get('task_id', 'stream')}:stream"
        appended = False
        stream = await self._ctx.run_stream(
            request,
            run_hook=self._run_hook,
            protocol_request=protocol_request,
            response_hook=self._response_hook,
            channel_name=self._channel_name,
        )
        async for update in stream:
            parts = _contents_to_parts(update.contents)
            if not parts:
                continue
            await updater.add_artifact(
                parts=parts,
                artifact_id=stream_artifact_id,
                append=True if appended else None,
            )
            appended = True
        await stream.get_final_response()
