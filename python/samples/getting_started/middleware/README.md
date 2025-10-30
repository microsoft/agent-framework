# Middleware Examples

This folder contains examples demonstrating various middleware patterns with the Agent Framework. Middleware allows you to intercept and modify behavior at different execution stages, including agent runs, function calls, and chat interactions.

## Examples

| File | Description |
|------|-------------|
| [`function_based_middleware.py`](function_based_middleware.py) | Demonstrates how to implement middleware using simple async functions instead of classes. Shows security validation, logging, and performance monitoring middleware. Function-based middleware is ideal for simple, stateless operations and provides a lightweight approach. |
| [`class_based_middleware.py`](class_based_middleware.py) | Shows how to implement middleware using class-based approach by inheriting from `AgentMiddleware` and `FunctionMiddleware` base classes. Includes security checks for sensitive information and detailed function execution logging with timing. |
| [`decorator_middleware.py`](decorator_middleware.py) | Demonstrates how to use `@agent_middleware` and `@function_middleware` decorators to explicitly mark middleware functions without requiring type annotations. Shows different middleware detection scenarios and explicit decorator usage. |
| [`middleware_termination.py`](middleware_termination.py) | Shows how middleware can terminate execution using the `context.terminate` flag. Includes examples of pre-termination (prevents agent processing) and post-termination (allows processing but stops further execution). Useful for security checks, rate limiting, or early exit conditions. |
| [`exception_handling_with_middleware.py`](exception_handling_with_middleware.py) | Demonstrates how to use middleware for centralized exception handling in function calls. Shows how to catch exceptions from functions, provide graceful error responses, and override function results when errors occur to provide user-friendly messages. |
| [`override_result_with_middleware.py`](override_result_with_middleware.py) | Shows how to use middleware to intercept and modify function results after execution, supporting both regular and streaming agent responses. Demonstrates result filtering, formatting, enhancement, and custom streaming response generation. |
| [`shared_state_middleware.py`](shared_state_middleware.py) | Demonstrates how to implement function-based middleware within a class to share state between multiple middleware functions. Shows how middleware can work together by sharing state, including call counting and result enhancement. |
| [`thread_behavior_middleware.py`](thread_behavior_middleware.py) | Demonstrates how middleware can access and track thread state across multiple agent runs. Shows how `AgentRunContext.thread` behaves differently before and after the `next()` call, how conversation history accumulates in threads, and timing of thread message updates. Essential for understanding conversation flow in middleware. |
| [`agent_and_run_level_middleware.py`](agent_and_run_level_middleware.py) | Explains the difference between agent-level middleware (applied to ALL runs of the agent) and run-level middleware (applied to specific runs only). Shows security validation, performance monitoring, and context-specific middleware patterns. |
| [`chat_middleware.py`](chat_middleware.py) | Demonstrates how to use chat middleware to observe and override inputs sent to AI models. Shows how to intercept chat requests, log and modify input messages, and override entire responses before they reach the underlying AI service. |

## Key Concepts

### Middleware Types

- **Agent Middleware**: Intercepts agent run execution, allowing you to modify requests and responses
- **Function Middleware**: Intercepts function calls within agents, enabling logging, validation, and result modification
- **Chat Middleware**: Intercepts chat requests sent to AI models, allowing input/output transformation

### Implementation Approaches

- **Function-based**: Simple async functions for lightweight, stateless operations
- **Class-based**: Inherit from base middleware classes for complex, stateful operations
- **Decorator-based**: Use decorators for explicit middleware marking

### Common Use Cases

- **Security**: Validate requests, block sensitive information, implement access controls
- **Logging**: Track execution timing, log parameters and results, monitor performance
- **Error Handling**: Catch exceptions, provide graceful fallbacks, implement retry logic
- **Result Transformation**: Filter, format, or enhance function outputs
- **State Management**: Share data between middleware functions, maintain execution context

### Execution Control

- **Termination**: Use `context.terminate` to stop execution early
- **Result Override**: Modify or replace function/agent results
- **Streaming Support**: Handle both regular and streaming responses
