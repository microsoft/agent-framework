# Copyright (c) Microsoft. All rights reserved.

"""Execution engine that wraps Agent Framework's native streaming."""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional, Union

if TYPE_CHECKING:
    from agent_framework import AgentProtocol, AgentThread
    from agent_framework.workflow import Workflow

    from ._tracing import TracingManager

from ._models import DebugStreamEvent


def _format_message_for_telemetry(message) -> str:
    """Format message for telemetry attributes (OpenTelemetry requires primitive types)."""
    if isinstance(message, str):
        return message[:100] + "..." if len(message) > 100 else message
    if hasattr(message, "text"):  # ChatMessage or similar
        text = message.text
        return text[:100] + "..." if len(text) > 100 else text
    if isinstance(message, list):
        # Handle list of ChatMessage objects
        texts = []
        for msg in message:
            if hasattr(msg, "text"):
                texts.append(msg.text)
            else:
                texts.append(str(msg))
        combined = " ".join(texts)
        return combined[:100] + "..." if len(combined) > 100 else combined
    return str(message)[:100] + "..." if len(str(message)) > 100 else str(message)


logger: logging.Logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Wraps Agent Framework execution with minimal overhead.

    Passes through native framework types with optional debug metadata.
    This ensures zero maintenance burden while preserving all framework capabilities.
    """

    def __init__(self, telemetry_config: Optional[Dict[str, bool]] = None) -> None:
        """Initialize the execution engine.
        
        Args:
            telemetry_config: Optional telemetry configuration from server
        """
        self.telemetry_config = telemetry_config or {
            'enable_framework_traces': True,
            'enable_workflow_traces': False,
            'enable_sensitive_data': False,
        }

    async def execute_agent_streaming(
        self,
        agent: "AgentProtocol",
        message: Union[str, List[Any]],
        thread: Optional["AgentThread"] = None,
        thread_id: Optional[str] = None,
        tracing_manager: Optional["TracingManager"] = None,
    ) -> AsyncGenerator[DebugStreamEvent, None]:
        """Execute agent and yield native AgentRunResponseUpdate wrapped in debug envelope.

        Args:
            agent: The Agent Framework agent to execute
            message: The message to send to the agent
            thread: Optional conversation thread
            thread_id: Optional thread identifier for session tracking
            tracing_manager: Optional tracing manager for span streaming

        Yields:
            DebugStreamEvent containing native AgentRunResponseUpdate
        """
        # Store trace events to yield alongside regular events
        trace_events = []

        # Set up tracing with callback to collect trace events
        enable_traces = self.telemetry_config.get('enable_framework_traces', False)
        if tracing_manager and thread_id and enable_traces:

            def collect_trace_event(trace_event: DebugStreamEvent):
                trace_events.append(trace_event)

            tracing_manager.setup_streaming_tracing(collect_trace_event)

        try:
            # Create a manual span for agent execution if tracing is enabled
            if tracing_manager and thread_id:
                try:
                    from opentelemetry import trace

                    tracer = trace.get_tracer("devui.execution")

                    # Create a top-level span for this agent execution
                    with tracer.start_as_current_span(
                        f"agent_execution.{getattr(agent, 'name', 'unknown')}",
                        attributes={
                            "thread_id": thread_id,
                            "agent_name": getattr(agent, "name", "unknown"),
                            "message": _format_message_for_telemetry(message),
                        },
                    ) as span:
                        span.set_attribute("devui.session_id", thread_id)

                        try:
                            # Execute agent using framework's native streaming
                            update_count = 0
                            async for update in agent.run_stream(message, thread=thread):
                                update_count += 1
                                # Yield any pending trace events first
                                while trace_events:
                                    yield trace_events.pop(0)

                                # Minimal wrapping - preserve native types completely
                                yield DebugStreamEvent(
                                    type="agent_run_update",
                                    update=update,  # Native AgentRunResponseUpdate - no modification
                                    timestamp=self._get_timestamp(),
                                    thread_id=thread_id,
                                    debug_metadata=self._get_debug_metadata(update) if enable_traces else None,
                                )

                            # Mark span as successful after processing all updates
                            span.set_status(trace.Status(trace.StatusCode.OK))
                            span.set_attribute("devui.update_count", update_count)

                        except Exception as e:
                            # Mark span as failed on exception
                            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                            span.record_exception(e)
                            raise
                except ImportError:
                    logger.debug("OpenTelemetry not available for manual span creation")
                    # Fall back to execution without spans
                    try:
                        async for update in agent.run_stream(message, thread=thread):
                            # Yield any pending trace events first
                            while trace_events:
                                yield trace_events.pop(0)

                            # Minimal wrapping - preserve native types completely
                            yield DebugStreamEvent(
                                type="agent_run_update",
                                update=update,  # Native AgentRunResponseUpdate - no modification
                                timestamp=self._get_timestamp(),
                                thread_id=thread_id,
                                debug_metadata=self._get_debug_metadata(update) if enable_traces else None,
                            )
                    except Exception as e:
                        logger.error(f"Error in agent execution fallback: {e}")
                        raise
            else:
                # Execute without tracing
                try:
                    async for update in agent.run_stream(message, thread=thread):
                        # Yield any pending trace events first
                        while trace_events:
                            yield trace_events.pop(0)

                        # Minimal wrapping - preserve native types completely
                        yield DebugStreamEvent(
                            type="agent_run_update",
                            update=update,  # Native AgentRunResponseUpdate - no modification
                            timestamp=self._get_timestamp(),
                            thread_id=thread_id,
                            debug_metadata=self._get_debug_metadata(update) if enable_traces else None,
                        )
                except Exception as e:
                    logger.error(f"Error in agent execution without tracing: {e}")
                    raise

            # Yield any remaining trace events
            while trace_events:
                yield trace_events.pop(0)

            # Signal completion
            yield DebugStreamEvent(type="completion", timestamp=self._get_timestamp(), thread_id=thread_id)

        except Exception as e:
            logger.error(f"Error executing agent {getattr(agent, 'name', 'unknown')}: {e}")
            yield DebugStreamEvent(type="error", error=str(e), timestamp=self._get_timestamp(), thread_id=thread_id)

    async def execute_workflow_streaming(
        self,
        workflow: "Workflow",
        input_data: Union[str, Dict[str, Any]],
        tracing_manager: Optional["TracingManager"] = None,
    ) -> AsyncGenerator[DebugStreamEvent, None]:
        """Execute workflow and yield native WorkflowEvent wrapped in debug envelope.

        Args:
            workflow: The Agent Framework workflow to execute
            input_data: The input data for the workflow (string or structured dict)
            tracing_manager: Optional tracing manager for span streaming

        Yields:
            DebugStreamEvent containing native WorkflowEvent
        """
        # Store trace events to yield alongside regular events
        trace_events = []

        # Set up tracing with callback to collect trace events
        enable_traces = self.telemetry_config.get('enable_workflow_traces', False)
        if tracing_manager and enable_traces:

            def collect_trace_event(trace_event: DebugStreamEvent):
                trace_events.append(trace_event)

            tracing_manager.setup_streaming_tracing(collect_trace_event)

        try:
            # First, send workflow structure information (minimal - just raw dump)
            try:
                yield DebugStreamEvent(
                    type="workflow_structure", workflow_dump=workflow, timestamp=self._get_timestamp()
                )
            except Exception as e:
                logger.warning(f"Could not generate workflow structure: {e}")

            # Parse input data based on workflow requirements
            if isinstance(input_data, dict):
                parsed_input = self._parse_structured_workflow_input(workflow, input_data)
            else:
                # Legacy string input - use existing parsing logic
                parsed_input = self._parse_workflow_input(workflow, input_data)

            # Create a span for workflow execution if tracing is enabled
            if tracing_manager and enable_traces:
                try:
                    from opentelemetry import trace

                    tracer = trace.get_tracer("devui.execution")

                    with tracer.start_as_current_span(
                        f"workflow_execution.{getattr(workflow, 'name', 'unknown')}",
                        attributes={"workflow_name": getattr(workflow, "name", "unknown"), "input_data": str(input_data)[:100] + "..." if len(str(input_data)) > 100 else str(input_data)},
                    ) as span:
                        try:
                            # Execute workflow using framework's native streaming
                            event_count = 0
                            async for event in workflow.run_stream(parsed_input):
                                event_count += 1
                                # Yield any pending trace events first
                                while trace_events:
                                    yield trace_events.pop(0)

                                # Minimal wrapping - preserve native types completely
                                yield DebugStreamEvent(
                                    type="workflow_event",
                                    event=self._serialize_workflow_event(event),  # Convert to serializable format
                                    timestamp=self._get_timestamp(),
                                    debug_metadata=self._get_debug_metadata(event) if enable_traces else None,
                                )

                            # Mark span as successful
                            span.set_status(trace.Status(trace.StatusCode.OK))
                            span.set_attribute("devui.event_count", event_count)

                        except Exception as e:
                            # Mark span as failed
                            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                            span.record_exception(e)
                            raise

                except ImportError:
                    logger.debug("OpenTelemetry not available for workflow span creation")
                    # Fall back to execution without spans
                    try:
                        async for event in workflow.run_stream(parsed_input):
                            # Yield any pending trace events first
                            while trace_events:
                                yield trace_events.pop(0)

                            # Minimal wrapping - preserve native types completely
                            yield DebugStreamEvent(
                                type="workflow_event",
                                event=self._serialize_workflow_event(event),  # Convert to serializable format
                                timestamp=self._get_timestamp(),
                                debug_metadata=self._get_debug_metadata(event) if enable_traces else None,
                            )
                    except Exception as e:
                        logger.error(f"Error in workflow execution fallback: {e}")
                        raise
            else:
                # Execute without tracing
                try:
                    async for event in workflow.run_stream(parsed_input):
                        # Yield any pending trace events first
                        while trace_events:
                            yield trace_events.pop(0)

                        # Minimal wrapping - preserve native types completely
                        yield DebugStreamEvent(
                            type="workflow_event",
                            event=self._serialize_workflow_event(event),  # Convert to serializable format
                            timestamp=self._get_timestamp(),
                            debug_metadata=self._get_debug_metadata(event) if enable_traces else None,
                        )
                except Exception as e:
                    logger.error(f"Error in workflow execution without tracing: {e}")
                    raise

            # Yield any remaining trace events
            while trace_events:
                yield trace_events.pop(0)

            # Signal completion
            yield DebugStreamEvent(type="completion", timestamp=self._get_timestamp())

        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            yield DebugStreamEvent(type="error", error=str(e), timestamp=self._get_timestamp())

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    def _get_debug_metadata(self, obj: Any) -> Optional[Dict[str, Any]]:
        """Extract debug metadata from framework objects."""
        metadata: Dict[str, Any] = {}

        # Add common metadata
        if hasattr(obj, "message_id"):
            metadata["message_id"] = obj.message_id
        if hasattr(obj, "response_id"):
            metadata["response_id"] = obj.response_id
        if hasattr(obj, "role"):
            metadata["role"] = obj.role

        # Add timing if available
        if hasattr(obj, "timestamp"):
            metadata["framework_timestamp"] = obj.timestamp

        return metadata


    def _parse_structured_workflow_input(self, workflow: "Workflow", input_data: Dict[str, Any]) -> Any:
        """Parse structured input data for workflow execution.

        This method takes a dictionary of form data from the UI and converts it
        to the appropriate input type expected by the workflow's start executor.

        Args:
            workflow: The workflow to get input type from
            input_data: Structured input data from UI form

        Returns:
            Parsed input object ready for workflow execution
        """
        try:
            # Get the start executor and its input type
            start_executor = workflow.get_start_executor()
            if not start_executor or not hasattr(start_executor, "_handlers"):
                logger.debug("Cannot determine input type for workflow - using raw dict")
                return input_data

            message_types = list(start_executor._handlers.keys())
            if not message_types:
                logger.debug("No message types found for start executor - using raw dict")
                return input_data

            # Get the first (primary) input type
            input_type = message_types[0]

            # If input type is dict, return as-is
            if input_type == dict:
                return input_data

            # Handle primitive types (str, int, float, bool)
            if input_type in (str, int, float, bool):
                try:
                    # For primitive types, the input_data should be the value directly
                    if isinstance(input_data, input_type):
                        return input_data
                    # For non-dict input, try to convert/cast directly
                    if not isinstance(input_data, dict):
                        return input_type(input_data)
                    # If input_data is a dict, extract the actual value
                    # UI sends string primitives as {"input": "value"}
                    if isinstance(input_data, dict):
                        if "input" in input_data:
                            return input_type(input_data["input"])
                        # If dict has only one key, use that value
                        if len(input_data) == 1:
                            value = list(input_data.values())[0]
                            return input_type(value)
                    # Fallback - return as-is
                    logger.warning(f"Received dict for primitive type {input_type}, returning as-is")
                    return input_data
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to convert input to {input_type}: {e}")
                    return input_data

            # If it's a Pydantic model, validate and create instance
            if hasattr(input_type, "model_validate"):
                try:
                    return input_type.model_validate(input_data)
                except Exception as e:
                    logger.warning(f"Failed to validate input as {input_type}: {e}")
                    # Try with just the data if validation fails
                    return input_data

            # If it's a dataclass or other type with annotations
            elif hasattr(input_type, "__annotations__"):
                try:
                    return input_type(**input_data)
                except Exception as e:
                    logger.warning(f"Failed to create {input_type} from input data: {e}")
                    return input_data

        except Exception as e:
            logger.warning(f"Error parsing structured workflow input: {e}")

        # Fallback: return raw dict
        logger.debug("Using raw dict input as fallback")
        return input_data

    def _parse_workflow_input(self, workflow: "Workflow", raw_input: str) -> Any:
        """Parse raw input string based on workflow's expected input type.

        Args:
            workflow: The workflow to get input type from
            raw_input: Raw string input from user

        Returns:
            Parsed input object or the raw string if parsing fails
        """
        try:
            # Get the start executor and its input type
            start_executor = workflow.get_start_executor()
            if not start_executor or not hasattr(start_executor, "_handlers"):
                logger.debug("Cannot determine input type for workflow - using raw string")
                return raw_input

            message_types = list(start_executor._handlers.keys())
            if not message_types:
                logger.debug("No message types found for start executor - using raw string")
                return raw_input

            # Get the first (primary) input type
            input_type = message_types[0]

            # If input type is str, return as-is
            if input_type == str:
                return raw_input

            # If it's a Pydantic model, try to parse JSON
            if hasattr(input_type, "model_validate_json"):
                try:
                    # First try to parse as JSON
                    if raw_input.strip().startswith("{"):
                        return input_type.model_validate_json(raw_input)
                    # If not JSON, try to create from string (for simple cases)
                    try:
                        parsed_json = json.loads(raw_input)
                        return input_type.model_validate(parsed_json)
                    except:
                        # Last resort: try to create with raw string in common field names
                        common_fields = ["message", "text", "input", "data", "content"]
                        for field in common_fields:
                            try:
                                return input_type(**{field: raw_input})
                            except:
                                continue
                        # If all else fails, try default constructor
                        return input_type()
                except Exception as e:
                    logger.debug(f"Failed to parse input as {input_type}: {e}")

            # If it's a dataclass or other type, try JSON parsing
            elif hasattr(input_type, "__annotations__"):
                try:
                    if raw_input.strip().startswith("{"):
                        parsed = json.loads(raw_input)
                        return input_type(**parsed)
                except Exception as e:
                    logger.debug(f"Failed to parse input as {input_type}: {e}")

        except Exception as e:
            logger.debug(f"Error determining workflow input type: {e}")

        # Fallback: return raw string
        logger.debug("Using raw string input as fallback")
        return raw_input

    def _serialize_workflow_event(self, event: Any) -> Dict[str, Any]:
        """Convert workflow event to serializable format."""
        event_dict = {"type": event.__class__.__name__, "data": None}

        # Add common attributes
        if hasattr(event, "executor_id"):
            event_dict["executor_id"] = event.executor_id
        if hasattr(event, "request_id"):
            event_dict["request_id"] = event.request_id
        if hasattr(event, "source_executor_id"):
            event_dict["source_executor_id"] = event.source_executor_id
        if hasattr(event, "request_type"):
            event_dict["request_type"] = (
                event.request_type.__name__ if hasattr(event.request_type, "__name__") else str(event.request_type)
            )

        # Serialize data based on type
        if hasattr(event, "data") and event.data is not None:
            try:
                # Try to serialize simple types
                if isinstance(event.data, (str, int, float, bool, list, dict)):
                    event_dict["data"] = event.data
                else:
                    # Convert complex objects to string representation
                    event_dict["data"] = str(event.data)
            except Exception:
                event_dict["data"] = str(event.data)

        return event_dict
