# File-Based Agent Skills Sample

This sample demonstrates how to use **file-based Agent Skills** with a `ChatClientAgent`.

## What it demonstrates

- Discovering skills from `SKILL.md` files on disk via `AgentFileSkillsSource`
- The progressive disclosure pattern: advertise → load → read resources → run scripts
- Using the `AgentSkillsProvider` constructor with a skill directory path and script runner
- Running file-based scripts (Python) via a subprocess-based executor
- Opting a skill out of the system prompt listing with `advertise: false` in its frontmatter

## Skills Included

### unit-converter

Converts between common units (miles↔km, pounds↔kg) using a multiplication factor.

- `references/conversion-table.md` — Conversion factor table
- `scripts/convert.py` — Python script that performs the conversion

### temperature-converter

Converts between Celsius and Fahrenheit. Its frontmatter sets `advertise: false`, so its name and
description are **not** auto-listed in the system prompt:

```yaml
---
name: temperature-converter
description: Convert between Celsius and Fahrenheit temperatures.
advertise: false
---
```

The skill can still be loaded by name via the `load_skill` tool — in this sample the agent's
instructions reference it explicitly. Use this to keep the system prompt small, or for skills that
should only be used when the developer (or another skill) points the model at them. Omitting
`advertise` defaults to `true`.

## Running the Sample

### Prerequisites

- .NET 10.0 SDK
- Azure OpenAI endpoint with a deployed model
- Python 3 installed and available as `python3` on your PATH

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
Converting units with file-based skills
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **75 kg → 165.35 lbs**

Converting temperatures with an unadvertised skill
------------------------------------------------------------
Agent: 100°F is approximately **37.78°C**.
```
