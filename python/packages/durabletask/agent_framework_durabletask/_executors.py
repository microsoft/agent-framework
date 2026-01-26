# Copyright (c) Microsoft. All rights reserved.

"""Provider strategies for Durable Agent execution.

These classes are internal execution strategies used by the DurableAIAgent shim.
They are intentionally separate from the public client/orchestration APIs to keep
only `get_agent` exposed to consumers. Executors implement the execution contract
and are injected into the shim.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from agent_framework import AgentResponse, AgentThread, ChatMessage, Content, Role, get_logger
from durabletask.client import TaskHubGrpcClient
from durabletask.entities import EntityInstanceId
from durabletask.task import CompletableTask, CompositeTask, OrchestrationContext, Task
from pydantic import BaseModel

from ._constants import DEFAULT_MAX_POLL_RETRIES, DEFAULT_POLL_INTERVAL_SECONDS
from ._durable_agent_state import DurableAgentState
from ._models import AgentSessionId, DurableAgentThread, RunRequest
from ._response_utils import ensure_response_format, load_agent_response

logger = get_logger("agent_framework.durabletask.executors")

# TypeVar for the task type returned by executors
TaskT = TypeVar("TaskT")


class DurableAgentTask(CompositeTask[AgentResponse], CompletableTask[AgentResponse]):
    """A custom Task that wraps entity calls and provides typed AgentResponse results.

    This task wraps the underlying entity call task and intercepts its completion
    to convert the raw result into a typed AgentResponse object.

    When yielded in an orchestration, this task returns an AgentResponse:
        response: AgentResponse = yield durable_agent_task
    """

    def __init__(
        self,
        entity_task: CompletableTask[Any],
        response_format: type[BaseModel] | None,
        correlation_id: str,
    ):
        """Initialize the DurableAgentTask.

        Args:
            entity_task: The underlying entity call task
            response_format: Optional Pydantic model for response parsing
            correlation_id: Correlation ID for logging
        """
        self._response_format = response_format
        self._correlation_id = correlation_id
        super().__init__([entity_task])  # type: ignore

    def on_child_completed(self, task: Task[Any]) -> None:
        """Handle completion of the underlying entity task.

        Parameters
        ----------
        task : Task
            The entity call task that just completed
        """
        if self.is_complete:
            return

        if task.is_failed:
            # Propagate the failure - pass the original exception directly
            self.fail("call_entity Task failed", task.get_exception())
            return

        # Task succeeded - transform the raw result
        raw_result = task.get_result()
        logger.debug(
            "[DurableAgentTask] Converting raw result for correlation_id %s",
            self._correlation_id,
        )

        try:
            response = load_agent_response(raw_result)

            if self._response_format is not None:
                ensure_response_format(
                    self._response_format,
                    self._correlation_id,
                    response,
                )

            # Set the typed AgentResponse as this task's result
            self.complete(response)

        except Exception as ex:
            err_msg = "[DurableAgentTask] Failed to convert result for correlation_id: " + self._correlation_id
            logger.exception(err_msg)
            self.fail(err_msg, ex)


class DurableAgentExecutor(ABC, Generic[TaskT]):
    """Abstract base class for durable agent execution strategies.

    Type Parameters:
        TaskT: The task type returned by this executor
    """

    @abstractmethod
    def run_durable_agent(
        self,
        agent_name: str,
        run_request: RunRequest,
        thread: AgentThread | None = None,
    ) -> TaskT:
        """Execute the durable agent.

        Returns:
            TaskT: The task type specific to this executor implementation
        """
        raise NotImplementedError

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> DurableAgentThread:
        """Create a new DurableAgentThread with random session ID."""
        session_id = self._create_session_id(agent_name)
        return DurableAgentThread.from_session_id(session_id, **kwargs)

    def _create_session_id(
        self,
        agent_name: str,
        thread: AgentThread | None = None,
    ) -> AgentSessionId:
        """Create the AgentSessionId for the execution."""
        if isinstance(thread, DurableAgentThread) and thread.session_id is not None:
            return thread.session_id
        # Create new session ID - either no thread provided or it's a regular AgentThread
        key = self.generate_unique_id()
        return AgentSessionId(name=agent_name, key=key)

    def generate_unique_id(self) -> str:
        """Generate a new Unique ID."""
        return uuid.uuid4().hex

    def get_run_request(
        self,
        message: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> RunRequest:
        """Create a RunRequest from message and options."""
        correlation_id = self.generate_unique_id()

        # Create a copy to avoid modifying the caller's dict
        opts = dict(options) if options else {}

        # Extract and REMOVE known keys from options copy
        response_format = opts.pop("response_format", None)
        enable_tool_calls = opts.pop("enable_tool_calls", True)
        wait_for_response = opts.pop("wait_for_response", True)

        return RunRequest(
            message=message,
            response_format=response_format,
            enable_tool_calls=enable_tool_calls,
            wait_for_response=wait_for_response,
            correlation_id=correlation_id,
            options=opts,
        )

    def _create_acceptance_response(self, correlation_id: str) -> AgentResponse:
        """Create an acceptance response for fire-and-forget mode.

        Args:
            correlation_id: Correlation ID for tracking the request

        Returns:
            AgentResponse: Acceptance response with correlation ID
        """
        acceptance_message = ChatMessage(
            role=Role.SYSTEM,
            contents=[
                Content.from_text(
                    f"Request accepted for processing (correlation_id: {correlation_id}). "
                    f"Agent is executing in the background. "
                    f"Retrieve response via your configured streaming or callback mechanism."
                )
            ],
        )
        return AgentResponse(
            messages=[acceptance_message],
            created_at=datetime.now(timezone.utc).isoformat(),
        )


class ClientAgentExecutor(DurableAgentExecutor[AgentResponse]):
    """Execution strategy for external clients.

    Note: Returns AgentResponse directly since the execution
    is blocking until response is available via polling
    as per the design of TaskHubGrpcClient.
    """

    def __init__(
        self,
        client: TaskHubGrpcClient,
        max_poll_retries: int = DEFAULT_MAX_POLL_RETRIES,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ):
        self._client = client
        self.max_poll_retries = max_poll_retries
        self.poll_interval_seconds = poll_interval_seconds

    def run_durable_agent(
        self,
        agent_name: str,
        run_request: RunRequest,
        thread: AgentThread | None = None,
    ) -> AgentResponse:
        """Execute the agent via the durabletask client.

        Signals the agent entity with a message request, then polls the entity
        state to retrieve the response once processing is complete.

        Note: This is a blocking/synchronous operation (in line with how
        TaskHubGrpcClient works) that polls until a response is available or
        timeout occurs.

        Args:
            agent_name: Name of the agent to execute
            run_request: The run request containing message and optional response format
            thread: Optional conversation thread (creates new if not provided)

        Returns:
            AgentResponse: The agent's response after execution completes, or an immediate
                            acknowledgement if wait_for_response is False
        """
        # Signal the entity with the request
        entity_id = self._signal_agent_entity(agent_name, run_request, thread)

        # If fire-and-forget mode, return immediately without polling
        if not run_request.wait_for_response:
            logger.info(
                "[ClientAgentExecutor] Fire-and-forget mode: request signaled (correlation: %s)",
                run_request.correlation_id,
            )
            return self._create_acceptance_response(run_request.correlation_id)

        # Poll for the response
        agent_response = self._poll_for_agent_response(entity_id, run_request.correlation_id)

        # Handle and return the result
        return self._handle_agent_response(agent_response, run_request.response_format, run_request.correlation_id)

    def _signal_agent_entity(
        self,
        agent_name: str,
        run_request: RunRequest,
        thread: AgentThread | None,
    ) -> EntityInstanceId:
        """Signal the agent entity with a run request.

        Args:
            agent_name: Name of the agent to execute
            run_request: The run request containing message and optional response format
            thread: Optional conversation thread

        Returns:
            entity_id
        """
        # Get or create session ID
        session_id = self._create_session_id(agent_name, thread)

        # Create the entity ID
        entity_id = EntityInstanceId(
            entity=session_id.entity_name,
            key=session_id.key,
        )

        logger.debug(
            "[ClientAgentExecutor] Signaling entity '%s' (session: %s, correlation: %s)",
            agent_name,
            session_id,
            run_request.correlation_id,
        )

        self._client.signal_entity(entity_id, "run", run_request.to_dict())
        return entity_id

    def _poll_for_agent_response(
        self,
        entity_id: EntityInstanceId,
        correlation_id: str,
    ) -> AgentResponse | None:
        """Poll the entity for a response with retries.

        Args:
            entity_id: Entity instance identifier
            correlation_id: Correlation ID to track the request

        Returns:
            The agent response if found, None if timeout occurs
        """
        agent_response = None

        for attempt in range(1, self.max_poll_retries + 1):
            # Initial sleep is intentional - give the entity time to process before first poll
            time.sleep(self.poll_interval_seconds)

            agent_response = self._poll_entity_for_response(entity_id, correlation_id)
            if agent_response is not None:
                logger.info(
                    "[ClientAgentExecutor] Found response (attempt %d/%d, correlation: %s)",
                    attempt,
                    self.max_poll_retries,
                    correlation_id,
                )
                break

            logger.debug(
                "[ClientAgentExecutor] Response not ready (attempt %d/%d)",
                attempt,
                self.max_poll_retries,
            )

        return agent_response

    def _handle_agent_response(
        self,
        agent_response: AgentResponse | None,
        response_format: type[BaseModel] | None,
        correlation_id: str,
    ) -> AgentResponse:
        """Handle the agent response or create an error response.

        Args:
            agent_response: The response from polling, or None if timeout
            response_format: Optional response format for validation
            correlation_id: Correlation ID for logging

        Returns:
            AgentResponse with either the agent's response or an error message
        """
        if agent_response is not None:
            try:
                # Validate response format if specified
                if response_format is not None:
                    ensure_response_format(
                        response_format,
                        correlation_id,
                        agent_response,
                    )

                return agent_response

            except Exception as e:
                logger.exception(
                    "[ClientAgentExecutor] Error converting response for correlation: %s",
                    correlation_id,
                )
                error_message = ChatMessage(
                    role=Role.SYSTEM,
                    contents=[
                        Content.from_error(
                            message=f"Error processing agent response: {e}",
                            error_code="response_processing_error",
                        )
                    ],
                )
        else:
            logger.warning(
                "[ClientAgentExecutor] Timeout after %d attempts (correlation: %s)",
                self.max_poll_retries,
                correlation_id,
            )
            error_message = ChatMessage(
                role=Role.SYSTEM,
                contents=[
                    Content.from_error(
                        message=f"Timeout waiting for agent response after {self.max_poll_retries} attempts",
                        error_code="response_timeout",
                    )
                ],
            )

        return AgentResponse(
            messages=[error_message],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _poll_entity_for_response(
        self,
        entity_id: EntityInstanceId,
        correlation_id: str,
    ) -> AgentResponse | None:
        """Poll the entity state for a response matching the correlation ID.

        Args:
            entity_id: Entity instance identifier
            correlation_id: Correlation ID to search for

        Returns:
            Response AgentResponse, None otherwise
        """
        try:
            entity_metadata = self._client.get_entity(entity_id, include_state=True)

            if entity_metadata is None:
                return None

            state_json = entity_metadata.get_state()
            if not state_json:
                return None

            state = DurableAgentState.from_json(state_json)

            # Use the helper method to get response by correlation ID
            return state.try_get_agent_response(correlation_id)

        except Exception as e:
            logger.warning(
                "[ClientAgentExecutor] Error reading entity state: %s",
                e,
            )
            return None


class OrchestrationAgentExecutor(DurableAgentExecutor[DurableAgentTask]):
    """Execution strategy for orchestrations (sync/yield)."""

    def __init__(self, context: OrchestrationContext):
        self._context = context
        logger.debug("[OrchestrationAgentExecutor] Initialized")

    def generate_unique_id(self) -> str:
        """Create a new UUID that is safe for replay within an orchestration or operation."""
        return self._context.new_uuid()

    def get_run_request(
        self,
        message: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> RunRequest:
        """Get the current run request from the orchestration context.

        Returns:
            RunRequest: The current run request
        """
        request = super().get_run_request(
            message,
            options=options,
        )
        request.orchestration_id = self._context.instance_id
        return request

    def run_durable_agent(
        self,
        agent_name: str,
        run_request: RunRequest,
        thread: AgentThread | None = None,
    ) -> DurableAgentTask:
        """Execute the agent via orchestration context.

        Calls the agent entity and returns a DurableAgentTask that can be yielded
        in orchestrations to wait for the entity's response.

        Args:
            agent_name: Name of the agent to execute
            run_request: The run request containing message and optional response format
            thread: Optional conversation thread (creates new if not provided)

        Returns:
            DurableAgentTask: A task wrapping the entity call that yields AgentResponse
        """
        # Resolve session
        session_id = self._create_session_id(agent_name, thread)

        # Create the entity ID
        entity_id = EntityInstanceId(
            entity=session_id.entity_name,
            key=session_id.key,
        )

        logger.debug(
            "[OrchestrationAgentExecutor] correlation_id: %s entity_id: %s session_id: %s",
            run_request.correlation_id,
            entity_id,
            session_id,
        )

        # Branch based on wait_for_response
        if not run_request.wait_for_response:
            # Fire-and-forget mode: signal entity and return pre-completed task
            logger.info(
                "[OrchestrationAgentExecutor] Fire-and-forget mode: signaling entity (correlation: %s)",
                run_request.correlation_id,
            )
            self._context.signal_entity(entity_id, "run", run_request.to_dict())

            # Create a pre-completed task with acceptance response
            acceptance_response = self._create_acceptance_response(run_request.correlation_id)
            entity_task: CompletableTask[AgentResponse] = CompletableTask()  # type: ignore[no-untyped-call]
            entity_task.complete(acceptance_response)
        else:
            # Blocking mode: call entity and wait for response
            entity_task = self._context.call_entity(entity_id, "run", run_request.to_dict())  # type: ignore

        # Wrap in DurableAgentTask for response transformation
        return DurableAgentTask(
            entity_task=entity_task,
            response_format=run_request.response_format,
            correlation_id=run_request.correlation_id,
        )
