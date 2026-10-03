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
| [`atr_validation_middleware.py`](./atr_validation_middleware.py) | Demonstrates deterministic validation at the tool-execution boundary: a `FunctionMiddleware` that inspects the validated tool arguments and raises `MiddlewareTermination` before the tool runs when they match an attack rule. Loads the open, MIT-licensed Agent Threat Rules ruleset and runs the real engine locally (`pip install pyatr`), with a built-in deny-list fallback when it is not installed. |
| [`chat_middleware.py`](./chat_middleware.py) | Shows class-based and function-based chat middleware that can observe, modify, and override model calls. |
| [`class_based_middleware.py`](./class_based_middleware.py) | Shows class-based agent and function middleware. |
| [`decorator_middleware.py`](./decorator_middleware.py) | Demonstrates middleware registration with decorators. |
| [`exception_handling_with_middleware.py`](./exception_handling_with_middleware.py) | Shows how middleware can handle failures and recover cleanly. |
| [`function_based_middleware.py`](./function_based_middleware.py) | Shows function-based agent and function middleware. |
| [`ismalicious_content_gate.py`](./ismalicious_content_gate.py) | Checks the destination before one operator-approved text-fetch tool executes, then scans its complete result before another model call. |
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

### Running the IsMalicious content gate sample

This example uses `FunctionInvocationContext` and `call_next()` around one local
fetch tool. A separate operator decision authorizes the hostname. The middleware
checks its URL with `GET /gate/url`, executes the tool only when policy permits,
then sends the complete UTF-8 result and source URL to `POST /gate/scan`.
Both gate requests go to `https://api.ismalicious.com`. The selected document's
text and URL are transmitted to that external service; these calls consume its
separate scan quota. Obtain credentials at [IsMalicious account settings](https://ismalicious.com/app/account).

Install the Python development environment following [DEV_SETUP.md](../../../DEV_SETUP.md),
or run the self-contained script with its PEP 723 dependencies using `uv run`.
The script uses `agent-framework-foundry`, `httpx`, and `python-dotenv`; it does not
change the framework's dependency set. Run `az login`, then configure:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com"
export FOUNDRY_MODEL="your-model-deployment"
export ISMALICIOUS_API_KEY="your-api-key"
export ISMALICIOUS_API_SECRET="your-api-secret"
export CONTENT_GATE_HOST="learn.microsoft.com"
export CONTENT_GATE_URL="https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview"
uv run samples/02-agents/middleware/ismalicious_content_gate.py
```

Use managed secrets for deployments. Credentials are sent as
`X-API-KEY: Base64(apiKey:apiSecret)` on a separate client and never attached to
the document fetch. HTTPS verification stays enabled, redirects are refused,
requests have a 15-second timeout, and quota failures are not retried.
Decision logs contain only verdicts. Do not enable sensitive framework telemetry
when handling documents that must not appear in model/tool traces.

`block` and `warn` stop the run by default. An operator can explicitly set
`IsMaliciousContentGate(..., allow_warn=True)` to release `warn` results.
Timeouts, HTTP failures, redirects, malformed or unsupported verdicts, and
incomplete link inspection also stop the run. The middleware replaces its current
result with a fixed withholding message before raising `MiddlewareTermination`,
since termination alone can preserve a result that has already been produced.

An `allow` result means the service did not object under its current rules;
it does not prove content or a destination is benign. The service currently maps
unknown link reputation to `allow`. Unknown records and additive response fields
are retained in `context.metadata["ismalicious_scan"]` for another middleware to
inspect; this sample refuses `links_truncated=True`. Original allowed text is
released unchanged, without using `sanitized_content` as a replacement.
The request uses `mode="fast"`; the reserved `thorough` mode currently behaves as
`fast` and is not a stronger inspection path.

The example covers only non-streaming `Agent.run()` with this exact selected
local tool, returning a complete UTF-8 `text/plain` or `text/html` string. It
refuses objects, binary content, invalid UTF-8 and documents whose complete
serialized scan request exceeds 1 MiB, without truncation. The selected hostname
should be a public document source under operator control; this example is not a
general-purpose network sandbox. MCP tools and tools executed by a provider are
outside its tested scope. Gate requests are direct client calls, so they do not
re-enter the tool middleware.

Expected output includes destination/content verdict logs and an agent-run status
line. Actual verdicts depend on the selected document. To check enforcement
without keys or live HTTP/model services, run from `python/`:

```bash
uv run pytest tests/samples/middleware/test_ismalicious_content_gate.py -q
```

These tests use the actual `Agent` function-calling loop and middleware pipeline
with simulated model and HTTP responses. They verify ordering, withholding,
unmodified allowed text, explicit warning policy, request encoding, body limits,
response validation and credential-free decision logs. They do not test detector
accuracy or live Foundry/IsMalicious availability.

`AgentLoopMiddleware.with_judge` (used by `agent_loop_middleware_judge.py` and
`agent_loop_middleware_report.py`) is an explicit opt-in to sending the original request and the
agent's latest response to a second, external judge chat client on every iteration. A compromised
or malicious judge endpoint could exfiltrate that data, or return a manipulated verdict/gap
analysis that gets fed back into the loop as feedback — a form of indirect prompt injection. Only
configure a judge client that points at a service you trust as much as the primary model.
