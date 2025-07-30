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

In Python, we will use `pydantic` to define and operate with these data types.

## Content types

The core data type is `AIContent`, which represents content used by AI services. While the Agent Framework will primarily use the abstracted types, shared across implementations of the underlying Model Client, the `raw_representation` field allows for more tightly-coupled implementations where appropriate.

```python
class AIContent(BaseModel):
    raw_representation: Any | None = None
    additional_properties: dict[str, Any] | None = None
```

The basic data-bearing types (`TextContent`, `TextReasoningContent`, `DataContent`, and `UriContent`) represent an interface for developers to input data into the system, as well as for agents to output resulting data. In AutoGen, messages containing these content types were considered `ChatMesssage` objects, contrasting with `AgentEvent` objects that were primarily used for internal events (such as tool calls, etc.)

```python
class TextContent(AIContent):
    text: str


class TextReasoningContent(AIContent):
    text: str


AnyTextualContent = TextContent | TextReasoningContent | "UriContent"


class DataContent(AIContent):
    data: bytes
    media_type: str

    @property
    def base64_data(self) -> str:
        """Returns the data represented by this instance encoded as a Base64 string."""
        ...

    @property
    def uri(self) -> str:
        """Returns the data as a data URI."""
        ...


class UriContent(AIContent):
    uri: str
    media_type: str


LocatableContent = DataContent | UriContent  # TODO: Consider other names that are more descriptive.
```

Note that `TextContent` and `TextReasoningContent` do not have an inheritance relationship, and similarly `DataContent` and `UriContent` do not inherit from one-another. In this case, we opt to remain consistent with the .NET-side M.E.AI design. To abstract over both pairs, we provide the `AnyTextualContent` and `LocatableContent` type aliases.

Function calls and results have dedicated content types to represent the ModelClient's request for tool use as well as the means to flow the results back to the agent.


```python
class FunctionCallContent(AIContent):
    call_id: str
    name: str
    arguments: dict[str, Any | None] | None = None
    exception: Exception | None = None


class FunctionResultContent(AIContent):
    call_id: str
    result: Any | None = None
    exception: Exception | None = None
```

The types contain all necessary error reporting channels (`FunctionCallContext.exception` when the raw function call request cannot be successfully mapped to the input to the tool - likely due to argument mismatch - and `FunctionResultContent.exception` when the tool execution fails). `ErrorContent` is a more general-purpose error reporting type, but one that should be used for reporting non-fatal errors. The way to think about this is that this is akin to a "400" error or a transient "500" error in HTTP parlance.


```python
class ErrorContent(AIContent):
    error_code: str | None = None
    details: str | None = None
    message: str | None
```


Communicating the usage details when invoking a model client is important, but it has traditionally not been well supported in various frameworks, typically ending up relying on the implementor of the assistant consuming the underlying LLM to handle this. Ideally, the Model Client would provide an a-prori means to compute the usage given a message:


```python

class TokenEstimator(Protocol):
    """Estimates the count of tokens in the provided message"""
    def estimate(message: ChatMessage) -> int:
        ...

    def estimate_all(message: Sequence[ChatMessage]) -> Generator[int, None, int]
        ...


@runtime_checkable
class ModelClientWithEstimator(Protocol, ModelClient):
    @property
    def token_estimator(self) -> TokenEstimator:
        """Returns the token estimator for this model client."""
        ...
```

As this is not available in the current MEAI design, not generally a capability of native clients of existing hosted models, we will rely on the `UsageDetails` pattern to let the Model Client communicate this data into the Agent consuming it. Custom agents will be responsible for proper aggregation; built-in ones should provide the patterns and ideally implementation helper types. The `UsageDetails` class will provide a canonical additional operator.

```python
class UsageContent(AIContent):
    """Usage content type."""
    details: UsageDetails


class UsageDetails:
    """Provides usage details about a request/response."""
    input_token_count: int | None = None
    """The number of tokens in the input."""
    output_token_count: int | None = None
    """The number of tokens in the output."""
    total_token_count: int | None = None
    """The total number of tokens used to produce the response."""
    additional_counts: AdditionalCounts | None = None
    """A dictionary of additional usage counts."""
```


The `AdditionalCounts` class is a `TypedDict` that allows for us to define well-known keys for additional counts (e.g. `thought_token_count` and `image_token_count`), while also allowing for arbitrary keys to be used by the underlying AI service prvoider. We recommend that services prefix their keys with a service identifier (e.g. `openai.`) to avoid collisions, unles using a well-known key.

```python
class AdditionalCounts(TypedDict, total=False):
    """Represents well-known additional counts for usage. This is not an exhaustive list.

    Remarks:
        To make it possible to avoid colisions between similarly-named, but unrelated, additional counts
        between different AI services, any keys not explicitly defined here should be prefixed with the
        name of the AI service, e.g., "openai." or "azure.". The separator "." was chosen because it cannot
        be a legal character in a JSON key.

        Over time additional counts may be added to this class.
    """
    thought_token_count: int
    """The number of tokens used for thought processing."""
    image_token_count: int
    """The number of token equivalents used for image processing."""
```


## Tool types

Align with the [MEAI tool types](https://learn.microsoft.com/en-us/dotnet/api/microsoft.extensions.ai.aifunction?view=net-9.0-pp)
in terms of the core attributes and methods.

See [Tools](./tools.md) for more details.

## Model client and `ChatMessage` types

Align with the MEAI model client types in terms of the core attributes and methods.

See [Models](./models.md) for more details.