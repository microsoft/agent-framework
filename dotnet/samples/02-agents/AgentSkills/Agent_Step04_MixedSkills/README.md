# Mixed Agent Skills Sample (Advanced)

This sample demonstrates an **advanced scenario**: combining multiple skill types in a single agent using `AgentSkillsProviderBuilder`.

> **Tip:** For simpler, single-source scenarios, use the `AgentSkillsProvider` constructors directly — see [Step01](../Agent_Step01_FileBasedSkills/) (file-based), [Step02](../Agent_Step02_CodeDefinedSkills/) (code-defined), or [Step03](../Agent_Step03_ClassBasedSkills/) (class-based).

## What it demonstrates

- Combining file-based, code-defined, and class-based skills in one provider
- Using `UseFileSkill` and `UseSkill` on the builder to register different skill types
- Aggregating skills from all sources into a single provider with automatic deduplication

## When to use `AgentSkillsProviderBuilder`

The builder is intended for advanced scenarios where the simple `AgentSkillsProvider` constructors are insufficient:

| Scenario | Builder method |
|----------|---------------|
| **Mixed skill types** — combine file-based, code-defined, and class-based skills | `UseFileSkill` + `UseSkill` / `UseSkills` |
| **Multiple file script runners** — use different script runners for different file skill directories | `UseFileSkill` / `UseFileSkills` with per-source `scriptRunner` |
| **Skill filtering** — include/exclude skills using a predicate | `UseFilter(predicate)` |

## Skills Included

### unit-converter (file-based)

Discovered from `skills/unit-converter/SKILL.md` on disk. Converts miles↔km, pounds↔kg.

### volume-converter (code-defined)

Defined as `AgentInlineSkill` in `Program.cs`. Converts gallons↔liters.

### temperature-converter (class-based)

Defined as `TemperatureConverterSkill` class in `Program.cs`. Converts °F↔°C↔K.

## Running the Sample

### Prerequisites

- .NET 10.0 SDK
- Azure OpenAI endpoint with a deployed model

### Setup

```bash
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"
```

### Run

```bash
dotnet run
```

### Expected Output

```
Converting with mixed skills (file + code + class)
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **5 gallons → 18.93 liters**
3. **98.6°F → 37.0°C**
```
