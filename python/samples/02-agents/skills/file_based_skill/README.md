# File-Based Agent Skills

This sample demonstrates how to use **file-based Agent Skills** with a `SkillsProvider` in the Microsoft Agent Framework. File-based skills are discovered from `SKILL.md` files on disk and can include reference documents and executable scripts.

## What are Agent Skills?

Agent Skills are modular packages of instructions and resources that enable AI agents to perform specialized tasks. They follow the [Agent Skills specification](https://agentskills.io/) and implement progressive disclosure:

1. **Advertise**: Skills are advertised with name + description (~100 tokens per skill)
2. **Load**: Full instructions are loaded on-demand via `load_skill` tool
3. **Resources**: References and other files loaded via `read_skill_resource` tool
4. **Scripts**: Executable scripts run via `run_skill_script` tool

## Skills Included

### unit-converter
Converts between common units (miles↔km, pounds↔kg) using a multiplication factor following [agentskills.io guidelines](https://agentskills.io/skill-creation/using-scripts).
- `references/CONVERSION_TABLES.md` — Supported conversions and their factors
- `scripts/convert.py` — Executable script with `--value` and `--factor` flags, JSON output, and `--help` support

## Key Components

- **`SkillsProvider`** — Discovers skills from `SKILL.md` files in a directory and registers tools for the agent
- **`subprocess_script_runner`** — A `SkillScriptRunner` callback that runs scripts as local Python subprocesses, enabling the `run_skill_script` tool. Converts argument dicts to CLI flags (e.g. `{"value": 26.2, "factor": 1.60934}` → `--value 26.2 --factor 1.60934`). Shared across samples in [`../subprocess_script_runner.py`](../subprocess_script_runner.py).

## Project Structure

```
file_based_skill/
├── file_based_skill.py
├── README.md
└── skills/
    └── unit-converter/
        ├── SKILL.md
        ├── references/
        │   └── CONVERSION_TABLES.md
        └── scripts/
            └── convert.py
```

## Running the Sample

### Prerequisites
- An [Azure AI Foundry](https://ai.azure.com/) project with a deployed model (e.g. `gpt-4o-mini`)

### Environment Variables

Set the required environment variables in a `.env` file (see `python/.env.example`):

- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `AZURE_OPENAI_DEPLOYMENT_NAME`: The name of your model deployment (defaults to `gpt-4o-mini`)

### Authentication

This sample uses `AzureCliCredential` for authentication. Run `az login` in your terminal before running the sample.

### Run

```bash
cd python
uv run samples/02-agents/skills/file_based_skill/file_based_skill.py
```

## Learn More

- [Agent Skills Specification](https://agentskills.io/)
- [Code-Defined Skills Sample](../code_defined_skill/)
- [Mixed Skills Sample](../mixed_skills/)
- [Microsoft Agent Framework Documentation](../../../../../docs/)
