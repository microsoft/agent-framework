# Hosting and deployment

Use this path after the agent or workflow works locally. Keep Agent Framework application readiness separate from
cloud provisioning, RBAC, quota, networking, and deployment operations.

Hosting packages have independent lifecycle states. Verify current package maturity and host contracts before
generating files.

## Choose the hosting family

| Need | Hosting family |
| --- | --- |
| Local execution | Direct Python process |
| Protocol hosting in any self-managed environment | General `agent-framework-hosting*` packages |
| Microsoft Foundry Agent Server | `agent-framework-foundry-hosting` |
| Durable execution or Azure Functions | Durable Agent Framework extension |

Start with [hosting guidance](https://learn.microsoft.com/agent-framework/get-started/hosting) and then open the
selected host's detailed documentation and current sample.

## General hosting

The general hosting packages expose Agent Framework applications through protocols without targeting a specific cloud
or deployment environment. The application owns the process, network endpoint, scaling, identity, persistence, and
deployment platform.

| Protocol or surface | Package |
| --- | --- |
| Shared hosting abstractions | `agent-framework-hosting` |
| OpenAI-compatible Responses | `agent-framework-hosting-responses` |
| Agent-to-Agent (A2A) | `agent-framework-hosting-a2a` |
| Model Context Protocol (MCP) | `agent-framework-hosting-mcp` |
| Telegram | `agent-framework-hosting-telegram` |

These packages provide host adapters and protocol behavior; they do not provision or deploy the surrounding
infrastructure. They are currently alpha packages, so verify their current contracts before depending on them.

Treat protocol request bodies and translated run options as caller-controlled input. Forward only an explicit allowlist
of options that the application supports; do not pass caller-supplied tools, instructions, or
`additional_function_arguments` into `agent.run(...)` unless the application deliberately exposes those capabilities.

## Foundry hosting

`agent-framework-foundry-hosting` is specifically for the Microsoft Foundry Agent Server and currently provides at
least two hosting protocols:

| Foundry protocol | API |
| --- | --- |
| OpenAI-compatible Responses | `ResponsesHostServer` |
| Custom invocation request and response contracts | `InvocationsHostServer` |

This package integrates Agent Framework sessions, responses, approvals, workflows, and Foundry sandbox identity with
the platform host. It is not the general-purpose hosting layer for arbitrary environments.

### Responses protocol

`agent-framework-foundry-hosting` is currently beta, so allow prerelease resolution when installing it.

```python
from __future__ import annotations

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, ResponsesHostServer
from azure.identity import DefaultAzureCredential


agent = Agent(
    client=FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=DefaultAzureCredential(),
    ),
    instructions="You are a helpful assistant.",
    default_options={"store": False},
)

ResponsesHostServer(agent=agent, history_source="agent_server").run()
```

Choose the history source deliberately:

- `agent_server` lets the host reconstruct outer Responses history and disables duplicate inner storage;
- `service` uses the downstream service's private continuation;
- `agent` lets the agent's history provider or client storage own history.

Do not combine competing history owners.

### Invocations protocol

Use `InvocationsHostServer` when the hosted application needs its own invocation payload and response contract instead
of the OpenAI Responses protocol. Supply the documented parser or invocation handler and make session, identity, and
workflow continuation behavior explicit.

## Foundry agent and workflow ownership

- Passing an agent instance reuses it for the host lifetime.
- Pass a zero-argument sync or async factory when the agent owns mutable state outside `AgentSession`.
- Prefer native `workflow=` hosting when the host supports workflows.
- Hosting `workflow.as_agent()` is deprecated in Foundry hosting because a shared workflow agent is stateful and can
  leak state across requests.
- Workflow factories must build fresh workflows, executors, agents, clients, providers, and mutable tools while
  preserving stable workflow and executor identities for checkpoint restoration.

## Entry-point contracts

- `build_agent()` is an application convention, not a framework requirement.
- Export a module-level `agent` only when the selected discovery or hosting path requires it.
- Foundry host servers accept an agent instance or factory through `agent=`.
- Native Foundry workflow hosting has its own `workflow=` and request-parsing contracts.
- General Responses, A2A, MCP, Telegram, and durable hosts use their own adapters; follow the selected package's
  examples instead of applying Foundry-specific server contracts.

## Configuration and identity

Document only variables required by the selected provider and host. Common Foundry examples use:

- `FOUNDRY_PROJECT_ENDPOINT`;
- `FOUNDRY_MODEL`;
- a development credential such as `AzureCliCredential`;
- a deliberate production credential, commonly managed identity.

Do not commit secrets. Review `DefaultAzureCredential` for production because its fallback chain may probe credentials
the application did not intend to use.

## Deployment readiness checklist

- `pyproject.toml` declares only required runtime packages.
- The selected entry point imports and constructs the agent or workflow.
- Required environment variables fail with clear messages.
- Session, checkpoint, response, and service-history ownership are explicit.
- Tool side effects and approval behavior are documented.
- External files, skills, prompts, and resources are packaged intentionally.
- Health, logging, telemetry, and sensitive-data settings match the host.
- Request-scoped resources are created and cleaned up by the request-scoped factory.
- The deployment package contains no local credentials, caches, or unrelated files.
- Host-specific manifests are added only by the deployment workflow that consumes them.

## Deploy a hosted agent to Microsoft Foundry

After local readiness is proven, follow the Foundry Hosted Agent deployment flow rather than inventing manifests or
infrastructure files:

1. Start from a compatible `agent.manifest.yaml` for the selected Responses or Invocations host.
2. Initialize the deployment project with `azd ai agent init -m <manifest-url>`.
3. Run `azd provision` only when the required Foundry project, model deployment, registry, and monitoring resources do
   not already exist.
4. Test the host locally with `azd ai agent run` and `azd ai agent invoke --local`.
5. Deploy with `azd deploy`.

Use these instructions according to the scenario:

- [Agent Framework: Foundry hosted agents and deployment](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent#deploying-to-foundry)
- [Foundry quickstart: deploy your first hosted agent with azd](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Foundry: deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Foundry: deploy a hosted agent from source code](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code)
- [Host Agent Framework agents as Foundry hosted agents](https://learn.microsoft.com/azure/foundry/how-to/develop/framework-hosted-agents#deploy)
- [Manage deployed hosted agents](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-agent)
- [Agent Framework hosted-agent sample deployment instructions](https://github.com/microsoft/agent-framework/tree/main/python/samples/04-hosting/foundry-hosted-agents#deploying-the-agent-to-foundry)

Use dedicated Foundry tooling for provisioning, deployment, invocation, traces, RBAC, quota, capacity, and
troubleshooting. Host manifests and runtime environment variables are deployment contracts; copy them from the current
guide or sample for the selected protocol instead of constructing them from memory.

Current examples:

- [First hosted agent](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/07_hosting.py)
- [Foundry hosting package guidance](https://github.com/microsoft/agent-framework/blob/main/python/packages/foundry_hosting/README.md)
- [Foundry hosted-agent samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/04-hosting/foundry-hosted-agents)
