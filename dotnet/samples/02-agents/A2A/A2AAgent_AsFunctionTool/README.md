# A2A Agent as a Function Tool

This sample demonstrates how to expose an A2A agent as a single function tool that another AI agent can call.

The sample:

- Discovers a remote A2A agent from its agent card
- Converts the agent card to an `AIAgent`
- Converts that agent to one function tool with `AsAIFunction()`
- Registers the function tool with a main AI agent

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Access to the A2A agent host service
- A Microsoft Foundry project with a deployed model

**Note**: These samples need to be run against a valid A2A server. If no A2A server is available, they can be run against the echo-agent that can be spun up locally by following the guidelines at: https://github.com/a2aproject/a2a-dotnet/blob/main/samples/AgentServer/README.md

Set the following environment variables:

Authenticate with Azure CLI by running `az login`, then set:

```powershell
$env:A2A_AGENT_HOST="https://your-a2a-agent-host" # Replace with your A2A agent host endpoint
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project" # Replace with your Foundry project endpoint
$env:FOUNDRY_MODEL="gpt-5.4-mini"  # Optional, defaults to gpt-5.4-mini
```
