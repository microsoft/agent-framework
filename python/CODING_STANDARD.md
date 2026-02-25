# Coding Standards

This document describes the coding standards and conventions for the Agent Framework project.

## Code Style and Formatting

We use [ruff](https://github.com/astral-sh/ruff) for both linting and formatting with the following configuration:

- **Line length**: 120 characters
- **Target Python version**: 3.10+
- **Google-style docstrings**: All public functions, classes, and modules should have docstrings following Google conventions

### Module Docstrings

Public modules must include a module-level docstring, including `__init__.py` files.

- Namespace-style `__init__.py` modules (for example under `agent_framework/<provider>/`) should use a structured
  docstring that includes:
  - A one-line summary of the namespace
  - A short "This module lazily re-exports objects from:" section that lists only pip install package names
    (for example `agent-framework-a2a`)
  - A short "Supported classes:" (or "Supported classes and functions:") section
- The main `agent_framework/__init__.py` should include a concise background-oriented docstring rather than a long
  per-symbol list.
- Core modules with broad surface area, including `agent_framework/exceptions.py` and
  `agent_framework/observability.py`, should always have explicit module docstrings.

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

## Exception Hierarchy

The Agent Framework defines a structured exception hierarchy rooted at `AgentFrameworkException`. Every AF-specific
exception inherits from this base, so callers can catch `AgentFrameworkException` as a broad fallback. The hierarchy
is organized into domain-specific L1 branches, each with a consistent set of leaf exceptions where applicable.

### Design Principles

- **Domain-scoped branches**: Exceptions are grouped by the subsystem that raises them (agent, chat client,
  integration, workflow, content, tool, middleware), not by HTTP status code or generic error category.
- **Consistent suberror pattern**: The `AgentException`, `ChatClientException`, and `IntegrationException` branches
  share a parallel set of leaf exceptions (`InvalidAuth`, `InvalidRequest`, `InvalidResponse`, `ContentFilter`) so
  that callers can handle the same failure mode uniformly across domains.
- **Built-ins for validation**: Configuration/parameter validation errors use Python built-in exceptions
  (`ValueError`, `TypeError`, `RuntimeError`) rather than AF-specific classes. AF exceptions are reserved for
  domain-level failures that callers may want to catch and handle distinctly from programming errors.
- **No compatibility aliases**: When exceptions are renamed or removed, the old names are not kept as aliases.
  This is a deliberate trade-off for hierarchy clarity over backward compatibility.
- **Suffix convention**: L1 branch classes use `...Exception` (e.g., `AgentException`). Leaf classes may use
  either `...Exception` or `...Error` depending on the domain convention (e.g., `ContentError`,
  `WorkflowValidationError`). Within a branch, the suffix is consistent.

### Full Hierarchy

```
AgentFrameworkException                          # Base for all AF exceptions
├── AgentException                               # Agent-scoped failures
│   ├── AgentInvalidAuthException                # Agent auth failures
│   ├── AgentInvalidRequestException             # Invalid request to agent (e.g., agent not found, bad input)
│   ├── AgentInvalidResponseException            # Invalid/unexpected response from agent
│   └── AgentContentFilterException              # Agent content filter triggered
│
├── ChatClientException                          # Chat client lifecycle and communication failures
│   ├── ChatClientInvalidAuthException           # Chat client auth failures
│   ├── ChatClientInvalidRequestException        # Invalid request to chat client
│   ├── ChatClientInvalidResponseException       # Invalid/unexpected response from chat client
│   └── ChatClientContentFilterException         # Chat client content filter triggered
│
├── IntegrationException                         # External service/dependency integration failures
│   ├── IntegrationInitializationError           # Wrapped dependency lifecycle failure during setup
│   ├── IntegrationInvalidAuthException          # Integration auth failures (e.g., 401/403)
│   ├── IntegrationInvalidRequestException       # Invalid request to integration
│   ├── IntegrationInvalidResponseException      # Invalid/unexpected response from integration
│   └── IntegrationContentFilterException        # Integration content filter triggered
│
├── ContentError                                 # Content processing/validation failures
│   └── AdditionItemMismatch                     # Type mismatch when merging content items
│
├── WorkflowException                            # Workflow engine failures
│   ├── WorkflowRunnerException                  # Runtime execution failures
│   │   ├── WorkflowConvergenceException         # Runner exceeded max iterations
│   │   └── WorkflowCheckpointException          # Checkpoint save/restore/decode failures
│   ├── WorkflowValidationError                  # Graph validation errors
│   │   ├── EdgeDuplicationError                 # Duplicate edge in workflow graph
│   │   ├── TypeCompatibilityError               # Type mismatch between connected executors
│   │   └── GraphConnectivityError               # Graph connectivity issues
│   ├── WorkflowActionError                      # User-level error from declarative ThrowException action
│   └── DeclarativeWorkflowError                 # Declarative workflow definition/YAML errors
│
├── ToolException                                # Tool-related failures
│   └── ToolExecutionException                   # Failure during tool execution
│
├── MiddlewareException                          # Middleware failures
│   └── MiddlewareTermination                    # Control-flow: early middleware termination
│
└── SettingNotFoundError                         # Required setting not resolved from any source
```

### When to Use AF Exceptions vs Built-ins

| Scenario | Exception to use |
|---|---|
| Missing or invalid constructor argument (e.g., `api_key` is `None`) | `ValueError` or `TypeError` |
| Object in wrong state (e.g., client not initialized) | `RuntimeError` |
| External service returns 401/403 | `IntegrationInvalidAuthException` (or `ChatClient`/`Agent` variant) |
| External service returns unexpected response | `IntegrationInvalidResponseException` (or variant) |
| Content filter blocks a request | `IntegrationContentFilterException` (or variant) |
| Request validation fails before sending to service | `IntegrationInvalidRequestException` (or variant) |
| Agent not found in registry | `AgentInvalidRequestException` |
| Agent returned no/bad response | `AgentInvalidResponseException` |
| Workflow runner exceeds max iterations | `WorkflowConvergenceException` |
| Checkpoint serialization/deserialization failure | `WorkflowCheckpointException` |
| Workflow graph has invalid structure | `WorkflowValidationError` (or specific subclass) |
| Declarative YAML definition error | `DeclarativeWorkflowError` |
| Tool execution failure | `ToolExecutionException` |
| Content merge type mismatch | `AdditionItemMismatch` |

### Choosing Between Agent, ChatClient, and Integration Branches

- **`AgentException`**: The failure is scoped to agent-level logic — agent lookup, agent response handling,
  agent content filtering. Use when the agent itself is the source of the problem.
- **`ChatClientException`**: The failure is scoped to the chat client (the LLM provider connection) — auth with
  the LLM provider, request/response format issues specific to the chat protocol, chat-level content filtering.
- **`IntegrationException`**: The failure is in a non-chat external dependency — search services, vector stores,
  Purview, custom APIs, or any service that is not the primary LLM chat provider.

When in doubt: if the code is in a chat client constructor or method, use `ChatClient*`. If it's in an agent
method, use `Agent*`. If it's talking to an external service that isn't the chat LLM, use `Integration*`.

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
  - **Always document** Agent Framework specific exceptions (e.g., `AgentInvalidRequestException`, `IntegrationInvalidAuthException`)
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

Do not use ``__all__`` in internal modules. Define it in the ``__init__`` file of the level you want to expose.
If a non-``__init__`` module is intentionally part of the public API surface (for example, ``observability.py``),
it should define ``__all__`` as well.

Also avoid identity alias imports in ``__init__`` files. Use ``from ._module import Symbol`` instead of
``from ._module import Symbol as Symbol``.

```python
# ✅ Preferred - explicit __all__ and named imports
from ._agents import Agent
from ._types import Message, ChatResponse

# ✅ For many exports, use parenthesized multi-line imports
from ._types import (
    AgentResponse,
    ChatResponse,
    Message,
    ResponseStream,
)

__all__ = [
    "Agent",
    "AgentResponse",
    "ChatResponse",
    "Message",
    "ResponseStream",
]

# ❌ Prohibited pattern: wildcard/star imports (do not use)
# from ._agents import *
# from ._types import *

# ❌ Prohibited pattern: identity alias imports (do not use)
# from ._agents import Agent as Agent
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

### Integration Test Markers

New integration tests that call external services must have all three markers:

```python
@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_chat_completion() -> None:
    ...
```

- `@pytest.mark.flaky` — marks the test as potentially flaky since it depends on external services
- `@pytest.mark.integration` — enables selecting/excluding integration tests with `-m integration` / `-m "not integration"`
- `@skip_if_..._integration_tests_disabled` — skips the test when required API keys or service endpoints are missing

For test modules where all tests are integration tests, use `pytestmark`:

```python
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("01_single_agent"),
]
```

When adding integration tests for a new provider, update the path filters and job assignments in **both** `python-merge-tests.yml` and `python-integration-tests.yml` — these workflows must be kept in sync. See the `python-testing` skill for details.
