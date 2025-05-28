# Core Data Types

A design goal of the new framework to simplify the interaction between agent components
through a common set of data types, minimizing boilerplate code
in the application for transforming data between components.

For example, text, images, function calls, tool schema are
all examples of such data types.
These data types are used to interact with agent components (model clients, tools, MCP, threads, and memory),
forming the connective tissue between those components.

In AutoGen, these are the data types mostly defined in `autogen_core.models` module,
and others like `autogen_core.Image` and `autogen_core.FunctionCall`. This is just
an example as AutoGen has no formal definition of model context.

To start, we should follow [MEAI](https://learn.microsoft.com/en-us/dotnet/api/microsoft.extensions.ai?view=net-9.0-pp).

This document describes the data types from Python perspective,
while for .NET, we should directly use the MEAI data types.

## Content types

```python
class AIContent(ABC):
    """Base class for all AI content types."""
    additional_properties: Dict[str, Any] = field(default_factory=dict)
    """Additional properties for extensibility, allowing custom fields."""

class DataContent(AIContent):
    """Data content type."""
    data: bytes # Raw binary data.
    media_type: str # MIME type of the data, e.g., "image/png", "application/json"
    uri: str # URI constructed from the data.
    base64: str # Base64 encoded data for easy transport.

class ErrorContent(AIContent):
    """Error content type."""
    details: str # Detailed error message.
    error_code: str # Error code for programmatic handling.
    message: str # Human-readable error message.

class FunctionCallContent(AIContent):
    """Function call content type."""
    name: str # Name of the function to call.
    arguments: Dict[str, Any] # Arguments for the function call, serialized as JSON.
    call_id: str # Unique identifier for the function call.
    exception: Optional[Exception] = None # Optional exception for error occurred while mapping the original function call data to this content type.

class FunctionResultContent(AIContent):
    """Function result content type."""
    call_id: str # Unique identifier for the function call.
    result: Any # Result of the function call, or a generic error message.
    exception: Optional[Exception] = None # Optional exception for error occurred while executing the function call.

class TextContent(AIContent):
    """Text content type."""
    text: str

class TextReasoningContent(AIContent):
    """Text reasoning content type."""
    text: str


class UriContent(AIContent):
    """URI content type."""
    uri: str # URI of the content, e.g., a link to an image or document.
    media_type: str # MIME type of the content, e.g., "image/png", "application/pdf".


class UsageDetails:
    input_token_count: Optional[int] = None
    output_token_count: Optional[int] = None
    additional_counts: Optional[Dict[str, int]] = None
    total_token_count: Optional[int] = None


class UsageContent(AIContent):
    """Usage content type."""
    details: UsageDetails

```

## `ChatMessage`

A message in a thread that is sent to or received from a model client.

> Should we use `Message` instead of `ChatMessage`?

> We may need to extend this class to support more framework-level functionalities 
> such as handoff, stopping, and so on?

```python
class ChatRole(Enum):
    """The role of the author in a chat message."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class ChatMessage:
    message_id: str # Unique identifier for the message.
    author: str # Unique identifier for the author of the message.
    role: ChatRole # Role of the author in the chat, e.g., user, assistant, system, tool.
    contents: List[AIContent] # List of content types in the message, e.g., text, images, function calls.
```

## Tool types

Align with the [MEAI tool types](https://learn.microsoft.com/en-us/dotnet/api/microsoft.extensions.ai.aifunction?view=net-9.0-pp) 
in terms of the core attributes and methods.

See [Tools](./tools.md) for more details.

## Model client types

Align with the MEAI model client types in terms of the core attributes and methods.

See [Models](./models.md) for more details.