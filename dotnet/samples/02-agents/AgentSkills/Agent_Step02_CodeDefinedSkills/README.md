# Code-Defined Agent Skills Sample

This sample demonstrates how to define **Agent Skills entirely in code** using `AgentInlineSkill`.

## What it demonstrates

- Creating skills programmatically with `AgentInlineSkill` — no SKILL.md files needed
- **Static resources** via `AddResource` with inline content
- **Dynamic resources** via `AddResource` with a factory delegate (computed at runtime)
- **Code scripts** via `AddScript` with a delegate handler
- Using the `AgentSkillsProvider` constructor with inline skills

## Skills Included

### unit-converter (code-defined)

Converts between common units using multiplication factors. Defined entirely in C# code:

- `conversion-table` — Static resource with factor table
- `conversion-policy` — Dynamic resource with formatting rules (generated at runtime)
- `convert` — Script that performs `value × factor` conversion

## Running the Sample

### Prerequisites

- .NET 10.0 SDK
- A Microsoft Foundry project with a deployed model

### Setup

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
export FOUNDRY_MODEL="gpt-5.4-mini"
```

### Run

```bash
dotnet run
```

### Expected Output

```
Converting units with code-defined skills
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **75 kg → 165.35 lbs**
```
