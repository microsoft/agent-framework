# Foundry Toolbox MCP Skills

This sample uses
`AgentSkillsProviderBuilder` to discover MCP-based skills from a Foundry Toolbox endpoint
and inject them as `AIContextProviders` so the agent can discover and use them at runtime.

## What this sample demonstrates

- Connecting to a Foundry toolbox's MCP endpoint via Streamable HTTP transport
- Injecting a fresh Azure AI bearer token (`https://ai.azure.com/.default`) on every MCP request
- Using `AgentSkillsProviderBuilder.UseMcpSkills(client)` to discover skills from the toolbox
- Injecting the discovered skills into `AIProjectClient.AsAIAgent(...)` via `AIContextProviders`

## Prerequisites

- A Microsoft Foundry project with a toolbox already configured
- The toolbox MCP endpoint must expose `skill://index.json` with `skill-md` entries (SEP-2640). If the resource is absent, the sample runs but the skills provider will be empty.
- An authenticated Azure identity (for example, sign in with `az login`)

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
$env:FOUNDRY_TOOLBOX_MCP_SERVER_URL="https://your-foundry-service.services.ai.azure.com/api/projects/your-project/toolboxes/your-toolbox/mcp?api-version=v1"
```

## Run the sample

```powershell
dotnet run
```

