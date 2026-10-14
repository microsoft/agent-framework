# Providers and integrations

Choose integrations only after the application contract is clear. A model provider or agent service supplies the
underlying intelligence; tools, memory, protocols, UI, and hosting add separate capabilities.

Package and provider availability changes more frequently than core agent patterns. Check current Microsoft Learn
documentation and package metadata before adding dependencies or promising feature parity.

## Python version compatibility

Agent Framework supports Python 3.10 through 3.15. Python 3.10 remains supported and tested for the current release but
is deprecated because upstream Python 3.10 has reached end of life. New environments should use Python 3.11 or later.

Python 3.15 supports the core framework and most integrations, with these current limitations:

| Area | Python 3.15 limitation |
| --- | --- |
| Declarative Power Fx | `agent-framework-declarative` installs without its `powerfx` dependency. Expressions beginning with `=` are not evaluated. |
| Redis | `agent-framework-redis` is unavailable because RedisVL requires Python earlier than 3.15. |
| Hyperlight | `agent-framework-hyperlight` is unavailable until a compatible sandbox backend wheel is published. |
| AG-UI A2UI | Base `agent-framework-ag-ui` works, but its optional `a2ui` extra is unavailable because the toolkit requires Python earlier than 3.15. |

Check each selected distribution's `Requires-Python` metadata instead of assuming every integration supports the full
framework range.

## Providers and agent services

Common released distributions include:

- `agent-framework-foundry` for Microsoft Foundry chat clients, managed agents, memory, embeddings, and Foundry evals;
- `agent-framework-openai` for OpenAI and Azure OpenAI Responses or Chat Completions clients;
- `agent-framework-github-copilot` for GitHub Copilot-backed scenarios.

Other providers and agent services have independent lifecycle states and Python requirements. Install only the selected
distribution and allow prerelease packages only when required.

Start with the current
[model provider catalog](https://learn.microsoft.com/agent-framework/integrations/by-component/model-providers/) and
[agent service catalog](https://learn.microsoft.com/agent-framework/integrations/by-component/agent-services/).

Verify:

- authentication and identity;
- Python and package version support;
- streaming and structured output;
- hosted tools;
- application-managed versus service-managed history;
- tool approval and function-loop behavior.

## Tools

Choose local versus hosted execution deliberately:

- function tools for application-owned Python functions;
- local MCP for caller-owned MCP clients and sessions;
- hosted MCP, web search, file search, or code interpreter only when the selected provider supports them;
- Agent Skills through `SkillsProvider` when the built agent should discover reusable capabilities.

Keep local function and MCP side effects under the application's approval and security policy. Hosted execution still
requires explicit identity, data-boundary, and provider-capability review.

## Memory, retrieval, and vector stores

Use normal sessions and context providers first. Add a connector when persistence, scale, search, or an external data
model requires it.

Current integration categories include:

- chat history and context providers;
- Foundry memory;
- Azure AI Search;
- Cosmos DB and Redis;
- vector-store connectors such as PostgreSQL, MongoDB, Qdrant, DuckDB, Oracle, SQL Server, and DocumentDB;
- graph and third-party memory providers.

Some connector packages are alpha or beta even when core is released. Check lifecycle state and supported operations.

Define tenant, user, retention, deletion, authorization, and encryption boundaries before persisting conversation,
memory, or vector data.

## Protocol and UI integrations

- A2A for interoperable agent-to-agent communication.
- MCP hosting when the application exposes tools through MCP.
- ChatKit and other application-specific UI integrations where appropriate.

Protocol integration does not replace authorization. Validate identities, payloads, exposed tools, and cross-tenant
behavior at every boundary.

### AG-UI

Use `agent-framework-ag-ui` to connect Agent Framework agents and workflows to AG-UI-compatible frontends.

- `add_agent_framework_fastapi_endpoint(...)` exposes a `SupportsAgentRun` implementation or `Workflow` through a
  FastAPI endpoint.
- `AgentFrameworkAgent` and `AgentFrameworkWorkflow` provide the protocol adapters.
- `AGUIChatClient` connects an Agent Framework application to an existing AG-UI server.
- AG-UI supports streaming events, tool calls, shared state, interrupts, approval resume, and thread snapshots.
- Use a thread-scoped workflow factory when workflow instances hold mutable runtime state.
- AG-UI thread and run IDs are correlation identifiers, not authentication or tenant-isolation boundaries.
- The application owns authorization, durable snapshot storage, scaling, and frontend rendering policy.

Current starting point:
[AG-UI single-agent sample](https://github.com/microsoft/agent-framework/tree/main/python/samples/05-end-to-end/ag_ui_single_agent).

## Durable and cloud integrations

Durable Task and Azure Functions integrations are maintained in the
[Durable Agent Framework extension](https://github.com/microsoft/agent-framework-durable-extension), not in the main
Python package tree.

Foundry hosting and other host adapters have separate packages and lifecycle states. Read
`hosting-and-deployment.md` before adding host or deployment files.

## Selection checklist

1. Confirm the provider or service and authentication model.
2. Check package lifecycle and Python support.
3. Check required provider features rather than assuming parity.
4. Add only the selected integration packages.
5. Define data, network, identity, approval, and retention boundaries.
6. Build a focused integration test or opt-in live smoke test.
7. Document required environment variables and permissions.

Current catalogs:

- [Agent Framework integrations](https://learn.microsoft.com/agent-framework/integrations/)
- [Python package status](https://github.com/microsoft/agent-framework/blob/main/python/PACKAGE_STATUS.md)
- [Python samples](https://github.com/microsoft/agent-framework/tree/main/python/samples)
