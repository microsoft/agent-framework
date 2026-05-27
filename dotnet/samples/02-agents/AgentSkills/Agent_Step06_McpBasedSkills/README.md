# MCP-Based Agent Skills Sample

This sample demonstrates how to discover **Agent Skills served over MCP** with a `ChatClientAgent`.

## What it demonstrates

- Hosting a small MCP server (in this same executable, launched with `--server`) that
  exposes skill resources following the SEP-2640 convention.
- Connecting an `McpClient` to the embedded server via stdio transport.
- Building an `AgentSkillsProvider` via `UseMcpSkills(client)`, which reads
  `skill://index.json` (SEP-2640 canonical discovery) and constructs skills from the
  index entries.
- The progressive disclosure pattern across MCP: advertise → load → read resources, exactly
  as for filesystem-backed skills.

## Running the Sample

### Prerequisites

- .NET 10.0 SDK
- Azure OpenAI endpoint with a deployed model

### Setup

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"
```

### Run

```powershell
dotnet run
```
