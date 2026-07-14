# MCP-Based Agent Skills Sample

This sample demonstrates how to discover **Agent Skills served over MCP** with an `Agent`.

## What it demonstrates

- Connecting to a remote MCP server (over streamable HTTP) that exposes skill
  resources following the SEP-2640 convention.
- Building a `SkillsProvider` from an `MCPSkillsSource`, which reads
  `skill://index.json` (SEP-2640 canonical discovery) and constructs skills from
  the index entries.
- Both discovery entry types: `skill-md` (the `SKILL.md` body and sibling
  resources are fetched on demand from the server) and `archive` (a single ZIP /
  TAR / gzip-TAR resource that is downloaded and safely unpacked to a local
  directory, then served like a file-based skill). Archive extraction is hardened
  against path-traversal, link-based escapes, and decompression bombs, and
  scripts bundled in an archive are never exposed as runnable — MCP-delivered
  scripts are always treated as read-only content.
- The progressive disclosure pattern across MCP: advertise → load → read
  resources, exactly as for filesystem-backed skills.

## Running the Sample

### Prerequisites

- Python 3.10+
- A [Microsoft Foundry](https://ai.azure.com/) project with a deployed model
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
resources (`skill://index.json` plus per-skill `SKILL.md` for `skill-md`
entries and/or a downloadable archive resource for `archive` entries).

- See [`samples/02-agents/mcp/agent_as_mcp_server.py`](../../mcp/agent_as_mcp_server.py)
  for an example of hosting an MCP server via the Agent Framework.
- The Model Context Protocol working group maintains reference MCP-skills
  servers at
  [`modelcontextprotocol/experimental-ext-skills`](https://github.com/modelcontextprotocol/experimental-ext-skills).

## Security Considerations

Discovering skills over MCP means an *external* MCP server controls what skill content
(including instructions and, for script-capable skills, the scripts the agent may run)
reaches the agent. A compromised or untrustworthy server could return adversarial content
designed to manipulate the agent (indirect prompt injection) or to exfiltrate data through
skill instructions/scripts. This source is never enabled by default — connecting
`MCPSkillsSource` to a server is an explicit opt-in. Only connect to MCP servers you have
vetted and trust, and treat their responses as untrusted input.
