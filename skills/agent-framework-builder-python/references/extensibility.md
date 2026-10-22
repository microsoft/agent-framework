# Extensibility

Use this reference when an application needs framework behavior that is not provided by an existing model or agent
provider, ContextProvider, or middleware component.

## Choose an extension point

| Requirement | Extension point |
| --- | --- |
| Connect an unsupported model-style endpoint | Custom `BaseChatClient` |
| Connect a remote agent service or non-chat runtime | Custom `SupportsAgentRun`, usually a `BaseAgent` |
| Add retrieval, memory, dynamic instructions, per-run tools, or post-run extraction | Custom `ContextProvider` |
| Add cross-cutting execution policy, retries, caching, validation, or transforms | Agent, chat, or function middleware |

Prefer composition through these public extension points over forking an existing provider or modifying framework
internals.

## Custom providers

Build a provider when the application must integrate a model endpoint or remote agent service that no existing Agent
Framework package supports, or when a private gateway requires custom authentication, transport, option mapping, or
protocol translation.

Choose the provider shape that matches the backend:

- Implement a chat client when the backend accepts messages and returns model-style chat responses. Subclass
  `BaseChatClient` and implement `_inner_get_response(...)` for both regular and streaming execution.
- Implement an agent when the backend already owns agent behavior or does not fit chat-client semantics. Implement
  `SupportsAgentRun`, usually by subclassing `BaseAgent`, and support both `stream=False` and `stream=True`.
- Use middleware instead of a provider when the underlying model protocol is already supported and the requirement is
  cross-cutting policy, retries, routing, logging, or request transformation.

A custom chat client is responsible for:

- converting Agent Framework `Message` and `Content` values to the backend request;
- mapping backend responses, streaming updates, usage, identifiers, and finish information back to framework types;
- defining typed provider-specific options without discarding unknown application options unintentionally;
- mapping provider failures to actionable exceptions and preserving cancellation;
- declaring service-managed history behavior and persisting continuation identifiers through `AgentSession` when
  supported;
- owning and cleaning up network clients or other context-managed resources it creates.

If a custom client needs the standard tool loop, chat middleware, and telemetry, compose the public layers in this
order: function invocation, chat middleware, chat telemetry, then the raw or base client. Prefer an existing
fully-featured client when only configuration or middleware differs.

Current references:

- [BaseChatClient API](https://learn.microsoft.com/python/api/agent-framework-core/agent_framework.basechatclient?view=agent-framework-python-latest)
- [Custom chat client sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/chat_client/custom_chat_client.py)
- [Custom agent sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/providers/custom/custom_agent.py)

## Custom ContextProviders

Build a custom `ContextProvider` when an application needs reusable context engineering that runs with an agent, such
as retrieval, user or tenant memory, dynamic instructions, per-run tools, request-scoped data, or post-run extraction.
Use middleware instead when the requirement is primarily execution control around the agent, model, or tools.

1. Subclass `ContextProvider` and give each provider instance a stable, unique `source_id`.
2. Override `before_run(...)` to add context through `SessionContext`:
   - `extend_instructions(...)` for dynamic instructions;
   - `extend_messages(...)` for retrieved or remembered messages;
   - `extend_tools(...)` for tools available only to this invocation;
   - `extend_middleware(...)` for invocation-scoped chat or function middleware.
3. Override `after_run(...)` to inspect the input and response, extract new information, or persist provider-owned
   state.
4. Store mutable provider data in the supplied provider-scoped `state` dictionary. Use `session.state` directly only
   when deliberate coordination across providers is required.
5. Register custom persisted classes with `register_state_type(...)` at module import time so restored sessions can
   deserialize them before the application loads a session.

Set `after_run_once_per_turn=True` when an `AgentLoopMiddleware` should defer `after_run` until the whole user turn is
complete. Context providers may add chat or function middleware, but not agent middleware.

For cross-session memory, include origin session attribution and enforce authorization before injecting content.

Current references:

- [Context Provider concepts](https://learn.microsoft.com/agent-framework/concepts/agents/conversations/context-providers)
- [ContextProvider API](https://learn.microsoft.com/python/api/agent-framework-core/agent_framework.contextprovider)
- [Custom ContextProvider sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/context_providers/simple_context_provider.py)

## Custom middleware

Use middleware for reusable behavior that belongs around an execution boundary rather than in agent instructions,
business tools, or a provider implementation. Common cases include policy enforcement, retries, caching, routing,
dynamic tool exposure, validation, observability, result transformation, and shared runtime context.

Choose the narrowest boundary:

- **Agent middleware** runs around `Agent.run(...)`. Use it for run-level policy, caching, termination, result
  overrides, or shared state.
- **Chat middleware** runs around each model call, including calls inside a tool loop. Use it for retries, request and
  response transformation, model routing, or per-call usage behavior.
- **Function middleware** runs around each local tool invocation. Use it for validated-argument checks, authorization
  context, logging, exception handling, or tool-result transformation.

Create middleware either by subclassing `AgentMiddleware`, `ChatMiddleware`, or `FunctionMiddleware`, or by using the
matching decorator. The implementation receives a context and `call_next`:

1. Inspect or update the context before execution.
2. Call `await call_next()` without passing the context again.
3. Inspect or transform the result after execution.

Skip `call_next()` only when deliberately terminating the pipeline or returning a complete valid result. Keep state
scoped to the run or session unless cross-run sharing is intentional, and test both streaming and non-streaming paths.

Current references:

- [Middleware concepts](https://learn.microsoft.com/agent-framework/concepts/agents/middleware/)
- [Middleware samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/middleware)
- [Class-based middleware sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/middleware/class_based_middleware.py)

## Validation

- Custom providers: test regular and streaming parity, tools, structured output, usage, cancellation, session
  continuation, resource cleanup, and layer ordering.
- Custom ContextProviders: test attribution, multiple sessions, serialization and restoration, provider ordering,
  missing data, cross-session authorization, and failure behavior.
- Middleware: test the before/after paths, short-circuit behavior, exceptions, state scope, and both streaming and
  non-streaming execution.
