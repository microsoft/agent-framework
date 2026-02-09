# Samples Structure & Design Choices — Python

> This file documents the structure and conventions of the Python samples so that
> agents (AI or human) can maintain them without rediscovering decisions.

## Directory layout

```
python/samples/
├── 01-get-started/          # Progressive tutorial (steps 01–06)
├── 02-agents/               # Deep-dive concept samples
│   ├── tools/               # One file per tool type
│   ├── middleware/           # One file per middleware concept
│   ├── conversations/       # Thread, storage, suspend/resume
│   └── providers/           # One file per provider
├── 03-workflows/            # One sub-folder per workflow pattern
│   └── declarative/         # Includes workflow.yaml
├── 04-hosting/              # Multi-file projects where needed
│   ├── a2a/                 # Single-file (agent_with_a2a.py)
│   ├── azure-functions/     # Multi-file sub-projects (01_, 02_, 03_)
│   └── durable-tasks/       # Multi-file sub-projects (01_, 02_)
├── 05-end-to-end/           # Complete applications & evaluation
│   ├── evaluation/          # red_teaming, self_reflection
│   ├── hosted-agents/
│   ├── m365-agent/
│   └── workflow-evaluation/
├── autogen-migration/       # Migration guides (do not restructure)
├── semantic-kernel-migration/
├── _assets/                 # Shared data files for samples
└── _to_delete/              # Deprecated samples awaiting review
```

## Design principles

1. **Progressive complexity**: Sections 01→05 build from "hello world" to
   production deployment. Within 01-get-started, files are numbered 01–06 and
   each step adds exactly one concept.

2. **One concept per file**: Each `.py` in 02-agents/ demonstrates a single
   topic (e.g. `function_tools.py`, `chat_middleware.py`). Don't combine
   multiple unrelated concepts.

3. **Single-file by default**: Sections 01–03 are single `.py` files runnable
   with `python <file>.py`. Only 04-hosting and 05-end-to-end use multi-file
   projects (folders with their own README).

4. **Flat tools/middleware/providers**: Each sub-folder under 02-agents/ is flat
   (no nesting). File names match the concept they demonstrate.

## Default provider

All canonical samples use **OpenAI Responses** via `OpenAIResponsesClient`:

```python
from agent_framework.openai import OpenAIResponsesClient

client = OpenAIResponsesClient(
    api_key=os.environ.get("OPENAI_API_KEY"),
    model_id=os.environ.get("OPENAI_RESPONSES_MODEL_ID", "gpt-4o"),
)
agent = client.as_agent(name="...", instructions="...")
```

Environment variables should always be **explicit** (pass `api_key=`, `model_id=`),
not implicit. Provider-specific samples (02-agents/providers/) show other providers.

## Snippet tags for docs integration

Every sample embeds named snippet regions that the docs repo references via
`:::code` directives. Tags use XML-style comments:

```python
# <snippet_name>
code here
# </snippet_name>
```

Common tag names and their meaning:

| Tag | Used in | Purpose |
|-----|---------|---------|
| `create_agent` | 01-get-started/01_hello_agent.py | Agent instantiation |
| `run_agent` | 01-get-started/01_hello_agent.py | Non-streaming run |
| `run_agent_streaming` | 01-get-started/01_hello_agent.py | Streaming run |
| `define_tool` | 01-get-started/02_add_tools.py | Tool definition |
| `create_agent_with_tools` | 01-get-started/02_add_tools.py | Agent + tools |
| `multi_turn` | 01-get-started/03_multi_turn.py | Thread-based conversation |

When adding a new sample or modifying an existing one:
- **Keep existing snippet tags** — the docs repo depends on them
- Use `snake_case` for tag names
- If you add new tags, update the corresponding docs `.md` file to reference them

## Docs integration

The docs repo at `semantic-kernel-pr/agent-framework/` references samples via:

```markdown
:::code language="python" source="~/agent-framework/python/samples/01-get-started/01_hello_agent.py" id="create_agent" highlight="1-4":::
```

- `source=` paths use `~/agent-framework/` as the docset root
- `id=` matches a `# <name>` / `# </name>` region in the sample
- `highlight=` line numbers are **relative to the displayed snippet** (not the file)
- `id=` and `range=` cannot coexist in the same directive

**If you rename or move a sample file**, you must also update the corresponding
docs page. See the mapping below.

## File → docs page mapping

| Sample path | Docs page |
|-------------|-----------|
| `01-get-started/01_hello_agent.py` | `get-started/your-first-agent.md` |
| `01-get-started/02_add_tools.py` | `get-started/add-tools.md` |
| `01-get-started/03_multi_turn.py` | `get-started/multi-turn.md` |
| `01-get-started/04_memory.py` | `get-started/memory.md` |
| `01-get-started/05_first_workflow.py` | `get-started/workflows.md` |
| `01-get-started/06_host_your_agent.py` | `get-started/hosting.md` |
| `02-agents/tools/*.py` | `agents/tools/<matching-name>.md` |
| `02-agents/middleware/*.py` | `agents/middleware/<matching-name>.md` |
| `02-agents/providers/*.py` | `agents/providers/<matching-name>.md` |
| `02-agents/conversations/*.py` | `agents/conversations/<matching-name>.md` |
| `03-workflows/<pattern>/*.py` | `workflows/<matching-name>.md` |
| `04-hosting/*` | `integrations/<matching-name>.md` |

## Naming conventions

- **Python files**: `snake_case.py` (e.g. `function_tools.py`, `01_hello_agent.py`)
- **Folders**: `kebab-case` (e.g. `human-in-the-loop`, `azure-functions`)
- **Getting started numbering**: `01_` through `06_` prefix
- **README.md**: Required in every section folder and every multi-file project

## Package install

```bash
pip install agent-framework --pre
```

The `--pre` flag is needed during preview. `openai` is a core dependency — no
extras bracket needed.

## When adding a new sample

1. Put it in the correct section folder based on complexity
2. Add snippet tags for any code that should appear in docs
3. Follow the single-file pattern unless hosting/deployment requires multiple files
4. Use explicit env vars, not implicit detection
5. Add a corresponding docs page (or update the existing one) with `:::code` refs
6. Update this file's mapping table if adding a new file
