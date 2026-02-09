# Samples Structure & Design Choices — .NET

> This file documents the structure and conventions of the .NET samples so that
> agents (AI or human) can maintain them without rediscovering decisions.

## Directory layout

```
dotnet/samples/
├── 01-get-started/          # Progressive tutorial (steps 01–06)
├── 02-agents/               # Deep-dive concept samples
│   ├── tools/               # One file per tool type
│   ├── middleware/           # One file per middleware concept
│   ├── conversations/       # Storage, persistence
│   └── providers/           # One file per provider
├── 03-workflows/            # One sub-folder per workflow pattern
├── 04-hosting/              # Multi-project solutions
│   ├── a2a/                 # Client + Server projects
│   ├── ag-ui/               # Client + Server projects
│   ├── azure-functions/     # Function projects + console apps
│   └── openai-endpoints/    # Hosted agent projects
├── 05-end-to-end/           # Complete applications
│   ├── agent-web-chat/      # .NET Aspire solution
│   ├── agui-web-chat/       # AG-UI full-stack demo
│   ├── m365-agent/          # Teams/M365 integration
│   └── purview/             # Governance integration
├── _to_delete/              # Deprecated samples awaiting review
└── Directory.Build.props    # Shared MSBuild properties
```

## Design principles

1. **Progressive complexity**: Sections 01→05 build from "hello world" to
   production deployment. Within 01-get-started, files are numbered 01–06 and
   each step adds exactly one concept.

2. **One concept per file**: Each `.cs` in 02-agents/ demonstrates a single
   topic (e.g. `FunctionTools.cs`, `ChatClientMiddleware.cs`). Don't combine
   multiple unrelated concepts.

3. **Single-file for 01–03**: Sections 01-get-started, 02-agents, and
   03-workflows use single `.cs` top-level-statement files runnable with
   `dotnet run`. Sections 04 and 05 are multi-project solutions.

4. **Flat tools/middleware/providers**: Each sub-folder under 02-agents/ is flat
   (no nesting). File names match the concept they demonstrate.

## Default provider

All canonical samples use **Azure AI Foundry** via `AIProjectClient`:

```csharp
using Azure.AI.Projects;
using Azure.Identity;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "...",
    model: deploymentName,
    instructions: "...");
```

Environment variables should always be **explicit**. Provider-specific samples
(02-agents/providers/) show other providers.

## Snippet tags for docs integration

Every sample embeds named snippet regions that the docs repo references via
`:::code` directives. Tags use C# XML comment style:

```csharp
// <snippet_name>
code here
// </snippet_name>
```

Common tag names and their meaning:

| Tag | Used in | Purpose |
|-----|---------|---------|
| `create_agent` | 01-get-started/01_HelloAgent.cs | Agent instantiation |
| `run_agent` | 01-get-started/01_HelloAgent.cs | Non-streaming run |
| `run_agent_streaming` | 01-get-started/01_HelloAgent.cs | Streaming run |
| `define_tool` | 01-get-started/02_AddTools.cs | Tool definition |
| `create_agent_with_tools` | 01-get-started/02_AddTools.cs | Agent + tools |
| `multi_turn` | 01-get-started/03_MultiTurn.cs | Thread-based conversation |

When adding a new sample or modifying an existing one:
- **Keep existing snippet tags** — the docs repo depends on them
- Use `snake_case` for tag names (even in C# files)
- If you add new tags, update the corresponding docs `.md` file to reference them

## Docs integration

The docs repo at `semantic-kernel-pr/agent-framework/` references samples via:

```markdown
:::code language="csharp" source="~/agent-framework/dotnet/samples/01-get-started/01_HelloAgent.cs" id="create_agent" highlight="4-6":::
```

- `source=` paths use `~/agent-framework/` as the docset root
- `id=` matches a `// <name>` / `// </name>` region in the sample
- `highlight=` line numbers are **relative to the displayed snippet** (not the file)
- `id=` and `range=` cannot coexist in the same directive
- Docs pages use `zone_pivot_groups: programming-languages` to show C#/Python side by side

**If you rename or move a sample file**, you must also update the corresponding
docs page. See the mapping below.

## File → docs page mapping

| Sample path | Docs page |
|-------------|-----------|
| `01-get-started/01_HelloAgent.cs` | `get-started/your-first-agent.md` |
| `01-get-started/02_AddTools.cs` | `get-started/add-tools.md` |
| `01-get-started/03_MultiTurn.cs` | `get-started/multi-turn.md` |
| `01-get-started/04_Memory.cs` | `get-started/memory.md` |
| `01-get-started/05_FirstWorkflow.cs` | `get-started/workflows.md` |
| `01-get-started/06_HostYourAgent.cs` | `get-started/hosting.md` |
| `02-agents/tools/*.cs` | `agents/tools/<matching-name>.md` |
| `02-agents/middleware/*.cs` | `agents/middleware/<matching-name>.md` |
| `02-agents/providers/*.cs` | `agents/providers/<matching-name>.md` |
| `02-agents/conversations/*.cs` | `agents/conversations/<matching-name>.md` |
| `03-workflows/<pattern>/*.cs` | `workflows/<matching-name>.md` |
| `04-hosting/*` | `integrations/<matching-name>.md` |

## Naming conventions

- **C# files**: `PascalCase.cs` (e.g. `FunctionTools.cs`, `01_HelloAgent.cs`)
- **Folders**: `kebab-case` (e.g. `human-in-the-loop`, `azure-functions`)
- **Getting started numbering**: `01_` through `06_` prefix
- **README.md**: Required in every section folder and every multi-project folder

## NuGet packages

```bash
dotnet add package Microsoft.Agents.AI
```

For Azure AI Foundry provider:
```bash
dotnet add package Azure.AI.Projects
```

## When adding a new sample

1. Put it in the correct section folder based on complexity
2. Add snippet tags for any code that should appear in docs
3. Use single-file top-level statements for 01–03; multi-project for 04–05
4. Use explicit env vars via `Environment.GetEnvironmentVariable()`
5. Add a corresponding docs page (or update the existing one) with `:::code` refs
6. Update this file's mapping table if adding a new file
