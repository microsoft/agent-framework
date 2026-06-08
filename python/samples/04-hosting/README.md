# Hosting Samples

This directory contains Python samples that demonstrate different ways to host Agent Framework agents. Use this page to choose the hosting model that best fits your scenario, then continue to the README in the relevant subdirectory.

## Hosting Options

| Option | Use this when you need... | Start here |
|--------|----------------------------|------------|
| A2A | Agent-to-Agent protocol interoperability or remote agent invocation. | [`a2a/README.md`](./a2a/README.md) |
| Azure Functions | HTTP or serverless hosting on Azure Functions. | [`azure_functions/README.md`](./azure_functions/README.md) |
| Durable Task | Durable execution, long-running flows, or orchestration patterns. | [`durabletask/README.md`](./durabletask/README.md) |
| Foundry Hosted Agents | Azure AI Foundry hosted agent deployment. | [`foundry-hosted-agents/README.md`](./foundry-hosted-agents/README.md) |

## How to Choose

- Start with **A2A** if you want one agent to call or expose another agent over the A2A protocol.
- Start with **Azure Functions** if you want an HTTP-hosted or serverless entry point using Azure Functions.
- Start with **Durable Task** if you need persistent state, durable workflows, or orchestration across multiple steps.
- Start with **Foundry Hosted Agents** if you want to package and deploy an agent as a hosted agent in Azure AI Foundry.

## Common Prerequisites

Most hosting samples share a small set of prerequisites:

- A supported Python environment for running the samples locally.
- An Azure AI Foundry project endpoint and model deployment name for `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`.
- Azure CLI authentication via `az login` when the sample uses `AzureCliCredential`.
- Any hosting-specific tools or extra services called out in the subdirectory README.

## Next Steps

1. Pick the hosting approach that matches your scenario.
2. Open the corresponding README for setup and run instructions.
3. Follow that sample's environment, dependency, and execution steps.
