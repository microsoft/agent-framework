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

All canonical samples (01-get-started) use **OpenAI Responses** via `OpenAIResponsesClient`:

```python
import os
from agent_framework.openai import OpenAIResponsesClient

client = OpenAIResponsesClient(
    api_key=os.environ["OPENAI_API_KEY"],
    model_id=os.environ.get("OPENAI_RESPONSES_MODEL_ID", "gpt-4o"),
)
agent = client.as_agent(name="...", instructions="...")
```

Environment variables should always be **explicit** (pass `api_key=`, `model_id=`).

## Snippet tags for docs integration

Samples embed named snippet regions for future `:::code` integration:

```python
# <snippet_name>
code here
# </snippet_name>
```

## Package install

```bash
pip install agent-framework --pre
```

The `--pre` flag is needed during preview. `openai` is a core dependency.

## Current API notes

- `Agent` class renamed from `ChatAgent` (use `from agent_framework import Agent`)
- `Message` class renamed from `ChatMessage` (use `from agent_framework import Message`)
- `call_next` in middleware takes NO arguments: `await call_next()` (not `await call_next(context)`)
- Prefer `client.as_agent(...)` over `Agent(client=client, ...)`
- Tool methods on hosted tools are now functions, not classes (e.g. `hosted_mcp_tool(...)` not `HostedMCPTool(...)`)
