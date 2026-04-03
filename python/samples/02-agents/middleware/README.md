# Middleware samples

This folder contains focused middleware samples for `Agent`, chat clients, tools, sessions, and runtime context behavior.

## Files

| File | Description |
|------|-------------|
| [`agent_and_run_level_middleware.py`](./agent_and_run_level_middleware.py) | Demonstrates combining agent-level and run-level middleware. |
| [`chat_middleware.py`](./chat_middleware.py) | Shows class-based and function-based chat middleware that can observe, modify, and override model calls. |
| [`class_based_middleware.py`](./class_based_middleware.py) | Shows class-based agent and function middleware. |
| [`decorator_middleware.py`](./decorator_middleware.py) | Demonstrates middleware registration with decorators. |
| [`exception_handling_with_middleware.py`](./exception_handling_with_middleware.py) | Shows how middleware can handle failures and recover cleanly. |
| [`function_based_middleware.py`](./function_based_middleware.py) | Shows function-based agent and function middleware. |
| [`middleware_termination.py`](./middleware_termination.py) | Demonstrates stopping a middleware pipeline early. |
| [`override_result_with_middleware.py`](./override_result_with_middleware.py) | Shows how middleware can replace regular and streaming results, then post-process the final response. |
| [`runtime_context_delegation.py`](./runtime_context_delegation.py) | Demonstrates delegating arguments with runtime context data. |
| [`session_behavior_middleware.py`](./session_behavior_middleware.py) | Shows how middleware interacts with session-backed runs. |
| [`shared_state_middleware.py`](./shared_state_middleware.py) | Demonstrates sharing mutable state across middleware invocations. |
| [`usage_tracking_middleware.py`](./usage_tracking_middleware.py) | Demonstrates one chat middleware function that tracks per-call usage in non-streaming and streaming tool-loop runs. |

## Running the usage tracking sample

The new usage tracking sample uses `OpenAIChatClient`, so set the usual OpenAI responses environment variables first:

```bash
export OPENAI_API_KEY="your-openai-api-key"
export OPENAI_CHAT_MODEL="gpt-4.1-mini"
```

Then run:

```bash
uv run samples/02-agents/middleware/usage_tracking_middleware.py
```

The sample forces a tool call so you can see middleware output for each inner model call in both non-streaming and streaming modes.
