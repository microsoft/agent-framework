# MCP-Based Agent Skills Sample

This sample demonstrates how to discover **Agent Skills served over MCP** with a `ChatClientAgent`.

## What it demonstrates

- Hosting a small MCP server (in this same executable, launched with `--server`) that
  advertises the `io.modelcontextprotocol/skills` extension and exposes `skills/list`.
- Connecting an `McpClient` to the embedded server via stdio transport.
- Building an `AgentSkillsProvider` via `UseMcpSkills(client)`, which discovers skills
  through `skills/list` and reads their instructions through `resources/read`.
- Returning a complete skill list with frontmatter and the resource URIs of
  `SKILL.md` and `references/conversion-table.md`.
- Serving the conversion-table resource from the file-based skills sample, which the
  skill instructions tell the agent to read before performing a conversion.
- The progressive disclosure pattern across MCP: advertise → load → read resources, exactly
  as for filesystem-backed skills.

## Running the Sample

### Prerequisites

- .NET 10.0 SDK
- Microsoft Foundry project with a deployed model

### Setup

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

Authenticate with `az login`.

### Run

```powershell
dotnet run
```

## Security Considerations

Discovering skills over MCP means an external MCP server controls what skill content (including
instructions and supporting resources) reaches the agent. A compromised or
untrustworthy server could return adversarial content designed to manipulate the agent (indirect
prompt injection) or to exfiltrate data through skill instructions/scripts. Only connect `UseMcpSkills`
to MCP servers you have vetted and trust.
