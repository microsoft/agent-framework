# Foundry Toolbox MCP Skills

This sample uses
`AgentSkillsProviderBuilder` to discover MCP-based skills from a Foundry Toolbox endpoint
and inject them as `AIContextProviders` so the agent can discover and use them at runtime.

## What this sample demonstrates

- Connecting to a Foundry toolbox's MCP endpoint via Streamable HTTP transport
- Injecting a fresh Azure AI bearer token (`https://ai.azure.com/.default`) on every MCP request
- Using `AgentSkillsProviderBuilder.UseMcpSkills(client)` to discover skills from the toolbox through `skills/list`
- Injecting the discovered skills into `AIProjectClient.AsAIAgent(...)` via `AIContextProviders`
- Auto-approving skill tools with `UseToolApproval` and `AgentSkillsProvider.AllToolsAutoApprovalRule`

Auto-approval is used for demonstration simplicity. In production, prompt the user before
allowing script execution. See [Skills Auto Approval](../../../AgentSkills/Agent_Step07_SkillsAutoApproval)
for a walkthrough of the full approval flow.

## Prerequisites

- A Microsoft Foundry project with a toolbox already configured
- The toolbox MCP endpoint must declare the `io.modelcontextprotocol/skills` extension and implement `skills/list` and resource reads for the advertised skills. If the extension is not declared, the skills provider will be empty.
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
