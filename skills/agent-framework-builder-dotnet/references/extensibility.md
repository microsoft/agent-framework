# Extensibility

Use this reference when an application needs framework behavior that is not provided by an existing model or agent
provider, context provider, or middleware component.

## Choose an extension point

| Requirement | Extension point |
| --- | --- |
| Connect an unsupported model-style endpoint | Custom `IChatClient` (usually via `DelegatingChatClient` or an SDK adapter) |
| Connect a remote agent service or non-chat runtime | Custom `AIAgent` |
| Wrap or modify an existing agent | `DelegatingAIAgent` or `AIAgentBuilder.Use(...)` |
| Add retrieval, memory, dynamic instructions, per-run tools, or post-run extraction | Custom `AIContextProvider` or `MessageAIContextProvider` |
| Own how chat history is loaded and stored | Custom `ChatHistoryProvider` |
| Add cross-cutting execution policy, retries, caching, validation, or transforms | Agent, chat client, or function-invocation middleware |

Prefer composition through these public extension points over forking an existing provider or modifying framework
internals.

## Custom providers

Build a provider when the application must integrate a model endpoint or remote agent service that no existing Agent
Framework package supports, or when a private gateway requires custom authentication, transport, option mapping, or
protocol translation.

- Implement `IChatClient` when the backend accepts messages and returns model-style chat responses. Implement both
  `GetResponseAsync` and `GetStreamingResponseAsync`, plus `GetService`, and wrap the result with `ChatClientAgent`.
  Check whether the backend's SDK already exposes an `IChatClient` adapter before writing one.
- Derive from `AIAgent` when the backend already owns agent behavior or does not fit chat semantics. Implement the
  run and streaming-run methods and the session create/serialize/deserialize methods, defining what the session state
  contains.
- Use middleware instead of a provider when the underlying model protocol is already supported and the requirement is
  cross-cutting policy, retries, routing, logging, or request transformation.

A custom chat client is responsible for:

- converting `ChatMessage` and `AIContent` values to the backend request, and mapping responses, streaming updates,
  usage, identifiers, and finish reasons back;
- honoring `ChatOptions` (including tools and response format) or deliberately ignoring unsupported options without
  discarding them silently;
- mapping provider failures to actionable exceptions and honoring `CancellationToken`;
- declaring service-managed conversation behavior (`ConversationId`) when supported;
- owning and disposing any network clients it creates.

If a custom client needs the standard tool loop and telemetry, compose it with `ChatClientBuilder` (for example
`UseFunctionInvocation()` and `UseOpenTelemetry()`). `ChatClientAgent` adds function invocation itself unless
`UseProvidedChatClientAsIs` is set, so avoid layering it twice. Prefer an existing fully-featured client when only
configuration or middleware differs.

Current references:

- [Microsoft.Extensions.AI](https://learn.microsoft.com/dotnet/ai/microsoft-extensions-ai)
- [Agent samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents)
- [Agent provider samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/AgentProviders)

## Custom context providers

Build a custom `AIContextProvider` when an application needs reusable context engineering that runs with an agent, such
as retrieval, user or tenant memory, dynamic instructions, per-run tools, request-scoped data, or post-run extraction.
Use middleware instead when the requirement is primarily execution control around the agent, model, or tools.

1. Derive from `AIContextProvider` (or `MessageAIContextProvider` when only messages are added).
2. Understand the two layers. `InvokingAsync` and `InvokedAsync` are the public entry points the agent calls before and
   after the model run; they are not overridden. Each delegates to a protected virtual `...CoreAsync` method that
   carries the default behavior, which in turn calls a narrower `Provide`/`Store` hook:

   | Phase | Public entry point | Overridable core (full control) | Hook for most providers |
   | --- | --- | --- | --- |
   | Before the model call | `InvokingAsync` | `InvokingCoreAsync` | `ProvideAIContextAsync` |
   | After the model call | `InvokedAsync` | `InvokedCoreAsync` | `StoreAIContextAsync` |

   - Override `ProvideAIContextAsync` and `StoreAIContextAsync` for typical providers. `ProvideAIContextAsync`
     returns only the additional `AIContext` (instructions, messages, tools) to merge into the run. The default
     `InvokingCoreAsync` filters the input messages, calls it, stamps returned messages with
     `AgentRequestMessageSourceType.AIContextProvider` attribution, and merges the result with the original input.
     `StoreAIContextAsync` receives the request and response messages after a run; the default `InvokedCoreAsync`
     skips it when the run failed and applies the store-input message filters first.
   - Override `InvokingCoreAsync` or `InvokedCoreAsync` only when you need control over the whole context: your own
     filtering, merging, or source stamping before the call, or error handling (for example reacting to
     `InvokeException`) after it. You then call `ProvideAIContextAsync` or `StoreAIContextAsync` yourself if you still
     want them.
   - For `MessageAIContextProvider`, the equivalent hook is `ProvideMessagesAsync` (additional messages only), with
     `InvokingCoreAsync` as the full-control override.
3. Keep per-session mutable data in the session state bag (for example with `ProviderSessionState<TState>`) under a
   key unique to the provider (see `StateKeys`), not in instance fields, so one provider instance can serve many
   sessions.
4. Ensure state types are serializable with the session's `JsonSerializerOptions`; with trimming or AOT, use
   source-generated JSON contexts.
5. Register the provider through `ChatClientAgentOptions.AIContextProviders`.

`ChatHistoryProvider` uses the same `InvokingAsync` / `InvokedAsync` pair, but its job is to return the stored
messages to prepend and to persist the new request and response messages.

For cross-session memory, include origin session attribution and enforce authorization before injecting content.

Current references:

- [Context provider concepts](https://learn.microsoft.com/agent-framework/concepts/agents/conversations/context-providers)
- [Additional AI context sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents/Agent_Step17_AdditionalAIContext)
- [Third-party chat history storage sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents/Agent_Step04_3rdPartyChatHistoryStorage)

## Custom middleware

Use middleware for reusable behavior that belongs around an execution boundary rather than in agent instructions,
business tools, or a provider implementation. Common cases include policy enforcement, retries, caching, routing,
dynamic tool exposure, validation, observability, result transformation, and shared runtime context.

Choose the narrowest boundary:

- **Agent middleware** wraps the agent run. Add it with `agent.AsBuilder().Use(...)` (a run delegate and, optionally,
  a streaming delegate) or by deriving from `DelegatingAIAgent`. Use it for run-level policy, caching, termination,
  or result overrides.
- **Chat client middleware** wraps each model call, including calls inside a tool loop. Build it with
  `ChatClientBuilder.Use(...)` or a `DelegatingChatClient`. Use it for retries, request and response transformation,
  model routing, or per-call usage behavior.
- **Function-invocation middleware** wraps each tool call. Add it with the `AIAgentBuilder.Use(...)` overload that
  receives a function invocation context. Use it for argument checks, authorization context, logging, exception
  handling, or tool-result transformation.

The shared-delegate and function-invocation overloads receive a `next` delegate:

1. Inspect or change the input before execution.
2. Await `next` once, passing the inputs along.
3. Inspect or transform the result after execution.

The result-producing agent overload, `Use(runFunc, runStreamingFunc)`, instead receives the inner `AIAgent`. Call
`innerAgent.RunAsync(...)` in the run callback and `innerAgent.RunStreamingAsync(...)` in the streaming callback; the
streaming callback returns an `IAsyncEnumerable<AgentResponseUpdate>`, so enumerate and yield the inner updates.

Skip the inner call only when deliberately terminating the pipeline or returning a complete valid result. Keep state scoped to
the run or session unless cross-run sharing is intentional. Provide both non-streaming and streaming behavior; if only
the non-streaming delegate is supplied, check how streaming calls are handled.

### Ambient context

Middleware often needs to know which agent, session, or input a run belongs to without that being threaded through
every delegate. Two ambient (async-flowing) contexts exist:

- **`AIAgent.CurrentRunContext`** is a static property that holds an `AgentRunContext` for the current agent run. It
  exposes the running `Agent`, the `Session`, the request messages (`RequestMessages`), and the `RunOptions`. Read it
  from agent middleware, function middleware, tools, or chat client middleware executing inside the run. It is `null`
  outside a run, and each run (including a nested agent run) sets its own value, so read it where it is needed
  instead of caching it across runs.
- **`FunctionInvokingChatClient.CurrentContext`** is a static property that holds the `FunctionInvocationContext` for
  the tool call being executed: the function, its arguments, the call content, the originating chat messages and
  options, and the iteration position. Read it from inside a tool or chat client middleware that runs during function
  invocation. It is `null` outside function invocation, and it is the way a tool method reaches run-level data such as
  the options that started the run.

Use these instead of capturing the agent or session in closures, and do not store them beyond the call that read them.

Current references:

- [Middleware concepts](https://learn.microsoft.com/agent-framework/concepts/agents/middleware/)
- [Middleware sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents/Agent_Step11_Middleware)
- [Dependency injection sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents/Agent_Step06_DependencyInjection)

## Validation

- Custom providers: test regular and streaming parity, tools, structured output, usage, cancellation, session
  continuation, and disposal.
- Custom context providers: test attribution, multiple sessions, serialization and restoration, provider ordering,
  missing data, cross-session authorization, and failure behavior.
- Middleware: test the before/after paths, short-circuit behavior, exceptions, state scope, and both streaming and
  non-streaming execution.
