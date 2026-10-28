# Class-Based Agent Skills

This sample demonstrates how to define **Agent Skills as Python classes** using `ClassSkill`.

## What's Demonstrated

- Creating skills as classes that extend `ClassSkill`
- Bundling name, description, instructions, resources, and scripts into a single class
- Using `@ClassSkill.resource` decorator for automatic resource discovery
- Using `@ClassSkill.script` decorator for automatic script discovery
- Injecting `FunctionInvocationContext` into a script method to read host-controlled rounding precision
- Lazy-loading and caching of resources and scripts
- Registering class-based skills with `SkillsProvider`

## Skills Included

### unit-converter (class-based)

A `UnitConverterSkill` class that converts between common units. Defined in `class_based_skill.py`:

- `conversion-table` — Static resource with factor table
- `convert` — Script that performs `value × factor` conversion

## Runtime Context

`main()` supplies `function_invocation_kwargs={"precision": 4}` to `agent.run()`.
The `convert_units` method declares `*, ctx: FunctionInvocationContext` and
reads `ctx.kwargs["precision"]`, while `value` and `factor` come from the model.
The context parameter is hidden from the script schema and cannot be supplied
through script arguments. Missing host precision raises an error.

Context injection works for `@ClassSkill.script` methods just as it does for
`@skill.script` callbacks. `SkillsProvider` supplies the context automatically
during agent execution. See the
[recommended script pattern](../README.md#host-runtime-context).

## Project Structure

```
class_based_skill/
├── class_based_skill.py
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
uv run samples/02-agents/skills/class_based_skill/class_based_skill.py
```

### Expected Output

```
Converting units with class-based skills
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **75 kg → 165.35 lbs**
```

## Learn More

- [Agent Skills Specification](https://agentskills.io/)
- [Code-Defined Skills Sample](../code_defined_skill/)
- [Mixed Skills Sample](../mixed_skills/)
- [Microsoft Agent Framework Documentation](../../../../../docs/)
