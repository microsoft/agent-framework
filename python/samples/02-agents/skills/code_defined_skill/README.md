# Code-Defined Agent Skills

This sample demonstrates how to create **Agent Skills** in Python code, without needing `SKILL.md` files on disk. A unit-converter skill shows three approaches:

## What's Demonstrated

1. **Static Resources** — Pass inline content via the `resources` parameter when constructing a `Skill`
2. **Dynamic Resources** — Attach callable functions via the `@skill.resource` decorator that return content computed at runtime
3. **Dynamic Scripts** — Attach callable scripts via the `@skill.script` decorator (unit conversion via a single factor parameter)

All three can be combined with file-based skills in a single `SkillsProvider`.

## Project Structure

```
code_defined_skill/
├── code_defined_skill.py
└── README.md
```

## Running the Sample

### Prerequisites
- An [Azure AI Foundry](https://ai.azure.com/) project with a deployed model (e.g. `gpt-4o-mini`)

### Environment Variables

Set the required environment variables in a `.env` file (see `python/.env.example`):

- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `AZURE_OPENAI_MODEL`: The name of your model deployment (defaults to `gpt-4o-mini`)

### Authentication

This sample uses `AzureCliCredential` for authentication. Run `az login` in your terminal before running the sample.

### Run

```bash
cd python
uv run samples/02-agents/skills/code_defined_skill/code_defined_skill.py
```

## Learn More

- [Agent Skills Specification](https://agentskills.io/)
- [File-Based Skills Sample](../file_based_skill/)
- [Mixed Skills Sample](../mixed_skills/)
- [Microsoft Agent Framework Documentation](../../../../../docs/)
