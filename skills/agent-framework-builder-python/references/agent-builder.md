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

## Minimal project

```text
my-agent/
  pyproject.toml
  agent.py
```

For the canonical Foundry-backed starting point, use the package manager selected by the project or user:

```bash
# uv
uv init --bare --python 3.13
uv add agent-framework-foundry azure-identity

# pip
python -m pip install agent-framework-foundry azure-identity
```

Install only the distributions required by the selected provider and capabilities. Add prerelease resolution only when
one of those distributions is prerelease.

## Minimal Foundry agent

Use environment variables in real applications:

```python
from __future__ import annotations

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


async def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=AzureCliCredential(),
        ),
        name="my-agent",
        instructions="Describe the agent behavior here.",
    )
    print(await agent.run("Hello"))


if __name__ == "__main__":
    asyncio.run(main())
```

Agent Framework does not automatically load `.env` files. Add `python-dotenv` and call `load_dotenv()` only when the
application intentionally uses a `.env` file.

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

Use an `AgentSession` for multi-turn state:

```python
session = agent.create_session()
await agent.run("Remember Amsterdam.", session=session)
response = await agent.run("What city should you remember?", session=session)
```

- Do not reuse a session concurrently unless the provider and application explicitly support it.
- Treat persisted session state as sensitive data.

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

## Middleware

Choose the narrowest middleware layer:

- agent middleware for run-level policy, termination, result overrides, and shared state;
- chat middleware for model request and response behavior;
- function middleware for tool invocation behavior.

In Python middleware, call `await call_next()` without passing the context again.

## Validation

1. Import and construct the client and agent without invoking the model where practical.
2. Validate required environment variables with clear errors.
3. Unit-test deterministic tools, schemas, context providers, and middleware.
4. Add an opt-in live smoke test only when provider access is available.
5. Exercise a second turn when session behavior is required.
6. Check approval behavior with at least one side-effecting tool.

Current examples:

- [Minimal agent](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/01_hello_agent.py)
- [Function tool](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/02_add_tools.py)
- [Multi-turn session](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/03_multi_turn.py)
