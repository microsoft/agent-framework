---
status: Proposed
contact: eavanvalkenburg
date: 2026-01-26
deciders: eavanvalkenburg, markwallace-microsoft,  sphenry, alliscode, taochenosu, moonbox3, dmytrostruk, giles17
consulted: westey-m, johanste, brettcannon, zooba
---

# Making Agents generic over Input and Output types

## Context and Problem Statement

Currently, the Agent Framework's `AgentProtocol` and agent implementations are tightly coupled to chat-based interactions. The `run()` method accepts `str | ChatMessage | Sequence[str | ChatMessage]` and returns `AgentResponse` containing a `messages: list[ChatMessage]` field.

This design limits extensibility for agents that work with different input/output types, such as:
- Structured data agents (JSON input/output)
- Specialized protocol agents (A2A, Copilot Studio)
- Domain-specific agents with custom types

How can we make the Agent abstraction generic over input and output types with proper type safety?

## Decision Drivers

- **Type Safety**: Enable static type checking for agent inputs and outputs
- **Ergonomics**: The common case (chat-based agents) should remain simple to use
- **Protocol Flexibility**: Allow protocol adapters (A2A, Copilot Studio) to express their native types
- **Composability**: Agents with compatible types should be easily composable
- **Naming Clarity**: Field names should reflect the generic nature (not "messages" for non-message types)
- **API Simplicity**: Unified method signature for streaming and non-streaming modes

## Current State Analysis

### AgentProtocol and ChatAgent

```python
# Current implementation
class AgentProtocol(Protocol):
    async def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> AgentResponse:
        ...

class AgentResponse:
    messages: list[ChatMessage]  # Tightly coupled to ChatMessage
    response_id: str | None
    # ...
```

### Specialized Agents

| Agent | Input Type | Output Type | Notes |
|-------|-----------|-------------|-------|
| `ChatAgent` | `str \| ChatMessage \| Sequence[str \| ChatMessage]` | `ChatMessage` | Primary use case |
| `A2AAgent` | `str \| ChatMessage \| Sequence[str \| ChatMessage]` | `ChatMessage` | Internally converts to A2A `Message`/`Task` |
| `CopilotStudioAgent` | `str \| ChatMessage \| list[str] \| list[ChatMessage]` | `ChatMessage` | Maps to DirectLine activities |
| `GithubCopilotAgent` | `str \| ChatMessage \| Sequence[str \| ChatMessage]` | `ChatMessage` | Maps to Copilot SDK events |


## Decision Outcome

Update to use a Input and Output type generic for all agent types.

1. **Type Safety**: Provides compile-time type checking for agent composition
2. **Flexibility**: Allows any input/output type combination
3. **Future-Proof**: Supports future agent types without protocol changes

Make `Agent` generic over `TInput` and `TOutput`:

```python
from typing import TypeVar, Generic

TInput = TypeVar("TInput", contravariant=True)
TOutput = TypeVar("TOutput", covariant=True)

class AgentProtocol(Protocol, Generic[TInput, TOutput]):
    def run(
        self,
        input: TInput | Sequence[TInput] | None = None,  # renamed from 'messages'
        *,
        stream: bool = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[TOutput]] | ResponseStream[AgentResponseUpdate[TOutput], AgentResponse[TOutput]]:
        ...  # Returns AgentResponse when stream=False, ResponseStream when stream=True

class AgentResponse(Generic[TOutput]):
    items: list[TOutput]  # renamed from 'messages'
    response_id: str | None
    # ...

# ChatAgent becomes:
ChatInput = str | ChatMessage
class ChatAgent(BaseAgent, Generic[TOptions_co]):
    def run(
        self,
        messages: ChatInput | Sequence[ChatInput] | None = None,
        *,
        stream: bool = False,
        ...
    ) -> Awaitable[AgentResponse[ChatMessage]] | ResponseStream[AgentResponseUpdate[ChatMessage], AgentResponse[ChatMessage]]:
```

**Typing Examples:**

```python
# ChatAgent
ChatAgent: Agent[str | ChatMessage, ChatMessage]

# A2AAgent - could expose native types or maintain ChatMessage facade
A2AAgent: Agent[str | ChatMessage, ChatMessage]  # current behavior
# or native:
A2AAgent: Agent[A2AMessage, A2AMessage | Task]

# Hypothetical structured data agent
class JsonAgent(BaseAgent, Generic[TInput, TOutput]):
    ...
JsonAgent[MyInputSchema, MyOutputSchema]
```


### Consequences for implementation

#### 1. AgentResponse becomes Generic

```python
from typing import TypeVar, Generic

TOutput = TypeVar("TOutput", covariant=True)

class AgentResponse(Generic[TOutput], SerializationMixin):
    """Represents the response to an Agent run request."""

    def __init__(
        self,
        *,
        items: TOutput | Sequence[TOutput] | None = None,
        response_id: str | None = None,
        # ... other fields
    ) -> None:
        ...

    @property
    def items(self) -> list[TOutput]:
        """The output items from the agent."""
        ...

    @property
    def text(self) -> str:
        """Concatenated text (only valid when TOutput is ChatMessage)."""
        ...
```

#### 2. AgentResponseUpdate becomes Generic

```python
class AgentResponseUpdate(Generic[TOutput], SerializationMixin):
    """Streaming response chunk."""

    def __init__(
        self,
        *,
        items: Sequence[TOutput] | None = None,
        ...
    ) -> None:
        ...
```

#### 3. ResponseStream provides typed streaming with final response access

```python
TUpdate = TypeVar("TUpdate", covariant=True)
TFinal = TypeVar("TFinal", covariant=True)

class ResponseStream(Generic[TUpdate, TFinal], AsyncIterable[TUpdate]):
    """A stream of response updates with access to the final aggregated response.

    This type wraps async iteration over streaming updates while also providing
    access to the final response after iteration completes.

    Type Parameters:
        TUpdate: The type of streaming updates (e.g., AgentResponseUpdate[ChatMessage])
        TFinal: The type of the final response (e.g., AgentResponse[ChatMessage])
    """

    def __aiter__(self) -> AsyncIterator[TUpdate]:
        """Iterate over streaming updates."""
        ...

    async def response(self) -> TFinal:
        """Get the final aggregated response.

        If iteration hasn't completed, this will consume the remaining stream
        and return the final response.
        """
        ...

    @property
    def is_complete(self) -> bool:
        """Whether the stream has been fully consumed."""
        ...
```

#### 4. AgentProtocol becomes Generic with Unified `run()` Method

```python
TInput = TypeVar("TInput", contravariant=True)
TOutput = TypeVar("TOutput", covariant=True)

@runtime_checkable
class AgentProtocol(Protocol, Generic[TInput, TOutput]):
    """A protocol for an agent that can be invoked."""

    id: str
    name: str | None
    description: str | None

    @overload
    def run(
        self,
        input: TInput | Sequence[TInput] | None = None,
        *,
        stream: Literal[False] = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Coroutine[Any, Any, AgentResponse[TOutput]]:
        ...

    @overload
    def run(
        self,
        input: TInput | Sequence[TInput] | None = None,
        *,
        stream: Literal[True],
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate[TOutput], AgentResponse[TOutput]]:
        ...

    def run(
        self,
        input: TInput | Sequence[TInput] | None = None,
        *,
        stream: bool = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Coroutine[Any, Any, AgentResponse[TOutput]] | ResponseStream[AgentResponseUpdate[TOutput], AgentResponse[TOutput]]:
        """Run the agent.

        Args:
            input: The input(s) to send to the agent.
            stream: If True, returns a ResponseStream. If False, returns the final response.
            thread: The conversation thread associated with the input(s).
            **kwargs: Additional keyword arguments.

        Returns:
            AgentResponse[TOutput] when stream=False (awaitable)
            ResponseStream[AgentResponseUpdate[TOutput], AgentResponse[TOutput]] when stream=True
        """
        ...
```

#### 5. ChatAgent Implementation

```python
ChatInput = str | ChatMessage

class ChatAgent(BaseAgent, Generic[TOptions_co]):
    """A Chat Client Agent - implements Agent[ChatInput, ChatMessage]."""

    @overload
    def run(
        self,
        messages: ChatInput | Sequence[ChatInput] | None = None,
        *,
        stream: Literal[False] = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[ChatMessage]]:
        ...

    @overload
    def run(
        self,
        messages: ChatInput | Sequence[ChatInput] | None = None,
        *,
        stream: Literal[True],
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate[ChatMessage], AgentResponse[ChatMessage]]:
        ...

    def run(
        self,
        messages: ChatInput | Sequence[ChatInput] | None = None,
        *,
        stream: bool = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[ChatMessage]] | ResponseStream[AgentResponseUpdate[ChatMessage], AgentResponse[ChatMessage]]:
        ...
```

**Usage:**
```python
# Non-streaming (default)
response = await agent.run("Hello")
print(response.text)

# Streaming with iteration
async for update in agent.run("Hello", stream=True):
    print(update.text, end="")

# Streaming with final response access
stream = agent.run("Hello", stream=True)
async for update in stream:
    print(update.text, end="")
final_response = await stream.response()  # Get aggregated AgentResponse
print(f"\nTotal tokens: {final_response.usage_details}")
```

### Typing for Specialized Agents

#### A2AAgent

```python
class A2AAgent(BaseAgent):
    """Agent2Agent protocol implementation.

    Implements: Agent[str | ChatMessage, ChatMessage]

    Internally converts to/from A2A protocol types (Message, Task, Artifact).
    """

    def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        stream: bool = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[ChatMessage]] | ResponseStream[AgentResponseUpdate[ChatMessage], AgentResponse[ChatMessage]]:
        # Converts ChatMessage -> A2A Message internally
        # Converts A2A Message/Task/Artifact -> ChatMessage in response
        ...
```

**Alternative (Native Types)**:

> To decide, do we want to offer native types for this?

```python
from a2a.types import Message as A2AMessage, Task, Artifact

A2AInput = str | ChatMessage | A2AMessage
A2AOutput = ChatMessage | A2AMessage | Task

class A2AAgent(BaseAgent):
    """Implements: Agent[A2AInput, A2AOutput]"""
    ...
```

#### CopilotStudioAgent

```python
class CopilotStudioAgent(BaseAgent):
    """A Copilot Studio Agent.

    Implements: Agent[str | ChatMessage, ChatMessage]

    Internally maps to DirectLine activities.
    """

    def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        stream: bool = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[ChatMessage]] | ResponseStream[AgentResponseUpdate[ChatMessage], AgentResponse[ChatMessage]]:
        ...
```

#### GithubCopilotAgent

```python
class GithubCopilotAgent(BaseAgent, Generic[TOptions]):
    """A GitHub Copilot Agent.

    Implements: Agent[str | ChatMessage, ChatMessage]

    Internally maps to Copilot SDK events.
    """

    def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        stream: bool = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[ChatMessage]] | ResponseStream[AgentResponseUpdate[ChatMessage], AgentResponse[ChatMessage]]:
        ...
```

### Field Naming: `messages` → `items`

The `AgentResponse.messages` field is renamed to `items` to reflect that:
- The output may not be "messages" (could be structured data, binary, etc.)
- It's a more generic term that applies to all agent types

## Consequences

### Positive

- Enables type-safe agent composition
- Supports diverse agent types beyond chat
- Better IDE support with type inference
- Clearer API with generic naming
- Simplified API surface with unified `run()` method
- `ResponseStream[TUpdate, TFinal]` provides typed access to both updates and final response

### Negative

- Increased complexity in type signatures
- Generic variance rules may be tricky for some users

### Neutral

- Protocol agents (A2A, Copilot Studio, GitHub Copilot) can choose to expose native types or maintain ChatMessage facade
- Thread management remains unchanged
