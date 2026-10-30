# Middleware samples

This folder contains focused middleware samples for `Agent`, chat clients, tools, sessions, and runtime context behavior.

## Files

| File | Description |
|------|-------------|
| [`agent_and_run_level_middleware.py`](./agent_and_run_level_middleware.py) | Demonstrates combining agent-level and run-level middleware. |
| [`agent_loop_middleware_refinement.py`](./agent_loop_middleware_refinement.py) | Demonstrates `AgentLoopMiddleware` with a `should_continue` predicate: a completion-marker refinement loop with feedback tracking and `fresh_context`. |
| [`agent_loop_middleware_todos.py`](./agent_loop_middleware_todos.py) | Demonstrates `AgentLoopMiddleware` with a `should_continue` predicate built from a `TodoProvider` via `todos_remaining`, so the agent keeps working while open todos remain. |
| [`agent_loop_middleware_judge.py`](./agent_loop_middleware_judge.py) | Demonstrates `AgentLoopMiddleware.with_judge`: a ChatClient judge re-runs the agent until it decides the original request was answered, with `criteria` shared between the agent and the judge. |
| [`agent_loop_middleware_report.py`](./agent_loop_middleware_report.py) | Demonstrates composing two `AgentLoopMiddleware` on one agent: an inner `todos_remaining` loop that drafts a report todo-by-todo, wrapped by an outer report-style `with_judge` loop that re-runs it until an editor chat client judges the report publication-ready. |
| [`atr_validation_middleware.py`](./atr_validation_middleware.py) | Demonstrates deterministic validation at the tool-execution boundary: a `FunctionMiddleware` that raises `MiddlewareTermination` before the tool runs when the arguments match a high- or critical-severity Agent Threat Rules rule, and logs lower-severity matches as warnings. It is not a dangerous-command filter, so use tool approval in production. Runs the open, MIT-licensed ruleset locally (`pip install pyatr`). |
| [`chat_middleware.py`](./chat_middleware.py) | Shows class-based and function-based chat middleware that can observe, modify, and override model calls. |
| [`class_based_middleware.py`](./class_based_middleware.py) | Shows class-based agent and function middleware. |
| [`decorator_middleware.py`](./decorator_middleware.py) | Demonstrates middleware registration with decorators. |
| [`exception_handling_with_middleware.py`](./exception_handling_with_middleware.py) | Shows how middleware can handle failures and recover cleanly. |
| [`function_based_middleware.py`](./function_based_middleware.py) | Shows function-based agent and function middleware. |
| [`middleware_termination.py`](./middleware_termination.py) | Demonstrates stopping a middleware pipeline early. |
| [`message_injection_middleware.py`](./message_injection_middleware.py) | Demonstrates `MessageInjectionMiddleware` with a real Foundry chat client: enqueueing a follow-up message into the active session while a long-running async tool is awaiting. |
| [`override_result_with_middleware.py`](./override_result_with_middleware.py) | Shows how middleware registers result transforms and buffered re-derivation on its context before execution, then post-processes regular and streaming responses. |
| [`runtime_context_delegation.py`](./runtime_context_delegation.py) | Demonstrates delegating arguments with runtime context data. |
| [`session_behavior_middleware.py`](./session_behavior_middleware.py) | Shows how middleware interacts with session-backed runs. |
| [`shared_state_middleware.py`](./shared_state_middleware.py) | Demonstrates sharing mutable state across middleware invocations. |
| [`usage_tracking_middleware.py`](./usage_tracking_middleware.py) | Demonstrates one chat middleware function that registers stream transforms on `ChatContext` before execution to track per-call usage in non-streaming and streaming tool-loop runs. |

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

## Security Considerations

`AgentLoopMiddleware.with_judge` (used by `agent_loop_middleware_judge.py` and
`agent_loop_middleware_report.py`) is an explicit opt-in to sending the original request and the
agent's latest response to a second, external judge chat client on every iteration. A compromised
or malicious judge endpoint could exfiltrate that data, or return a manipulated verdict/gap
analysis that gets fed back into the loop as feedback — a form of indirect prompt injection. Only
configure a judge client that points at a service you trust as much as the primary model.

### Per-tool execution deadlines

The `per_tool_execution_deadlines.py` sample demonstrates independent
asynchronous deadlines using the existing `FunctionMiddleware` extension
point and Python 3.10-compatible `asyncio` APIs.

Run from the `python` directory:

```bash
python samples/02-agents/middleware/per_tool_execution_deadlines.py
python -m pytest samples/02-agents/middleware/test_per_tool_execution_deadlines.py -v
```

Each configured tool has an independent deadline. Unconfigured tools
execute normally.

- **Read-only tools:** Deadline expiry produces a recoverable result.
- **Side-effecting tools:** Deadline expiry raises `MiddlewareFailure`
  because side effects may already have occurred.
- **Tool-generated timeouts:** A tool's own `TimeoutError` propagates
  separately from an enforced deadline.
- **Caller cancellation:** Cancellation propagates rather than being
  converted into a normal timeout result.
- **Concurrency:** Different tools can have independent budgets.

The sample introduces no new framework API and does not implement
automatic retries or distributed deadline enforcement.

**Cancellation and cleanup limitations:** Async cancellation is
cooperative. Cleanup can take longer than the configured deadline.
Synchronous worker threads or remote operations may continue running.
Deadline expiry does not guarantee rollback, exactly-once execution,
or absence of side effects.

Caller cancellation is propagated after requesting cancellation of the
underlying asynchronous task. That task may continue cooperative cleanup
after the caller has been cancelled. Any eventual task exception is
observed to avoid an unhandled-task warning.

This sample does not provide hard termination, rollback, exactly-once
execution, or automatic retries.
