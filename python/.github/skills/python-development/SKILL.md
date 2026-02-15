---
name: python-development
description: >
  Coding standards, conventions, and patterns for developing Python code in the
  Agent Framework repository. Use this when writing or modifying Python source
  files in the python/ directory.
---

# Python Development Standards

## File Header

Every `.py` file must start with:

```python
# Copyright (c) Microsoft. All rights reserved.
```

## Type Annotations

- Always specify return types and parameter types
- Use `Type | None` instead of `Optional[Type]`
- Use `from __future__ import annotations` to enable postponed evaluation
- Use suffix `T` for TypeVar names: `ChatResponseT = TypeVar("ChatResponseT", bound=ChatResponse)`
- Use `Mapping` instead of `MutableMapping` for read-only input parameters
- Prefer `# type: ignore[...]` over unnecessary casts, or `isinstance` checks, when these are internally called and executed methods
    But make sure the ignore is specific for both mypy and pyright so that we don't miss other mistakes

## Function Parameters

- Positional parameters: up to 3 fully expected parameters
- Use keyword-only arguments (after `*`) for optional parameters
- Provide string-based overrides to avoid requiring extra imports:

```python
def create_agent(name: str, tool_mode: Literal['auto', 'required', 'none'] | ChatToolMode) -> Agent:
    if isinstance(tool_mode, str):
        tool_mode = ChatToolMode(tool_mode)
```

- Avoid shadowing built-ins (use `next_handler` instead of `next`)
- Avoid `**kwargs` unless needed for subclass extensibility; prefer named parameters

## Docstrings

Use Google-style docstrings for all public APIs:

```python
def equal(arg1: str, arg2: str) -> bool:
    """Compares two strings and returns True if they are the same.

    Args:
        arg1: The first string to compare.
        arg2: The second string to compare.

    Returns:
        True if the strings are the same, False otherwise.

    Raises:
        ValueError: If one of the strings is empty.
    """
```

- Always document Agent Framework specific exceptions
- Explicitly use `Keyword Args` when applicable
- Only document standard Python exceptions when the condition is non-obvious

## Import Structure

```python
# Core
from agent_framework import ChatAgent, Message, tool

# Components
from agent_framework.observability import enable_instrumentation

# Connectors (lazy-loaded)
from agent_framework.openai import OpenAIChatClient
from agent_framework.azure import AzureOpenAIChatClient
```

## Public API and Exports

In `__init__.py` files that define package-level public APIs, use direct re-export imports plus an explicit
`__all__`. Avoid identity aliases like `from ._agents import ChatAgent as ChatAgent`, and avoid
`from module import *`.

Do not define `__all__` in internal non-`__init__.py` modules. Exception: modules intentionally exposed as a
public import surface (for example, `agent_framework.observability`) should define `__all__`.

```python
__all__ = ["ChatAgent", "Message", "ChatResponse"]

from ._agents import ChatAgent
from ._types import Message, ChatResponse
```

## Performance Guidelines

- Cache expensive computations (e.g., JSON schema generation)
- Prefer `match/case` on `.type` attribute over `isinstance()` in hot paths
- Avoid redundant serialization — compute once, reuse

## Style

- Line length: 120 characters
- Format only files you changed, not the entire codebase
- Prefer attributes over inheritance when parameters are mostly the same
- Async by default — assume everything is asynchronous

## Naming Conventions for Connectors

- `_prepare_<object>_for_<purpose>` for methods that prepare data for external services
- `_parse_<object>_from_<source>` for methods that process data from external services
