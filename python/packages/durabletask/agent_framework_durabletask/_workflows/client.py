# Copyright (c) Microsoft. All rights reserved.

"""Workflow client wrapper for Durable Task Agent Framework.

This module provides :class:`DurableWorkflowClient` for external clients to start,
await, and drive (including human-in-the-loop) workflows registered on a worker via
``DurableAIAgentWorker.configure_workflow``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any, cast

from agent_framework import WorkflowEvent
from durabletask.client import TaskHubGrpcClient

from .orchestrator import WORKFLOW_ORCHESTRATOR_NAME
from .serialization import deserialize_workflow_event, deserialize_workflow_output, strip_pickle_markers

logger = logging.getLogger("agent_framework.durabletask")


class DurableWorkflowClient:
    """Client wrapper for starting and driving durable workflows externally.

    This class wraps a durabletask ``TaskHubGrpcClient`` and provides a convenient
    interface for the workflow registered by ``DurableAIAgentWorker.configure_workflow``:
    starting it, awaiting its output, and responding to human-in-the-loop (HITL) pauses.

    For interacting with individual durable *agents*, use
    :class:`~agent_framework_durabletask.DurableAIAgentClient` instead. Both wrap the
    same underlying ``TaskHubGrpcClient``, so an application that needs both can
    construct both over one client.

    Example:
        ```python
        from durabletask.azuremanaged.client import DurableTaskSchedulerClient
        from agent_framework.azure import DurableWorkflowClient

        # Create the underlying client
        client = DurableTaskSchedulerClient(host_address="localhost:8080", taskhub="default")

        # Wrap it with the workflow client
        workflow_client = DurableWorkflowClient(client)

        # Start a workflow and wait for its output
        instance_id = workflow_client.start_workflow(input="some input")
        output = workflow_client.await_workflow_output(instance_id)
        print(output)
        ```
    """

    def __init__(self, client: TaskHubGrpcClient):
        """Initialize the workflow client wrapper.

        Args:
            client: The durabletask client instance to wrap.
        """
        self._client = client
        logger.debug("[DurableWorkflowClient] Initialized with client type: %s", type(client).__name__)

    def start_workflow(self, input: Any = None, *, instance_id: str | None = None) -> str:
        """Start the workflow orchestration registered by ``configure_workflow``.

        This schedules the orchestrator that ``DurableAIAgentWorker.configure_workflow``
        auto-registers, so callers do not need to know its internal name.

        Args:
            input: The initial message/payload for the workflow.
            instance_id: Optional explicit orchestration instance ID. If omitted, one
                is generated.

        Returns:
            The orchestration instance ID, for use with ``await_workflow_output``.
        """
        new_instance_id = self._client.schedule_new_orchestration(
            WORKFLOW_ORCHESTRATOR_NAME,
            input=input,
            instance_id=instance_id,
        )
        logger.debug("[DurableWorkflowClient] Started workflow instance: %s", new_instance_id)
        return new_instance_id

    def await_workflow_output(self, instance_id: str, *, timeout_seconds: int = 300) -> Any:
        """Wait for a workflow orchestration to complete and return its output.

        Args:
            instance_id: The instance ID returned by ``start_workflow``.
            timeout_seconds: Maximum time, in seconds, to wait for completion.

        Returns:
            The deserialized workflow output (typically a list of yielded outputs),
            or ``None`` if the workflow produced no output.

        Raises:
            TimeoutError: If the workflow does not complete within ``timeout_seconds``.
            RuntimeError: If the workflow completes with a non-successful status.
        """
        metadata = self._client.wait_for_orchestration_completion(instance_id, timeout=timeout_seconds)
        if metadata is None:
            raise TimeoutError(f"Workflow '{instance_id}' did not complete within {timeout_seconds}s")

        status = metadata.runtime_status.name
        if status != "COMPLETED":
            raise RuntimeError(f"Workflow '{instance_id}' ended with status {status}: {metadata.serialized_output}")

        if metadata.serialized_output is None:
            return None
        # The shared activity encodes each yielded output with serialize_value()
        # before it reaches the orchestrator, so typed objects come back as
        # checkpoint-marker dicts. Reconstruct the originals before returning.
        return deserialize_workflow_output(json.loads(metadata.serialized_output))

    async def run_workflow(
        self,
        input: Any = None,
        *,
        instance_id: str | None = None,
        wait: bool = True,
        timeout_seconds: int = 300,
    ) -> Any:
        """Start the workflow and, by default, await its output.

        The async counterpart to ``start_workflow`` + ``await_workflow_output``. The
        underlying durabletask client is synchronous, so the blocking calls run in a
        worker thread to avoid blocking the event loop.

        Args:
            input: The initial message/payload for the workflow.
            instance_id: Optional explicit orchestration instance ID. If omitted,
                one is generated.
            wait: When ``True`` (default), wait for completion and return the
                deserialized output. When ``False``, return the instance ID as
                soon as the workflow is scheduled (use with ``stream_workflow`` or
                the HITL methods).
            timeout_seconds: Maximum time, in seconds, to wait for completion when
                ``wait`` is ``True``.

        Returns:
            The deserialized workflow output when ``wait`` is ``True``; otherwise
            the orchestration instance ID.

        Raises:
            TimeoutError: If ``wait`` is ``True`` and the workflow does not complete
                within ``timeout_seconds``.
            RuntimeError: If ``wait`` is ``True`` and the workflow ends with a
                non-successful status.
        """
        new_instance_id = await asyncio.to_thread(self.start_workflow, input, instance_id=instance_id)
        if not wait:
            return new_instance_id
        return await asyncio.to_thread(self.await_workflow_output, new_instance_id, timeout_seconds=timeout_seconds)

    def get_runtime_status(self, instance_id: str) -> str | None:
        """Return the workflow's current runtime status name, or ``None`` if unknown.

        Lets callers distinguish a workflow that is still running or paused for
        human input from one that has reached a terminal state (for example
        ``COMPLETED``, ``FAILED``, or ``TERMINATED``) — useful when polling, so a
        workflow that ends without pausing is not mistaken for one that never paused.

        Args:
            instance_id: The instance ID returned by ``start_workflow``.

        Returns:
            The runtime status name (e.g. ``"RUNNING"``, ``"COMPLETED"``), or
            ``None`` if no state is available for the instance.
        """
        state = self._client.get_orchestration_state(instance_id)
        if state is None:
            return None
        return state.runtime_status.name

    async def stream_workflow(
        self,
        instance_id: str,
        *,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[WorkflowEvent]:
        """Stream the workflow's events as typed :class:`WorkflowEvent` objects.

        Yields the workflow's events (``executor_invoked`` / ``executor_completed`` /
        ``output`` / ``request_info`` / ...) in order, finishing when the workflow
        reaches a terminal state. Each event's ``data`` payload is already
        reconstructed into its original typed object, so callers do not deserialize
        anything themselves.

        This is brokerless: it polls the orchestration custom status, into which the
        orchestrator publishes accumulated events after each superstep. Granularity is
        per executor and per yielded output, not token-level. Non-agent executors emit
        events with data payloads; agent executors emit coarse ``executor_invoked`` /
        ``executor_completed`` lifecycle events. The custom status accumulates events
        for the run, so this suits workflows with a bounded number of executors rather
        than very long-running fan-outs.

        Args:
            instance_id: The instance ID returned by ``start_workflow``.
            poll_interval_seconds: Delay between status polls.
            timeout_seconds: Optional overall timeout; ``None`` streams until the
                workflow reaches a terminal state.

        Yields:
            :class:`WorkflowEvent` objects as the workflow progresses.

        Raises:
            TimeoutError: If ``timeout_seconds`` elapses before completion.
        """
        cursor = 0
        terminal_statuses = {"COMPLETED", "FAILED", "TERMINATED"}
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds

        while True:
            state = await asyncio.to_thread(self._client.get_orchestration_state, instance_id)

            if state is not None and state.serialized_custom_status:
                try:
                    status = json.loads(state.serialized_custom_status)
                except (json.JSONDecodeError, TypeError):
                    status = None
                if isinstance(status, dict):
                    events = cast("dict[str, Any]", status).get("events")
                    if isinstance(events, list):
                        typed_events = cast("list[dict[str, Any]]", events)
                        while cursor < len(typed_events):
                            yield deserialize_workflow_event(typed_events[cursor])
                            cursor += 1

            runtime_status = state.runtime_status.name if state is not None else None
            if runtime_status in terminal_statuses:
                return

            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Workflow '{instance_id}' did not complete within {timeout_seconds}s")

            await asyncio.sleep(poll_interval_seconds)

    def get_pending_hitl_requests(self, instance_id: str) -> list[dict[str, Any]]:
        """Return the workflow's pending human-in-the-loop (HITL) requests, if any.

        While a workflow is paused awaiting human input, the orchestrator records the
        open requests in its custom status. This method reads and normalizes that
        status so callers do not need to know its internal schema.

        Args:
            instance_id: The workflow instance ID returned by ``start_workflow``.

        Returns:
            A list of pending requests. Each entry contains ``request_id``,
            ``source_executor_id``, ``data``, ``request_type``, and ``response_type``.
            Empty if the workflow is not currently waiting for human input.
        """
        state = self._client.get_orchestration_state(instance_id)
        if state is None or not state.serialized_custom_status:
            return []

        try:
            custom_status = json.loads(state.serialized_custom_status)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(custom_status, dict):
            return []
        status_dict = cast(dict[str, Any], custom_status)

        pending = status_dict.get("pending_requests")
        if not isinstance(pending, dict):
            return []
        pending_dict = cast(dict[str, Any], pending)

        requests: list[dict[str, Any]] = []
        for request_id, req_data in pending_dict.items():
            if not isinstance(req_data, dict):
                continue
            req = cast(dict[str, Any], req_data)
            requests.append({
                "request_id": req.get("request_id", request_id),
                "source_executor_id": req.get("source_executor_id"),
                "data": req.get("data"),
                "request_type": req.get("request_type"),
                "response_type": req.get("response_type"),
            })
        return requests

    def send_hitl_response(self, instance_id: str, request_id: str, response: Any) -> None:
        """Send a response to a pending HITL request, resuming the workflow.

        The orchestrator correlates the response by using ``request_id`` as the
        external-event name, so callers do not need to know that convention.

        Args:
            instance_id: The workflow instance ID.
            request_id: The pending request's ID (from ``get_pending_hitl_requests``).
            response: The response payload (e.g. a dict matching the expected
                response type the executor's ``@response_handler`` expects).

        Note:
            The payload is sanitized with ``strip_pickle_markers`` before delivery to
            neutralize pickle-marker injection, since the worker deserializes it.
        """
        safe_response = strip_pickle_markers(response)
        self._client.raise_orchestration_event(instance_id, event_name=request_id, data=safe_response)
        logger.debug(
            "[DurableWorkflowClient] Sent HITL response for request %s on instance %s", request_id, instance_id
        )
