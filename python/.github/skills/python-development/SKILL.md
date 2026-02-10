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
- Only document standard Python exceptions when the condition is non-obvious

## Logging

Use the centralized logging system, never direct `import logging`:

```python
from agent_framework import get_logger

logger = get_logger()
# For subpackages:
logger = get_logger('agent_framework.azure')
```

## Import Structure

```python
# Core
from agent_framework import ChatAgent, ChatMessage, tool

# Components
from agent_framework.observability import enable_instrumentation

# Connectors (lazy-loaded)
from agent_framework.openai import OpenAIChatClient
from agent_framework.azure import AzureOpenAIChatClient
```

## Public API and Exports

Define `__all__` in each module. Avoid `from module import *` in `__init__.py` files:

```python
__all__ = ["ChatAgent", "ChatMessage", "ChatResponse"]

from ._agents import ChatAgent
from ._types import ChatMessage, ChatResponse
```

## Performance Guidelines

- Cache expensive computations (e.g., JSON schema generation)
- Prefer `match/case` on `.type` attribute over `isinstance()` in hot paths
- Avoid redundant serialization — compute once, reuse

## Style

- Line length: 120 characters
- Avoid excessive comments; prefer clear code
- Format only files you changed, not the entire codebase
- Prefer attributes over inheritance when parameters are mostly the same
- Async by default — assume everything is asynchronous

## Naming Conventions for Connectors

- `_prepare_<object>_for_<purpose>` for methods that prepare data for external services
- `_parse_<object>_from_<source>` for methods that process data from external services
