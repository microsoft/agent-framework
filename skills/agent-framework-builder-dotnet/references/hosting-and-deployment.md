# Hosting and deployment

Use hosting after the agent or workflow works locally. Separate the runtime protocol from the deployment platform:
hosting libraries expose an application; infrastructure tooling deploys it.

## Choose the hosting family

| Need | Source of detail |
| --- | --- |
| Self-managed protocol endpoint (ASP.NET Core) | [Agent Framework hosting](https://learn.microsoft.com/agent-framework/hosting/) |
| Microsoft Foundry Agent Server | [Foundry hosted agents](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent) |
| Durable execution or Azure Functions | [Durable agent samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/04-hosting/DurableAgents) and [durable workflow samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/04-hosting/DurableWorkflows) |

`Microsoft.Agents.AI.Hosting` registers agents and workflows with dependency injection (`AddAIAgent(...)`,
`WithSessionStore(...)`, `WithAITool(...)`). Protocol adapters sit on top of it for ASP.NET Core: OpenAI-compatible
Responses, Chat Completions, and Conversations (`Microsoft.Agents.AI.Hosting.OpenAI`), A2A
(`Microsoft.Agents.AI.Hosting.A2A.AspNetCore`), and AG-UI (`Microsoft.Agents.AI.Hosting.AGUI.AspNetCore`).
`Microsoft.Agents.AI.Foundry.Hosting` is specific to the Foundry Agent Server. Check current package maturity (most
hosting packages are preview or alpha) and protocol documentation rather than copying option inventories into
application code.

## Stable hosting rules

- Treat translated request options as caller-controlled input and forward only an explicit allowlist.
- Choose one history owner; do not combine competing host, service, and agent history mechanisms.
- Register an agent as a singleton only when all mutable state is session-scoped. Otherwise use a request-owned factory
  or scoped registration.
- Prefer native workflow hosting. A shared workflow wrapped as an agent can leak workflow state across requests.
- Build fresh workflows and request-owned resources while keeping workflow and executor IDs stable for checkpoint
  restoration.
- Use an `AgentSessionStore` (`WithSessionStore`) that persists across instances for scaled-out deployments; the
  in-memory store is for development. Use isolation keys (for example the claims-based provider) so one caller cannot
  read another caller's sessions.
- Authenticate and authorize endpoints with ASP.NET Core middleware; protocol adapters do not do this for you. Never
  expose DevUI publicly.
- Make session, checkpoint, response, identity, approval, storage, and cleanup ownership explicit.

Read the selected host's XML docs and maintained sample for options, history modes, storage providers, and protocol
details.

## Deployment readiness

Verify the app starts and the endpoint responds, required packages and files are published, configuration fails
clearly, history and storage ownership are documented, request-owned resources are disposed, and no local credentials,
user secrets, or development settings enter the deployment package. Use managed identity or another token credential in
the hosted environment.

## Deploy to Microsoft Foundry

Foundry deployment commands, manifests, prerequisites, and injected configuration change independently from Agent
Framework. Use current authoritative instructions:

- [Agent Framework Foundry deployment guidance](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent#deploying-to-foundry)
- [Foundry hosted-agent quickstart](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Deploy from source code](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code)
- [Manage hosted agents](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-agent)
- [Agent Framework hosted-agent SDK samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/04-hosting/FoundryHostedAgents)
- [Foundry-hosted Agent Framework deployment gallery](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/csharp/hosted-agents/agent-framework)

Use those sources for `azd`, provisioning, manifests, environment variables, deployment, invocation, RBAC, quota,
monitoring, and troubleshooting. Do not reconstruct deployment files from memory.

## Learn more

- [Local hosting samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/04-hosting/af-hosting)
- [Host your agent (getting started)](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/01-get-started/06_host_your_agent)
