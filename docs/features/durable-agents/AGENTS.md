# AGENTS.md

Instructions for AI coding agents working on durable agents documentation.

## Scope

This directory contains feature documentation for the durable agents integration. The source code and samples live elsewhere:

- .NET implementation: `dotnet/src/Microsoft.Agents.AI.DurableTask/` and `dotnet/src/Microsoft.Agents.AI.Hosting.AzureFunctions/`
- Python implementation: `python/packages/durabletask/` and `python/packages/azurefunctions/` (package `agent-framework-azurefunctions`)
- .NET samples: `dotnet/samples/04-hosting/DurableAgents/`
- Python samples: `python/samples/04-hosting/durabletask/`
- Official docs (Microsoft Learn): <https://learn.microsoft.com/agent-framework/integrations/azure-functions>

## Document structure

| File | Purpose |
| --- | --- |
| `README.md` | Main technical overview: architecture, hosting models, orchestration patterns, and links to samples. |
| `durable-agents-ttl.md` | Deep-dive on session Time-To-Live (TTL) configuration and behavior. |

Add new sibling documents when a topic is too detailed for the README (e.g., a new feature like reliable streaming or MCP tool exposure). Keep the README focused on orientation and link out to siblings for depth.

## Writing guidelines

- **Audience**: Developers already familiar with the Microsoft Agent Framework who want to understand what durability adds and how to use it.
- **Host-agnostic first**: Durable agents work in console apps, Azure Functions, and any Durable Task–compatible host. Show host-agnostic patterns (plain orchestration functions, `IServiceCollection` registration) before Azure Functions–specific patterns. Avoid giving the impression that Azure Functions is the only hosting option.
- **Both languages**: Always include C# and Python examples side by side. Keep them equivalent in functionality.
- **Callout syntax**: Use GitHub-flavored callouts (`> [!NOTE]`, `> [!IMPORTANT]`, `> [!WARNING]`) rather than bold-text callouts (`> **Note:** ...`).
- **Line length**: Do not wrap long lines. Rely on text viewers / renderers for line wrapping.
- **Tables**: Use spaces around pipes in separator rows (`| --- |` not `|---|`).
- **Code snippets**: Keep them minimal and self-contained. Omit boilerplate (using statements, environment variable reads) unless the snippet is specifically about setup.
- **Cross-references**: Link to Microsoft Learn for conceptual background (Durable Entities, Durable Task Scheduler, Azure Functions). Link to sibling docs within this directory for feature deep-dives.

## Linting

Run markdownlint on all documents before committing, with line-length checks disabled:

```bash
markdownlint docs/features/durable-agents/ --disable MD013
```

## When to update these docs

- A new durable agent feature is added (e.g., a new orchestration pattern, hosting model, or configuration option).
- The public API surface changes in a way that affects how developers use durable agents.
- New sample directories are added — update the sample links in README.md.
- The official Microsoft Learn documentation is restructured — update external links.
