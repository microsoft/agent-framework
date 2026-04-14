# Class-Based Agent Skills Sample

This sample demonstrates how to define **Agent Skills as C# classes** using `AgentClassSkill`
with **attributes** for automatic script and resource discovery.

## What it demonstrates

- Creating skills as classes that extend `AgentClassSkill`
- Using `[AgentSkillResource]` on properties to define resources
- Using `[AgentSkillScript]` on methods to define scripts
- Automatic discovery (no need to override `Resources`/`Scripts`)
- Using the `AgentSkillsProvider` constructor with class-based skills
- Overriding `SerializerOptions` for Native AOT compatibility

## Skills Included

### unit-converter (class-based)

A `UnitConverterSkill` class that converts between common units. Defined in `Program.cs`:

- `conversion-table` — Static resource with factor table
- `convert` — Script that performs `value × factor` conversion

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
Converting units with class-based skills
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **75 kg → 165.35 lbs**
```
