# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework executor implementation."""

import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from agent_framework import AgentProtocol
from agent_framework._workflows._events import RequestInfoEvent

from ._conversations import ConversationStore, InMemoryConversationStore
from ._discovery import EntityDiscovery
from ._mapper import MessageMapper
from ._tracing import capture_traces
from .models import AgentFrameworkRequest, OpenAIResponse
from .models._discovery_models import EntityInfo

logger = logging.getLogger(__name__)


class EntityNotFoundError(Exception):
    """Raised when an entity is not found."""

    pass


class AgentFrameworkExecutor:
    """Executor for Agent Framework entities - agents and workflows."""

    def __init__(
        self,
        entity_discovery: EntityDiscovery,
        message_mapper: MessageMapper,
        conversation_store: ConversationStore | None = None,
    ):
        """Initialize Agent Framework executor.

        Args:
            entity_discovery: Entity discovery instance
            message_mapper: Message mapper instance
            conversation_store: Optional conversation store (defaults to in-memory)
        """
        self.entity_discovery = entity_discovery
        self.message_mapper = message_mapper
        self._setup_tracing_provider()
        self._setup_agent_framework_tracing()

        # Use provided conversation store or default to in-memory
        self.conversation_store = conversation_store or InMemoryConversationStore()

        # Create checkpoint manager (wraps conversation store)
        from ._conversations import CheckpointConversationManager

        self.checkpoint_manager = CheckpointConversationManager(self.conversation_store)

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
        # Configure Agent Framework tracing only if ENABLE_OTEL is set
        if os.environ.get("ENABLE_OTEL"):
            try:
                from agent_framework.observability import OBSERVABILITY_SETTINGS, setup_observability

                # Only configure if not already executed
                if not OBSERVABILITY_SETTINGS._executed_setup:
                    # Get OTLP endpoint from either custom or standard env var
                    # This handles the case where env vars are set after ObservabilitySettings was imported
                    otlp_endpoint = os.environ.get("OTLP_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

                    # Pass the endpoint explicitly to setup_observability
                    # This ensures OTLP exporters are created even if env vars were set late
                    setup_observability(enable_sensitive_data=True, otlp_endpoint=otlp_endpoint)
                    logger.info("Enabled Agent Framework observability")
                else:
                    logger.debug("Agent Framework observability already configured")
            except Exception as e:
                logger.warning(f"Failed to enable Agent Framework observability: {e}")
        else:
            logger.debug("ENABLE_OTEL not set, skipping observability setup")

    async def discover_entities(self) -> list[EntityInfo]:
        """Discover all available entities.

        Returns:
            List of discovered entities
        """
        return await self.entity_discovery.discover_entities()

    def get_entity_info(self, entity_id: str) -> EntityInfo:
        """Get entity information.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity information

        Raises:
            EntityNotFoundError: If entity is not found
        """
        entity_info = self.entity_discovery.get_entity_info(entity_id)
        if entity_info is None:
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        return entity_info

    async def execute_streaming(self, request: AgentFrameworkRequest) -> AsyncGenerator[Any, None]:
        """Execute request and stream results in OpenAI format.

        Args:
            request: Request to execute

        Yields:
            OpenAI response stream events
        """
        try:
            entity_id = request.get_entity_id()
            if not entity_id:
                logger.error("No entity_id specified in request")
                return

            # Validate entity exists
            if not self.entity_discovery.get_entity_info(entity_id):
                logger.error(f"Entity '{entity_id}' not found")
                return

            # Execute entity and convert events
            async for raw_event in self.execute_entity(entity_id, request):
                openai_events = await self.message_mapper.convert_event(raw_event, request)
                for event in openai_events:
                    yield event

        except Exception as e:
            logger.exception(f"Error in streaming execution: {e}")
            # Could yield error event here

    async def execute_sync(self, request: AgentFrameworkRequest) -> OpenAIResponse:
        """Execute request synchronously and return complete response.

        Args:
            request: Request to execute

        Returns:
            Final aggregated OpenAI response
        """
        # Collect all streaming events
        events = [event async for event in self.execute_streaming(request)]

        # Aggregate into final response
        return await self.message_mapper.aggregate_to_response(events, request)

    async def execute_entity(self, entity_id: str, request: AgentFrameworkRequest) -> AsyncGenerator[Any, None]:
        """Execute the entity and yield raw Agent Framework events plus trace events.

        Args:
            entity_id: ID of entity to execute
            request: Request to execute

        Yields:
            Raw Agent Framework events and trace events
        """
        try:
            # Get entity info
            entity_info = self.get_entity_info(entity_id)

            # Trigger lazy loading (will return from cache if already loaded)
            entity_obj = await self.entity_discovery.load_entity(entity_id, checkpoint_manager=self.checkpoint_manager)

            if not entity_obj:
                raise EntityNotFoundError(f"Entity object for '{entity_id}' not found")

            logger.info(f"Executing {entity_info.type}: {entity_id}")

            # Extract session_id from request for trace context
            session_id = getattr(request.extra_body, "session_id", None) if request.extra_body else None

            # Use simplified trace capture
            with capture_traces(session_id=session_id, entity_id=entity_id) as trace_collector:
                if entity_info.type == "agent":
                    async for event in self._execute_agent(entity_obj, request, trace_collector):
                        yield event
                elif entity_info.type == "workflow":
                    async for event in self._execute_workflow(entity_obj, request, trace_collector):
                        # Log RequestInfoEvent for debugging HIL flow
                        event_class = event.__class__.__name__ if hasattr(event, "__class__") else type(event).__name__
                        if event_class == "RequestInfoEvent":
                            logger.info("🔔 [EXECUTOR] RequestInfoEvent detected from workflow!")
                            logger.info(f"   request_id: {getattr(event, 'request_id', 'N/A')}")
                            logger.info(f"   source_executor_id: {getattr(event, 'source_executor_id', 'N/A')}")
                            logger.info(f"   request_type: {getattr(event, 'request_type', 'N/A')}")
                            data = getattr(event, "data", None)
                            logger.info(f"   data type: {type(data).__name__ if data else 'None'}")
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
        self, agent: AgentProtocol, request: AgentFrameworkRequest, trace_collector: Any
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
            # Emit agent lifecycle start event
            from .models._openai_custom import AgentStartedEvent

            yield AgentStartedEvent()

            # Convert input to proper ChatMessage or string
            user_message = self._convert_input_to_chat_message(request.input)

            # Get thread from conversation parameter (OpenAI standard!)
            thread = None
            conversation_id = request.get_conversation_id()
            if conversation_id:
                thread = self.conversation_store.get_thread(conversation_id)
                if thread:
                    logger.debug(f"Using existing conversation: {conversation_id}")
                else:
                    logger.warning(f"Conversation {conversation_id} not found, proceeding without thread")

            if isinstance(user_message, str):
                logger.debug(f"Executing agent with text input: {user_message[:100]}...")
            else:
                logger.debug(f"Executing agent with multimodal ChatMessage: {type(user_message)}")
            # Check if agent supports streaming
            if hasattr(agent, "run_stream") and callable(agent.run_stream):
                # Use Agent Framework's native streaming with optional thread
                if thread:
                    async for update in agent.run_stream(user_message, thread=thread):
                        for trace_event in trace_collector.get_pending_events():
                            yield trace_event

                        yield update
                else:
                    async for update in agent.run_stream(user_message):
                        for trace_event in trace_collector.get_pending_events():
                            yield trace_event

                        yield update
            elif hasattr(agent, "run") and callable(agent.run):
                # Non-streaming agent - use run() and yield complete response
                logger.info("Agent lacks run_stream(), using run() method (non-streaming)")
                if thread:
                    response = await agent.run(user_message, thread=thread)
                else:
                    response = await agent.run(user_message)

                # Yield trace events before response
                for trace_event in trace_collector.get_pending_events():
                    yield trace_event

                # Yield the complete response (mapper will convert to streaming events)
                yield response
            else:
                raise ValueError("Agent must implement either run() or run_stream() method")

            # Emit agent lifecycle completion event
            from .models._openai_custom import AgentCompletedEvent

            yield AgentCompletedEvent()

        except Exception as e:
            logger.error(f"Error in agent execution: {e}")
            # Emit agent lifecycle failure event
            from .models._openai_custom import AgentFailedEvent

            yield AgentFailedEvent(error=e)

            # Still yield the error for backward compatibility
            yield {"type": "error", "message": f"Agent execution error: {e!s}"}

    async def _execute_workflow(
        self, workflow: Any, request: AgentFrameworkRequest, trace_collector: Any
    ) -> AsyncGenerator[Any, None]:
        """Execute Agent Framework workflow with checkpoint support via conversation items.

        Args:
            workflow: Workflow object to execute
            request: Request to execute
            trace_collector: Trace collector to get events from

        Yields:
            Workflow events and trace events
        """
        try:
            entity_id = request.get_entity_id() or "unknown"

            # Get or create session conversation for checkpoint storage
            conversation_id = request.get_conversation_id()
            if not conversation_id:
                # Create default session if not provided
                import time
                import uuid

                conversation_id = f"session_{entity_id}_{uuid.uuid4().hex[:8]}"
                logger.info(f"Created new workflow session: {conversation_id}")

                # Create conversation in store
                self.conversation_store.create_conversation(
                    metadata={
                        "entity_id": entity_id,
                        "type": "workflow_session",
                        "created_at": str(int(time.time())),
                    },
                    conversation_id=conversation_id,
                )
            else:
                # Validate conversation exists, create if missing (handles deleted conversations)
                import time

                existing = self.conversation_store.get_conversation(conversation_id)
                if not existing:
                    logger.warning(f"Conversation {conversation_id} not found (may have been deleted), recreating")
                    self.conversation_store.create_conversation(
                        metadata={
                            "entity_id": entity_id,
                            "type": "workflow_session",
                            "created_at": str(int(time.time())),
                        },
                        conversation_id=conversation_id,
                    )

            # Get session-scoped checkpoint storage (InMemoryCheckpointStorage from conv_data)
            # Each conversation has its own storage instance, providing automatic session isolation.
            # This storage is passed to workflow.run_stream() which sets it as runtime override,
            # ensuring all checkpoint operations (save/load) use THIS conversation's storage.
            # The framework guarantees runtime storage takes precedence over build-time storage.
            checkpoint_storage = self.checkpoint_manager.get_checkpoint_storage(conversation_id)

            # Check for HIL responses first
            hil_responses = self._extract_workflow_hil_responses(request.input)

            # Determine checkpoint_id (explicit or auto-latest for HIL responses)
            checkpoint_id = None
            if request.extra_body and "checkpoint_id" in request.extra_body:
                checkpoint_id = request.extra_body["checkpoint_id"]
                logger.debug(f"Using explicit checkpoint_id from request: {checkpoint_id}")
            elif hil_responses:
                # Only auto-resume from latest checkpoint when we have HIL responses
                # Regular "Run" clicks should start fresh, not resume from checkpoints
                checkpoints = await checkpoint_storage.list_checkpoints()  # No workflow_id filter needed!
                if checkpoints:
                    latest = max(checkpoints, key=lambda cp: cp.timestamp)
                    checkpoint_id = latest.checkpoint_id
                    logger.info(f"Auto-resuming from latest checkpoint in session {conversation_id}: {checkpoint_id}")
                else:
                    logger.warning(f"HIL responses received but no checkpoints in session {conversation_id}")

            if hil_responses:
                # HIL continuation mode requires checkpointing
                if not checkpoint_id:
                    error_msg = (
                        "Cannot process HIL responses without a checkpoint. "
                        "Workflows using HIL must be configured with .with_checkpointing() "
                        "and a checkpoint must exist before sending responses."
                    )
                    logger.error(error_msg)
                    yield {"type": "error", "message": error_msg}
                    return

                logger.info(f"Resuming workflow with HIL responses for {len(hil_responses)} request(s)")

                # Unwrap primitive responses if they're wrapped in {response: value} format
                from ._utils import parse_input_for_type

                unwrapped_responses = {}
                for request_id, response_value in hil_responses.items():
                    if isinstance(response_value, dict) and "response" in response_value:
                        response_value = response_value["response"]
                    unwrapped_responses[request_id] = response_value

                hil_responses = unwrapped_responses

                # NOTE: Two-step approach for stateless HTTP (framework limitation):
                # 1. Restore checkpoint to load pending requests into workflow's in-memory state
                # 2. Then send responses using send_responses_streaming
                # Future: Framework should support run_stream(checkpoint_id, responses) in single call
                # (checkpoint_id is guaranteed to exist due to earlier validation)
                logger.debug(f"Restoring checkpoint {checkpoint_id} then sending HIL responses")

                try:
                    # Step 1: Restore checkpoint to populate workflow's in-memory pending requests
                    restored = False
                    async for _event in workflow.run_stream(
                        checkpoint_id=checkpoint_id, checkpoint_storage=checkpoint_storage
                    ):
                        restored = True
                        break  # Stop immediately after restoration, don't process events

                    if not restored:
                        raise RuntimeError("Checkpoint restoration did not yield any events")

                    # Reset running flags so we can call send_responses_streaming
                    if hasattr(workflow, "_is_running"):
                        workflow._is_running = False
                    if hasattr(workflow, "_runner") and hasattr(workflow._runner, "_running"):
                        workflow._runner._running = False

                    # Extract response types from restored workflow and convert responses to proper types
                    try:
                        if hasattr(workflow, "_runner") and hasattr(workflow._runner, "context"):
                            runner_context = workflow._runner.context
                            pending_requests_dict = await runner_context.get_pending_request_info_events()

                            converted_responses = {}
                            for request_id, response_value in hil_responses.items():
                                if request_id in pending_requests_dict:
                                    pending_request = pending_requests_dict[request_id]
                                    if hasattr(pending_request, "response_type"):
                                        response_type = pending_request.response_type
                                        try:
                                            response_value = parse_input_for_type(response_value, response_type)
                                            logger.debug(
                                                f"Converted HIL response for {request_id} to {type(response_value)}"
                                            )
                                        except Exception as e:
                                            logger.warning(f"Failed to convert HIL response for {request_id}: {e}")

                                converted_responses[request_id] = response_value

                            hil_responses = converted_responses
                    except Exception as e:
                        logger.warning(f"Could not convert HIL responses to proper types: {e}")

                    # Step 2: Now send responses to the in-memory workflow
                    async for event in workflow.send_responses_streaming(hil_responses):
                        for trace_event in trace_collector.get_pending_events():
                            yield trace_event
                        yield event

                except (AttributeError, ValueError, RuntimeError) as e:
                    error_msg = f"Failed to send HIL responses: {e}"
                    logger.error(error_msg)
                    yield {"type": "error", "message": error_msg}

            elif checkpoint_id:
                # Resume from checkpoint (explicit or auto-latest) using unified API
                logger.info(f"Resuming workflow from checkpoint {checkpoint_id} in session {conversation_id}")

                try:
                    async for event in workflow.run_stream(
                        checkpoint_id=checkpoint_id, checkpoint_storage=checkpoint_storage
                    ):
                        if isinstance(event, RequestInfoEvent):
                            self._enrich_request_info_event_with_response_schema(event, workflow)

                        for trace_event in trace_collector.get_pending_events():
                            yield trace_event

                        yield event

                        # Note: Removed break on RequestInfoEvent - continue yielding all events
                        # The workflow is already paused by ctx.request_info() in the framework
                        # DevUI should continue yielding events even during HIL pause

                except ValueError as e:
                    error_msg = f"Cannot resume from checkpoint: {e}"
                    logger.error(error_msg)
                    yield {"type": "error", "message": error_msg}

            else:
                # First run - pass DevUI's checkpoint storage to enable checkpointing
                logger.info(f"Starting fresh workflow in session {conversation_id}")

                parsed_input = await self._parse_workflow_input(workflow, request.input)

                async for event in workflow.run_stream(parsed_input, checkpoint_storage=checkpoint_storage):
                    if isinstance(event, RequestInfoEvent):
                        self._enrich_request_info_event_with_response_schema(event, workflow)

                    for trace_event in trace_collector.get_pending_events():
                        yield trace_event

                    yield event

                    # Note: Removed break on RequestInfoEvent - continue yielding all events
                    # The workflow is already paused by ctx.request_info() in the framework
                    # DevUI should continue yielding events even during HIL pause

        except Exception as e:
            logger.error(f"Error in workflow execution: {e}")
            yield {"type": "error", "message": f"Workflow execution error: {e!s}"}

    def _convert_input_to_chat_message(self, input_data: Any) -> Any:
        """Convert OpenAI Responses API input to Agent Framework ChatMessage or string.

        Handles various input formats including text, images, files, and multimodal content.
        Falls back to string extraction for simple cases.

        Args:
            input_data: OpenAI ResponseInputParam (List[ResponseInputItemParam])

        Returns:
            ChatMessage for multimodal content, or string for simple text
        """
        # Import Agent Framework types
        try:
            from agent_framework import ChatMessage, DataContent, Role, TextContent
        except ImportError:
            # Fallback to string extraction if Agent Framework not available
            return self._extract_user_message_fallback(input_data)

        # Handle simple string input (backward compatibility)
        if isinstance(input_data, str):
            return input_data

        # Handle OpenAI ResponseInputParam (List[ResponseInputItemParam])
        if isinstance(input_data, list):
            return self._convert_openai_input_to_chat_message(input_data, ChatMessage, TextContent, DataContent, Role)

        # Fallback for other formats
        return self._extract_user_message_fallback(input_data)

    def _convert_openai_input_to_chat_message(
        self, input_items: list[Any], ChatMessage: Any, TextContent: Any, DataContent: Any, Role: Any
    ) -> Any:
        """Convert OpenAI ResponseInputParam to Agent Framework ChatMessage.

        Processes text, images, files, and other content types from OpenAI format
        to Agent Framework ChatMessage with appropriate content objects.

        Args:
            input_items: List of OpenAI ResponseInputItemParam objects (dicts or objects)
            ChatMessage: ChatMessage class for creating chat messages
            TextContent: TextContent class for text content
            DataContent: DataContent class for data/media content
            Role: Role enum for message roles

        Returns:
            ChatMessage with converted content
        """
        contents = []

        # Process each input item
        for item in input_items:
            # Handle dict format (from JSON)
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "message":
                    # Extract content from OpenAI message
                    message_content = item.get("content", [])

                    # Handle both string content and list content
                    if isinstance(message_content, str):
                        contents.append(TextContent(text=message_content))
                    elif isinstance(message_content, list):
                        for content_item in message_content:
                            # Handle dict content items
                            if isinstance(content_item, dict):
                                content_type = content_item.get("type")

                                if content_type == "input_text":
                                    text = content_item.get("text", "")
                                    contents.append(TextContent(text=text))

                                elif content_type == "input_image":
                                    image_url = content_item.get("image_url", "")
                                    if image_url:
                                        # Extract media type from data URI if possible
                                        # Parse media type from data URL, fallback to image/png
                                        if image_url.startswith("data:"):
                                            try:
                                                # Extract media type from data:image/jpeg;base64,... format
                                                media_type = image_url.split(";")[0].split(":")[1]
                                            except (IndexError, AttributeError):
                                                logger.warning(
                                                    f"Failed to parse media type from data URL: {image_url[:30]}..."
                                                )
                                                media_type = "image/png"
                                        else:
                                            media_type = "image/png"
                                        contents.append(DataContent(uri=image_url, media_type=media_type))

                                elif content_type == "input_file":
                                    # Handle file input
                                    file_data = content_item.get("file_data")
                                    file_url = content_item.get("file_url")
                                    filename = content_item.get("filename", "")

                                    # Determine media type from filename
                                    media_type = "application/octet-stream"  # default
                                    if filename:
                                        if filename.lower().endswith(".pdf"):
                                            media_type = "application/pdf"
                                        elif filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                                            media_type = f"image/{filename.split('.')[-1].lower()}"
                                        elif filename.lower().endswith((
                                            ".wav",
                                            ".mp3",
                                            ".m4a",
                                            ".ogg",
                                            ".flac",
                                            ".aac",
                                        )):
                                            ext = filename.split(".")[-1].lower()
                                            # Normalize extensions to match audio MIME types
                                            media_type = "audio/mp4" if ext == "m4a" else f"audio/{ext}"

                                    # Use file_data or file_url
                                    if file_data:
                                        # Assume file_data is base64, create data URI
                                        data_uri = f"data:{media_type};base64,{file_data}"
                                        contents.append(DataContent(uri=data_uri, media_type=media_type))
                                    elif file_url:
                                        contents.append(DataContent(uri=file_url, media_type=media_type))

                                elif content_type == "function_approval_response":
                                    # Handle function approval response (DevUI extension)
                                    try:
                                        from agent_framework import FunctionApprovalResponseContent, FunctionCallContent

                                        request_id = content_item.get("request_id", "")
                                        approved = content_item.get("approved", False)
                                        function_call_data = content_item.get("function_call", {})

                                        # Create FunctionCallContent from the function_call data
                                        function_call = FunctionCallContent(
                                            call_id=function_call_data.get("id", ""),
                                            name=function_call_data.get("name", ""),
                                            arguments=function_call_data.get("arguments", {}),
                                        )

                                        # Create FunctionApprovalResponseContent with correct signature
                                        approval_response = FunctionApprovalResponseContent(
                                            approved,  # positional argument
                                            id=request_id,  # keyword argument 'id', NOT 'request_id'
                                            function_call=function_call,  # FunctionCallContent object
                                        )
                                        contents.append(approval_response)
                                        logger.info(
                                            f"Added FunctionApprovalResponseContent: id={request_id}, "
                                            f"approved={approved}, call_id={function_call.call_id}"
                                        )
                                    except ImportError:
                                        logger.warning(
                                            "FunctionApprovalResponseContent not available in agent_framework"
                                        )
                                    except Exception as e:
                                        logger.error(f"Failed to create FunctionApprovalResponseContent: {e}")

            # Handle other OpenAI input item types as needed
            # (tool calls, function results, etc.)

        # If no contents found, create a simple text message
        if not contents:
            contents.append(TextContent(text=""))

        chat_message = ChatMessage(role=Role.USER, contents=contents)

        logger.info(f"Created ChatMessage with {len(contents)} contents:")
        for idx, content in enumerate(contents):
            content_type = content.__class__.__name__
            if hasattr(content, "media_type"):
                logger.info(f"  [{idx}] {content_type} - media_type: {content.media_type}")
            else:
                logger.info(f"  [{idx}] {content_type}")

        return chat_message

    def _extract_user_message_fallback(self, input_data: Any) -> str:
        """Fallback method to extract user message as string.

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

    def _get_start_executor_message_types(self, workflow: Any) -> tuple[Any | None, list[Any]]:
        """Return start executor and its declared input types."""
        try:
            start_executor = workflow.get_start_executor()
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.debug(f"Unable to access workflow start executor: {exc}")
            return None, []

        if not start_executor:
            return None, []

        message_types: list[Any] = []

        try:
            input_types = getattr(start_executor, "input_types", None)
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.debug(f"Failed to read executor input_types: {exc}")
        else:
            if input_types:
                message_types = list(input_types)

        if not message_types and hasattr(start_executor, "_handlers"):
            try:
                handlers = start_executor._handlers
                if isinstance(handlers, dict):
                    message_types = list(handlers.keys())
            except Exception as exc:  # pragma: no cover - defensive logging path
                logger.debug(f"Failed to read executor handlers: {exc}")

        return start_executor, message_types

    def _extract_workflow_hil_responses(self, input_data: Any) -> dict[str, Any] | None:
        """Extract workflow HIL responses from OpenAI input format.

        Looks for special content type: workflow_hil_response

        Args:
            input_data: OpenAI ResponseInputParam

        Returns:
            Dict of {request_id: response_value} if found, None otherwise
        """
        # Handle case where input_data might be a JSON string (from streamWorkflowExecutionOpenAI)
        # The input field type is: str | list[Any] | dict[str, Any]
        if isinstance(input_data, str):
            try:
                parsed = json.loads(input_data)
                # Only use parsed value if it's a list (ResponseInputParam format expected for HIL)
                if isinstance(parsed, list):
                    input_data = parsed
                else:
                    # Parsed to dict, string, or primitive - not HIL response format
                    return None
            except (json.JSONDecodeError, TypeError):
                # Plain text string, not valid JSON - not HIL format
                return None

        # At this point, input_data should be a list or dict
        # HIL responses are always in list format (ResponseInputParam)
        if isinstance(input_data, dict):
            # This is structured workflow input (dict), not HIL responses
            return None

        if not isinstance(input_data, list):
            return None

        for item in input_data:
            if isinstance(item, dict) and item.get("type") == "message":
                message_content = item.get("content", [])

                if isinstance(message_content, list):
                    for content_item in message_content:
                        if isinstance(content_item, dict):
                            content_type = content_item.get("type")

                            if content_type == "workflow_hil_response":
                                # Extract responses dict
                                # dict.get() returns Any, so we explicitly type it
                                responses: dict[str, Any] = content_item.get("responses", {})  # type: ignore[assignment]
                                logger.info(f"Found workflow HIL responses: {list(responses.keys())}")
                                return responses

        return None

    def _get_or_create_conversation(self, conversation_id: str, entity_id: str) -> Any:
        """Get existing conversation or create a new one.

        Args:
            conversation_id: Conversation ID from frontend
            entity_id: Entity ID (e.g., "spam_workflow") for metadata filtering

        Returns:
            Conversation object
        """
        conversation = self.conversation_store.get_conversation(conversation_id)
        if not conversation:
            # Create conversation with frontend's ID
            # Use agent_id in metadata so it can be filtered by list_conversations(agent_id=...)
            conversation = self.conversation_store.create_conversation(
                metadata={"agent_id": entity_id}, conversation_id=conversation_id
            )
            logger.info(f"Created conversation {conversation_id} for entity {entity_id}")

        return conversation

    def _parse_structured_workflow_input(self, workflow: Any, input_data: dict[str, Any]) -> Any:
        """Parse structured input data for workflow execution.

        Args:
            workflow: Workflow object
            input_data: Structured input data

        Returns:
            Parsed input for workflow
        """
        try:
            from ._utils import parse_input_for_type

            # Get the start executor and its input type
            start_executor, message_types = self._get_start_executor_message_types(workflow)
            if not start_executor:
                logger.debug("Cannot determine input type for workflow - using raw dict")
                return input_data

            if not message_types:
                logger.debug("No message types found for start executor - using raw dict")
                return input_data

            # Get the first (primary) input type
            from ._utils import select_primary_input_type

            input_type = select_primary_input_type(message_types)
            if input_type is None:
                logger.debug("Could not select primary input type for workflow - using raw dict")
                return input_data

            # Use consolidated parsing logic from _utils
            return parse_input_for_type(input_data, input_type)

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
            from ._utils import parse_input_for_type

            # Get the start executor and its input type
            start_executor, message_types = self._get_start_executor_message_types(workflow)
            if not start_executor:
                logger.debug("Cannot determine input type for workflow - using raw string")
                return raw_input

            if not message_types:
                logger.debug("No message types found for start executor - using raw string")
                return raw_input

            # Get the first (primary) input type
            from ._utils import select_primary_input_type

            input_type = select_primary_input_type(message_types)
            if input_type is None:
                logger.debug("Could not select primary input type for workflow - using raw string")
                return raw_input

            # Use consolidated parsing logic from _utils
            return parse_input_for_type(raw_input, input_type)

        except Exception as e:
            logger.debug(f"Error parsing workflow input: {e}")
            return raw_input

    def _enrich_request_info_event_with_response_schema(self, event: Any, workflow: Any) -> None:
        """Extract response type from workflow executor and attach response schema to RequestInfoEvent.

        Args:
            event: RequestInfoEvent to enrich
            workflow: Workflow object containing executors
        """
        try:
            from agent_framework_devui._utils import extract_response_type_from_executor, generate_input_schema

            # Get source executor ID and request type from event
            source_executor_id = getattr(event, "source_executor_id", None)
            request_type = getattr(event, "request_type", None)

            if not source_executor_id or not request_type:
                logger.debug("RequestInfoEvent missing source_executor_id or request_type")
                return

            # Find the source executor in the workflow
            if not hasattr(workflow, "executors") or not isinstance(workflow.executors, dict):
                logger.debug("Workflow doesn't have executors dict")
                return

            source_executor = workflow.executors.get(source_executor_id)
            if not source_executor:
                logger.debug(f"Could not find executor '{source_executor_id}' in workflow")
                return

            # Extract response type from the executor's handler signature
            response_type = extract_response_type_from_executor(source_executor, request_type)

            if response_type:
                # Generate JSON schema for response type
                response_schema = generate_input_schema(response_type)

                # Attach response_schema to event for mapper to include in output
                event._response_schema = response_schema

                logger.debug(f"Extracted response schema for {request_type.__name__}: {response_schema}")
            else:
                # Even if extraction fails, provide a reasonable default to avoid warnings
                logger.debug(
                    f"Could not extract response type for {request_type.__name__}, using default string schema"
                )
                response_schema = {"type": "string"}
                event._response_schema = response_schema

        except Exception as e:
            logger.warning(f"Failed to enrich RequestInfoEvent with response schema: {e}")
