# Copyright (c) Microsoft. All rights reserved.

import re
from abc import ABC, abstractmethod

from a2a.types import FilePart, FileWithBytes, FileWithUri, Part, TaskState, TextPart
from agent_framework import AgentRunResponseUpdate, DataContent, Role, TextContent, UriContent

from ._a2a_execution_context import A2aExecutionContext


class A2aEventAdapter(ABC):
    """Abstract base class for adapting agent framework messages to A2A protocol events.

    This class defines the interface for converting agent framework chat messages into A2A protocol
    compatible events. Implementers are responsible for handling different types of agent framework
    messages and translating them into appropriate A2A task updates and protocol events.

    The adapter pattern allows for flexible transformation of various message formats from the
    agent framework into the standardized A2A protocol format, enabling seamless integration
    between different agent implementations and the A2A task execution framework.

    Key Responsibilities:
        - Parse and validate incoming agent framework messages
        - Extract content from various message types (text, data, URI)
        - Create appropriate A2A protocol parts and updates
        - Handle role-based message routing (assistant vs. user messages)
        - Manage metadata and content type mappings
        - Update task state and send protocol events

    Example:
        Basic custom adapter implementation:

        ```python
        class CustomEventAdapter(A2aEventAdapter):
            async def handle_events(self, message: AgentRunResponseUpdate, context: A2aExecutionContext) -> None:
                # Process the message
                if message.role == Role.ASSISTANT:
                    parts = []
                    for content in message.contents:
                        if isinstance(content, TextContent):
                            parts.append(Part(root=TextPart(text=content.text)))

                    if parts:
                        await context.updater.update_status(
                            state=TaskState.working,
                            message=context.updater.new_agent_message(parts=parts),
                        )
        ```

    Integration Pattern:
        ```python
        # Create adapter and context
        adapter = CustomEventAdapter()
        context = A2aExecutionContext(request=req, task=task, updater=updater)

        # Process agent responses
        for response in agent_responses:
            await adapter.handle_events(response, context)
        ```

    Note:
        Implementers should:
        - Filter out user messages (typically ignored in task updates)
        - Handle multiple content types gracefully
        - Provide appropriate error handling for unsupported content
        - Update task state consistently
        - Preserve message metadata when possible
    """

    @abstractmethod
    async def handle_events(self, message: AgentRunResponseUpdate, context: A2aExecutionContext) -> None:
        """Handle agent framework messages and convert them to A2A protocol events.

        This is the primary method called to process agent framework messages and translate them
        into A2A protocol-compatible updates. Implementations should handle content extraction,
        message routing, and task state management.

        Args:
            message (AgentRunResponseUpdate): The agent framework response message containing
                one or more content items to be processed
            context (A2aExecutionContext): The execution context containing the task updater,
                request context, and task information needed to update protocol state

        Returns:
            None: Updates are sent through the context.updater

        Raises:
            Implementations may raise exceptions for:
            - Invalid content types (should document expected types)
            - Missing required context information
            - Task state conflicts

        Supported Message Types:
            This method should handle conversions for:
            - TextContent -> A2A TextPart (simple text responses)
            - DataContent -> A2A FilePart with FileWithBytes (binary data)
            - UriContent -> A2A FilePart with FileWithUri (file references)
            - Role.ASSISTANT -> Task update (should process)
            - Role.USER -> May be skipped (typically not relevant for task updates)

        Example:
            Typical implementation pattern:

            ```python
            async def handle_events(self, message: AgentRunResponseUpdate, context: A2aExecutionContext) -> None:
                # Scenario 1: Skip user messages
                if message.role == Role.USER:
                    return

                # Scenario 2: Collect message parts
                parts: List[Part] = []
                for content in message.contents:
                    if isinstance(content, TextContent):
                        # Extract and convert text content
                        parts.append(Part(root=TextPart(text=content.text)))
                    elif isinstance(content, DataContent):
                        # Extract binary data from URI
                        binary_data = extract_binary_from_uri(content.uri)
                        parts.append(Part(root=FilePart(file=FileWithBytes(bytes=binary_data))))
                    elif isinstance(content, UriContent):
                        # Create file reference
                        parts.append(
                            Part(root=FilePart(file=FileWithUri(uri=content.uri, mime_type=content.media_type)))
                        )

                # Scenario 3: Send update to A2A protocol
                if parts:
                    await context.updater.update_status(
                        state=TaskState.working,
                        message=context.updater.new_agent_message(parts=parts),
                    )
            ```

        Note:
            - Multiple content items in a single message should be collected into a single
              update for efficiency
            - Task state should be set to TaskState.working to indicate ongoing processing
            - Empty message parts should not generate protocol updates
            - Metadata should be preserved and passed through when available
        """
        pass


class BaseA2aEventAdapter(A2aEventAdapter):
    """Base implementation of A2aEventAdapter with standard event handling.

    This class provides a default implementation for converting agent framework messages to A2A
    protocol events. It handles text content, multimedia content, and structured data, offering
    a production-ready adapter that covers the most common use cases.

    The adapter provides:
        - Automatic message type detection and routing
        - Text content conversion to A2A text parts
        - Binary data handling with base64 extraction
        - URI-based file reference handling
        - Metadata preservation and propagation
        - Role-based message filtering (user messages ignored)
        - Task state management and updates

    Processing Pipeline:
        1. Check message role (skip user messages)
        2. Iterate through message contents
        3. Convert each content item to appropriate A2A part
        4. Collect all parts into a single message
        5. Send update to task via context.updater
        6. Task state is set to TaskState.working

    Example:
        Basic usage of the base adapter:

        ```python
        from agent_framework import ChatMessage, Role, TextContent, AgentRunResponseUpdate
        from a2a.types import TaskState

        # Initialize adapter
        adapter = BaseA2aEventAdapter()
        context = A2aExecutionContext(request=req, task=task, updater=updater)

        # Scenario 1: Handle a simple text message
        message = AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[TextContent(text="Analysis complete")])
        await adapter.handle_events(message, context)

        # Scenario 2: Handle message with multiple content types
        message = AgentRunResponseUpdate(
            role=Role.ASSISTANT,
            contents=[
                TextContent(text="Processing result:"),
                DataContent(uri="data:application/json;base64,eyJyZXN1bHQiOiAidmFsdWUifQ=="),
                UriContent(uri="https://example.com/file.pdf", media_type="application/pdf"),
            ],
        )
        await adapter.handle_events(message, context)

        # Scenario 3: User messages are automatically filtered
        message = AgentRunResponseUpdate(role=Role.USER, contents=[TextContent(text="User request")])
        await adapter.handle_events(message, context)  # This is safely ignored

        # Scenario 4: Empty messages don't create updates
        message = AgentRunResponseUpdate(
            role=Role.ASSISTANT,
            contents=[],  # Empty
        )
        await adapter.handle_events(message, context)  # No update sent
        ```

    Advanced Usage:
        ```python
        # Process streaming agent responses
        async def process_agent_stream(agent, context):
            adapter = BaseA2aEventAdapter()
            async for response in agent.stream_responses():
                # Adapter handles all conversion and update logic
                await adapter.handle_events(response, context)


        # Integration with task execution loop
        async def execute_task(task, request, updater):
            context = A2aExecutionContext(request=request, task=task, updater=updater)
            adapter = BaseA2aEventAdapter()

            # Get agent responses
            responses = await agent.run(task.parameters)

            # Process each response through adapter
            for response in responses:
                await adapter.handle_events(response, context)

            # Mark task complete
            await context.updater.update_status(state=TaskState.completed)
        ```

    Content Type Mapping:
        - TextContent -> Part with TextPart (direct text conversion)
        - DataContent -> Part with FilePart + FileWithBytes (base64 extraction)
        - UriContent -> Part with FilePart + FileWithUri (direct reference)
        - Unknown types -> Silently skipped (no error, no update)

    Metadata Handling:
        The adapter preserves message metadata through the 'additional_properties' attribute:

        ```python
        # Metadata is automatically extracted and passed through
        message = AgentRunResponseUpdate(
            role=Role.ASSISTANT,
            contents=[TextContent(text="Result")],
            additional_properties={"timestamp": "2025-11-23T10:30:00Z", "source": "agent_v2"},
        )
        await adapter.handle_events(message, context)
        # Metadata is included in the A2A protocol update
        ```

    Error Handling:
        - Invalid content types are silently skipped (no exception raised)
        - Empty message content results in no protocol update
        - User messages are filtered automatically
        - Malformed base64 in data URIs are passed through as-is
    """

    async def handle_events(self, message: AgentRunResponseUpdate, context: A2aExecutionContext) -> None:
        """Process agent framework messages and update A2A task state.

        This implementation handles various types of agent framework messages and converts
        them into appropriate A2A protocol updates. It provides automatic content type detection,
        validation, and transformation.

        Args:
            message (AgentRunResponseUpdate): The message to process, containing one or more
                content items of various types (text, data, URI)
            context (A2aExecutionContext): The execution context providing access to task updater,
                request information, and task state

        Returns:
            None: All updates are sent through context.updater.update_status()

        Raises:
            No exceptions are raised. Unsupported content types are silently skipped.
            Invalid data URIs are passed through as-is for downstream handling.

        Processing Details:
            1. Checks message role - User messages are filtered out (common agent framework behavior)
            2. Extracts metadata from message.additional_properties if available
            3. Iterates through all content items in the message
            4. For each content item:
               - TextContent: Creates TextPart with the text
               - DataContent: Extracts base64 data from URI and creates FilePart with FileWithBytes
               - UriContent: Creates FilePart with FileWithUri including mime type
               - Other types: Silently skipped
            5. Collects all converted parts
            6. If any parts were created, sends update to task with TaskState.working
            7. Metadata is passed through to the A2A message

        Example:
            Demonstrating the internal processing:

            ```python
            # Example 1: Text message processing
            message = AgentRunResponseUpdate(
                role=Role.ASSISTANT, contents=[TextContent(text="Task processing started")]
            )
            # Internally:
            # - Role check: ASSISTANT role, continue processing
            # - Content: TextContent detected
            # - Conversion: TextPart created with "Task processing started"
            # - Update: Sent to context.updater with TaskState.working
            await adapter.handle_events(message, context)

            # Example 2: Multiple content types in one message
            message = AgentRunResponseUpdate(
                role=Role.ASSISTANT,
                contents=[
                    TextContent(text="Summary:"),
                    DataContent(uri="data:text/plain;base64,SGVsbG8gV29ybGQ="),
                    UriContent(uri="s3://bucket/results.json", media_type="application/json"),
                ],
            )
            # Internally:
            # - Creates 3 parts: TextPart, FilePart(base64), FilePart(URI)
            # - Sends single combined update with all 3 parts
            await adapter.handle_events(message, context)

            # Example 3: User message filtering
            message = AgentRunResponseUpdate(role=Role.USER, contents=[TextContent(text="Some user input")])
            # Internally:
            # - Role check: USER role detected
            # - Early return: No processing, no update sent
            await adapter.handle_events(message, context)

            # Example 4: Message with metadata
            message = AgentRunResponseUpdate(
                role=Role.ASSISTANT,
                contents=[TextContent(text="Result")],
                additional_properties={"model": "gpt-4", "version": "1.0"},
            )
            # Internally:
            # - Metadata extracted from additional_properties
            # - Metadata passed through to new_agent_message()
            # - Protocol update includes metadata in message envelope
            await adapter.handle_events(message, context)
            ```

        Note:
            - Only agent messages (Role.ASSISTANT) are processed; user messages are ignored
            - Task state is always set to TaskState.working when sending updates
            - Empty messages don't generate protocol updates
            - Multiple content items are batched into a single protocol update for efficiency
            - Invalid base64 in data URIs are passed through unchanged; decoding errors
              are handled downstream
            - Content type filtering is lenient; unknown types are silently skipped
        """
        if message.role == Role.USER:
            # This is a user message, we can ignore it in the context of task updates
            return

        parts: list[Part] = []
        metadata = getattr(message, "additional_properties", None)

        for content in message.contents:
            if isinstance(content, TextContent):
                parts.append(Part(root=TextPart(text=content.text)))
            if isinstance(content, DataContent):
                parts.append(Part(root=FilePart(file=FileWithBytes(bytes=_extract_base64_from_uri(content.uri)))))
            if isinstance(content, UriContent):
                # Handle URI content
                parts.append(
                    Part(
                        root=FilePart(file=FileWithUri(uri=content.uri, mime_type=getattr(content, "media_type", None)))
                    )
                )
            # Silently skip unsupported content types

        if parts:
            await context.updater.update_status(
                state=TaskState.working,
                message=context.updater.new_agent_message(parts=parts, metadata=metadata),
            )


def _extract_base64_from_uri(uri: str) -> str:
    """Extract base64 data from a data URI.

    This helper function parses RFC 2397 data URIs and extracts the base64-encoded payload.
    Data URIs follow the format: data:[<media type>][;base64],<data>

    The function specifically handles base64-encoded data URIs and returns the encoded
    payload portion which can be decoded by downstream consumers.

    Args:
        uri (str): A complete data URI string in the format specified by RFC 2397.
            Expected format: data:[<media type>][;base64],<data>
            Examples:
            - "data:text/plain;base64,SGVsbG8gV29ybGQ="
            - "data:application/json;base64,eyJrZXkiOiAidmFsdWUifQ=="
            - "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEA..."

    Returns:
        str: The base64-encoded data portion of the URI. If the URI is a valid data URI with
            base64 encoding, returns the base64 string. If the URI doesn't match the expected
            format, returns the input URI unchanged (as a fallback).

    Pattern Explanation:
        The regex pattern used for matching:
        `^data:(?P<media_type>[^;]+);base64,(?P<base64_data>[A-Za-z0-9+/=]+)$`

        - `^data:` - Anchors to start, matches "data:" protocol scheme
        - `(?P<media_type>[^;]+)` - Named group capturing media type (e.g., "text/plain")
        - `;base64,` - Literal characters separating media type from data
        - `(?P<base64_data>[A-Za-z0-9+/=]+)` - Named group capturing valid base64 characters
        - `$` - Anchors to end of string

    Note:
        - Only matches RFC 2397 data URIs with explicit base64 encoding
        - Non-matching URIs are returned unchanged as a fallback (no exception raised)
        - The function does not validate that the base64 string is well-formed or decodable
        - Validation and decoding of the returned base64 data is the responsibility of
          the caller
        - Supports any media type (text/plain, application/json, image/png, etc.)
        - Handles edge cases gracefully: malformed URIs, missing encoding declaration,
          incomplete data portions are all returned unchanged
    """
    pattern = r"^data:(?P<media_type>[^;]+);base64,(?P<base64_data>[A-Za-z0-9+/=]+)$"
    match = re.match(pattern, uri)
    if match:
        return match.group("base64_data")
    return uri
