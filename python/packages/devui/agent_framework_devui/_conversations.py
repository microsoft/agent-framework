# Copyright (c) Microsoft. All rights reserved.

"""Conversation storage abstraction for OpenAI Conversations API.

This module provides a clean abstraction layer for managing conversations
with in-memory message storage.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import MutableSequence
from typing import Any, Literal, cast

from agent_framework import AgentSession, Content, Message
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage, WorkflowCheckpoint
from openai.types.conversations import Conversation, ConversationDeletedResource
from openai.types.conversations.conversation_item import ConversationItem
from openai.types.conversations.message import Content as OpenAIContent
from openai.types.conversations.message import Message as OpenAIMessage
from openai.types.conversations.text_content import TextContent
from openai.types.responses import (
    ResponseFunctionToolCallItem,
    ResponseFunctionToolCallOutputItem,
    ResponseInputFile,
    ResponseInputImage,
)

from ._utils import infer_media_type

# Type alias for OpenAI Message role literals
MessageRole = Literal["unknown", "user", "assistant", "system", "critic", "discriminator", "developer", "tool"]

# Checkpoint item type constants
CONVERSATION_ITEM_TYPE_CHECKPOINT = "checkpoint"
CONVERSATION_TYPE_CHECKPOINT_CONTAINER = "checkpoint_container"


class ConversationStore(ABC):
    """Abstract base class for conversation storage.

    Provides OpenAI Conversations API interface while managing
    message storage internally.
    """

    @abstractmethod
    def create_conversation(
        self, metadata: dict[str, str] | None = None, conversation_id: str | None = None
    ) -> Conversation:
        """Create a new conversation.

        Args:
            metadata: Optional metadata dict (e.g., {"agent_id": "weather_agent"})
            conversation_id: Optional conversation ID (if None, generates one)

        Returns:
            Conversation object with generated or provided ID
        """
        pass

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Retrieve conversation metadata.

        Args:
            conversation_id: Conversation ID

        Returns:
            Conversation object or None if not found
        """
        pass

    @abstractmethod
    def update_conversation(self, conversation_id: str, metadata: dict[str, str]) -> Conversation:
        """Update conversation metadata.

        Args:
            conversation_id: Conversation ID
            metadata: New metadata dict

        Returns:
            Updated Conversation object

        Raises:
            ValueError: If conversation not found
        """
        pass

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> ConversationDeletedResource:
        """Delete conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            ConversationDeletedResource object

        Raises:
            ValueError: If conversation not found
        """
        pass

    @abstractmethod
    async def add_items(self, conversation_id: str, items: list[dict[str, Any]]) -> list[ConversationItem]:
        """Add items to conversation.

        Args:
            conversation_id: Conversation ID
            items: List of conversation items to add

        Returns:
            List of added ConversationItem objects

        Raises:
            ValueError: If conversation not found
        """
        pass

    @abstractmethod
    async def list_items(
        self, conversation_id: str, limit: int = 100, after: str | None = None, order: str = "asc"
    ) -> tuple[list[ConversationItem], bool]:
        """List conversation items.

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of items to return
            after: Cursor for pagination (item_id)
            order: Sort order ("asc" or "desc")

        Returns:
            Tuple of (items list, has_more boolean)

        Raises:
            ValueError: If conversation not found
        """
        pass

    @abstractmethod
    async def get_item(self, conversation_id: str, item_id: str) -> ConversationItem | None:
        """Get a specific conversation item by ID.

        Supports checkpoint items - will load full checkpoint state from storage.
        For checkpoints, the full state is included in metadata.full_checkpoint.

        Args:
            conversation_id: Conversation ID
            item_id: Item ID

        Returns:
            ConversationItem or None if not found
        """
        pass

    @abstractmethod
    def get_session(self, conversation_id: str) -> AgentSession | None:
        """Get AgentSession for agent execution.

        This is the critical method that allows the executor to get the
        AgentSession for running agents with conversation context.

        Args:
            conversation_id: Conversation ID

        Returns:
            AgentSession object or None if not found
        """
        pass

    @abstractmethod
    async def list_conversations_by_metadata(self, metadata_filter: dict[str, str]) -> list[Conversation]:
        """Filter conversations by metadata (e.g., agent_id).

        Args:
            metadata_filter: Metadata key-value pairs to match

        Returns:
            List of matching Conversation objects
        """
        pass

    @abstractmethod
    def add_trace(self, conversation_id: str, trace_event: dict[str, Any]) -> None:
        """Add a trace event to the conversation for context inspection.

        Traces capture execution metadata like token usage, timing, and LLM context
        that is useful for debugging.

        Args:
            conversation_id: Conversation ID
            trace_event: Trace event data (from ResponseTraceEvent.data)
        """
        pass

    @abstractmethod
    def get_traces(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get all trace events for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of trace event dicts, or empty list if not found
        """
        pass


class InMemoryConversationStore(ConversationStore):
    """In-memory conversation storage.

    This implementation stores conversations in memory with their
    underlying message lists and AgentSession instances for execution.
    """

    def __init__(self) -> None:
        """Initialize in-memory conversation storage.

        Storage structure maps conversation IDs to conversation data including
        messages, metadata, and cached ConversationItems.
        """
        self._conversations: dict[str, dict[str, Any]] = {}

        # Item index for O(1) lookup: {conversation_id: {item_id: ConversationItem}}
        self._item_index: dict[str, dict[str, ConversationItem]] = {}

    def create_conversation(
        self, metadata: dict[str, str] | None = None, conversation_id: str | None = None
    ) -> Conversation:
        """Create a new conversation with message storage and checkpoint storage."""
        conv_id = conversation_id or f"conv_{uuid.uuid4().hex}"
        created_at = int(time.time())

        # Create message list for internal storage and AgentSession for execution
        messages: list[Message] = []
        session = AgentSession(session_id=conv_id)

        # Create session-scoped checkpoint storage (one per conversation)
        checkpoint_storage = InMemoryCheckpointStorage()

        self._conversations[conv_id] = {
            "id": conv_id,
            "messages": messages,
            "session": session,
            "checkpoint_storage": checkpoint_storage,
            "metadata": metadata or {},
            "created_at": created_at,
            "items": [],
            "traces": [],  # Trace events for context inspection (token usage, timing, etc.)
        }

        # Initialize item index for this conversation
        self._item_index[conv_id] = {}

        return Conversation(id=conv_id, object="conversation", created_at=created_at, metadata=metadata)

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Retrieve conversation metadata."""
        conv_data = self._conversations.get(conversation_id)
        if not conv_data:
            return None

        return Conversation(
            id=conv_data["id"],
            object="conversation",
            created_at=conv_data["created_at"],
            metadata=conv_data.get("metadata"),
        )

    def update_conversation(self, conversation_id: str, metadata: dict[str, str]) -> Conversation:
        """Update conversation metadata."""
        conv_data = self._conversations.get(conversation_id)
        if not conv_data:
            raise ValueError(f"Conversation {conversation_id} not found")

        conv_data["metadata"] = metadata

        return Conversation(
            id=conv_data["id"],
            object="conversation",
            created_at=conv_data["created_at"],
            metadata=metadata,
        )

    def delete_conversation(self, conversation_id: str) -> ConversationDeletedResource:
        """Delete conversation."""
        if conversation_id not in self._conversations:
            raise ValueError(f"Conversation {conversation_id} not found")

        del self._conversations[conversation_id]
        # Cleanup item index
        self._item_index.pop(conversation_id, None)

        return ConversationDeletedResource(id=conversation_id, object="conversation.deleted", deleted=True)

    async def add_items(self, conversation_id: str, items: list[dict[str, Any]]) -> list[ConversationItem]:
        """Add items to conversation."""
        conv_data = self._conversations.get(conversation_id)
        if not conv_data:
            raise ValueError(f"Conversation {conversation_id} not found")

        stored_messages: list[Message] = conv_data["messages"]

        # Convert items to Messages and add to storage
        chat_messages: list[Message] = []
        for item in items:
            role = item.get("role", "user")
            content = item.get("content", [])
            contents: list[Content] = []

            if isinstance(content, str):
                contents.append(Content.from_text(text=content))
            elif isinstance(content, list):
                for content_item in cast(list[object], content):
                    if isinstance(content_item, dict):
                        agent_content = self._to_agent_content(cast(dict[str, Any], content_item))
                        if agent_content is not None:
                            contents.append(agent_content)

            if not contents:
                raise ValueError("Conversation message did not contain any supported content")

            chat_msg = Message(role=role, contents=contents)
            chat_messages.append(chat_msg)

        # Add messages to internal storage
        stored_messages.extend(chat_messages)

        # Create Message objects (ConversationItem is a Union - use concrete Message type)
        conv_items: list[ConversationItem] = []
        for msg in chat_messages:
            item_id = f"item_{uuid.uuid4().hex}"

            # Convert Message contents to OpenAI TextContent format
            message_content: MutableSequence[OpenAIContent] = []
            for content_item in msg.contents:
                openai_content = self._to_openai_content(content_item)
                if openai_content is not None:
                    message_content.append(openai_content)

            # Create Message object (concrete type from ConversationItem union)
            message = OpenAIMessage(
                id=item_id,
                type="message",  # Required discriminator for union
                role=cast(MessageRole, msg.role),  # Safe: Agent Framework roles match OpenAI roles,
                content=message_content,
                status="completed",  # Required field
            )
            conv_items.append(message)

        # Cache items
        conv_data["items"].extend(conv_items)

        # Update item index for O(1) lookup
        if conversation_id not in self._item_index:
            self._item_index[conversation_id] = {}

        for conv_item in conv_items:
            if conv_item.id:  # Guard against None
                self._item_index[conversation_id][conv_item.id] = conv_item

        return conv_items

    async def list_items(
        self, conversation_id: str, limit: int = 100, after: str | None = None, order: str = "asc"
    ) -> tuple[list[ConversationItem], bool]:
        """List conversation items.

        Converts stored Messages to proper OpenAI ConversationItem types:
        - Messages with text/images/files → Message
        - Function calls → ResponseFunctionToolCallItem
        - Function results → ResponseFunctionToolCallOutputItem
        """
        conv_data = self._conversations.get(conversation_id)
        if not conv_data:
            raise ValueError(f"Conversation {conversation_id} not found")

        stored_messages: list[Message] = conv_data["messages"]

        # Convert stored messages to ConversationItem types
        items: list[ConversationItem] = []
        af_messages = stored_messages

        # Convert each AgentFramework Message to appropriate ConversationItem type(s)
        for i, msg in enumerate(af_messages):
            item_id = f"item_{i}"
            role_str = msg.role if hasattr(msg.role, "value") else str(msg.role)
            role = cast(MessageRole, role_str)  # Safe: Agent Framework roles match OpenAI roles

            # Process each content item in the message
            # A single Message may produce multiple ConversationItems
            # (e.g., a message with both text and a function call)
            message_contents: list[TextContent | ResponseInputImage | ResponseInputFile] = []
            function_calls: list[ResponseFunctionToolCallItem] = []
            function_results: list[ResponseFunctionToolCallOutputItem] = []

            for content in msg.contents:
                content_type = getattr(content, "type", None)
                mapped_content = self._to_openai_content(content)

                if mapped_content is not None:
                    message_contents.append(mapped_content)
                elif content_type == "function_call":
                    # Function call - create separate ConversationItem
                    call_id = getattr(content, "call_id", None)
                    name = getattr(content, "name", "")
                    arguments = getattr(content, "arguments", "")

                    if call_id and name:
                        function_calls.append(
                            ResponseFunctionToolCallItem(
                                id=f"{item_id}_call_{call_id}",
                                call_id=call_id,
                                name=name,
                                arguments=arguments,
                                type="function_call",
                                status="completed",
                            )
                        )

                elif content_type == "function_result":
                    # Function result - create separate ConversationItem
                    call_id = getattr(content, "call_id", None)
                    # Output is stored in the 'result' field of FunctionResultContent
                    result_value = getattr(content, "result", None)
                    # Convert result to string (it could be dict, list, or other types)
                    if result_value is None:
                        output = ""
                    elif isinstance(result_value, str):
                        output = result_value
                    else:
                        import json

                        try:
                            output = json.dumps(result_value)
                        except (TypeError, ValueError):
                            output = str(result_value)

                    if call_id:
                        function_results.append(
                            ResponseFunctionToolCallOutputItem(
                                id=f"{item_id}_result_{call_id}",
                                call_id=call_id,
                                output=output,
                                type="function_call_output",
                                status="completed",
                            )
                        )

            # Create ConversationItems based on what we found
            # If message has text/images/files, create a Message item
            if message_contents:
                message = OpenAIMessage(
                    id=item_id,
                    type="message",
                    role=role,
                    content=message_contents,  # type: ignore
                    status="completed",
                )
                items.append(message)

            # Add function call items
            items.extend(function_calls)

            # Add function result items
            items.extend(function_results)

        # Include checkpoints from checkpoint storage as conversation items
        checkpoint_storage = conv_data.get("checkpoint_storage")
        if checkpoint_storage:
            # Get all checkpoints for this conversation
            checkpoints = self._list_all_checkpoints(checkpoint_storage)
            for checkpoint in checkpoints:
                # Create a conversation item for each checkpoint with summary metadata
                # Full checkpoint state is NOT included here (too large for list view)
                # Use get_item() to retrieve full checkpoint details
                # Calculate approximate size of checkpoint
                import json

                checkpoint_json = json.dumps(checkpoint.to_dict())
                checkpoint_size = len(checkpoint_json.encode("utf-8"))

                checkpoint_item = {
                    "id": f"checkpoint_{checkpoint.checkpoint_id}",
                    "type": "checkpoint",
                    "checkpoint_id": checkpoint.checkpoint_id,
                    # Keep workflow_id for backward compatibility with existing UI payloads.
                    "workflow_id": checkpoint.workflow_name,
                    "workflow_name": checkpoint.workflow_name,
                    "timestamp": checkpoint.timestamp,
                    "status": "completed",
                    "metadata": {
                        # Summary metrics for list view
                        "iteration_count": checkpoint.iteration_count,
                        "pending_hil_count": len(checkpoint.pending_request_info_events),
                        "has_pending_hil": len(checkpoint.pending_request_info_events) > 0,
                        "message_count": sum(len(msgs) for msgs in checkpoint.messages.values()),
                        "size_bytes": checkpoint_size,
                        "version": checkpoint.version,
                        "graph_signature_hash": checkpoint.graph_signature_hash,
                    },
                }
                items.append(cast(ConversationItem, checkpoint_item))

        # Apply pagination
        if order == "desc":
            items = items[::-1]

        start_idx = 0
        if after:
            # Find the index after the cursor
            for i, item in enumerate(items):
                if item.id == after:
                    start_idx = i + 1
                    break

        paginated_items = items[start_idx : start_idx + limit]
        has_more = len(items) > start_idx + limit

        return paginated_items, has_more

    @staticmethod
    def _to_agent_content(content: dict[str, Any]) -> Content | None:
        """Convert one supported OpenAI conversation message part."""
        content_type = content.get("type")
        if content_type in ("text", "input_text", "output_text"):
            text = content.get("text")
            return Content.from_text(text=text) if isinstance(text, str) else None

        if content_type == "input_image":
            detail = content.get("detail", "auto")
            image_properties = {
                "openai_content_type": "input_image",
                "detail": detail if isinstance(detail, str) else "auto",
            }
            image_url = content.get("image_url")
            if isinstance(image_url, str) and image_url:
                return Content.from_uri(
                    uri=image_url,
                    media_type=infer_media_type(uri=image_url, default="image/png"),
                    additional_properties=image_properties,
                )
            file_id = content.get("file_id")
            if isinstance(file_id, str) and file_id:
                return Content.from_hosted_file(
                    file_id=file_id,
                    additional_properties=image_properties,
                )
            return None

        if content_type == "input_file":
            filename = content.get("filename")
            filename = filename if isinstance(filename, str) else ""
            detail = content.get("detail")
            file_properties: dict[str, Any] = {"openai_content_type": "input_file"}
            if filename:
                file_properties["filename"] = filename
            if isinstance(detail, str):
                file_properties["detail"] = detail

            file_data = content.get("file_data")
            if isinstance(file_data, str) and file_data:
                media_type = infer_media_type(
                    filename=filename,
                    uri=file_data,
                    default="application/octet-stream",
                )
                uri = file_data if file_data.startswith("data:") else f"data:{media_type};base64,{file_data}"
                return Content.from_uri(
                    uri=uri,
                    media_type=media_type,
                    additional_properties=file_properties,
                )

            file_url = content.get("file_url")
            if isinstance(file_url, str) and file_url:
                return Content.from_uri(
                    uri=file_url,
                    media_type=infer_media_type(
                        filename=filename,
                        uri=file_url,
                        default="application/octet-stream",
                    ),
                    additional_properties=file_properties,
                )

            file_id = content.get("file_id")
            if isinstance(file_id, str) and file_id:
                return Content.from_hosted_file(
                    file_id=file_id,
                    media_type=infer_media_type(filename=filename, default="application/octet-stream"),
                    name=filename or None,
                    additional_properties=file_properties,
                )

        return None

    @staticmethod
    def _to_openai_content(content: Content) -> TextContent | ResponseInputImage | ResponseInputFile | None:
        """Convert one supported Agent Framework message part."""
        content_type = content.type
        if content_type == "text":
            return TextContent(type="text", text=content.text or "")

        additional_properties = content.additional_properties or {}
        openai_content_type = additional_properties.get("openai_content_type")
        is_image = openai_content_type == "input_image" or (
            openai_content_type is None and bool(content.media_type and content.media_type.startswith("image/"))
        )

        if content_type in ("data", "uri"):
            if is_image:
                detail = additional_properties.get("detail", "auto")
                if detail not in ("low", "high", "auto", "original"):
                    detail = "auto"
                return ResponseInputImage(
                    type="input_image",
                    image_url=content.uri,
                    detail=detail,
                )

            filename = additional_properties.get("filename")
            detail = additional_properties.get("detail")
            if detail not in ("low", "high", "auto"):
                detail = None
            return ResponseInputFile(
                type="input_file",
                file_url=content.uri,
                filename=filename if isinstance(filename, str) else None,
                detail=detail,
            )

        if content_type == "hosted_file":
            if is_image:
                detail = additional_properties.get("detail", "auto")
                if detail not in ("low", "high", "auto", "original"):
                    detail = "auto"
                return ResponseInputImage(
                    type="input_image",
                    file_id=content.file_id,
                    detail=detail,
                )

            filename = content.name or additional_properties.get("filename")
            detail = additional_properties.get("detail")
            if detail not in ("low", "high", "auto"):
                detail = None
            return ResponseInputFile(
                type="input_file",
                file_id=content.file_id,
                filename=filename if isinstance(filename, str) else None,
                detail=detail,
            )

        return None

    async def get_item(self, conversation_id: str, item_id: str) -> ConversationItem | None:
        """Get a specific conversation item by ID.

        Supports checkpoint items - will load full checkpoint state from storage.
        For checkpoints, the full state is included in metadata.full_checkpoint.
        """
        # First check item index for messages, function calls, etc. (O(1) lookup)
        conv_items = self._item_index.get(conversation_id, {})
        item = conv_items.get(item_id)
        if item:
            return item

        # If not found and ID is a checkpoint, load from checkpoint storage
        if item_id.startswith("checkpoint_"):
            checkpoint_id = item_id[len("checkpoint_") :]  # Remove "checkpoint_" prefix
            conv_data = self._conversations.get(conversation_id)
            if not conv_data:
                return None

            checkpoint_storage = conv_data.get("checkpoint_storage")
            if not checkpoint_storage:
                return None

            # Load full checkpoint from storage
            try:
                checkpoint = await checkpoint_storage.load(checkpoint_id)
            except Exception:
                return None

            # Calculate size of checkpoint
            import json

            checkpoint_json = json.dumps(checkpoint.to_dict())
            checkpoint_size = len(checkpoint_json.encode("utf-8"))

            # Build checkpoint item with FULL state in metadata
            checkpoint_item = {
                "id": item_id,
                "type": "checkpoint",
                "checkpoint_id": checkpoint.checkpoint_id,
                # Keep workflow_id for backward compatibility with existing UI payloads.
                "workflow_id": checkpoint.workflow_name,
                "workflow_name": checkpoint.workflow_name,
                "timestamp": checkpoint.timestamp,
                "status": "completed",
                "metadata": {
                    # Summary metrics (same as list view)
                    "iteration_count": checkpoint.iteration_count,
                    "pending_hil_count": len(checkpoint.pending_request_info_events),
                    "has_pending_hil": len(checkpoint.pending_request_info_events) > 0,
                    "message_count": sum(len(msgs) for msgs in checkpoint.messages.values()),
                    "size_bytes": checkpoint_size,
                    "version": checkpoint.version,
                    "graph_signature_hash": checkpoint.graph_signature_hash,
                    # 🔥 FULL checkpoint state (lazy loaded)
                    "full_checkpoint": checkpoint.to_dict(),
                },
            }

            return cast(ConversationItem, checkpoint_item)

        return None

    def get_session(self, conversation_id: str) -> AgentSession | None:
        """Get AgentSession for execution - CRITICAL for agent.run()."""
        conv_data = self._conversations.get(conversation_id)
        return conv_data["session"] if conv_data else None

    def add_trace(self, conversation_id: str, trace_event: dict[str, Any]) -> None:
        """Add a trace event to the conversation for context inspection.

        Traces capture execution metadata like token usage, timing, and LLM context
        that is useful for debugging.

        Args:
            conversation_id: Conversation ID
            trace_event: Trace event data (from ResponseTraceEvent.data)
        """
        conv_data = self._conversations.get(conversation_id)
        if conv_data:
            traces = conv_data.get("traces", [])
            traces.append(trace_event)
            conv_data["traces"] = traces

    def get_traces(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get all trace events for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of trace event dicts, or empty list if not found
        """
        conv_data = self._conversations.get(conversation_id)
        return conv_data.get("traces", []) if conv_data else []

    async def list_conversations_by_metadata(self, metadata_filter: dict[str, str]) -> list[Conversation]:
        """Filter conversations by metadata (e.g., agent_id)."""
        results: list[Conversation] = []
        for conv_data in self._conversations.values():
            conv_meta = conv_data.get("metadata", {}).copy()  # Copy to avoid mutating original

            # Check if all filter items match
            if all(conv_meta.get(k) == v for k, v in metadata_filter.items()):
                # Enrich workflow sessions with checkpoint summary
                if conv_meta.get("type") == "workflow_session":
                    checkpoint_storage = conv_data.get("checkpoint_storage")
                    if checkpoint_storage:
                        checkpoints = self._list_all_checkpoints(checkpoint_storage)
                        latest = max(checkpoints, key=lambda cp: cp.timestamp) if checkpoints else None
                        conv_meta["checkpoint_summary"] = {
                            "count": len(checkpoints),
                            "latest_iteration": latest.iteration_count if latest else 0,
                            "has_pending_hil": len(latest.pending_request_info_events) > 0 if latest else False,
                            "pending_hil_count": len(latest.pending_request_info_events) if latest else 0,
                        }

                results.append(
                    Conversation(
                        id=conv_data["id"],
                        object="conversation",
                        created_at=conv_data["created_at"],
                        metadata=conv_meta,
                    )
                )

        # Sort by created_at descending (most recent first)
        results.sort(key=lambda c: c.created_at, reverse=True)

        return results

    @staticmethod
    def _list_all_checkpoints(checkpoint_storage: Any) -> list[WorkflowCheckpoint]:
        """Return all checkpoints from a conversation-scoped storage instance.

        DevUI uses one checkpoint storage per conversation. Core storage APIs now
        require workflow_name filters, so we gather directly from in-memory storage
        internals to provide conversation-wide listing for UI views.
        """
        checkpoint_map = getattr(checkpoint_storage, "_checkpoints", None)
        if isinstance(checkpoint_map, dict):
            return list(cast(dict[str, WorkflowCheckpoint], checkpoint_map).values())
        return []


class CheckpointConversationManager:
    """Manages checkpoint storage for workflow sessions - SESSION-SCOPED.

    Simplified architecture: Each conversation has its own InMemoryCheckpointStorage
    stored in conv_data["checkpoint_storage"]. This manager just retrieves it.
    Session isolation comes from each conversation having a separate storage instance.
    """

    def __init__(self, conversation_store: ConversationStore):
        # Runtime validation since we need specific implementation details
        if not isinstance(conversation_store, InMemoryConversationStore):
            raise TypeError("CheckpointConversationManager currently requires InMemoryConversationStore")
        self._store: InMemoryConversationStore = conversation_store
        # Keep public reference for backward compatibility with tests
        self.conversation_store = conversation_store

    def get_checkpoint_storage(self, conversation_id: str) -> InMemoryCheckpointStorage:
        """Get the checkpoint storage for a specific conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            InMemoryCheckpointStorage instance for this conversation

        Raises:
            ValueError: If conversation not found
        """
        # Access internal conversations dict (we know it's InMemoryConversationStore)
        conversations_dict = cast(dict[str, dict[str, Any]], getattr(self._store, "_conversations", {}))
        conv_data = conversations_dict.get(conversation_id)
        if not conv_data:
            raise ValueError(f"Conversation {conversation_id} not found")

        checkpoint_storage = conv_data["checkpoint_storage"]
        if not isinstance(checkpoint_storage, InMemoryCheckpointStorage):
            raise TypeError(f"Expected InMemoryCheckpointStorage but got {type(checkpoint_storage)}")
        return checkpoint_storage
