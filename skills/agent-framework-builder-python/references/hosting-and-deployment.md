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
- Prefer native workflow hosting. A shared `workflow.as_agent()` instance can leak workflow state across requests.
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

For Foundry `ResponsesHostServer`, use `history_source="host_managed"` (default), `"agent_managed"`,
or `"inference_service"`. Background execution uses `background_source="host_managed"` (default) or
`"inference_service"`; the latter requires inference-service history. `agent_managed` preserves the
agent's developer-owned HistoryProvider or downstream service storage choices. Configure the outer
storage backend with `response_store=`, not the removed constructor `store=` alias. The caller's
wire-level `store` flag is unchanged. See the
[constructor migration guide](https://github.com/microsoft/agent-framework/blob/main/python/packages/foundry_hosting/README.md#migrate-historybackground-names-and-the-response-store-argument)
for renamed literals; do not copy old names into new applications.

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
