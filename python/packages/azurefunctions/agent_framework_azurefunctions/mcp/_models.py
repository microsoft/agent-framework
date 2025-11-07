# Copyright (c) Microsoft. All rights reserved.

"""MCP Protocol Data Models.

This module defines the data structures used for MCP protocol communication.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPTool:
    """Represents an MCP tool definition.

    An MCP tool corresponds to a durable agent that can be invoked by MCP clients.
    """

    name: str
    description: str
    inputSchema: dict[str, Any]
    displayName: str | None = None
    category: str | None = None
    examples: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }
        if self.displayName:
            result["displayName"] = self.displayName
        if self.category:
            result["category"] = self.category
        if self.examples:
            result["examples"] = self.examples
        return result


@dataclass
class MCPResource:
    """Represents an MCP resource (e.g., conversation history).

    Resources provide read-only access to data like conversation histories.
    """

    uri: str
    name: str
    mimeType: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "uri": self.uri,
            "name": self.name,
            "mimeType": self.mimeType,
        }
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class MCPCallResult:
    """Result from calling an MCP tool.

    Contains the response content and optional metadata about the invocation.
    """

    content: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] | None = None
    isError: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"content": self.content}
        if self.metadata:
            result["metadata"] = self.metadata
        if self.isError:
            result["isError"] = self.isError
        return result

    @classmethod
    def from_text(
        cls,
        text: str,
        metadata: dict[str, Any] | None = None,
        is_error: bool = False,
    ) -> "MCPCallResult":
        """Create a result from text content."""
        return cls(
            content=[{"type": "text", "text": text}],
            metadata=metadata,
            isError=is_error,
        )

    @classmethod
    def from_error(cls, error_message: str, **metadata: Any) -> "MCPCallResult":
        """Create an error result."""
        return cls(
            content=[{"type": "text", "text": f"Error: {error_message}"}],
            metadata=metadata if metadata else None,
            isError=True,
        )
