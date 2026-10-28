# Code-Defined Agent Skills

This sample demonstrates how to create **Agent Skills** in Python code, without needing `SKILL.md` files on disk. A unit-converter skill shows three approaches:

## What's Demonstrated

1. **Static Resources** — Pass inline content via the `resources` parameter when constructing a `Skill`
2. **Dynamic Resources** — Attach callable functions via the `@skill.resource` decorator that return content computed at runtime
3. **Dynamic Scripts** — Attach callable scripts via the `@skill.script` decorator, with an injected `FunctionInvocationContext` for host-controlled rounding precision

All three can be combined with file-based skills in a single `SkillsProvider`.

## Runtime Context vs Model Arguments

`main()` passes `function_invocation_kwargs={"precision": 2}` to `agent.run()`.
The `convert` script declares `*, ctx: FunctionInvocationContext` and reads
`ctx.kwargs["precision"]`. The model supplies only `value` and `factor`; `ctx`
is hidden from the script schema and cannot be supplied through script arguments.
Missing host precision raises an error rather than silently using a default.

The dynamic resource receives host values through `**kwargs`; script callbacks
use the separate `ctx.kwargs` mapping. `SkillsProvider` supplies the context
automatically during agent execution. See the
[recommended script pattern](../README.md#host-runtime-context).

## Project Structure

```
code_defined_skill/
├── code_defined_skill.py
└── README.md
```

## Running the Sample

### Prerequisites
- A [Microsoft Foundry](https://ai.azure.com/) project with a deployed model (e.g. `gpt-4o-mini`)

### Environment Variables

Set the required environment variables in a `.env` file (see `python/.env.example`):

- `FOUNDRY_PROJECT_ENDPOINT`: Your Microsoft Foundry project endpoint
- `FOUNDRY_MODEL`: The name of your model deployment (defaults to `gpt-4o-mini`)

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
