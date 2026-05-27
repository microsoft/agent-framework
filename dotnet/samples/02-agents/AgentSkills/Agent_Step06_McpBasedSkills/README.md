# MCP-Based Agent Skills Sample

This sample demonstrates how to discover **Agent Skills served over MCP** with a `ChatClientAgent`.

## What it demonstrates

- Connecting an `McpClient` to an external MCP server via Streamable HTTP transport.
- Building an `AgentSkillsProvider` via `UseMcpSkills(client)`, which reads
  `skill://index.json` (SEP-2640 canonical discovery) and constructs skills from the
  index entries.
- The progressive disclosure pattern across MCP: advertise → load → read resources, exactly
  as for filesystem-backed skills.

## Running the Sample

### Prerequisites

- .NET 10.0 SDK
- Azure OpenAI endpoint with a deployed model
- An MCP server that exposes Agent Skills resources following the
  [SEP-2640](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2640) convention

### Setup

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"
$env:MCP_SKILLS_ENDPOINT="https://your-mcp-server/mcp"
```

### Run

```powershell
dotnet run
```
