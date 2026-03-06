# Code-Defined Agent Skills Sample

This sample demonstrates how to create **Agent Skills** in Python code, without needing `SKILL.md` files on disk.

## What are Code-Defined Skills?

While file-based skills use `SKILL.md` files discovered on disk, code-defined skills let you define skills entirely in Python using `Skill` and `SkillResource` classes. Three patterns are shown:

1. **Basic Code Skill** — Create a `Skill` directly with static resources (inline content)
2. **Dynamic Resources** — Attach callable resources via the `@skill.resource` decorator that generate content at invocation time
3. **Dynamic Resources with kwargs** — Attach a callable resource that accepts `**kwargs` to receive runtime arguments passed via `agent.run()`, useful for injecting request-scoped context (user tokens, session data)

All patterns can be combined with file-based skills in a single `SkillsProvider`.

## Project Structure

```
code_skill/
├── code_skill.py
└── README.md
```

## Running the Sample

### Prerequisites
- An [Azure AI Foundry](https://ai.azure.com/) project with a deployed model (e.g. `gpt-4o-mini`)

### Environment Variables

Set the required environment variables in a `.env` file (see `python/.env.example`):

- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your model deployment (defaults to `gpt-4o-mini`)

### Authentication

This sample uses `AzureCliCredential` for authentication. Run `az login` in your terminal before running the sample.

### Run

```bash
cd python
uv run samples/02-agents/skills/code_skill/code_skill.py
```

### Examples

The sample runs two examples:

1. **Code style question** — Uses Pattern 1 (static resources): the agent loads the `code-style` skill and reads the `style-guide` resource to answer naming convention questions
2. **Project info question** — Uses Patterns 2 & 3 (dynamic resources with kwargs): the agent reads the dynamically generated `team-roster` resource and the `environment` resource which receives `app_version` via runtime kwargs

## Learn More

- [Agent Skills Specification](https://agentskills.io/)
- [File-based Skills Sample](../basic_skill/)
- [Microsoft Agent Framework Documentation](../../../../../docs/)
