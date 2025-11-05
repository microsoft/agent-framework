# Tools Examples

This folder contains examples demonstrating how to use AI functions (tools) with the Agent Framework. AI functions allow agents to interact with external systems, perform computations, and execute custom logic.

## Examples

| File | Description |
|------|-------------|
| [`ai_function_declaration_only.py`](ai_function_declaration_only.py) | Demonstrates how to create function declarations without implementations. Useful for testing agent reasoning about tool usage or when tools are defined elsewhere. Shows how agents request tool calls even when the tool won't be executed. |
| [`ai_function_from_dict_with_dependency_injection.py`](ai_function_from_dict_with_dependency_injection.py) | Shows how to create AI functions from dictionary definitions using dependency injection. The function implementation is injected at runtime during deserialization, enabling dynamic tool creation and configuration. Note: This serialization/deserialization feature is in active development. |
| [`ai_function_recover_from_failures.py`](ai_function_recover_from_failures.py) | Demonstrates graceful error handling when tools raise exceptions. Shows how agents receive error information and can recover from failures, deciding whether to retry or respond differently based on the exception. |
| [`ai_function_with_approval.py`](ai_function_with_approval.py) | Shows how to implement user approval workflows for function calls without using threads. Demonstrates both streaming and non-streaming approval patterns where users can approve or reject function executions before they run. |
| [`ai_function_with_approval_and_threads.py`](ai_function_with_approval_and_threads.py) | Demonstrates tool approval workflows using threads for automatic conversation history management. Shows how threads simplify approval workflows by automatically storing and retrieving conversation context. Includes both approval and rejection examples. |
| [`ai_function_with_max_exceptions.py`](ai_function_with_max_exceptions.py) | Shows how to limit the number of times a tool can fail with exceptions using `max_invocation_exceptions`. Useful for preventing expensive tools from being called repeatedly when they keep failing. |
| [`ai_function_with_max_invocations.py`](ai_function_with_max_invocations.py) | Demonstrates limiting the total number of times a tool can be invoked using `max_invocations`. Useful for rate-limiting expensive operations or ensuring tools are only called a specific number of times per conversation. |
| [`ai_functions_in_class.py`](ai_functions_in_class.py) | Shows how to use `ai_function` decorator with class methods to create stateful tools. Demonstrates how class state can control tool behavior dynamically, allowing you to adjust tool functionality at runtime by modifying class properties. |

## Key Concepts

### AI Function Features

- **Function Declarations**: Define tool schemas without implementations for testing or external tools
- **Dependency Injection**: Create tools from configurations with runtime-injected implementations
- **Error Handling**: Gracefully handle and recover from tool execution failures
- **Approval Workflows**: Require user approval before executing sensitive or important operations
- **Invocation Limits**: Control how many times tools can be called or fail
- **Stateful Tools**: Use class methods as tools to maintain state and dynamically control behavior

### Common Patterns

#### Basic Tool Definition

```python
from agent_framework import ai_function
from typing import Annotated

@ai_function
def my_tool(param: Annotated[str, "Description"]) -> str:
    """Tool description for the AI."""
    return f"Result: {param}"
```

#### Tool with Approval

```python
@ai_function(approval_mode="always_require")
def sensitive_operation(data: Annotated[str, "Data to process"]) -> str:
    """This requires user approval before execution."""
    return f"Processed: {data}"
```

#### Tool with Invocation Limits

```python
@ai_function(max_invocations=3)
def limited_tool() -> str:
    """Can only be called 3 times total."""
    return "Result"

@ai_function(max_invocation_exceptions=2)
def fragile_tool() -> str:
    """Can only fail 2 times before being disabled."""
    return "Result"
```

#### Stateful Tools with Classes

```python
class MyTools:
    def __init__(self, mode: str = "normal"):
        self.mode = mode

    def process(self, data: Annotated[str, "Data to process"]) -> str:
        """Process data based on current mode."""
        if self.mode == "safe":
            return f"Safely processed: {data}"
        return f"Processed: {data}"

# Create instance and use methods as tools
tools = MyTools(mode="safe")
agent = client.create_agent(tools=tools.process)

# Change behavior dynamically
tools.mode = "normal"
```

### Error Handling

When tools raise exceptions:
1. The exception is captured and sent to the agent as a function result
2. The agent receives the error message and can reason about what went wrong
3. The agent can retry with different parameters, use alternative tools, or explain the issue to the user
4. With invocation limits, tools can be disabled after repeated failures

### Approval Workflows

Two approaches for handling approvals:

1. **Without Threads**: Manually manage conversation context, including the query, approval request, and response in each iteration
2. **With Threads**: Thread automatically manages conversation history, simplifying the approval workflow

## Usage Tips

- Use **declaration-only** functions when you want to test agent reasoning without execution
- Use **dependency injection** for dynamic tool configuration and plugin architectures
- Implement **approval workflows** for operations that modify data, spend money, or require human oversight
- Set **invocation limits** to prevent runaway costs or infinite loops with expensive tools
- Handle **exceptions gracefully** to create robust agents that can recover from failures
- Use **class-based tools** when you need to maintain state or dynamically adjust tool behavior at runtime

## Running the Examples

Each example is a standalone Python script that can be run directly:

```bash
uv run python ai_function_with_approval.py
```

Make sure you have the necessary environment variables configured (like `OPENAI_API_KEY` or Azure credentials) before running the examples.
