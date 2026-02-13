# Coding Standards

This document describes the coding standards and conventions for the Agent Framework project.

## Code Style and Formatting

We use [ruff](https://github.com/astral-sh/ruff) for both linting and formatting with the following configuration:

- **Line length**: 120 characters
- **Target Python version**: 3.10+
- **Google-style docstrings**: All public functions, classes, and modules should have docstrings following Google conventions

## Type Annotations

### Future Annotations

> **Note:** This convention is being adopted. See [#3578](https://github.com/microsoft/agent-framework/issues/3578) for progress.

Use `from __future__ import annotations` at the top of files to enable postponed evaluation of annotations. This prevents the need for string-based type hints for forward references:

```python
# ✅ Preferred - use future annotations
from __future__ import annotations

class Agent:
    def create_child(self) -> Agent:  # No quotes needed
        ...

# ❌ Avoid - string-based type hints
class Agent:
    def create_child(self) -> "Agent":  # Requires quotes without future annotations
        ...
```

### TypeVar Naming Convention

> **Note:** This convention is being adopted. See [#3594](https://github.com/microsoft/agent-framework/issues/3594) for progress.

Use the suffix `T` for TypeVar names instead of a prefix:

```python
# ✅ Preferred - suffix T
ChatResponseT = TypeVar("ChatResponseT", bound=ChatResponse)
AgentT = TypeVar("AgentT", bound=Agent)

# ❌ Avoid - prefix T
TChatResponse = TypeVar("TChatResponse", bound=ChatResponse)
TAgent = TypeVar("TAgent", bound=Agent)
```

### Mapping Types

> **Note:** This convention is being adopted. See [#3577](https://github.com/microsoft/agent-framework/issues/3577) for progress.

Use `Mapping` instead of `MutableMapping` for input parameters when mutation is not required:

```python
# ✅ Preferred - Mapping for read-only access
def process_config(config: Mapping[str, Any]) -> None:
    ...

# ❌ Avoid - MutableMapping when mutation isn't needed
def process_config(config: MutableMapping[str, Any]) -> None:
    ...
```

## Function Parameter Guidelines

To make the code easier to use and maintain:

- **Positional parameters**: Only use for up to 3 fully expected parameters (this is not a hard rule, but a guideline there are instances where this does make sense to exceed)
- **Keyword-only parameters**: Arguments after `*` in function signatures are keyword-only; prefer these for optional parameters
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
- **Avoid shadowing built-ins**: Do not use parameter names that shadow Python built-ins (e.g., use `next_handler` instead of `next`). See [#3583](https://github.com/microsoft/agent-framework/issues/3583) for progress.

### Using `**kwargs`

> **Note:** This convention is being adopted. See [#3642](https://github.com/microsoft/agent-framework/issues/3642) for progress.

Avoid `**kwargs` unless absolutely necessary. It should only be used as an escape route, not for well-known flows of data:

- **Prefer named parameters**: If there are known extra arguments being passed, use explicit named parameters instead of kwargs
- **Subclassing support**: kwargs is acceptable in methods that are part of classes designed for subclassing, allowing subclass-defined kwargs to pass through without issues. In this case, clearly document that kwargs exists for subclass extensibility and not for passing arbitrary data
- **Remove when possible**: In other cases, removing kwargs is likely better than keeping it
- **Separate kwargs by purpose**: When combining kwargs for multiple purposes, use specific parameters like `client_kwargs: dict[str, Any]` instead of mixing everything in `**kwargs`
- **Always document**: If kwargs must be used, always document how it's used, either by referencing external documentation or explaining its purpose

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
from agent_framework import Message

user_msg = Message("user", ["Hello, world!"])
asst_msg = Message("assistant", ["Hello, world!"])

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
  from agent_framework import Agent, tool
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

### Versioning and Core Dependency

All non-core packages declare a lower bound on `agent-framework-core` (e.g., `"agent-framework-core>=1.0.0b260130"`). Follow these rules when bumping versions:

- **Core version changes**: When `agent-framework-core` is updated with breaking or significant changes and its version is bumped, update the `agent-framework-core>=...` lower bound in every other package's `pyproject.toml` to match the new core version.
- **Non-core version changes**: Non-core packages (connectors, extensions) can have their own versions incremented independently while keeping the existing core lower bound pinned. Only raise the core lower bound if the non-core package actually depends on new core APIs.

### Installation Options

Connectors are distributed as separate packages and are not imported by default in the core package. Users install the specific connectors they need:

```bash
# Install core only
pip install agent-framework-core

# Install core with all connectors
pip install agent-framework-core[all]
# or (equivalently):
pip install agent-framework

# Install specific connector (pulls in core as dependency)
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
- A header for exceptions can be added, called `Raises:`, following these guidelines:
  - **Always document** Agent Framework specific exceptions (e.g., `AgentInitializationError`, `AgentExecutionException`)
  - **Only document** standard Python exceptions (TypeError, ValueError, KeyError, etc.) when the condition is non-obvious or provides value to API users
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
def create_agent(name: str, client: SupportsChatGetResponse) -> Agent:
    """Create a new agent with the specified configuration.

    Args:
        name: The name of the agent.
        client: The chat client to use for communication.

    Returns:
        True if the strings are the same, False otherwise.

    Raises:
        ValueError: If one of the strings is empty.
    """
    ...
```

If in doubt, use the link above to read much more considerations of what to do and when, or use common sense.

## Public API and Exports

### Explicit Exports

**All wildcard imports (`from ... import *`) are prohibited** in production code, including both `.py` and `.pyi` files. Always use explicit import lists to maintain clarity and avoid namespace pollution.

Define `__all__` in each module to explicitly declare the public API, then import specific symbols by name:

```python
# ✅ Preferred - explicit __all__ and named imports
__all__ = ["Agent", "Message", "ChatResponse"]

from ._agents import Agent
from ._types import Message, ChatResponse

# ✅ For many exports, use parenthesized multi-line imports
from ._types import (
    AgentResponse,
    ChatResponse,
    Message,
    ResponseStream,
)

# ❌ Prohibited pattern: wildcard/star imports (do not use)
# from ._agents import <all public symbols>
# from ._types import <all public symbols>
```

**Rationale:**
- **Clarity**: Explicit imports make it clear exactly what is being exported and used
- **IDE Support**: Enables better autocomplete, go-to-definition, and refactoring
- **Type Checking**: Improves static analysis and type checker accuracy
- **Maintenance**: Makes it easier to track symbol usage and detect breaking changes
- **Performance**: Avoids unnecessary symbol resolution during module import

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

## Test Organization

### Test Directory Structure

Test folders require specific organization to avoid pytest conflicts when running tests across packages:

1. **No `__init__.py` in test folders**: Test directories should NOT contain `__init__.py` files. This can cause import conflicts when pytest collects tests across multiple packages.

2. **File naming**: Files starting with `test_` are treated as test files by pytest. Do not use this prefix for helper modules or utilities. If you need shared test utilities, put them in `conftest.py` or a file with a different name pattern (e.g., `helpers.py`, `fixtures.py`).

3. **Package-specific conftest location**: The `tests/conftest.py` path is reserved for the core package (`packages/core/tests/conftest.py`). Other packages must place their tests in a uniquely-named subdirectory:

```plaintext
# ✅ Correct structure for non-core packages
packages/devui/
├── tests/
│   └── devui/           # Unique subdirectory matching package name
│       ├── conftest.py  # Package-specific fixtures
│       ├── test_server.py
│       └── test_mapper.py

packages/anthropic/
├── tests/
│   └── anthropic/       # Unique subdirectory
│       ├── conftest.py
│       └── test_client.py

# ❌ Incorrect - will conflict with core package
packages/devui/
├── tests/
│   ├── conftest.py      # Conflicts when running all tests
│   ├── test_server.py
│   └── test_helpers.py  # Bad name - looks like a test file

# ✅ Core package can use tests/ directly
packages/core/
├── tests/
│   ├── conftest.py      # Core's conftest.py
│   ├── core/
│   │   └── test_agents.py
│   └── openai/
│       └── test_client.py
```

4. **Keep the `tests/` folder**: Even when using a subdirectory, keep the `tests/` folder at the package root. Some test discovery commands and tooling rely on this convention.

### Fixture Guidelines

- Use `conftest.py` for shared fixtures within a test directory
- Factory functions with parameters should be regular functions, not fixtures (fixtures can't accept arguments)
- Import factory functions explicitly: `from conftest import create_test_request`
- Fixtures should use simple names that describe what they provide: `mapper`, `test_request`, `mock_client`
