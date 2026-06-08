# MCP-Based Agent Skills Sample

This sample demonstrates how to discover **Agent Skills served over MCP** with an `Agent`.

## What it demonstrates

- Connecting to a remote MCP server (over streamable HTTP) that exposes skill
  resources following the SEP-2640 convention.
- Building a `SkillsProvider` from an `MCPSkillsSource`, which reads
  `skill://index.json` (SEP-2640 canonical discovery) and constructs skills from
  the index entries.
- The progressive disclosure pattern across MCP: advertise → load → read
  resources, exactly as for filesystem-backed skills.

## Running the Sample

### Prerequisites

- Python 3.10+
- An [Azure AI Foundry](https://ai.azure.com/) project with a deployed model
- Azure CLI authentication (`az login`)
- A running MCP server that hosts SEP-2640 skill resources (see "Providing
  an MCP server" below)

### Setup

Set the following environment variables (in a `.env` file or your shell):

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-endpoint.services.ai.azure.com/api/projects/your-project"
$env:FOUNDRY_MODEL="gpt-4o-mini"
$env:MCP_SKILLS_SERVER_URL="https://your-mcp-server.example.com/mcp"
```

### Run

```powershell
python mcp_based_skill.py
```

## Providing an MCP server

This sample is a **consumer**: it does not host an MCP server itself. To try
it end-to-end you need an MCP server that exposes the SEP-2640 skill
resources (`skill://index.json` plus per-skill `SKILL.md`).

- See [`samples/02-agents/mcp/agent_as_mcp_server.py`](../../mcp/agent_as_mcp_server.py)
  for an example of hosting an MCP server via the Agent Framework.
- The Model Context Protocol working group maintains reference MCP-skills
  servers at
  [`modelcontextprotocol/experimental-ext-skills`](https://github.com/modelcontextprotocol/experimental-ext-skills).
