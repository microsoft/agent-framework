# Coding Standards

This document describes the coding standards and conventions for the Agent Framework project.

## Code Style and Formatting

We use [ruff](https://github.com/astral-sh/ruff) for both linting and formatting with the following configuration:

- **Line length**: 120 characters
- **Target Python version**: 3.10+
- **Google-style docstrings**: All public functions, classes, and modules should have docstrings following Google conventions

## Function Parameter Guidelines

To make the code easier to use and maintain:

- **Positional parameters**: Only use for up to 3 fully expected parameters
- **Keyword parameters**: Use for all other parameters, especially when there are multiple required parameters without obvious ordering
- **Avoid additional imports**: Do not require the user to import additional modules to use the function, so provide string based overrides when applicable, for instance:
```python
def create_agent(name: str, tool_mode: ChatToolMode) -> Agent:
    # Implementation here
```
Should be:
```python
def create_agent(name: str, tool_mode: Literal['auto', 'required', 'none'] | ChatToolMode) -> Agent:
    # Implementation here
    if isinstance(tool_mode, str):
        tool_mode = ChatToolMode(tool_mode)
```
- **Document kwargs**: Always document how `kwargs` are used, either by referencing external documentation or explaining their purpose
- **Separate kwargs**: When combining kwargs for multiple purposes, use specific parameters like `client_kwargs: dict[str, Any]` instead of mixing everything in `**kwargs`

## Method Naming Inside Connectors

When naming methods inside connectors, we have a loose preference for using the following conventions:
- Use `_prepare_<object>_for_<purpose>` as a prefix for methods that prepare data for sending to the external service.
- Use `_parse_<object>_from_<source>` as a prefix for methods that process data received from the external service.

This is not a strict rule, but a guideline to help maintain consistency across the codebase.

## Implementation Decisions

### Asynchronous Programming

It's important to note that most of this library is written with asynchronous in mind. The
developer should always assume everything is asynchronous. One can use the function signature
with either `async def` or `def` to understand if something is asynchronous or not.

### Attributes vs Inheritance

Prefer attributes over inheritance when parameters are mostly the same:

```python
# ✅ Preferred - using attributes
from agent_framework import ChatMessage

user_msg = ChatMessage(role="user", content="Hello, world!")
asst_msg = ChatMessage(role="assistant", content="Hello, world!")

# ❌ Not preferred - unnecessary inheritance
from agent_framework import UserMessage, AssistantMessage

user_msg = UserMessage(content="Hello, world!")
asst_msg = AssistantMessage(content="Hello, world!")
```

### Logging

Use the centralized logging system:

```python
from agent_framework import get_logger

# For main package
logger = get_logger()

# For subpackages
logger = get_logger('agent_framework.azure')
```

**Do not use** direct logging module imports:
```python
# ❌ Avoid this
import logging
logger = logging.getLogger(__name__)
```

### Import Structure

The package follows a flat import structure:

- **Core**: Import directly from `agent_framework`
  ```python
  from agent_framework import ChatAgent, tool
  ```

- **Components**: Import from `agent_framework.<component>`
  ```python
  from agent_framework.observability import enable_instrumentation, configure_otel_providers
  ```

- **Connectors**: Import from `agent_framework.<vendor/platform>`
  ```python
  from agent_framework.openai import OpenAIChatClient
  from agent_framework.azure import AzureOpenAIChatClient
  ```

## Package Structure

The project uses a monorepo structure with separate packages for each connector/extension:

```plaintext
python/
├── pyproject.toml              # Root package (agent-framework) depends on agent-framework-core[all]
├── samples/                    # Sample code and examples
├── packages/
│   ├── core/                   # agent-framework-core - Core abstractions and implementations
│   │   ├── pyproject.toml      # Defines [all] extra that includes all connector packages
│   │   ├── tests/              # Tests for core package
│   │   └── agent_framework/
│   │       ├── __init__.py     # Public API exports
│   │       ├── _agents.py      # Agent implementations
│   │       ├── _clients.py     # Chat client protocols and base classes
│   │       ├── _tools.py       # Tool definitions
│   │       ├── _types.py       # Type definitions
│   │       ├── _logging.py     # Logging utilities
│   │       │
│   │       │   # Provider folders - lazy load from connector packages
│   │       ├── openai/         # OpenAI clients (built into core)
│   │       ├── azure/          # Lazy loads from azure-ai, azure-ai-search, azurefunctions
│   │       ├── anthropic/      # Lazy loads from agent-framework-anthropic
│   │       ├── ollama/         # Lazy loads from agent-framework-ollama
│   │       ├── a2a/            # Lazy loads from agent-framework-a2a
│   │       ├── ag_ui/          # Lazy loads from agent-framework-ag-ui
│   │       ├── chatkit/        # Lazy loads from agent-framework-chatkit
│   │       ├── declarative/    # Lazy loads from agent-framework-declarative
│   │       ├── devui/          # Lazy loads from agent-framework-devui
│   │       ├── mem0/           # Lazy loads from agent-framework-mem0
│   │       └── redis/          # Lazy loads from agent-framework-redis
│   │
│   ├── azure-ai/               # agent-framework-azure-ai
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── agent_framework_azure_ai/
│   │       ├── __init__.py     # Public exports
│   │       ├── _chat_client.py # AzureAIClient implementation
│   │       ├── _client.py      # AzureAIAgentClient implementation
│   │       ├── _shared.py      # AzureAISettings and shared utilities
│   │       └── py.typed        # PEP 561 marker
│   ├── anthropic/              # agent-framework-anthropic
│   ├── bedrock/                # agent-framework-bedrock
│   ├── ollama/                 # agent-framework-ollama
│   └── ...                     # Other connector packages
```

### Lazy Loading Pattern

Provider folders in the core package use `__getattr__` to lazy load classes from their respective connector packages. This allows users to import from a consistent location while only loading dependencies when needed:

```python
# In agent_framework/azure/__init__.py
_IMPORTS: dict[str, tuple[str, str]] = {
    "AzureAIAgentClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    # ...
}

def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        import_path, package_name = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(import_path), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The package {package_name} is required to use `{name}`. "
                f"Install it with: pip install {package_name}"
            ) from exc
```

### Adding a New Connector Package

**Important:** Do not create a new package unless there is an issue that has been reviewed and approved by the core team.

#### Initial Release (Preview Phase)

For the first release of a new connector package:

1. Create a new directory under `packages/` (e.g., `packages/my-connector/`)
2. Add the package to `tool.uv.sources` in the root `pyproject.toml`
3. Include samples inside the package itself (e.g., `packages/my-connector/samples/`)
4. **Do NOT** add the package to the `[all]` extra in `packages/core/pyproject.toml`
5. **Do NOT** create lazy loading in core yet

#### Promotion to Stable

After the package has been released and gained a measure of confidence:

1. Move samples from the package to the root `samples/` folder
2. Add the package to the `[all]` extra in `packages/core/pyproject.toml`
3. Create a provider folder in `agent_framework/` with lazy loading `__init__.py`

### Installation Options

Connectors are distributed as separate packages and are not imported by default in the core package. Users install the specific connectors they need:

```bash
# Install core only
pip install agent-framework-core

# Install core with all connectors
pip install agent-framework-core[all]
# or (equivalently):
pip install agent-framework

# Install specific connector
pip install agent-framework-azure-ai
```

## Documentation

Each file should have a single first line containing: # Copyright (c) Microsoft. All rights reserved.

We follow the [Google Docstring](https://github.com/google/styleguide/blob/gh-pages/pyguide.md#383-functions-and-methods) style guide for functions and methods.
They are currently not checked for private functions (functions starting with '_').

They should contain:

- Single line explaining what the function does, ending with a period.
- If necessary to further explain the logic a newline follows the first line and then the explanation is given.
- The following three sections are optional, and if used should be separated by a single empty line.
- Arguments are then specified after a header called `Args:`, with each argument being specified in the following format:
  - `arg_name`: Explanation of the argument.
    - if a longer explanation is needed for a argument, it should be placed on the next line, indented by 4 spaces.
    - Type and default values do not have to be specified, they will be pulled from the definition.
- Returns are specified after a header called `Returns:` or `Yields:`, with the return type and explanation of the return value.
- Keyword arguments are specified after a header called `Keyword Args:`, with each argument being specified in the same format as `Args:`.
- A header for exceptions can be added, called `Raises:`, but should only be used for:
  - Agent Framework specific exceptions (e.g., `ServiceInitializationError`)
  - Base exceptions that might be unexpected in the context
  - Obvious exceptions like `ValueError` or `TypeError` do not need to be documented
  - Format: `ExceptionType`: Explanation of the exception.
  - If a longer explanation is needed, it should be placed on the next line, indented by 4 spaces.
- Code examples can be added using the `Examples:` header followed by `.. code-block:: python` directive.

Putting them all together, gives you at minimum this:

```python
def equal(arg1: str, arg2: str) -> bool:
    """Compares two strings and returns True if they are the same."""
    ...
```

Or a complete version of this:

```python
def equal(arg1: str, arg2: str) -> bool:
    """Compares two strings and returns True if they are the same.

    Here is extra explanation of the logic involved.

    Args:
        arg1: The first string to compare.
        arg2: The second string to compare.

    Returns:
        True if the strings are the same, False otherwise.
    """
```

A more complete example with keyword arguments and code samples:

```python
def create_client(
    model_id: str | None = None,
    *,
    timeout: float | None = None,
    env_file_path: str | None = None,
    **kwargs: Any,
) -> Client:
    """Create a new client with the specified configuration.

    Args:
        model_id: The model ID to use. If not provided,
            it will be loaded from settings.

    Keyword Args:
        timeout: Optional timeout for requests.
        env_file_path: If provided, settings are read from this file.
        kwargs: Additional keyword arguments passed to the underlying client.

    Returns:
        A configured client instance.

    Raises:
        ValueError: If the model_id is invalid.

    Examples:

        .. code-block:: python

            # Create a client with default settings:
            client = create_client(model_id="gpt-4o")

            # Or load from environment:
            client = create_client(env_file_path=".env")
    """
    ...
```

Use Google-style docstrings for all public APIs:

```python
def create_agent(name: str, chat_client: ChatClientProtocol) -> Agent:
    """Create a new agent with the specified configuration.

    Args:
        name: The name of the agent.
        chat_client: The chat client to use for communication.

    Returns:
        True if the strings are the same, False otherwise.

    Raises:
        ValueError: If one of the strings is empty.
    """
    ...
```

If in doubt, use the link above to read much more considerations of what to do and when, or use common sense.

## Performance considerations

### Cache Expensive Computations

Think about caching where appropriate. Cache the results of expensive operations that are called repeatedly with the same inputs:

```python
# ✅ Preferred - cache expensive computations
class FunctionTool:
    def __init__(self, ...):
        self._cached_parameters: dict[str, Any] | None = None

    def parameters(self) -> dict[str, Any]:
        """Return the JSON schema for the function's parameters.

        The result is cached after the first call for performance.
        """
        if self._cached_parameters is None:
            self._cached_parameters = self.input_model.model_json_schema()
        return self._cached_parameters

# ❌ Avoid - recalculating every time
def parameters(self) -> dict[str, Any]:
    return self.input_model.model_json_schema()
```

### Prefer Attribute Access Over isinstance()

When checking types in hot paths, prefer checking a `type` attribute (fast string comparison) over `isinstance()` (slower due to method resolution order traversal):

```python
# ✅ Preferred - use match/case with type attribute (faster)
match content.type:
    case "function_call":
        # handle function call
    case "usage":
        # handle usage
    case _:
        # handle other types

# ❌ Avoid in hot paths - isinstance() is slower
if isinstance(content, FunctionCallContent):
    # handle function call
elif isinstance(content, UsageContent):
    # handle usage
```

For inline conditionals:

```python
# ✅ Preferred - type attribute comparison
result = value if content.type == "function_call" else other

# ❌ Avoid - isinstance() in hot paths
result = value if isinstance(content, FunctionCallContent) else other
```

### Avoid Redundant Serialization

When the same data needs to be used in multiple places, compute it once and reuse it:

```python
# ✅ Preferred - reuse computed representation
otel_message = _to_otel_message(message)
otel_messages.append(otel_message)
logger.info(otel_message, extra={...})

# ❌ Avoid - computing the same thing twice
otel_messages.append(_to_otel_message(message)) # this already serializes
message_data = message.to_dict(exclude_none=True)  # and this does so again!
logger.info(message_data, extra={...})
```
