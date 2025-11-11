# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import json

from dataclasses import dataclass
from typing import Any, List, Dict, Optional
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


class DurableAgentState:
    data: DurableAgentStateData
    schema_version: str = "1.0.0"

    def __init__(self, data: dict = None, schema_version: str = "1.0.0"):
        self.data = data or {}
        self.schema_version = schema_version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "data": self.data
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

        data = obj.get("data")
        if data is None:
            raise ValueError("The durable agent state is missing the 'data' property.")

        return cls(data=data, schema_version=schema_version)

    @classmethod
    def from_json(cls, json_str: str) -> "DurableAgentState":
        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError("The durable agent state is not valid JSON.") from e

        return cls.from_dict(obj)

# Entry classes

class DurableAgentStateEntry:
    correlation_id: str
    created_at: datetime
    messages: List['DurableAgentStateMessage']
    extension_data: Optional[Dict]


class DurableAgentStateRequest(DurableAgentStateEntry):
    response_type: Optional[str] = None
    response_schema: Optional[Dict] = None

    @staticmethod
    def from_run_request(content):
        from agent_framework import TextContent
        return DurableAgentStateRequest(correlation_id=content.correlation_id,
                                        messages=[DurableAgentStateMessage.from_chat_message(msg) for msg in content.message],
                                        created_at=min((m.created_at for m in content.message), default=datetime.now(tz=timezone.utc)),
                                        extension_data=content.extension_data if hasattr(content, 'extension_data') else None,
                                        response_type="text" if isinstance(content.response_format, TextContent) else "json",
                                        response_schema=content.response_schema)


class DurableAgentStateResponse(DurableAgentStateEntry):
    usage: Optional['DurableAgentStateUsage'] = None

    @staticmethod
    def from_run_response(correlation_id: str, response) -> DurableAgentStateResponse:
        """
        Creates a DurableAgentStateResponse from an AgentRunResponse.
        """
        # Determine the earliest created_at timestamp among messages
        created_at = min((m.created_at for m in response.messages), default=datetime.now(tz=timezone.utc))

        return DurableAgentStateResponse(
            correlation_id=correlation_id,
            created_at=created_at,
            messages=[DurableAgentStateMessage.from_chat_message(m) for m in response.messages],
            usage=DurableAgentStateUsage.from_usage(response.usage) if response.usage else None
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
    extension_data: Optional[Dict]

    @staticmethod
    def from_chat_message(content):
        return DurableAgentStateMessage(role=content.role, contents=content.contents, author_name=content.author_name, created_at=content.created_at, extension_data=content.extension_data)

    def to_chat_message(self):
        from agent_framework import ChatMessage
        return ChatMessage(role=self.role, contents=self.contents, author_name=self.author_name, created_at=self.created_at, extension_data=self.extension_data)

# Content subclasses

class DurableAgentStateDataContent(DurableAgentStateContent):
    uri: str = ""
    media_type: Optional[str] = None

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

    @staticmethod
    def from_function_result_content(content):
        return DurableAgentStateFunctionResultContent(call_id=content.call_id, result=content.result)

    def to_ai_content(self):
        from agent_framework import FunctionResultContent
        return FunctionResultContent(call_id=self.call_id, result=self.result)


class DurableAgentStateHostedFileContent(DurableAgentStateContent):
    file_id: str

    @staticmethod
    def from_hosted_file_content(content):
        return DurableAgentStateHostedFileContent(file_id=content.file_id)

    def to_ai_content(self):
        from agent_framework import HostedFileContent
        return HostedFileContent(file_id=self.file_id)


class DurableAgentStateHostedVectorStoreContent(DurableAgentStateContent):
    vector_store_id: str

    @staticmethod
    def from_hosted_vector_store_content(content):
        return DurableAgentStateHostedVectorStoreContent(vector_store_id=content.vector_store_id)

    def to_ai_content(self):
        from agent_framework import HostedVectorStoreContent
        return HostedVectorStoreContent(vector_store_id=self.vector_store_id)


class DurableAgentStateTextContent(DurableAgentStateContent):
    text: Optional[str] = None

    @staticmethod
    def from_text_content(content):
        return DurableAgentStateTextContent(text=content.text)

    def to_ai_content(self):
        from agent_framework import TextContent
        return TextContent(text=self.text)


class DurableAgentStateTextReasoningContent(DurableAgentStateContent):
    text: Optional[str] = None

    @staticmethod
    def from_text_reasoning_content(content):
        return DurableAgentStateTextReasoningContent(text=content.text)

    def to_ai_content(self):
        from agent_framework import TextReasoningContent
        return TextReasoningContent(text=self.text)


class DurableAgentStateUriContent(DurableAgentStateContent):
    uri: str
    media_type: str

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
    extension_data: Optional[Dict]

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
