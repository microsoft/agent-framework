# Plain agent builder

Use this path for .NET agents whose behavior can be expressed with one `AIAgent` (usually a `ChatClientAgent`), a model
or remote-agent client, tools, sessions, context providers, and middleware.

## Requirement intake

Capture:

1. Goal and user-visible behavior.
2. Input and output shape, including streaming or structured output.
3. Model provider, authentication, and whether the definition is application-owned or service-managed.
4. Tools, hosted tools, and side effects that require approval.
5. Session, history, retrieval, memory, and compaction requirements.
6. Middleware, runtime context, observability, and evaluation criteria.
7. Console, ASP.NET Core, worker, protocol-hosted, durable, or Foundry-hosted deployment.

Ask only about unknowns that materially affect the design.

## Start from maintained examples

For a new application, select the provider first and add only its package. Use the current quickstart or maintained
sample for package commands and runnable code rather than copying versions or setup steps into the skill.

- [Your first agent](https://learn.microsoft.com/agent-framework/get-started/your-first-agent)
- [.NET getting-started samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/01-get-started)

The stable pattern is a provider client converted to an agent with `AsAIAgent(...)`, or `new ChatClientAgent(chatClient,
...)` for any `IChatClient`, configured with instructions, tools, and optionally `ChatClientAgentOptions` for context
providers and history. Configuration loading remains application-owned.

## Provider selection

| Need | Package and API |
| --- | --- |
| Foundry project model with application-owned instructions and tools | `Azure.AI.Projects` + `Microsoft.Agents.AI.Foundry`, `AIProjectClient.AsAIAgent(...)` |
| Interact with an existing agent already defined in Foundry | `Microsoft.Agents.AI.Foundry` Foundry agent APIs |
| Foundry Models, Azure OpenAI, or OpenAI with Responses semantics | `OpenAI` (or `Azure.AI.OpenAI`) + `Microsoft.Agents.AI.OpenAI`, `ResponsesClient.AsAIAgent(...)` |
| Foundry Models, Azure OpenAI, or OpenAI with Chat Completions semantics | `OpenAI` (or `Azure.AI.OpenAI`) + `Microsoft.Agents.AI.OpenAI`, `ChatClient.AsAIAgent(...)` |
| Anthropic, or Anthropic on Foundry | `Anthropic` or `Anthropic.Foundry` + `Microsoft.Agents.AI.Anthropic` |
| Ollama, Amazon Bedrock, Google Gemini, ONNX, Dapr, or any other `IChatClient` | The provider's `IChatClient` implementation, wrapped with `ChatClientAgent` or `chatClient.AsAIAgent(...)` from `Microsoft.Agents.AI` |
| Other agent service | Its current provider package and documented agent |

Several SDKs can reach Foundry, Azure OpenAI, OpenAI, or Anthropic. The SDK, NuGet packages, and endpoint format depend
on the service and authentication model, so use the
[model provider catalog](https://learn.microsoft.com/agent-framework/integrations/by-component/model-providers/?pivots=programming-language-csharp)
(the .NET view) to pick the exact packages, especially for the long tail of providers, rather than guessing package
names.

An agent that connects to an existing Foundry agent does not create, deploy, version, update, or otherwise manage that
agent definition; use the appropriate Foundry management APIs or deployment tools for those operations.

Use current provider documentation before assuming hosted-tool, storage, streaming, or structured-output parity.

## Tools and approval

- Prefer focused, typed, non-interactive tool methods. Create tools with `AIFunctionFactory.Create(...)` and describe
  methods and parameters with `[Description]`.
- Functions are invoked automatically by the function-invocation layer and do not require approval by default. Wrap
  side-effecting functions in `ApprovalRequiredAIFunction` so the run returns an approval request instead of executing
  the tool.
- Treat writes, sends, purchases, destructive operations, shell commands, and privileged external calls as side
  effects.
- Handle approval requests in the caller: inspect `ToolApprovalRequestContent` items in the response, then send back
  the matching approval response on the same session. Do not auto-approve in code unless the product explicitly
  accepts that policy.
- Keep return values structured when downstream code or evaluation consumes them.
- Use hosted tools only with providers that document support.
- Instance methods and DI-resolved services work as tools; keep captured state thread-safe because tools can run
  concurrently.

## Structured output

Use `RunAsync<T>(...)` for typed results when the provider supports JSON-schema output, and check for deserialization
failure instead of assuming success. For streaming, collect the updates first, then convert them to a response.

## Sessions

Create an `AgentSession` with `agent.CreateSessionAsync()` and pass the same session to each `RunAsync` call in one
logical conversation. Without a session, each call is independent.

- Do not use one session for concurrent runs. This is not supported, and `ChatClientAgent` does not guard against it;
  concurrent runs on one session can corrupt its state. (`ChatClientAgentOptions.AllowConcurrentInvocation` is
  unrelated: it controls parallel execution of multiple tool calls within a single run.)
- Persist with `agent.SerializeSessionAsync(session)` and restore with `agent.DeserializeSessionAsync(json)`. Restore
  with the same agent configuration (providers and state keys) that created the session.
- Treat persisted session state as sensitive data. It also holds pending tool-approval requests, which the server uses
  to validate approval responses. Store it server-side in tenant-authorized storage with integrity protection, never
  accept session JSON from a client, and bound deserialization size.
- Read [session documentation](https://learn.microsoft.com/agent-framework/concepts/agents/conversations/session) for
  serialization and provider-specific continuation behavior.

## History

Choose one primary history owner:

- **Application-managed history** uses a `ChatHistoryProvider` to load prior messages and persist new messages in
  `AgentSession` state or an external store. `InMemoryChatHistoryProvider` keeps history in the session state.
- **Service-managed history** is used when the provider stores the conversation and returns a service conversation
  identifier that Agent Framework keeps on the session; later turns send new input against that stored conversation
  instead of resending the full transcript.
- When the service does not manage history and no `ChatHistoryProvider` is configured, `ChatClientAgent` defaults to an
  `InMemoryChatHistoryProvider`, which keeps messages in the session state. Serializing and restoring the session
  therefore preserves history across restarts. Use a custom `ChatHistoryProvider` only when history must live in an
  external store (shared across instances, queried, or too large for session state).
- Not every provider supports service-managed storage, and continuation and branching behavior varies.
- Combining service-managed storage with a configured `ChatHistoryProvider` is a conflict. `ChatClientAgentOptions`
  controls the behavior (`ClearOnChatHistoryProviderConflict`, `WarnOnChatHistoryProviderConflict`,
  `ThrowOnChatHistoryProviderConflict`); do not relax these unless the combination is documented, or the model may
  receive duplicate history.
- Treat stored messages and service conversation identifiers as sensitive data.
- Add compaction (`Microsoft.Agents.AI.Compaction` strategies) when conversations or tool loops can exceed the model
  context window.

## Context providers

Use an `AIContextProvider` (or `MessageAIContextProvider` for message-only enrichment) when instructions, messages,
tools, retrieval results, memory, or other context must be supplied dynamically for a run or session. Register
providers through `ChatClientAgentOptions.AIContextProviders`.

- Keep conversation history ownership in a `ChatHistoryProvider`; context providers serve a different extension point.
- Prefer scoped context providers over concatenating changing data into static agent instructions.
- Define when the provider loads and persists data, and keep its session-state keys distinct from other providers.
- Treat retrieved and persisted context as sensitive and enforce tenant and user boundaries outside the model.
- Built-in providers include `TextSearchProvider` (retrieval), `ChatHistoryMemoryProvider` (vector-store memory over
  chat history), and the harness providers.

For custom providers, context providers, and middleware, read [Extensibility](extensibility.md).

## Dependency injection

In ASP.NET Core or generic-host apps, register agents through the hosting package (`AddAIAgent(...)` on the host
builder) instead of constructing them per request. Reuse an agent instance only when all mutable state is
session-scoped. See [Hosting and deployment](hosting-and-deployment.md).

## Validation

1. Build the project (`dotnet build`) and construct the client and agent without invoking the model where practical.
2. Check the selected provider documentation for its endpoint, model, and credential settings and tell the user to set
   them. Do not hard-code or print secrets, and let the SDK client resolve and validate credentials.
3. Unit-test deterministic tools, schemas, context providers, and middleware with a fake `IChatClient`.
4. Add an opt-in live smoke test only when provider access is available.
5. Exercise a second turn on the same session when session behavior is required, including a serialize/restore round
   trip when sessions are persisted.
6. Check approval behavior with at least one side-effecting tool.

Current examples:

- [Minimal agent](https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/01-get-started/01_hello_agent/Program.cs)
- [Function tool](https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/01-get-started/02_add_tools/Program.cs)
- [Multi-turn session](https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/01-get-started/03_multi_turn/Program.cs)
- [Agent samples (approvals, structured output, persistence, DI, middleware)](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents)
