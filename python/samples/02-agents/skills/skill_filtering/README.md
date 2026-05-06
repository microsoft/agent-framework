# Skill Filtering — FilteringSkillsSource

This sample demonstrates how to use `FilteringSkillsSource` to control
which file-based skills an agent sees by applying a predicate.

## Concepts

| Concept | Description |
|---------|-------------|
| **`FileSkillsSource`** | Discovers skills from `SKILL.md` files on disk |
| **`FilteringSkillsSource`** | Wraps a source and applies a predicate to include or exclude skills |
| **`DeduplicatingSkillsSource`** | Removes duplicate skill names (first-one-wins) |

## Skills in This Sample

### volume-converter (kept)

Converts between gallons and liters via `scripts/convert.py`.

### length-converter (filtered out)

Converts between miles ↔ km, feet ↔ meters. Excluded by the filter predicate
so the agent never sees it.

## How It Works

```
┌──────────────────────────────────────────────────────────┐
│  FileSkillsSource("./skills")                            │
│    discovers: volume-converter, length-converter         │
└─────────────┬────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────┐
│  FilteringSkillsSource(predicate=...)                     │
│    keeps: volume-converter                               │
│    drops: length-converter                               │
└─────────────┬────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────┐
│  DeduplicatingSkillsSource → SkillsProvider              │
└──────────────────────────────────────────────────────────┘
```

> **Note:** `FilteringSkillsSource` works with any source — file-based,
> in-memory, custom, or a mix. If you only need a single skill, point
> `FileSkillsSource` directly at that skill's directory instead of filtering.

## Prerequisites

Set environment variables (or create a `.env` file):

```
FOUNDRY_PROJECT_ENDPOINT=https://your-project.openai.azure.com/
FOUNDRY_MODEL=gpt-4o-mini
```

Authenticate with Azure CLI:

```bash
az login
```

## Running the Sample

```bash
cd python
uv run samples/02-agents/skills/skill_filtering/skill_filtering.py
```

## Directory Structure

```
skill_filtering/
├── skill_filtering.py
├── README.md
└── skills/
    ├── volume-converter/
    │   ├── SKILL.md
    │   └── scripts/
    │       └── convert.py
    └── length-converter/
        ├── SKILL.md
        └── scripts/
            └── convert.py
```

## Learn More

- [File-Based Skills Sample](../file_based_skill/)
- [Mixed Skills Sample](../mixed_skills/)
- [Code-Defined Skills Sample](../code_defined_skill/)
- [Agent Skills Specification](https://agentskills.io/)
