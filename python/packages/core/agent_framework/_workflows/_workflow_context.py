# Copyright (c) Microsoft. All rights reserved.

import inspect
import logging
import uuid
from types import UnionType
from typing import TYPE_CHECKING, Any, Generic, Union, cast, get_args, get_origin

from opentelemetry.propagate import inject
from opentelemetry.trace import SpanKind
from typing_extensions import Never, TypeVar, deprecated

from ..observability import OtelAttr, create_workflow_span
from ._const import EXECUTOR_STATE_KEY
from ._events import (
    RequestInfoEvent,
    WorkflowEvent,
    WorkflowEventSource,
    WorkflowFailedEvent,
    WorkflowLifecycleEvent,
    WorkflowOutputEvent,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
    WorkflowWarningEvent,
    _framework_event_origin,  # type: ignore
)
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState

if TYPE_CHECKING:
    from ._executor import Executor

T_Out = TypeVar("T_Out", default=Never)
T_W_Out = TypeVar("T_W_Out", default=Never)


logger = logging.getLogger(__name__)


def infer_output_types_from_ctx_annotation(ctx_annotation: Any) -> tuple[list[type[Any]], list[type[Any]]]:
    """Infer message types and workflow output types from the WorkflowContext generic parameters.

    Examples:
    - WorkflowContext -> ([], [])
    - WorkflowContext[str] -> ([str], [])
    - WorkflowContext[str, int] -> ([str], [int])
    - WorkflowContext[str | int, bool | int] -> ([str, int], [bool, int])
    - WorkflowContext[Union[str, int], Union[bool, int]] -> ([str, int], [bool, int])
    - WorkflowContext[Any] -> ([Any], [])
    - WorkflowContext[Any, Any] -> ([Any], [Any])
    - WorkflowContext[Never, Never] -> ([], [])
    - WorkflowContext[Never, int] -> ([], [int])

    Returns:
        Tuple of (message_types, workflow_output_types)
    """
    # If no annotation or not parameterized, return empty lists
    try:
        origin = get_origin(ctx_annotation)
    except Exception:
        origin = None

    # If annotation is unsubscripted WorkflowContext, nothing to infer
    if origin is None:
        return [], []

    # Expecting WorkflowContext[T_Out, T_W_Out]
    if origin is not WorkflowContext:
        return [], []

    args = list(get_args(ctx_annotation))
    if not args:
        return [], []

    # WorkflowContext[T_Out] -> message_types from T_Out, no workflow output types
    if len(args) == 1:
        t = args[0]
        t_origin = get_origin(t)
        if t is Any:
            return [cast(type[Any], Any)], []

        if t_origin in (Union, UnionType):
            message_types = [arg for arg in get_args(t) if arg is not Any and arg is not Never]
            return message_types, []

        if t is Never:
            return [], []
        return [t], []

    # WorkflowContext[T_Out, T_W_Out] -> message_types from T_Out, workflow_output_types from T_W_Out
    t_out, t_w_out = args[:2]  # Take first two args in case there are more

    # Process T_Out for message_types
    message_types = []
    t_out_origin = get_origin(t_out)
    if t_out is Any:
        message_types = [cast(type[Any], Any)]
    elif t_out is not Never:
        if t_out_origin in (Union, UnionType):
            message_types = [arg for arg in get_args(t_out) if arg is not Any and arg is not Never]
        else:
            message_types = [t_out]

    # Process T_W_Out for workflow_output_types
    workflow_output_types = []
    t_w_out_origin = get_origin(t_w_out)
    if t_w_out is Any:
        workflow_output_types = [cast(type[Any], Any)]
    elif t_w_out is not Never:
        if t_w_out_origin in (Union, UnionType):
            workflow_output_types = [arg for arg in get_args(t_w_out) if arg is not Any and arg is not Never]
        else:
            workflow_output_types = [t_w_out]

    return message_types, workflow_output_types


def _is_workflow_context_type(annotation: Any) -> bool:
    """Check if an annotation represents WorkflowContext, WorkflowContext[T], or WorkflowContext[T, U]."""
    origin = get_origin(annotation)
    if origin is WorkflowContext:
        return True
    # Also handle the case where the raw class is used
    return annotation is WorkflowContext


def validate_workflow_context_annotation(
    annotation: Any,
    parameter_name: str,
    context_description: str,
) -> tuple[list[type[Any]], list[type[Any]]]:
    """Validate a WorkflowContext annotation and return inferred types.

    Args:
        annotation: The type annotation to validate
        parameter_name: Name of the parameter (for error messages)
        context_description: Description of the context (e.g., "Function func1", "Handler method")

    Returns:
        Tuple of (output_types, workflow_output_types)

    Raises:
        ValueError: If the annotation is invalid
    """
    if annotation == inspect.Parameter.empty:
        raise ValueError(
            f"{context_description} {parameter_name} must have a WorkflowContext, "
            f"WorkflowContext[T] or WorkflowContext[T, U] type annotation, "
            f"where T is output message type and U is workflow output type"
        )

    if not _is_workflow_context_type(annotation):
        raise ValueError(
            f"{context_description} {parameter_name} must be annotated as "
            f"WorkflowContext, WorkflowContext[T], or WorkflowContext[T, U], "
            f"got {annotation}"
        )

    # Validate type arguments for WorkflowContext[T] or WorkflowContext[T, U]
    type_args = get_args(annotation)

    if len(type_args) > 2:
        raise ValueError(
            f"{context_description} {parameter_name} must have at most 2 type arguments, "
            "WorkflowContext, WorkflowContext[T], or WorkflowContext[T, U], "
            f"got {len(type_args)} arguments"
        )

    if type_args:
        # Helper function to check if a value is a valid type annotation
        def _is_type_like(x: Any) -> bool:
            """Check if a value is a type-like entity (class, type, or typing construct)."""
            return isinstance(x, type) or get_origin(x) is not None or x is Never

        for i, type_arg in enumerate(type_args):
            param_description = "T_Out" if i == 0 else "T_W_Out"

            # Allow Any explicitly
            if type_arg is Any:
                continue

            # Check if it's a union type and validate each member
            union_origin = get_origin(type_arg)
            if union_origin in (Union, UnionType):
                union_members = get_args(type_arg)
                invalid_members = [m for m in union_members if not _is_type_like(m) and m is not Any]
                if invalid_members:
                    raise ValueError(
                        f"{context_description} {parameter_name} {param_description} "
                        f"contains invalid type entries: {invalid_members}. "
                        f"Use proper types or typing generics"
                    )
            else:
                # Check if it's a valid type
                if not _is_type_like(type_arg):
                    raise ValueError(
                        f"{context_description} {parameter_name} {param_description} "
                        f"contains invalid type entry: {type_arg}. "
                        f"Use proper types or typing generics"
                    )

    return infer_output_types_from_ctx_annotation(annotation)


_FRAMEWORK_LIFECYCLE_EVENT_TYPES: tuple[type[WorkflowEvent], ...] = cast(
    tuple[type[WorkflowEvent], ...],
    tuple(get_args(WorkflowLifecycleEvent))
    or (
        WorkflowStartedEvent,
        WorkflowStatusEvent,
        WorkflowFailedEvent,
    ),
)


class WorkflowContext(Generic[T_Out, T_W_Out]):
    """Execution context that enables executors to interact with workflows and other executors.

    ## Overview
    WorkflowContext provides a controlled interface for executors to send messages, yield outputs,
    manage state, and interact with the broader workflow ecosystem. It enforces type safety through
    generic parameters while preventing direct access to internal runtime components.

    ## Type Parameters
    The context is parameterized to enforce type safety for different operations:

    ### WorkflowContext (no parameters)
    For executors that only perform side effects without sending messages or yielding outputs:

    .. code-block:: python

        async def log_handler(message: str, ctx: WorkflowContext) -> None:
            print(f"Received: {message}")  # Only side effects

    ### WorkflowContext[T_Out]
    Enables sending messages of type T_Out to other executors:

    .. code-block:: python

        async def processor(message: str, ctx: WorkflowContext[int]) -> None:
            result = len(message)
            await ctx.send_message(result)  # Send int to downstream executors

    ### WorkflowContext[T_Out, T_W_Out]
    Enables both sending messages (T_Out) and yielding workflow outputs (T_W_Out):

    .. code-block:: python

        async def dual_output(message: str, ctx: WorkflowContext[int, str]) -> None:
            await ctx.send_message(42)  # Send int message
            await ctx.yield_output("complete")  # Yield str workflow output

    ### Union Types
    Multiple types can be specified using union notation:

    .. code-block:: python

        async def flexible(message: str, ctx: WorkflowContext[int | str, bool | dict]) -> None:
            await ctx.send_message("text")  # or send 42
            await ctx.yield_output(True)  # or yield {"status": "done"}
    """

    def __init__(
        self,
        executor: "Executor",
        source_executor_ids: list[str],
        shared_state: SharedState,
        runner_context: RunnerContext,
        trace_contexts: list[dict[str, str]] | None = None,
        source_span_ids: list[str] | None = None,
    ):
        """Initialize the executor context with the given workflow context.

        Args:
            executor: The executor instance that this context belongs to.
            source_executor_ids: The IDs of the source executors that sent messages to this executor.
                This is a list to support fan_in scenarios where multiple sources send aggregated
                messages to the same executor.
            shared_state: The shared state for the workflow.
            runner_context: The runner context that provides methods to send messages and events.
            trace_contexts: Optional trace contexts from multiple sources for OpenTelemetry propagation.
            source_span_ids: Optional source span IDs from multiple sources for linking (not for nesting).
        """
        self._executor = executor
        self._executor_id = executor.id
        self._source_executor_ids = source_executor_ids
        self._runner_context = runner_context
        self._shared_state = shared_state

        # Track messages sent via send_message() for ExecutorCompletedEvent
        self._sent_messages: list[Any] = []

        # Store trace contexts and source span IDs for linking (supporting multiple sources)
        self._trace_contexts = trace_contexts or []
        self._source_span_ids = source_span_ids or []

        if not self._source_executor_ids:
            raise ValueError("source_executor_ids cannot be empty. At least one source executor ID is required.")

    async def send_message(self, message: T_Out, target_id: str | None = None) -> None:
        """Send a message to the workflow context.

        Args:
            message: The message to send. This must conform to the output type(s) declared on this context.
            target_id: The ID of the target executor to send the message to.
                       If None, the message will be sent to all target executors.
        """
        global OBSERVABILITY_SETTINGS
        from ..observability import OBSERVABILITY_SETTINGS

        # Create publishing span (inherits current trace context automatically)
        attributes: dict[str, str] = {OtelAttr.MESSAGE_TYPE: type(message).__name__}
        if target_id:
            attributes[OtelAttr.MESSAGE_DESTINATION_EXECUTOR_ID] = target_id
        with create_workflow_span(OtelAttr.MESSAGE_SEND_SPAN, attributes, kind=SpanKind.PRODUCER) as span:
            # Create Message wrapper
            msg = Message(data=message, source_id=self._executor_id, target_id=target_id)

            # Track sent message for ExecutorCompletedEvent
            self._sent_messages.append(message)

            # Inject current trace context if tracing enabled
            if OBSERVABILITY_SETTINGS.ENABLED and span and span.is_recording():  # type: ignore[name-defined]
                trace_context: dict[str, str] = {}
                inject(trace_context)  # Inject current trace context for message propagation

                msg.trace_contexts = [trace_context]
                msg.source_span_ids = [format(span.get_span_context().span_id, "016x")]

            await self._runner_context.send_message(msg)

    async def yield_output(self, output: T_W_Out) -> None:
        """Set the output of the workflow.

        Args:
            output: The output to yield. This must conform to the workflow output type(s)
                    declared on this context.
        """
        with _framework_event_origin():
            event = WorkflowOutputEvent(data=output, source_executor_id=self._executor_id)
        await self._runner_context.add_event(event)

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the workflow context."""
        if event.origin == WorkflowEventSource.EXECUTOR and isinstance(event, _FRAMEWORK_LIFECYCLE_EVENT_TYPES):
            event_name = event.__class__.__name__
            warning_msg = (
                f"Executor '{self._executor_id}' attempted to emit {event_name}, "
                "which is reserved for framework lifecycle notifications. The "
                "event was ignored."
            )
            logger.warning(warning_msg)
            await self._runner_context.add_event(WorkflowWarningEvent(warning_msg))
            return
        await self._runner_context.add_event(event)

    async def request_info(self, request_data: object, response_type: type) -> None:
        """Request information from outside of the workflow.

        Calling this method will cause the workflow to emit a RequestInfoEvent, carrying the
        provided request_data and request_type. External systems listening for such events
        can then process the request and respond accordingly.

        Executors must have the corresponding response handlers defined using the
        @response_handler decorator to handle the incoming responses.

        Args:
            request_data: The data associated with the information request.
            response_type: The expected type of the response, used for validation.
        """
        request_type: type = type(request_data)
        if not self._executor.is_request_supported(request_type, response_type):
            logger.warning(
                f"Executor '{self._executor_id}' requested info of type {request_type.__name__} "
                f"with expected response type {response_type.__name__}, but no matching "
                "response handler is defined. The request will not be ignored but responses will "
                "not be processed. Please define a response handler using the @response_handler decorator."
            )

        request_info_event = RequestInfoEvent(
            request_id=str(uuid.uuid4()),
            source_executor_id=self._executor_id,
            request_data=request_data,
            response_type=response_type,
        )
        await self._runner_context.add_request_info_event(request_info_event)

    async def get_shared_state(self, key: str) -> Any:
        """Get a value from the shared state."""
        return await self._shared_state.get(key)

    async def set_shared_state(self, key: str, value: Any) -> None:
        """Set a value in the shared state."""
        await self._shared_state.set(key, value)

    def get_source_executor_id(self) -> str:
        """Get the ID of the source executor that sent the message to this executor.

        Raises:
            RuntimeError: If there are multiple source executors, this method raises an error.
        """
        if len(self._source_executor_ids) > 1:
            raise RuntimeError(
                "Cannot get source executor ID when there are multiple source executors. "
                "Access the full list via the source_executor_ids property instead."
            )
        return self._source_executor_ids[0]

    @property
    def source_executor_ids(self) -> list[str]:
        """Get the IDs of the source executors that sent messages to this executor."""
        return self._source_executor_ids

    @property
    def shared_state(self) -> SharedState:
        """Get the shared state."""
        return self._shared_state

    def get_sent_messages(self) -> list[Any]:
        """Get all messages sent via send_message() during this handler execution.

        Returns:
            A list of messages that were sent to downstream executors.
        """
        return self._sent_messages.copy()

    @deprecated(
        "Override `on_checkpoint_save()` methods instead. "
        "For cross-executor state sharing, use set_shared_state() instead. "
        "This API will be removed after 12/01/2025."
    )
    async def set_executor_state(self, state: dict[str, Any]) -> None:
        """Store executor state in shared state under a reserved key.

        Executors call this with a JSON-serializable dict capturing the minimal
        state needed to resume. It replaces any previously stored state.
        """
        has_existing_states = await self._shared_state.has(EXECUTOR_STATE_KEY)
        if has_existing_states:
            existing_states = await self._shared_state.get(EXECUTOR_STATE_KEY)
        else:
            existing_states = {}

        if not isinstance(existing_states, dict):
            raise ValueError("Existing executor states in shared state is not a dictionary.")

        existing_states[self._executor_id] = state
        await self._shared_state.set(EXECUTOR_STATE_KEY, existing_states)

    @deprecated(
        "Override `on_checkpoint_restore()` methods instead. "
        "For cross-executor state sharing, use get_shared_state() instead. "
        "This API will be removed after 12/01/2025."
    )
    async def get_executor_state(self) -> dict[str, Any] | None:
        """Retrieve previously persisted state for this executor, if any."""
        has_existing_states = await self._shared_state.has(EXECUTOR_STATE_KEY)
        if not has_existing_states:
            return None

        existing_states = await self._shared_state.get(EXECUTOR_STATE_KEY)
        if not isinstance(existing_states, dict):
            raise ValueError("Existing executor states in shared state is not a dictionary.")

        return existing_states.get(self._executor_id)  # type: ignore

    def is_streaming(self) -> bool:
        """Check if the workflow is running in streaming mode.

        Returns:
            True if the workflow was started with run_stream(), False if started with run().
        """
        return self._runner_context.is_streaming()
