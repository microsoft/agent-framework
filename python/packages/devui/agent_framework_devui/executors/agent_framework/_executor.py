"""Agent Framework executor implementation."""

import json
import logging
import os
from typing import Any, AsyncGenerator, Dict

from ..._tracing import capture_traces
from ...models import AgentFrameworkRequest
from .._base import EntityNotFoundError, FrameworkExecutor
from ._discovery import AgentFrameworkEntityDiscovery
from ._mapper import AgentFrameworkMessageMapper

logger = logging.getLogger(__name__)


class AgentFrameworkExecutor(FrameworkExecutor):
    """Executor for Agent Framework entities - agents and workflows."""

    def __init__(self, entity_discovery: AgentFrameworkEntityDiscovery, message_mapper: AgentFrameworkMessageMapper):
        """Initialize Agent Framework executor.
        
        Args:
            entity_discovery: Entity discovery instance
            message_mapper: Message mapper instance
        """
        super().__init__(entity_discovery, message_mapper)
        self._setup_tracing_provider()
        self._setup_agent_framework_tracing()

    def _setup_tracing_provider(self) -> None:
        """Set up our own TracerProvider so we can add processors."""
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider

            # Only set up if no provider exists yet
            if not hasattr(trace, "_TRACER_PROVIDER") or trace._TRACER_PROVIDER is None:
                resource = Resource.create({
                    "service.name": "agent-framework-server",
                    "service.version": "1.0.0",
                })
                provider = TracerProvider(resource=resource)
                trace.set_tracer_provider(provider)
                logger.info("Set up TracerProvider for server tracing")
            else:
                logger.debug("TracerProvider already exists")

        except ImportError:
            logger.debug("OpenTelemetry not available")
        except Exception as e:
            logger.warning(f"Failed to setup TracerProvider: {e}")

    def _setup_agent_framework_tracing(self) -> None:
        """Set up Agent Framework's built-in tracing."""
        # Configure Agent Framework tracing only if OTLP endpoint is configured
        otlp_endpoint = os.environ.get("AGENT_FRAMEWORK_OTLP_ENDPOINT")
        if otlp_endpoint:
            try:
                from agent_framework.telemetry import setup_telemetry
                setup_telemetry(
                    enable_otel=True,
                    enable_sensitive_data=True,
                    otlp_endpoint=otlp_endpoint
                )
                logger.info(f"Enabled Agent Framework telemetry with endpoint: {otlp_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to enable Agent Framework tracing: {e}")
        else:
            logger.debug("No OTLP endpoint configured, skipping telemetry setup")

    async def execute_entity(self, entity_id: str, request: AgentFrameworkRequest) -> AsyncGenerator[Any, None]:
        """Execute the entity and yield raw Agent Framework events plus trace events.
        
        Args:
            entity_id: ID of entity to execute
            request: Request to execute
            
        Yields:
            Raw Agent Framework events and trace events
        """
        try:
            # Get entity info and object
            entity_info = self.get_entity_info(entity_id)
            entity_obj = self.entity_discovery.get_entity_object(entity_id)

            if not entity_obj:
                raise EntityNotFoundError(f"Entity object for '{entity_id}' not found")

            logger.info(f"Executing {entity_info.type}: {entity_id}")

            # Extract session_id from request for trace context
            session_id = request.extra_body.get("session_id") if request.extra_body else None

            # Use simplified trace capture
            with capture_traces(session_id=session_id, entity_id=entity_id) as trace_collector:
                if entity_info.type == "agent":
                    async for event in self._execute_agent(entity_obj, request, trace_collector):
                        yield event
                elif entity_info.type == "workflow":
                    async for event in self._execute_workflow(entity_obj, request, trace_collector):
                        yield event
                else:
                    raise ValueError(f"Unsupported entity type: {entity_info.type}")

                # Yield any remaining trace events after execution completes
                for trace_event in trace_collector.get_pending_events():
                    yield trace_event

        except Exception as e:
            logger.exception(f"Error executing entity {entity_id}: {e}")
            # Yield error event
            yield {"type": "error", "message": str(e), "entity_id": entity_id}

    async def _execute_agent(self, agent: Any, request: AgentFrameworkRequest, trace_collector: Any) -> AsyncGenerator[Any, None]:
        """Execute Agent Framework agent with trace collection.
        
        Args:
            agent: Agent object to execute
            request: Request to execute
            trace_collector: Trace collector to get events from
            
        Yields:
            Agent update events and trace events
        """
        try:
            # Extract user message from input
            user_message = self._extract_user_message(request.input)

            logger.debug(f"Executing agent with input: {user_message[:100]}...")

            # Use Agent Framework's native streaming
            async for update in agent.run_stream(user_message):
                # Yield any pending trace events first
                for trace_event in trace_collector.get_pending_events():
                    yield trace_event

                # Then yield the execution update
                yield update

        except Exception as e:
            logger.error(f"Error in agent execution: {e}")
            yield {"type": "error", "message": f"Agent execution error: {e!s}"}

    async def _execute_workflow(self, workflow: Any, request: AgentFrameworkRequest, trace_collector: Any) -> AsyncGenerator[Any, None]:
        """Execute Agent Framework workflow with trace collection.
        
        Args:
            workflow: Workflow object to execute
            request: Request to execute
            trace_collector: Trace collector to get events from
            
        Yields:
            Workflow events and trace events
        """
        try:
            # Parse input based on workflow's expected input type
            parsed_input = await self._parse_workflow_input(workflow, request.input)

            logger.debug(f"Executing workflow with parsed input type: {type(parsed_input)}")

            # Use Agent Framework workflow's native streaming
            async for event in workflow.run_stream(parsed_input):
                # Yield any pending trace events first
                for trace_event in trace_collector.get_pending_events():
                    yield trace_event

                # Then yield the workflow event
                yield event

        except Exception as e:
            logger.error(f"Error in workflow execution: {e}")
            yield {"type": "error", "message": f"Workflow execution error: {e!s}"}

    def _extract_user_message(self, input_data: Any) -> str:
        """Extract user message from various input formats.
        
        Args:
            input_data: Input data in various formats
            
        Returns:
            Extracted user message string
        """
        if isinstance(input_data, str):
            return input_data
        if isinstance(input_data, dict):
            # Try common field names
            for field in ["message", "text", "input", "content", "query"]:
                if field in input_data:
                    return str(input_data[field])
            # Fallback to JSON string
            return json.dumps(input_data)
        return str(input_data)

    async def _parse_workflow_input(self, workflow: Any, raw_input: Any) -> Any:
        """Parse input based on workflow's expected input type.
        
        Args:
            workflow: Workflow object
            raw_input: Raw input data
            
        Returns:
            Parsed input appropriate for the workflow
        """
        try:
            # Handle structured input
            if isinstance(raw_input, dict):
                return self._parse_structured_workflow_input(workflow, raw_input)
            return self._parse_raw_workflow_input(workflow, str(raw_input))

        except Exception as e:
            logger.warning(f"Error parsing workflow input: {e}")
            return raw_input

    def _parse_structured_workflow_input(self, workflow: Any, input_data: Dict[str, Any]) -> Any:
        """Parse structured input data for workflow execution.
        
        Args:
            workflow: Workflow object
            input_data: Structured input data
            
        Returns:
            Parsed input for workflow
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

            # Handle primitive types
            if input_type in (str, int, float, bool):
                try:
                    if isinstance(input_data, input_type):
                        return input_data
                    if "input" in input_data:
                        return input_type(input_data["input"])
                    if len(input_data) == 1:
                        value = list(input_data.values())[0]
                        return input_type(value)
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

        return input_data

    def _parse_raw_workflow_input(self, workflow: Any, raw_input: str) -> Any:
        """Parse raw input string based on workflow's expected input type.
        
        Args:
            workflow: Workflow object
            raw_input: Raw input string
            
        Returns:
            Parsed input for workflow
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

                    # Try common field names
                    common_fields = ["message", "text", "input", "data", "content"]
                    for field in common_fields:
                        try:
                            return input_type(**{field: raw_input})
                        except:
                            continue

                    # Last resort: try default constructor
                    return input_type()

                except Exception as e:
                    logger.debug(f"Failed to parse input as {input_type}: {e}")

            # If it's a dataclass, try JSON parsing
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
        return raw_input
