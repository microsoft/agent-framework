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
  checkpoint restoration.
- Make session, checkpoint, response, identity, approval, storage, and cleanup ownership explicit.

Read the selected host's public docstrings and maintained sample for constructor options, parsers, history modes,
storage providers, and protocol details.

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
