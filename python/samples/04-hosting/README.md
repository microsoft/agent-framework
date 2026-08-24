# Hosting Samples

This directory contains Python samples that demonstrate different ways to host Agent Framework agents. Use this page to choose the hosting model that best fits your scenario, then continue to the README in the relevant subdirectory.

## Hosting Options

| Option | Use this when you need... | Start here |
|--------|----------------------------|------------|
| A2A | Agent-to-Agent protocol interoperability or remote agent invocation. | [`a2a/README.md`](./a2a/README.md) |
| Azure Functions | HTTP or serverless hosting on Azure Functions. | [Durable extension Azure Functions samples](https://github.com/microsoft/agent-framework-durable-extension/tree/main/python/samples/azure_functions) |
| Durable Task | Durable execution, long-running flows, or orchestration patterns. | [Durable extension samples](https://github.com/microsoft/agent-framework-durable-extension/tree/main/python/samples) |
| Foundry Hosted Agents | Microsoft Foundry hosted agent deployment. | [`foundry-hosted-agents/README.md`](./foundry-hosted-agents/README.md) |
| Self-Hosted Protocol Helpers | Application-owned OpenAI Responses endpoints or Telegram bots. | [`af-hosting/README.md`](./af-hosting/README.md) |

## How to Choose

- Start with **A2A** if you want one agent to call or expose another agent over the A2A protocol.
- Start with the **Durable Agent Framework extension** if you need Azure Functions hosting, persistent state, durable workflows, or orchestration across multiple steps.
- Start with **Foundry Hosted Agents** if you want to package and deploy an agent as a hosted agent in Microsoft Foundry.
- Start with **Self-Hosted Protocol Helpers** if you want to own the web framework or native SDK, routing, authorization, and state storage while using OpenAI Responses or Telegram helpers.

## Common Prerequisites

Most hosting samples share a small set of prerequisites:

- A supported Python environment for running the samples locally.
- A Microsoft Foundry project endpoint and model deployment name for `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`.
- Azure CLI authentication via `az login` when the sample uses `AzureCliCredential`.
- Any hosting-specific tools or extra services called out in the subdirectory README.

## Next Steps

1. Pick the hosting approach that matches your scenario.
2. Open the corresponding README for setup and run instructions.
3. Follow that sample's environment, dependency, and execution steps.
