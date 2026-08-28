# A2A Agent Skills

This sample demonstrates how to expose each skill advertised by an A2A agent as a separate function tool for another AI agent.

Unlike exposing the whole A2A agent as one tool, this approach gives the model a distinct tool for each skill. The sample uses the skill metadata from the A2A agent card to name and describe those tools.

All generated tools invoke the same A2A agent. Their names and descriptions help the main agent choose an advertised capability; they do not invoke separate skill-specific endpoints.

The sample:

- Discovers a remote A2A agent and its skills from the agent card
- Creates one function tool for each advertised skill
- Adds the skill's description, tags, examples, and supported modes to the function description
- Registers all generated function tools with a main AI agent

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
