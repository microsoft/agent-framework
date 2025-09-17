# Copyright (c) Microsoft. All rights reserved.
"""Agent Framework executor implementation."""

import json
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from agent_framework import AgentThread

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

        # Minimal thread storage - no metadata needed
        self.thread_storage: dict[str, AgentThread] = {}
        self.agent_threads: dict[str, list[str]] = {}  # agent_id -> thread_ids

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

                setup_telemetry(enable_otel=True, enable_sensitive_data=True, otlp_endpoint=otlp_endpoint)
                logger.info(f"Enabled Agent Framework telemetry with endpoint: {otlp_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to enable Agent Framework tracing: {e}")
        else:
            logger.debug("No OTLP endpoint configured, skipping telemetry setup")

    # Thread Management Methods
    def create_thread(self, agent_id: str) -> str:
        """Create new thread for agent."""
        thread_id = f"thread_{uuid.uuid4().hex[:8]}"
        thread = AgentThread()

        self.thread_storage[thread_id] = thread

        if agent_id not in self.agent_threads:
            self.agent_threads[agent_id] = []
        self.agent_threads[agent_id].append(thread_id)

        return thread_id

    def get_thread(self, thread_id: str) -> AgentThread | None:
        """Get AgentThread by ID."""
        return self.thread_storage.get(thread_id)

    def list_threads_for_agent(self, agent_id: str) -> list[str]:
        """List thread IDs for agent."""
        return self.agent_threads.get(agent_id, [])

    def get_agent_for_thread(self, thread_id: str) -> str | None:
        """Find which agent owns this thread."""
        for agent_id, thread_ids in self.agent_threads.items():
            if thread_id in thread_ids:
                return agent_id
        return None

    def delete_thread(self, thread_id: str) -> bool:
        """Delete thread."""
        if thread_id not in self.thread_storage:
            return False

        # Remove from agent mapping
        for _agent_id, thread_ids in self.agent_threads.items():
            if thread_id in thread_ids:
                thread_ids.remove(thread_id)
                break

        del self.thread_storage[thread_id]
        return True

    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Get messages from a thread's message store, filtering for UI display."""
        thread = self.get_thread(thread_id)
        if not thread or not thread.message_store:
            return []

        try:
            # Get AgentFramework ChatMessage objects from thread
            af_messages = await thread.message_store.list_messages()

            ui_messages = []
            for i, af_msg in enumerate(af_messages):
                # Extract role value (handle enum)
                role = af_msg.role.value if hasattr(af_msg.role, "value") else str(af_msg.role)

                # Skip tool/function messages - only show user and assistant text
                if role not in ["user", "assistant"]:
                    continue

                # Extract user-facing text content only
                text_content = self._extract_display_text(af_msg.contents)

                # Skip messages with no displayable text
                if not text_content:
                    continue

                ui_message = {
                    "id": af_msg.message_id or f"restored-{i}",
                    "role": role,
                    "contents": [{"type": "text", "text": text_content}],
                    "timestamp": __import__("datetime").datetime.now().isoformat(),
                    "author_name": af_msg.author_name,
                    "message_id": af_msg.message_id,
                }

                ui_messages.append(ui_message)

            logger.info(f"Restored {len(ui_messages)} display messages for thread {thread_id}")
            return ui_messages

        except Exception as e:
            logger.error(f"Error getting thread messages: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return []

    def _extract_display_text(self, contents: list[Any]) -> str:
        """Extract user-facing text from message contents, filtering out internal mechanics."""
        text_parts = []

        for content in contents:
            content_type = getattr(content, "type", None)

            # Only include text content for display
            if content_type == "text":
                text = getattr(content, "text", "")

                # Handle double-encoded JSON from user messages
                if text.startswith('{"role":'):
                    try:
                        import json

                        parsed = json.loads(text)
                        if parsed.get("contents"):
                            for sub_content in parsed["contents"]:
                                if sub_content.get("type") == "text":
                                    text_parts.append(sub_content.get("text", ""))
                    except Exception:
                        text_parts.append(text)  # Fallback to raw text
                else:
                    text_parts.append(text)

            # Skip function_call, function_result, and other internal content types

        return " ".join(text_parts).strip()

    async def serialize_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Serialize thread state for persistence."""
        thread = self.get_thread(thread_id)
        if not thread:
            return None

        try:
            # Use AgentThread's built-in serialization
            serialized_state = await thread.serialize()

            # Add our metadata
            agent_id = self.get_agent_for_thread(thread_id)
            serialized_state["metadata"] = {"agent_id": agent_id, "thread_id": thread_id}

            return serialized_state

        except Exception as e:
            logger.error(f"Error serializing thread {thread_id}: {e}")
            return None

    async def deserialize_thread(self, thread_id: str, agent_id: str, serialized_state: dict[str, Any]) -> bool:
        """Deserialize thread state from persistence."""
        try:
            # Create new thread
            thread = AgentThread()

            # Use AgentThread's built-in deserialization
            from agent_framework._threads import deserialize_thread_state

            await deserialize_thread_state(thread, serialized_state)

            # Store the restored thread
            self.thread_storage[thread_id] = thread

            if agent_id not in self.agent_threads:
                self.agent_threads[agent_id] = []
            self.agent_threads[agent_id].append(thread_id)

            return True

        except Exception as e:
            logger.error(f"Error deserializing thread {thread_id}: {e}")
            return False

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

    async def _execute_agent(
        self, agent: Any, request: AgentFrameworkRequest, trace_collector: Any
    ) -> AsyncGenerator[Any, None]:
        """Execute Agent Framework agent with trace collection and optional thread support.

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

            # Get thread if provided in extra_body
            thread = None
            if request.extra_body and "thread_id" in request.extra_body:
                thread_id = request.extra_body["thread_id"]
                thread = self.get_thread(thread_id)
                if thread:
                    logger.debug(f"Using existing thread: {thread_id}")
                else:
                    logger.warning(f"Thread {thread_id} not found, proceeding without thread")

            logger.debug(f"Executing agent with input: {user_message[:100]}...")

            # Use Agent Framework's native streaming with optional thread
            if thread:
                async for update in agent.run_stream(user_message, thread=thread):
                    # Yield any pending trace events first
                    for trace_event in trace_collector.get_pending_events():
                        yield trace_event

                    # Then yield the execution update
                    yield update
            else:
                async for update in agent.run_stream(user_message):
                    # Yield any pending trace events first
                    for trace_event in trace_collector.get_pending_events():
                        yield trace_event

                    # Then yield the execution update
                    yield update

        except Exception as e:
            logger.error(f"Error in agent execution: {e}")
            yield {"type": "error", "message": f"Agent execution error: {e!s}"}

    async def _execute_workflow(
        self, workflow: Any, request: AgentFrameworkRequest, trace_collector: Any
    ) -> AsyncGenerator[Any, None]:
        """Execute Agent Framework workflow with trace collection.

        Args:
            workflow: Workflow object to execute
            request: Request to execute
            trace_collector: Trace collector to get events from

        Yields:
            Workflow events and trace events
        """
        try:
            # Get input data - prefer structured data from extra_body
            if request.extra_body and "input_data" in request.extra_body:
                input_data = request.extra_body["input_data"]
                logger.debug(f"Using structured input_data from extra_body: {type(input_data)}")
            else:
                input_data = request.input
                logger.debug(f"Using input field as fallback: {type(input_data)}")

            # Parse input based on workflow's expected input type
            parsed_input = await self._parse_workflow_input(workflow, input_data)

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

    def _parse_structured_workflow_input(self, workflow: Any, input_data: dict[str, Any]) -> Any:
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
            if input_type is dict:
                return input_data

            # Handle primitive types
            if input_type in (str, int, float, bool):
                try:
                    if isinstance(input_data, input_type):
                        return input_data
                    if "input" in input_data:
                        return input_type(input_data["input"])
                    if len(input_data) == 1:
                        value = next(iter(input_data.values()))
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
            if input_type is str:
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
                        except Exception as e:
                            logger.debug(f"Failed to parse input using field '{field}': {e}")
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
