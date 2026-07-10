# Samples Structure & Design Choices — Python

> This file documents the structure and conventions of the Python samples so that
> agents (AI or human) can maintain them without rediscovering decisions.

## Directory layout

```
python/samples/
├── 01-get-started/          # Progressive tutorial (steps 01–06)
├── 02-agents/               # Deep-dive concept samples
│   ├── tools/               # Tool patterns (function, approval, schema, etc.)
│   ├── middleware/           # One file per middleware concept
│   ├── conversations/       # Thread, storage, suspend/resume
│   ├── providers/           # One sub-folder per provider (azure_ai/, openai/, etc.)
│   ├── context_providers/   # Memory & context injection
│   ├── orchestrations/      # Multi-agent orchestration patterns
│   ├── observability/       # Tracing, telemetry
│   ├── declarative/         # Declarative agent definitions
│   ├── chat_client/         # Raw chat client usage
│   ├── mcp/                 # MCP server/client patterns
│   ├── multimodal_input/    # Image, audio inputs
│   └── devui/               # DevUI agent/workflow samples
├── 03-workflows/            # Workflow samples (preserved from upstream)
│   ├── _start-here/         # Introductory workflow samples
│   ├── agents/              # Agents in workflows
│   ├── checkpoint/          # Checkpointing & resume
│   ├── composition/         # Sub-workflows
│   ├── control-flow/        # Edges, conditions, loops
│   ├── declarative/         # YAML-based workflows
│   ├── human-in-the-loop/   # HITL patterns
│   ├── observability/       # Workflow telemetry
│   ├── parallelism/         # Fan-out, map-reduce
│   ├── state-management/    # State isolation, kwargs
│   ├── tool-approval/       # Tool approval in workflows
│   └── visualization/       # Workflow visualization
├── 04-hosting/              # Deployment & hosting
│   ├── a2a/                 # Agent-to-Agent protocol
│   ├── azure-functions/     # Azure Functions samples
│   └── durabletask/         # Durable task framework
├── 05-end-to-end/           # Complete applications
│   ├── chatkit-integration/
│   ├── evaluation/
│   ├── hosted_agents/
│   ├── m365-agent/
│   ├── purview_agent/
│   └── workflow_evaluation/
├── autogen-migration/       # Migration guides (do not restructure)
├── semantic-kernel-migration/
└── _to_delete/              # Old samples awaiting review
```

## Design principles

1. **Progressive complexity**: Sections 01→05 build from "hello world" to
   production. Within 01-get-started, files are numbered 01–06 and each step
   adds exactly one concept.

2. **One concept per file** in 01-get-started and flat files in 02-agents/.

3. **Workflows preserved**: 03-workflows/ keeps the upstream folder names
   and file names intact. Do not rename or restructure workflow samples.

4. **Single-file for 01-03**: Only 04-hosting and 05-end-to-end use multi-file
   projects with their own README.

## Default provider

All canonical samples (01-get-started) use **Azure AI Foundry project-backed chat** via `FoundryChatClient`
with an Azure AI Foundry project endpoint:

```python
import os
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

credential = AzureCliCredential()
client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["FOUNDRY_MODEL"],
    credential=credential,
)
agent = Agent(client=client, name="...", instructions="...")
```

Environment variables:
- `FOUNDRY_PROJECT_ENDPOINT` — Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL` — Model deployment name (e.g. gpt-4o)

For authentication, run `az login` before running samples.

## Snippet tags for docs integration

Samples embed named snippet regions for future `:::code` integration:

```python
# <snippet_name>
code here
# </snippet_name>
```

## Package install

```bash
pip install agent-framework
```

`agent-framework` is released, so `--pre` is not required here. `openai` is a core dependency.

## File structure

Every sample file follows this order:

1. PEP 723 inline script metadata (if external dependencies are needed)
2. Copyright header: `# Copyright (c) Microsoft. All rights reserved.`
3. Required imports
4. Module docstring explaining the purpose and key components
5. Helper functions
6. Main function(s) demonstrating functionality
7. Entry point: `if __name__ == "__main__": asyncio.run(main())`

Use PEP 723 inline script metadata for external sample-only dependencies; do not add sample-only dependencies to
the root `pyproject.toml` dev group.
PEP 723 dependencies must list the minimal specific Agent Framework distributions used by the script (for example,
`agent-framework-core`, `agent-framework-foundry`, or `agent-framework-openai`), never the `agent-framework`
meta-package.

## Syntax checking

Run sample checks from the `python/` directory:

```bash
uv run poe syntax -S
uv run poe pyright -S
```

## Documentation

Samples should be over-documented:

1. Include a README.md in each set of samples.
2. Mark code sections with numbered comments.
3. Include expected output at the end of the file.

## Current API notes

- `Agent` class renamed from `ChatAgent` (use `from agent_framework import Agent`)
- `Message` class renamed from `ChatMessage` (use `from agent_framework import Message`)
- `call_next` in middleware takes NO arguments: `await call_next()` (not `await call_next(context)`)
- Do not use `client.as_agent(...)` in samples; construct agents explicitly with `Agent(client=client, ...)`.
- Tool methods on hosted tools are now functions, not classes (e.g. `hosted_mcp_tool(...)` not `HostedMCPTool(...)`)
- When only using a description for the field of a `@tool` parameter, do not use `Field`; use the string directly.
