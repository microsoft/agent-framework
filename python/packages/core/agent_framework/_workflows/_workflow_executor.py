# Copyright (c) Microsoft. All rights reserved.

import contextlib
import inspect
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._workflow import Workflow

from ._events import (
    RequestInfoEvent,
    WorkflowErrorEvent,
    WorkflowFailedEvent,
    WorkflowRunState,
)
from ._executor import (
    Executor,
    handler,
)
from ._request_info_executor import (
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
)
from ._typing_utils import is_instance_of
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for tracking a single sub-workflow execution."""

    execution_id: str
    collected_responses: dict[str, Any]  # request_id -> response_data
    expected_response_count: int
    pending_requests: dict[str, Any]  # request_id -> original request data


class WorkflowExecutor(Executor):
    """An executor that wraps a workflow to enable hierarchical workflow composition.

    ## Overview
    WorkflowExecutor makes a workflow behave as a single executor within a parent workflow,
    enabling nested workflow architectures. It handles the complete lifecycle of sub-workflow
    execution including event processing, output forwarding, and request/response coordination
    between parent and child workflows.

    ## Execution Model
    When invoked, WorkflowExecutor:
    1. Starts the wrapped workflow with the input message
    2. Runs the sub-workflow to completion or until it needs external input
    3. Processes the sub-workflow's complete event stream after execution
    4. Forwards outputs to the parent workflow's event stream
    5. Handles external requests by routing them to the parent workflow
    6. Accumulates responses and resumes sub-workflow execution

    ## Event Stream Processing
    WorkflowExecutor processes events after sub-workflow completion:

    ### Output Forwarding
    All outputs from the sub-workflow are automatically forwarded to the parent:

    .. code-block:: python

        # Sub-workflow yields outputs
        await ctx.yield_output("sub-workflow result")

        # WorkflowExecutor forwards to parent via ctx.send_message()
        # Parent receives the output as a regular message

    ### Request/Response Coordination
    When sub-workflows need external information:

    .. code-block:: python

        # Sub-workflow makes request
        request = MyDataRequest(query="user info")
        # RequestInfoExecutor emits RequestInfoEvent

        # WorkflowExecutor sets source_executor_id and forwards to parent
        request.source_executor_id = "child_workflow_executor_id"
        # Parent workflow can handle via @handler for RequestInfoMessage subclasses,
        # or directly forward to external source via a RequestInfoExecutor in the parent
        # workflow.

    ### State Management
    WorkflowExecutor maintains execution state across request/response cycles:
    - Tracks pending requests by request_id
    - Accumulates responses until all expected responses are received
    - Resumes sub-workflow execution with complete response batch
    - Handles concurrent executions and multiple pending requests

    ## Type System Integration
    WorkflowExecutor inherits its type signature from the wrapped workflow:

    ### Input Types
    Matches the wrapped workflow's start executor input types:

    .. code-block:: python

        # If sub-workflow accepts str, WorkflowExecutor accepts str
        workflow_executor = WorkflowExecutor(my_workflow, id="wrapper")
        assert workflow_executor.input_types == my_workflow.input_types

    ### Output Types
    Combines sub-workflow outputs with request coordination types:

    .. code-block:: python

        # Includes all sub-workflow output types
        # Plus RequestInfoMessage if sub-workflow can make requests
    output_types = workflow.output_types + [RequestInfoMessage]  # if applicable
    ```

    ## Error Handling
    WorkflowExecutor propagates sub-workflow failures:
    - Captures WorkflowFailedEvent from sub-workflow
    - Converts to WorkflowErrorEvent in parent context
    - Provides detailed error information including sub-workflow ID

    ## Concurrent Execution Support
    WorkflowExecutor fully supports multiple concurrent sub-workflow executions:

    ### Per-Execution State Isolation
    Each sub-workflow invocation creates an isolated ExecutionContext:

    .. code-block:: python

        # Multiple concurrent invocations are supported
        workflow_executor = WorkflowExecutor(my_workflow, id="concurrent_executor")

        # Each invocation gets its own execution context
        # Execution 1: processes input_1 independently
        # Execution 2: processes input_2 independently
        # No state interference between executions

    ### Request/Response Coordination
    Responses are correctly routed to the originating execution:
    - Each execution tracks its own pending requests and expected responses
    - Request-to-execution mapping ensures responses reach the correct sub-workflow
    - Response accumulation is isolated per execution
    - Automatic cleanup when execution completes

    ### Memory Management
    - Unlimited concurrent executions supported
    - Each execution has unique UUID-based identification
    - Cleanup of completed execution contexts
    - Thread-safe state management for concurrent access

    ### Important Considerations
    **Shared Workflow Instance**: All concurrent executions use the same underlying workflow instance.
    For proper isolation, ensure that:
    - The wrapped workflow and its executors are stateless
    - Executors use WorkflowContext state management instead of instance variables
    - Any shared state is managed through WorkflowContext.get_shared_state/set_shared_state

    .. code-block:: python

        # Good: Stateless executor using context state
        class StatelessExecutor(Executor):
            @handler
            async def process(self, data: str, ctx: WorkflowContext[str]) -> None:
                # Use context state instead of instance variables
                state = await ctx.get_state() or {}
                state["processed"] = data
                await ctx.set_state(state)


        # Avoid: Stateful executor with instance variables
        class StatefulExecutor(Executor):
            def __init__(self):
                super().__init__(id="stateful")
                self.data = []  # This will be shared across concurrent executions!

    ## Integration with Parent Workflows
    Parent workflows can intercept sub-workflow requests:
    ```python
    class ParentExecutor(Executor):
        @handler
        async def handle_request(
            self,
            request: MyRequestType,  # Subclass of RequestInfoMessage
            ctx: WorkflowContext[RequestResponse[RequestInfoMessage, Any] | RequestInfoMessage],
        ) -> None:
            # Handle request locally or forward to external source
            if self.can_handle_locally(request):
                # Send response back to sub-workflow
                response = RequestResponse(data="local result", original_request=request, request_id=request.request_id)
                await ctx.send_message(response, target_id=request.source_executor_id)
            else:
                # Forward to external handler
                await ctx.send_message(request)
    ```

    ## Implementation Notes
    - Sub-workflows run to completion before processing their results
    - Event processing is atomic - all outputs are forwarded before requests
    - Response accumulation ensures sub-workflows receive complete response batches
    - Execution state is maintained for proper resumption after external requests
    - Concurrent executions are fully isolated and do not interfere with each other
    """

    def __init__(self, workflow: "Workflow", id: str, **kwargs: Any):
        """Initialize the WorkflowExecutor.

        Args:
            workflow: The workflow to execute as a sub-workflow.
            id: Unique identifier for this executor.

        Keyword Args:
            **kwargs: Additional keyword arguments passed to the parent constructor.
        """
        super().__init__(id, **kwargs)
        self.workflow = workflow

        # Track execution contexts for concurrent sub-workflow executions
        self._execution_contexts: dict[str, ExecutionContext] = {}  # execution_id -> ExecutionContext
        # Map request_id to execution_id for response routing
        self._request_to_execution: dict[str, str] = {}  # request_id -> execution_id
        self._active_executions: int = 0  # Count of active sub-workflow executions
        self._state_loaded: bool = False

    @property
    def input_types(self) -> list[type[Any]]:
        """Get the input types based on the underlying workflow's input types plus WorkflowExecutor-specific types.

        Returns:
            A list of input types that the WorkflowExecutor can accept.
        """
        input_types = list(self.workflow.input_types)

        # WorkflowExecutor can also handle RequestResponse for sub-workflow responses
        if RequestResponse not in input_types:
            input_types.append(RequestResponse)

        return input_types

    @property
    def output_types(self) -> list[type[Any]]:
        """Get the output types based on the underlying workflow's output types.

        Returns:
            A list of output types that the underlying workflow can produce.
            Includes specific RequestInfoMessage subtypes if the sub-workflow contains RequestInfoExecutor.
        """
        output_types = list(self.workflow.output_types)

        # Check if the sub-workflow contains a RequestInfoExecutor
        # If so, collect the specific RequestInfoMessage subtypes from all executors
        has_request_info_executor = any(
            isinstance(executor, RequestInfoExecutor) for executor in self.workflow.executors.values()
        )

        if has_request_info_executor:
            # Collect all RequestInfoMessage subtypes from executor output types
            for executor in self.workflow.executors.values():
                for output_type in executor.output_types:
                    # Check if this is a RequestInfoMessage subclass
                    if (
                        inspect.isclass(output_type)
                        and issubclass(output_type, RequestInfoMessage)
                        and output_type not in output_types
                    ):
                        output_types.append(output_type)

        return output_types

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["workflow"] = self.workflow.to_dict()
        return data

    def can_handle(self, message: Any) -> bool:
        """Override can_handle to only accept messages that the wrapped workflow can handle.

        This prevents the WorkflowExecutor from accepting messages that should go to other
        executors (like RequestInfoExecutor).
        """
        # Always handle RequestResponse (for the handle_response handler)
        if isinstance(message, RequestResponse):
            return True

        # For other messages, only handle if the wrapped workflow can accept them as input
        return any(is_instance_of(message, input_type) for input_type in self.workflow.input_types)

    @handler  # No output_types - can send any completion data type
    async def process_workflow(self, input_data: object, ctx: WorkflowContext[Any]) -> None:
        """Execute the sub-workflow with raw input data.

        This handler starts a new sub-workflow execution. When the sub-workflow
        needs external information, it pauses and sends a request to the parent.

        Args:
            input_data: The input data to send to the sub-workflow.
            ctx: The workflow context from the parent.
        """
        # Skip RequestResponse - it has a specific handler
        if isinstance(input_data, RequestResponse):
            logger.debug(f"WorkflowExecutor {self.id} ignoring input of type {type(input_data)}")
            return

        await self._ensure_state_loaded(ctx)

        # Create execution context for this sub-workflow run
        execution_id = str(uuid.uuid4())
        execution_context = ExecutionContext(
            execution_id=execution_id,
            collected_responses={},
            expected_response_count=0,
            pending_requests={},
        )
        self._execution_contexts[execution_id] = execution_context

        # Track this execution
        self._active_executions += 1

        logger.debug(f"WorkflowExecutor {self.id} starting sub-workflow {self.workflow.id} execution {execution_id}")

        try:
            # Run the sub-workflow and collect all events
            result = await self.workflow.run(input_data)

            logger.debug(
                f"WorkflowExecutor {self.id} sub-workflow {self.workflow.id} "
                f"execution {execution_id} completed with {len(result)} events"
            )

            # Process the workflow result using shared logic
            await self._process_workflow_result(result, execution_context, ctx)
        finally:
            # Clean up execution context if it's completed (no pending requests)
            if execution_id in self._execution_contexts:
                exec_ctx = self._execution_contexts[execution_id]
                if not exec_ctx.pending_requests:
                    del self._execution_contexts[execution_id]
                    self._active_executions -= 1

    async def _process_workflow_result(
        self, result: Any, execution_context: ExecutionContext, ctx: WorkflowContext[Any]
    ) -> None:
        """Process the result from a workflow execution.

        This method handles the common logic for processing outputs, request info events,
        and final states that is shared between process_workflow and handle_response.

        Args:
            result: The workflow execution result.
            execution_context: The execution context for this sub-workflow run.
            ctx: The workflow context.
        """
        # Collect all events from the workflow
        request_info_events = result.get_request_info_events()
        outputs = result.get_outputs()
        final_state = result.get_final_state()
        logger.debug(
            f"WorkflowExecutor {self.id} processing workflow result with "
            f"{len(outputs)} outputs and {len(request_info_events)} request info events, "
            f"final state: {final_state}"
        )

        # Process outputs
        for output in outputs:
            await ctx.send_message(output)

        # Process request info events
        for event in request_info_events:
            # Track the pending request in execution context
            execution_context.pending_requests[event.request_id] = event.data
            # Map request to execution for response routing
            self._request_to_execution[event.request_id] = execution_context.execution_id
            # Set source_executor_id for response routing and send to parent
            if not isinstance(event.data, RequestInfoMessage):
                raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
            # Set the source_executor_id to this WorkflowExecutor's ID for response routing
            event.data.source_executor_id = self.id
            await ctx.send_message(event.data)

        # Update expected response count for this execution
        execution_context.expected_response_count = len(request_info_events)

        # Handle final state
        if final_state == WorkflowRunState.FAILED:
            # Find the WorkflowFailedEvent.
            failed_events = [e for e in result if isinstance(e, WorkflowFailedEvent)]
            if failed_events:
                failed_event = failed_events[0]
                error_type = failed_event.details.error_type
                error_message = failed_event.details.message
                exception = Exception(
                    f"Sub-workflow {self.workflow.id} failed with error: {error_type} - {error_message}"
                )
                error_event = WorkflowErrorEvent(
                    data=exception,
                )
                await ctx.add_event(error_event)
                self._active_executions -= 1
        elif final_state == WorkflowRunState.IDLE:
            # Sub-workflow is idle - nothing more to do now
            logger.debug(f"Sub-workflow {self.workflow.id} is idle with {self._active_executions} active executions")
            self._active_executions -= 1  # Treat idle as completion for now
        elif final_state == WorkflowRunState.CANCELLED:
            # Sub-workflow was cancelled - treat as completion
            logger.debug(
                f"Sub-workflow {self.workflow.id} was cancelled with {self._active_executions} active executions"
            )
            self._active_executions -= 1
        elif final_state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS:
            # Sub-workflow is still running with pending requests
            logger.debug(
                f"Sub-workflow {self.workflow.id} is still in progress with {len(request_info_events)} "
                f"pending requests with {self._active_executions} active executions"
            )
        elif final_state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
            # Sub-workflow is idle but has pending requests
            logger.debug(
                f"Sub-workflow {self.workflow.id} is idle with pending requests: "
                f"{len(request_info_events)} with {self._active_executions} active executions"
            )
        else:
            raise RuntimeError(f"Unexpected final state: {final_state}")

        await self._persist_execution_state(ctx)

    @handler
    async def handle_response(
        self,
        response: RequestResponse[RequestInfoMessage, Any],
        ctx: WorkflowContext[Any],
    ) -> None:
        """Handle response from parent for a forwarded request.

        This handler accumulates responses and only resumes the sub-workflow
        when all expected responses have been received for that execution.

        Args:
            response: The response to a previous request.
            ctx: The workflow context.
        """
        await self._ensure_state_loaded(ctx)

        # Find the execution context for this request
        execution_id = self._request_to_execution.get(response.request_id)
        if not execution_id or execution_id not in self._execution_contexts:
            logger.warning(
                f"WorkflowExecutor {self.id} received response for unknown request_id: {response.request_id}, ignoring"
            )
            return

        execution_context = self._execution_contexts[execution_id]

        # Check if we have this pending request in the execution context
        if response.request_id not in execution_context.pending_requests:
            logger.warning(
                f"WorkflowExecutor {self.id} received response for unknown request_id: "
                f"{response.request_id} in execution {execution_id}, ignoring"
            )
            return

        # Remove the request from pending list and request mapping
        execution_context.pending_requests.pop(response.request_id, None)
        self._request_to_execution.pop(response.request_id, None)

        # Accumulate the response in this execution's context
        execution_context.collected_responses[response.request_id] = response.data

        await self._persist_execution_state(ctx)

        # Check if we have all expected responses for this execution
        if len(execution_context.collected_responses) < execution_context.expected_response_count:
            logger.debug(
                f"WorkflowExecutor {self.id} execution {execution_id} waiting for more responses: "
                f"{len(execution_context.collected_responses)}/{execution_context.expected_response_count} received"
            )
            return  # Wait for more responses

        # Send all collected responses to the sub-workflow
        responses_to_send = dict(execution_context.collected_responses)
        execution_context.collected_responses.clear()  # Clear for next batch

        try:
            # Resume the sub-workflow with all collected responses
            result = await self.workflow.send_responses(responses_to_send)

            # Process the workflow result using shared logic
            await self._process_workflow_result(result, execution_context, ctx)
        finally:
            # Clean up execution context if it's completed (no pending requests)
            if not execution_context.pending_requests:
                del self._execution_contexts[execution_id]
                self._active_executions -= 1

    async def _ensure_state_loaded(self, ctx: WorkflowContext[Any]) -> None:
        if self._state_loaded:
            return

        state: dict[str, Any] | None = None
        try:
            state = await ctx.get_state()
        except Exception:
            state = None

        if isinstance(state, dict) and state:
            with contextlib.suppress(Exception):
                self.restore_state(state)
                self._state_loaded = True
        else:
            self._state_loaded = True

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore pending request bookkeeping from a checkpoint snapshot."""
        self._execution_contexts = {}
        self._request_to_execution = {}

        executions_payload = state.get("executions")
        if isinstance(executions_payload, Mapping) and executions_payload:
            for execution_id, payload in executions_payload.items():
                if not isinstance(execution_id, str) or not isinstance(payload, Mapping):
                    continue

                pending_ids_raw = payload.get("pending_request_ids", [])
                if not isinstance(pending_ids_raw, list):
                    continue
                pending_ids = [rid for rid in pending_ids_raw if isinstance(rid, str)]

                expected = payload.get("expected_response_count", len(pending_ids))
                try:
                    expected_count = int(expected)
                except (TypeError, ValueError):
                    expected_count = len(pending_ids)

                collected_ids_raw = payload.get("collected_response_ids", [])
                collected: dict[str, Any] = {}
                if isinstance(collected_ids_raw, list):
                    for rid in collected_ids_raw:
                        if isinstance(rid, str):
                            collected[rid] = None

                exec_ctx = ExecutionContext(
                    execution_id=execution_id,
                    collected_responses=collected,
                    expected_response_count=expected_count,
                    pending_requests={rid: None for rid in pending_ids},
                )

                if exec_ctx.pending_requests or exec_ctx.collected_responses:
                    self._execution_contexts[execution_id] = exec_ctx
                    for rid in exec_ctx.pending_requests:
                        self._request_to_execution[rid] = execution_id
        else:
            pending_ids = state.get("pending_request_ids", [])
            if isinstance(pending_ids, list):
                pending = [rid for rid in pending_ids if isinstance(rid, str)]
                if pending:
                    try:
                        expected = int(state.get("expected_response_count", len(pending)))
                    except (TypeError, ValueError):
                        expected = len(pending)

                    execution_id = str(uuid.uuid4())
                    exec_ctx = ExecutionContext(
                        execution_id=execution_id,
                        collected_responses={},
                        expected_response_count=expected,
                        pending_requests={rid: None for rid in pending},
                    )
                    self._execution_contexts[execution_id] = exec_ctx
                    for rid in pending:
                        self._request_to_execution[rid] = execution_id

        try:
            self._active_executions = int(state.get("active_executions", len(self._execution_contexts)))
        except (TypeError, ValueError):
            self._active_executions = len(self._execution_contexts)

        helper_states = state.get("request_info_executor_states", {})
        restored_request_data: dict[str, RequestInfoMessage] = {}
        if isinstance(helper_states, Mapping):
            for exec_id, helper_state in helper_states.items():
                helper_executor = self.workflow.executors.get(exec_id)
                if not isinstance(helper_executor, RequestInfoExecutor) or not isinstance(helper_state, Mapping):
                    continue
                with contextlib.suppress(Exception):
                    helper_executor.restore_state(dict(helper_state))
                    for req_id, event in getattr(helper_executor, "_request_events", {}).items():  # type: ignore[attr-defined]
                        if (
                            isinstance(req_id, str)
                            and isinstance(event, RequestInfoEvent)
                            and isinstance(event.data, RequestInfoMessage)
                        ):
                            restored_request_data[req_id] = event.data

        if restored_request_data:
            for req_id, data in restored_request_data.items():
                execution_id = self._request_to_execution.get(req_id)
                if execution_id and execution_id in self._execution_contexts:
                    self._execution_contexts[execution_id].pending_requests[req_id] = data

        for execution_id, exec_ctx in self._execution_contexts.items():
            for req_id in exec_ctx.pending_requests:
                self._request_to_execution.setdefault(req_id, execution_id)

        request_map = state.get("request_to_execution")
        if isinstance(request_map, Mapping):
            for req_id, execution_id in request_map.items():
                if (
                    isinstance(req_id, str)
                    and isinstance(execution_id, str)
                    and execution_id in self._execution_contexts
                ):
                    self._request_to_execution.setdefault(req_id, execution_id)

        self._state_loaded = True

    def _build_state_snapshot(self) -> dict[str, Any]:
        executions: dict[str, Any] = {}
        pending_request_ids: list[str] = []

        for execution_id, exec_ctx in self._execution_contexts.items():
            if not exec_ctx.pending_requests and not exec_ctx.collected_responses:
                continue

            request_ids = list(exec_ctx.pending_requests.keys())
            pending_request_ids.extend(request_ids)

            summary: dict[str, Any] = {
                "pending_request_ids": request_ids,
                "expected_response_count": exec_ctx.expected_response_count,
            }

            if exec_ctx.collected_responses:
                summary["collected_response_ids"] = list(exec_ctx.collected_responses.keys())

            executions[execution_id] = summary

        helper_states: dict[str, Any] = {}
        for exec_id, executor in self.workflow.executors.items():
            if isinstance(executor, RequestInfoExecutor):
                with contextlib.suppress(Exception):
                    snapshot = executor.snapshot_state()
                    if snapshot:
                        helper_states[exec_id] = snapshot

        has_state = bool(executions or helper_states or self._request_to_execution)
        if not has_state:
            return {}

        state: dict[str, Any] = {
            "executions": executions,
            "request_to_execution": dict(self._request_to_execution),
            "pending_request_ids": pending_request_ids,
            "active_executions": self._active_executions,
        }

        if helper_states:
            state["request_info_executor_states"] = helper_states

        return state

    async def _persist_execution_state(self, ctx: WorkflowContext[Any]) -> None:
        snapshot = self._build_state_snapshot()
        try:
            await ctx.set_state(snapshot)
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"WorkflowExecutor {self.id} failed to persist state: {exc}")
