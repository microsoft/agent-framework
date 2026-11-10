# Hosting and deployment

Use hosting after the agent or workflow works locally. Separate the runtime protocol from the deployment platform:
hosting libraries expose an application; infrastructure tooling deploys it.

## Choose the hosting family

| Need | Source of detail |
| --- | --- |
| Self-managed protocol endpoint | [Agent Framework hosting](https://learn.microsoft.com/agent-framework/hosting/) |
| Microsoft Foundry Agent Server | [Foundry hosted agents](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent) |
| Durable execution or Azure Functions | [Durable Agent Framework extension](https://github.com/microsoft/agent-framework-durable-extension) |

General hosting packages target arbitrary environments and provide protocol adapters such as Responses, A2A, MCP, or
Telegram. `agent-framework-foundry-hosting` is specific to the Foundry Agent Server and supports Responses and
Invocations contracts. Check current package maturity and protocol documentation rather than copying option inventories
into application code.

## Stable hosting rules

- Treat translated request options as caller-controlled input and forward only an explicit allowlist.
- Choose one history owner; do not combine competing host, service, and agent history mechanisms.
- Reuse an agent instance only when all mutable state is session-scoped. Otherwise use a request-owned factory.
- Use native workflow hosting. Foundry agent hosts reject `WorkflowAgent` instances and factory results.
- Build fresh workflows and request-owned resources while keeping workflow and executor identities stable for
  checkpoint restoration. A builder reused across requests returns new workflows that share its registered
  executors, including each `AgentExecutor` and its `AgentSession`; create those executors inside the per-request
  factory.
- Make session, checkpoint, response, identity, approval, storage, and cleanup ownership explicit.

MCP `approval_mode` supports a synchronous callable so server-specific policies can be composed without
subclassing a transport. It receives a discovered `mcp.types.Tool` or `mcp.types.Prompt` and must return
`"always_require"` or `"never_require"` for every item, including its default decision. It runs on discovery
and refresh, not invocation; invalid results fail discovery. Ordinary MCP `approval_mode=None` means no approval.

`FoundryToolbox` instead uses `None` to select its metadata policy. See
[Toolbox approvals and trust boundary](https://github.com/microsoft/agent-framework/blob/main/python/packages/foundry_hosting/README.md#toolbox-tool-approvals)
for vendor-specific configuration, caller overrides, and the trust placed in read-only labels.

For MCP agent tools, `AgentMCPTool.call_tool(...)` validates the generated input schema before execution or
session-store access. Applications using `mcp_to_run(...)` directly must validate their own schema before conversion.
Keep schemas in trusted application configuration. Regex validation is synchronous and has no execution timeout;
choose patterns with predictable matching time for untrusted values and property names.

Read the selected host's public docstrings and maintained sample for constructor options, parsers, history modes,
storage providers, and protocol details.

### Foundry agent and native workflow hosts

Use `ResponsesHostServer(agent=...)` or `InvocationsHostServer(agent=...)` for agents.
Agent factories may be synchronous or asynchronous and can accept the protocol's request:
`ResponsesRequest` for Responses (including trusted scope and current-turn input), or
Starlette `Request` for Invocations. Zero-argument factories also work; when both forms bind,
the request form wins. Responses factories run before the options hook; Invocations factories
run after parsing and option preparation. Factory-owned resource cleanup is unchanged.
For native workflows, import `ResponsesWorkflowHostServer` or `InvocationsWorkflowHostServer`
from `agent_framework_foundry_hosting` (also available under `agent_framework.foundry`).
The agent hosts no longer accept `workflow=` or checkpoint stores, and reject `WorkflowAgent` even when
returned by a factory. Workflow factories must return a built `Workflow`, not an agent or wrapper.

Both workflow hosts require a request-aware sync/async `workflow` factory returning an isolated,
built `Workflow`. Create executors, agents, clients, providers, and mutable tools inside that factory;
a fresh graph wrapper around shared executors is not enough. Keep graph and executor IDs stable.
Built workflow instances are rejected even for local one-shot hosting.

Responses workflow hosts require `parse_input(ResponsesRequest) -> WorkflowTurn` and retain
the `prepare_options` model-options hook. Invocations workflow hosts require
`parse_input(starlette.requests.Request) -> WorkflowTurn`; configure workflow kwargs in that parser,
not through agent-only option hooks. Both support async parsers. Workflow state and pending replies
are checkpoint-owned, not agent-session-owned. Do not copy agent history/background-source settings,
agent-session stores, or separate agent approval stores into workflow hosts.
This split does not change SDK options, wire-level `store`, checkpoint/retry guarantees, or the
experimental status of Invocations and Toolbox.

For migration, rename `parse_response` (Responses workflows) or `parse_request` (Invocations agents/workflows)
to `parse_input`, and `HostedResponseRequest` to `ResponsesRequest`. There are no aliases for the old names.
Invocations agent parsers return `InvocationRun`; workflow parsers return `WorkflowTurn` for typed start input
or complete validated pending replies.

Responses agent history uses `history_source="host_managed"` (default), `"agent_managed"`, or
`"inference_service"`; the old values were `"agent_server"`, `"agent"`, and `"service"`, respectively.
`agent_managed` preserves developer-owned provider **or** service storage. Background execution uses
`background_source="host_managed"` (default) or `"inference_service"` instead of `"agent_server"` or
`"provider"`. Inference-service background requires inference-service history and a supported storing,
resumable client. These literal renames do not change defaults or execution behavior.
Use `response_store=` for the outer Responses storage backend. The old constructor `store=` alias
is removed and rejected, including `None`; the per-request wire `store` flag is unchanged.

## Deployment readiness

Verify the entry point imports, required packages and external files are included, configuration fails clearly, history
and storage ownership are documented, request-owned resources are cleaned up, and no local credentials or caches enter
the deployment package.

## Deploy to Microsoft Foundry

Foundry deployment commands, manifests, prerequisites, and injected configuration change independently from Agent
Framework. Use current authoritative instructions:

- [Agent Framework Foundry deployment guidance](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent#deploying-to-foundry)
- [Foundry hosted-agent quickstart](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Deploy from source code](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code)
- [Manage hosted agents](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-agent)
- [Agent Framework hosted-agent SDK samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/04-hosting/foundry-hosted-agents)
- [Foundry-hosted Agent Framework deployment gallery](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework)

Use those sources for `azd`, provisioning, manifests, environment variables, deployment, invocation, RBAC, quota,
monitoring, and troubleshooting. Do not reconstruct deployment files from memory.
