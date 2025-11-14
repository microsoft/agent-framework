# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import json

from typing import Any, List, Dict, Optional, cast
from datetime import datetime, timezone

# Base content type

class DurableAgentStateContent:
    extensionData: Optional[Dict]

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
    conversationHistory: List['DurableAgentStateEntry']
    extensionData: Optional[Dict]

    def __init__(self, conversationHistory=None, extensionData=None):
        self.conversationHistory = conversationHistory or []
        self.extensionData = extensionData


class DurableAgentState:
    data: DurableAgentStateData
    schema_version: str = "1.0.0"

    def __init__(self, schema_version: str = "1.0.0"):
        self.data = DurableAgentStateData()
        self.schema_version = schema_version

    def to_dict(self) -> Dict[str, Any]:
        # Serialize conversationHistory
        serialized_history = []
        for entry in self.data.conversationHistory:
            # Properly serialize each entry to a dictionary
            if hasattr(entry, 'to_dict'):
                serialized_history.append(entry.to_dict())
            else:
                # Fallback for already-serialized entries
                serialized_history.append(entry)

        return {
            "schemaVersion": self.schema_version,
            "data": {
                "conversationHistory": serialized_history,
                "extensionData": self.data.extensionData
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
                conversationHistory=data_dict.get("conversationHistory", []),
                extensionData=data_dict.get("extensionData")
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

        # Restore the conversation history - deserialize entries from dicts to objects
        history_data = data_dict.get("conversationHistory", [])
        deserialized_history = []
        for entry_dict in history_data:
            if isinstance(entry_dict, dict):
                # Deserialize based on whether it's a request or response
                if "usage" in entry_dict:
                    deserialized_history.append(DurableAgentStateResponse.from_dict(entry_dict))
                elif "response_type" in entry_dict:
                    deserialized_history.append(DurableAgentStateRequest.from_dict(entry_dict))
                else:
                    deserialized_history.append(DurableAgentStateEntry.from_dict(entry_dict))
            else:
                # Already an object
                deserialized_history.append(entry_dict)

        self.data.conversationHistory = deserialized_history
        self.data.extensionData = data_dict.get("extensionData")

    @property
    def message_count(self) -> int:
        """Get the count of conversation entries (requests + responses)."""
        return len(self.data.conversationHistory)

    @property
    def last_response(self) -> str | None:
        """Get the text from the last assistant response in the conversation history."""
        # Iterate through messages in reverse to find the last assistant message
        for entry in reversed(self.data.conversationHistory):
            for message in reversed(entry.messages):
                if message.role == "assistant":
                    return message.text
        return None

    def add_assistant_message(self, content: str, agent_run_response, correlationId: str) -> None:
        """Add an assistant message to the conversation history.

        Args:
            content: The message content
            agent_run_response: The agent's run response
            correlationId: The correlation ID for this response
        """
        # This method is called from the entity after storing the response
        # The response has already been added to conversationHistory, so we don't need to do anything here
        pass

    def try_get_agent_response(self, correlationId: str) -> Dict[str, Any] | None:
        """Try to get an agent response by correlation ID.

        Args:
            correlationId: The correlation ID to search for

        Returns:
            Response data dict if found, None otherwise
        """
        # Search through conversation history for a response with this correlationId
        for entry in self.data.conversationHistory:
            if hasattr(entry, 'correlationId') and entry.correlationId == correlationId:
                # Found the entry, extract response data
                if isinstance(entry, DurableAgentStateResponse):
                    # Get the text content from assistant messages only
                    content = ""
                    for message in entry.messages:
                        if hasattr(message, 'role') and message.role == "assistant" and hasattr(message, 'text'):
                            content += message.text

                    return {
                        "content": content,
                        "message_count": self.message_count,
                        "correlationId": correlationId
                    }
        return None

# Entry classes

class DurableAgentStateEntry:
    json_type: str
    correlationId: str
    created_at: datetime
    messages: List['DurableAgentStateMessage']
    extensionData: Optional[Dict]

    # Request-only
    responseType: Optional[str] = None
    responseSchema: Optional[dict] = None

    # Response-only
    usage: Optional["DurableAgentStateUsage"] = None


    def __init__(self, json_type, correlationId, created_at, messages, extensionData=None, responseType=None, responseSchema=None, usage=None):
        self.json_type = json_type
        self.correlationId = correlationId
        self.created_at = created_at
        self.messages = messages
        self.extensionData = extensionData
        self.responseType = responseType
        self.responseSchema = responseSchema
        self.usage = usage

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "$type": self.json_type,
            "correlationId": self.correlationId,
            "createdAt": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "messages": [m.to_dict() if hasattr(m, 'to_dict') else m for m in self.messages],
            "extensionData": self.extensionData
        }
        if self.json_type == "request":
            data.update({
                "responseType": self.responseType,
                "responseSchema": self.responseSchema,
            })
        elif self.json_type == "response":
            if self.usage:
                data["usage"] = self.usage.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DurableAgentStateEntry':
        from dateutil import parser as date_parser
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = date_parser.parse(created_at)

        messages = []
        for msg_dict in data.get("messages", []):
            if isinstance(msg_dict, dict):
                messages.append(DurableAgentStateMessage.from_dict(msg_dict))
            else:
                messages.append(msg_dict)

        return cls(
            correlationId=data.get("correlationId"),
            created_at=created_at,
            messages=messages,
            extensionData=data.get("extensionData")
        )


class DurableAgentStateRequest(DurableAgentStateEntry):
    response_type: Optional[str] = None
    response_schema: Optional[Dict] = None

    def __init__(self, correlationId, created_at, messages, json_type, extensionData=None, response_type=None, response_schema=None):
        self.correlationId = correlationId
        self.created_at = created_at
        self.messages = messages
        self.json_type = json_type
        self.extensionData = extensionData
        self.response_type = response_type
        self.response_schema = response_schema

    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict["response_type"] = self.response_type
        base_dict["response_schema"] = self.response_schema
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DurableAgentStateRequest':
        from dateutil import parser as date_parser
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = date_parser.parse(created_at)

        messages = []
        for msg_dict in data.get("messages", []):
            if isinstance(msg_dict, dict):
                messages.append(DurableAgentStateMessage.from_dict(msg_dict))
            else:
                messages.append(msg_dict)

        return cls(
            json_type=data.get("$type", "request"),
            correlationId=data.get("correlationId"),
            created_at=created_at,
            messages=messages,
            extensionData=data.get("extensionData"),
            response_type=data.get("response_type"),
            response_schema=data.get("response_schema")
        )

    @staticmethod
    def from_run_request(content):
        from agent_framework import TextContent
        return DurableAgentStateRequest(correlationId=content.correlationId,
                                        messages=[DurableAgentStateMessage.from_chat_message(content)],
                                        created_at=datetime.now(tz=timezone.utc),
                                        json_type="request",
                                        extensionData=content.extensionData if hasattr(content, 'extensionData') else None,
                                        response_type="text" if isinstance(content.response_format, TextContent) else "json",
                                        response_schema=content.response_format)


class DurableAgentStateResponse(DurableAgentStateEntry):
    usage: Optional['DurableAgentStateUsage'] = None

    def __init__(self, json_type, correlationId, created_at, messages, extensionData=None, usage=None):
        self.json_type = json_type
        self.correlationId = correlationId
        self.created_at = created_at
        self.messages = messages
        self.extensionData = extensionData
        self.usage = usage

    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict["usage"] = self.usage.to_dict() if self.usage and hasattr(self.usage, 'to_dict') else self.usage
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DurableAgentStateResponse':
        from dateutil import parser as date_parser
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = date_parser.parse(created_at)

        messages = []
        for msg_dict in data.get("messages", []):
            if isinstance(msg_dict, dict):
                messages.append(DurableAgentStateMessage.from_dict(msg_dict))
            else:
                messages.append(msg_dict)

        usage_dict = data.get("usage")
        usage = None
        if usage_dict and isinstance(usage_dict, dict):
            usage = DurableAgentStateUsage.from_dict(usage_dict)
        elif usage_dict:
            usage = usage_dict

        return cls(
            json_type=data.get("$type", "response"),
            correlationId=data.get("correlationId"),
            created_at=created_at,
            messages=messages,
            extensionData=data.get("extensionData"),
            usage=usage
        )

    @staticmethod
    def from_run_response(correlationId: str, response) -> DurableAgentStateResponse:
        """
        Creates a DurableAgentStateResponse from an AgentRunResponse.
        """
        # Determine the earliest created_at timestamp among messages (if available)
        timestamps = [m.created_at for m in response.messages if hasattr(m, 'created_at') and m.created_at is not None]
        created_at = min(timestamps) if timestamps else datetime.now(tz=timezone.utc)

        return DurableAgentStateResponse(
            json_type="response",
            correlationId=correlationId,
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
    extensionData: Optional[Dict] = None

    def __init__(self, role, contents, author_name=None, created_at=None, extensionData=None):
        self.role = role
        self.contents = contents
        self.author_name = author_name
        self.created_at = created_at
        self.extensionData = extensionData

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "contents": [
                {"$type": c.to_dict().get("type", "text"), **{k: v for k, v in c.to_dict().items() if k != "type"}} for c in self.contents
            ],
            "authorName": self.author_name,
            "createdAt": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "extensionData": self.extensionData
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DurableAgentStateMessage':
        from dateutil import parser as date_parser
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = date_parser.parse(created_at)

        contents = []
        for content_dict in data.get("contents", []):
            if isinstance(content_dict, dict):
                content_type = content_dict.get("type")
                if content_type == "text":
                    contents.append(DurableAgentStateTextContent(text=content_dict.get("text")))
                elif content_type == "data":
                    contents.append(DurableAgentStateDataContent(uri=content_dict.get("uri"), media_type=content_dict.get("media_type")))
                elif content_type == "error":
                    contents.append(DurableAgentStateErrorContent(message=content_dict.get("message"), error_code=content_dict.get("error_code"), details=content_dict.get("details")))
                elif content_type == "function_call":
                    contents.append(DurableAgentStateFunctionCallContent(call_id=content_dict.get("call_id"), name=content_dict.get("name"), arguments=content_dict.get("arguments")))
                elif content_type == "function_result":
                    contents.append(DurableAgentStateFunctionResultContent(call_id=content_dict.get("call_id"), result=content_dict.get("result")))
                elif content_type == "hosted_file":
                    contents.append(DurableAgentStateHostedFileContent(file_id=content_dict.get("file_id")))
                elif content_type == "hosted_vector_store":
                    contents.append(DurableAgentStateHostedVectorStoreContent(vector_store_id=content_dict.get("vector_store_id")))
                elif content_type == "text_reasoning":
                    contents.append(DurableAgentStateTextReasoningContent(text=content_dict.get("text")))
                elif content_type == "uri":
                    contents.append(DurableAgentStateUriContent(uri=content_dict.get("uri"), media_type=content_dict.get("media_type")))
                elif content_type == "usage":
                    usage_data = content_dict.get("usage")
                    if usage_data and isinstance(usage_data, dict):
                        contents.append(DurableAgentStateUsageContent(usage=DurableAgentStateUsage.from_dict(usage_data)))
                elif content_type == "unknown":
                    contents.append(DurableAgentStateUnknownContent(content=content_dict.get("content")))
            else:
                contents.append(content_dict)

        return cls(
            role=data.get("role"),
            contents=contents,
            author_name=data.get("author_name"),
            created_at=created_at,
            extensionData=data.get("extensionData")
        )

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
            extensionData=content.extensionData if hasattr(content, 'extensionData') else None
        )

    def to_chat_message(self):
        from agent_framework import ChatMessage
        # Convert DurableAgentStateContent objects back to agent_framework content objects
        ai_contents = [c.to_ai_content() for c in self.contents]
        return ChatMessage(role=self.role, contents=ai_contents, author_name=self.author_name, created_at=self.created_at, extensionData=self.extensionData)

# Content subclasses

class DurableAgentStateDataContent(DurableAgentStateContent):
    uri: str = ""
    media_type: Optional[str] = None

    def __init__(self, uri, media_type=None):
        self.uri = uri
        self.media_type = media_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "data",
            "uri": self.uri,
            "mediaType": self.media_type
        }

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "error",
            "message": self.message,
            "errorCode": self.error_code,
            "details": self.details
        }

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "function_call",
            "callId": self.call_id,
            "name": self.name,
            "arguments": self.arguments
        }

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "function_result",
            "callId": self.call_id,
            "result": self.result
        }

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "hosted_file",
            "fileId": self.file_id
        }

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "hosted_vector_store",
            "vectorStoreId": self.vector_store_id
        }

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "text",
            "text": self.text
        }

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "text_reasoning",
            "text": self.text
        }

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "uri",
            "uri": self.uri,
            "mediaType": self.media_type
        }

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
    extensionData: Optional[Dict] = None

    def __init__(self, input_token_count=None, output_token_count=None, total_token_count=None, extensionData=None):
        self.input_token_count = input_token_count
        self.output_token_count = output_token_count
        self.total_token_count = total_token_count
        self.extensionData = extensionData

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inputTokenCount": self.input_token_count,
            "outputTokenCount": self.output_token_count,
            "totalTokenCount": self.total_token_count,
            "extensionData": self.extensionData
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DurableAgentStateUsage':
        return cls(
            input_token_count=data.get("input_token_count"),
            output_token_count=data.get("output_token_count"),
            total_token_count=data.get("total_token_count"),
            extensionData=data.get("extensionData")
        )

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "usage",
            "usage": self.usage.to_dict() if hasattr(self.usage, 'to_dict') else self.usage
        }

    @staticmethod
    def from_usage_content(content):
        return DurableAgentStateUsageContent(usage=DurableAgentStateUsage.from_usage(content.details))

    def to_ai_content(self):
        from agent_framework import UsageContent
        return UsageContent(details=self.usage.to_usage_details())


class DurableAgentStateUnknownContent(DurableAgentStateContent):
    content: dict

    def __init__(self, content):
        self.content = content

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "unknown",
            "content": self.content
        }

    @staticmethod
    def from_unknown_content(content):
        return DurableAgentStateUnknownContent(content=json.loads(content))

    def to_ai_content(self):
        from agent_framework import BaseContent
        if not self.content:
            raise Exception(f"The content is missing and cannot be converted to valid AI content.")
        return BaseContent(content=json.loads(self.content))