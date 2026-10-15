# Plain agent builder

Use this path for Python agents whose behavior can be expressed with one `Agent`, a model or remote-agent client, tools,
sessions, context providers, and middleware.

## Requirement intake

Capture:

1. Goal and user-visible behavior.
2. Input and output shape, including streaming or structured output.
3. Model provider, authentication, and whether the definition is application-owned or service-managed.
4. Tools, hosted tools, and side effects that require approval.
5. Session, history, retrieval, memory, and compaction requirements.
6. Middleware, runtime context, observability, and evaluation criteria.
7. Local, self-hosted, protocol-hosted, durable, or Foundry-hosted deployment.

Ask only about unknowns that materially affect the design.

## Start from maintained examples

For a new application, select the provider first and install only its required distribution and capabilities. Use the
current quickstart or maintained sample for package commands and runnable code rather than copying versions or setup
steps into the skill.

- [Your first agent](https://learn.microsoft.com/agent-framework/get-started/your-first-agent)
- [Python getting-started samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/01-get-started)

The stable pattern is an `Agent` wrapping a chat client, instructions, tools, middleware, and ContextProviders. Agent
Framework does not automatically load `.env` files; configuration loading remains application-owned.

## Provider selection

| Need | Distribution and API |
| --- | --- |
| Foundry project model with application-owned instructions and tools | `agent-framework-foundry`, `FoundryChatClient` |
| Interact with an existing agent of any supported type already defined in Foundry | `agent-framework-foundry`, `FoundryAgent` |
| OpenAI and OpenAI-compatible endpoints with Responses semantics | `agent-framework-openai`, `OpenAIChatClient` |
| OpenAI and OpenAI-compatible endpoints with Chat Completions semantics | `agent-framework-openai`, `OpenAIChatCompletionClient` |
| Other model or agent service | Its current provider distribution and documented client or agent |

`FoundryAgent` connects to and interacts with an agent that already exists in Foundry. It does not create, deploy,
version, update, or otherwise manage that agent definition; use the appropriate Foundry management APIs or deployment
tools for those operations.

Use current provider documentation before assuming hosted-tool, storage, streaming, or structured-output parity.

## Tools and approval

- Prefer focused, typed, non-interactive tool functions.
- Use `@tool` or `FunctionTool` when explicit schema or approval behavior is needed.
- Tool approval defaults to `never_require`; set `approval_mode="always_require"` for side effects.
- Treat writes, sends, purchases, destructive operations, shell commands, and privileged external calls as side effects.
- Keep return values structured when downstream code or evaluation consumes them.
- Use hosted tools only with providers that document support.

For parameter descriptions, use normal annotations and current schema guidance rather than inventing provider-specific
JSON schemas.

## Sessions

Create an `AgentSession` through the agent and pass the same session to each run in one logical conversation.

- Do not reuse a session concurrently unless the provider and application explicitly support it.
- Treat persisted session state as sensitive data.
- Read [session documentation](https://learn.microsoft.com/agent-framework/concepts/agents/conversations/session) for
  serialization and provider-specific continuation behavior.

## History

Choose one primary history owner:

- **Application-managed history** uses a `HistoryProvider` to load prior messages and persist new messages in
  `AgentSession` state or an external store.
- **Service-managed history** is available on clients that support a `store` option. With `store=True`, the provider
  stores the conversation and returns a service continuation identifier that Agent Framework keeps in
  `AgentSession.service_session_id`; later turns can send new input against that stored conversation instead of
  resending the full transcript.
- With `store=False`, the provider does not retain the conversation. Use a `HistoryProvider` or supply the required
  prior messages when multi-turn context is needed.
- When the chat client does not support service-managed storage and no configured `HistoryProvider` reads history,
  `Agent` adds an `InMemoryHistoryProvider` by default so an `AgentSession` retains conversation history for the
  current process. Replace it with a persistent history provider when history must survive process restarts or scale
  across instances.

- Not every provider supports `store`, and service-managed continuation and branching behavior varies by provider.
- Avoid combining service-managed storage with a load-enabled history provider unless the provider documentation
  explicitly describes that combination; otherwise the model may receive duplicate history.
- Treat stored messages and service continuation identifiers as sensitive data.
- Add compaction when conversations or tool loops can exceed the model context window.

## Context providers

Use a `ContextProvider` when instructions, messages, tools, retrieval results, memory, or other context must be supplied
dynamically for a run or session.

- Keep conversation history ownership in a `HistoryProvider`; context providers serve a different extension point.
- Prefer scoped context providers over concatenating changing data into static agent instructions.
- Define when the provider loads and persists data, and keep its session-state keys distinct from other providers.
- Treat retrieved and persisted context as sensitive and enforce tenant and user boundaries outside the model.

For custom providers, ContextProviders, and middleware, read
[Extensibility](extensibility.md).

## Validation

1. Import and construct the client and agent without invoking the model where practical.
2. Check the selected client or provider documentation for its environment keys and tell the user to set them. Let the
   framework classes resolve and validate those settings. If values come from a `.env` file, pass the documented
   environment-file option or call `load_dotenv()` before construction; do not manually resolve each setting.
3. Unit-test deterministic tools, schemas, context providers, and middleware.
4. Add an opt-in live smoke test only when provider access is available.
5. Exercise a second turn when session behavior is required.
6. Check approval behavior with at least one side-effecting tool.

Current examples:

- [Minimal agent](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/01_hello_agent.py)
- [Function tool](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/02_add_tools.py)
- [Multi-turn session](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/03_multi_turn.py)
