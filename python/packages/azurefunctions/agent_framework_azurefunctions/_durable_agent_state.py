# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import json

from typing import Any, List, Dict, Optional, cast
from datetime import datetime, timezone

# Base content type

class DurableAgentStateContent:
    extension_data: Optional[Dict]

    def to_ai_content(self):
        raise NotImplementedError

    @staticmethod
    def from_ai_content(content):
        # Map AI content type to appropriate DurableAgentStateContent subclass
        from agent_framework import (
            DataContent, ErrorContent, FunctionCallContent, FunctionResultContent,
            HostedFileContent, HostedVectorStoreContent, TextContent,
            TextReasoningContent, UriContent, UsageContent
        )

        if isinstance(content, DataContent):
            return DurableAgentStateDataContent.from_data_content(content)
        elif isinstance(content, ErrorContent):
            return DurableAgentStateErrorContent.from_error_content(content)
        elif isinstance(content, FunctionCallContent):
            return DurableAgentStateFunctionCallContent.from_function_call_content(content)
        elif isinstance(content, FunctionResultContent):
            return DurableAgentStateFunctionResultContent.from_function_result_content(content)
        elif isinstance(content, HostedFileContent):
            return DurableAgentStateHostedFileContent.from_hosted_file_content(content)
        elif isinstance(content, HostedVectorStoreContent):
            return DurableAgentStateHostedVectorStoreContent.from_hosted_vector_store_content(content)
        elif isinstance(content, TextContent):
            return DurableAgentStateTextContent.from_text_content(content)
        elif isinstance(content, TextReasoningContent):
            return DurableAgentStateTextReasoningContent.from_text_reasoning_content(content)
        elif isinstance(content, UriContent):
            return DurableAgentStateUriContent.from_uri_content(content)
        elif isinstance(content, UsageContent):
            return DurableAgentStateUsageContent.from_usage_content(content)
        else:
            return DurableAgentStateUnknownContent.from_unknown_content(content)

# Core state classes

class DurableAgentStateData:
    conversation_history: List['DurableAgentStateEntry']
    extension_data: Optional[Dict]

    def __init__(self, conversation_history=None, extension_data=None):
        self.conversation_history = conversation_history or []
        self.extension_data = extension_data


class DurableAgentState:
    data: DurableAgentStateData
    schema_version: str = "1.0.0"

    def __init__(self, schema_version: str = "1.0.0"):
        self.data = DurableAgentStateData()
        self.schema_version = schema_version

    def to_dict(self) -> Dict[str, Any]:
        # Serialize conversation_history
        serialized_history = []
        for entry in self.data.conversation_history:
            # For now, store entries as-is (they should be serializable)
            # In production, you'd want proper serialization logic here
            serialized_history.append(entry)

        return {
            "schemaVersion": self.schema_version,
            "data": {
                "conversation_history": serialized_history,
                "extension_data": self.data.extension_data
            },
            "message_count": self.message_count,
            "last_response": self.last_response,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> "DurableAgentState":
        schema_version = obj.get("schemaVersion")
        if not schema_version:
            raise ValueError("The durable agent state is missing the 'schemaVersion' property.")

        if not schema_version.startswith("1."):
            raise ValueError(f"The durable agent state schema version '{schema_version}' is not supported.")

        data_dict = obj.get("data")
        if data_dict is None:
            raise ValueError("The durable agent state is missing the 'data' property.")

        instance = cls(schema_version=schema_version)
        # Deserialize the data dict into DurableAgentStateData
        if isinstance(data_dict, dict):
            instance.data = DurableAgentStateData(
                conversation_history=data_dict.get("conversation_history", []),
                extension_data=data_dict.get("extension_data")
            )
        return instance

    @classmethod
    def from_json(cls, json_str: str) -> "DurableAgentState":
        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError("The durable agent state is not valid JSON.") from e

        return cls.from_dict(obj)

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore state from a dictionary.

        Args:
            state: Dictionary containing schemaVersion and data (full state structure)
        """
        # Extract the data portion from the state
        data_dict = state.get("data", {})

        # Restore the conversation history
        history_data = data_dict.get("conversation_history", [])
        self.data.conversation_history = history_data
        self.data.extension_data = data_dict.get("extension_data")

    @property
    def message_count(self) -> int:
        """Get the count of conversation entries (requests + responses)."""
        return len(self.data.conversation_history)

    @property
    def last_response(self) -> str | None:
        """Get the text from the last assistant response in the conversation history."""
        # Iterate through messages in reverse to find the last assistant message
        for entry in reversed(self.data.conversation_history):
            for message in reversed(entry.messages):
                if message.role == "assistant":
                    return message.text
        return None

    def add_assistant_message(self, content: str, agent_run_response, correlation_id: str) -> None:
        """Add an assistant message to the conversation history.

        Args:
            content: The message content
            agent_run_response: The agent's run response
            correlation_id: The correlation ID for this response
        """
        # This method is called from the entity after storing the response
        # The response has already been added to conversation_history, so we don't need to do anything here
        pass

# Entry classes

class DurableAgentStateEntry:
    correlation_id: str
    created_at: datetime
    messages: List['DurableAgentStateMessage']
    extension_data: Optional[Dict]

    def __init__(self, correlation_id, created_at, messages, extension_data=None):
        self.correlation_id = correlation_id
        self.created_at = created_at
        self.messages = messages
        self.extension_data = extension_data


class DurableAgentStateRequest(DurableAgentStateEntry):
    response_type: Optional[str] = None
    response_schema: Optional[Dict] = None

    def __init__(self, correlation_id, created_at, messages, extension_data=None, response_type=None, response_schema=None):
        self.correlation_id = correlation_id
        self.created_at = created_at
        self.messages = messages
        self.extension_data = extension_data
        self.response_type = response_type
        self.response_schema = response_schema

    @staticmethod
    def from_run_request(content):
        from agent_framework import TextContent
        return DurableAgentStateRequest(correlation_id=content.correlation_id,
                                        messages=[DurableAgentStateMessage.from_chat_message(content)],
                                        created_at=datetime.now(tz=timezone.utc),
                                        extension_data=content.extension_data if hasattr(content, 'extension_data') else None,
                                        response_type="text" if isinstance(content.response_format, TextContent) else "json",
                                        response_schema=content.response_format)


class DurableAgentStateResponse(DurableAgentStateEntry):
    usage: Optional['DurableAgentStateUsage'] = None

    def __init__(self, correlation_id, created_at, messages, extension_data=None, usage=None):
        self.correlation_id = correlation_id
        self.created_at = created_at
        self.messages = messages
        self.extension_data = extension_data
        self.usage = usage

    @staticmethod
    def from_run_response(correlation_id: str, response) -> DurableAgentStateResponse:
        """
        Creates a DurableAgentStateResponse from an AgentRunResponse.
        """
        # Determine the earliest created_at timestamp among messages (if available)
        timestamps = [m.created_at for m in response.messages if hasattr(m, 'created_at') and m.created_at is not None]
        created_at = min(timestamps) if timestamps else datetime.now(tz=timezone.utc)

        return DurableAgentStateResponse(
            correlation_id=correlation_id,
            created_at=created_at,
            messages=[DurableAgentStateMessage.from_chat_message(m) for m in response.messages],
            usage=DurableAgentStateUsage.from_usage(response.usage) if hasattr(response, 'usage') and response.usage else None
        )

    def to_run_response(self):
        """
        Converts this DurableAgentStateResponse back to an AgentRunResponse.
        """
        from agent_framework import AgentRunResponse

        return AgentRunResponse(
            created_at=self.created_at,
            messages=[m.to_chat_message() for m in self.messages],
            usage=self.usage.to_usage_details() if self.usage else None
        )

# Message class

class DurableAgentStateMessage:
    role: str
    contents: List[DurableAgentStateContent]
    author_name: Optional[str] = None
    created_at: Optional[datetime] = None
    extension_data: Optional[Dict] = None

    def __init__(self, role, contents, author_name=None, created_at=None, extension_data=None):
        self.role = role
        self.contents = contents
        self.author_name = author_name
        self.created_at = created_at
        self.extension_data = extension_data

    @property
    def text(self) -> str:
        """Extract text from the contents list."""
        text_parts = []
        for content in self.contents:
            if isinstance(content, DurableAgentStateTextContent):
                text_parts.append(content.text or "")
        return "".join(text_parts)

    @staticmethod
    def from_chat_message(content):
        # Convert to a list of DurableAgentStateContent objects
        contents_list = []

        if hasattr(content, 'message') and isinstance(content.message, str):
            # RunRequest with 'message' attribute
            contents_list = [DurableAgentStateTextContent(text=content.message)]
        elif hasattr(content, 'contents') and content.contents:
            # ChatMessage with 'contents' attribute - convert each content object
            for c in content.contents:
                converted = DurableAgentStateContent.from_ai_content(c)
                contents_list.append(converted)

        # Convert role enum to string if needed
        role_value = content.role.value if hasattr(content.role, 'value') else str(content.role)

        return DurableAgentStateMessage(
            role=role_value,
            contents=contents_list,
            author_name=content.author_name if hasattr(content, 'author_name') else None,
            created_at=content.created_at if hasattr(content, 'created_at') else None,
            extension_data=content.extension_data if hasattr(content, 'extension_data') else None
        )

    def to_chat_message(self):
        from agent_framework import ChatMessage
        # Convert DurableAgentStateContent objects back to agent_framework content objects
        ai_contents = [c.to_ai_content() for c in self.contents]
        return ChatMessage(role=self.role, contents=ai_contents, author_name=self.author_name, created_at=self.created_at, extension_data=self.extension_data)

# Content subclasses

class DurableAgentStateDataContent(DurableAgentStateContent):
    uri: str = ""
    media_type: Optional[str] = None

    def __init__(self, uri, media_type=None):
        self.uri = uri
        self.media_type = media_type

    @staticmethod
    def from_data_content(content):
        return DurableAgentStateDataContent(uri=content.uri, media_type=content.media_type)

    def to_ai_content(self):
        from agent_framework import DataContent
        return DataContent(uri=self.uri, media_type=self.media_type)


class DurableAgentStateErrorContent(DurableAgentStateContent):
    message: Optional[str] = None
    error_code: Optional[str] = None
    details: Optional[str] = None

    def __init__(self, message=None, error_code=None, details=None):
        self.message = message
        self.error_code = error_code
        self.details = details

    @staticmethod
    def from_error_content(content):
        return DurableAgentStateErrorContent(message=content.message, error_code=content.error_code, details=content.details)

    def to_ai_content(self):
        from agent_framework import ErrorContent
        return ErrorContent(message=self.message, error_code=self.error_code, details=self.details)


class DurableAgentStateFunctionCallContent(DurableAgentStateContent):
    call_id: str
    name: str
    arguments: Dict[str, object]

    def __init__(self, call_id, name, arguments):
        self.call_id = call_id
        self.name = name
        self.arguments = arguments

    @staticmethod
    def from_function_call_content(content):
        return DurableAgentStateFunctionCallContent(
            call_id=content.call_id,
            name=content.name,
            arguments=content.arguments if content.arguments else {}
        )

    def to_ai_content(self):
        from agent_framework import FunctionCallContent
        return FunctionCallContent(call_id=self.call_id, name=self.name, arguments=self.arguments)


class DurableAgentStateFunctionResultContent(DurableAgentStateContent):
    call_id: str
    result: Optional[object] = None

    def __init__(self, call_id, result=None):
        self.call_id = call_id
        self.result = result

    @staticmethod
    def from_function_result_content(content):
        return DurableAgentStateFunctionResultContent(call_id=content.call_id, result=content.result)

    def to_ai_content(self):
        from agent_framework import FunctionResultContent
        return FunctionResultContent(call_id=self.call_id, result=self.result)


class DurableAgentStateHostedFileContent(DurableAgentStateContent):
    file_id: str

    def __init__(self, file_id):
        self.file_id = file_id

    @staticmethod
    def from_hosted_file_content(content):
        return DurableAgentStateHostedFileContent(file_id=content.file_id)

    def to_ai_content(self):
        from agent_framework import HostedFileContent
        return HostedFileContent(file_id=self.file_id)


class DurableAgentStateHostedVectorStoreContent(DurableAgentStateContent):
    vector_store_id: str

    def __init__(self, vector_store_id):
        self.vector_store_id = vector_store_id

    @staticmethod
    def from_hosted_vector_store_content(content):
        return DurableAgentStateHostedVectorStoreContent(vector_store_id=content.vector_store_id)

    def to_ai_content(self):
        from agent_framework import HostedVectorStoreContent
        return HostedVectorStoreContent(vector_store_id=self.vector_store_id)


class DurableAgentStateTextContent(DurableAgentStateContent):
    text: Optional[str] = None

    def __init__(self, text):
        self.text = text

    @staticmethod
    def from_text_content(content):
        return DurableAgentStateTextContent(text=content.text)

    def to_ai_content(self):
        from agent_framework import TextContent
        return TextContent(text=self.text)


class DurableAgentStateTextReasoningContent(DurableAgentStateContent):
    text: Optional[str] = None

    def __init__(self, text):
        self.text = text

    @staticmethod
    def from_text_reasoning_content(content):
        return DurableAgentStateTextReasoningContent(text=content.text)

    def to_ai_content(self):
        from agent_framework import TextReasoningContent
        return TextReasoningContent(text=self.text)


class DurableAgentStateUriContent(DurableAgentStateContent):
    uri: str
    media_type: str

    def __init__(self, uri, media_type):
        self.uri = uri
        self.media_type = media_type

    @staticmethod
    def from_uri_content(content):
        return DurableAgentStateUriContent(uri=content.uri, media_type=content.media_type)

    def to_ai_content(self):
        from agent_framework import UriContent
        return UriContent(uri=self.uri, media_type=self.media_type)


class DurableAgentStateUsage:
    input_token_count: Optional[int] = None
    output_token_count: Optional[int] = None
    total_token_count: Optional[int] = None
    extension_data: Optional[Dict] = None

    def __init__(self, input_token_count=None, output_token_count=None, total_token_count=None, extension_data=None):
        self.input_token_count = input_token_count
        self.output_token_count = output_token_count
        self.total_token_count = total_token_count
        self.extension_data = extension_data

    @staticmethod
    def from_usage(usage):
        if usage is None:
            return None
        return DurableAgentStateUsage(
            input_token_count=usage.input_token_count,
            output_token_count=usage.output_token_count,
            total_token_count=usage.total_token_count
        )

    def to_usage_details(self):
        # Convert back to AI SDK UsageDetails
        from agent_framework import UsageDetails
        return UsageDetails(
            input_token_count=self.input_token_count,
            output_token_count=self.output_token_count,
            total_token_count=self.total_token_count
        )


class DurableAgentStateUsageContent(DurableAgentStateContent):
    usage: DurableAgentStateUsage = DurableAgentStateUsage()

    def __init__(self, usage):
        self.usage = usage

    @staticmethod
    def from_usage_content(content):
        return DurableAgentStateUsageContent(usage=DurableAgentStateUsage.from_usage(content.details))

    def to_ai_content(self):
        from agent_framework import UsageContent
        return UsageContent(details=self.usage.to_usage_details())


class DurableAgentStateUnknownContent(DurableAgentStateContent):
    content: dict

    @staticmethod
    def from_unknown_content(content):
        return DurableAgentStateUnknownContent(content=json.loads(content))

    def to_ai_content(self):
        from agent_framework import BaseContent
        if not self.content:
            raise Exception(f"The content is missing and cannot be converted to valid AI content.")
        return BaseContent(content=json.loads(self.content))
