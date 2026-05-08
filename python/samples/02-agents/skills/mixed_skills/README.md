# Mixed Skills — Code, Class, and File Skills

This sample demonstrates how to combine **code-defined skills**,
**class-based skills**, and **file-based skills** in a single agent using
`SkillsProvider`.

## Concepts

| Concept | Description |
|---------|-------------|
| **Code skill** | A `Skill` created in Python with `@skill.script` decorators for in-process callable functions and `@skill.resource` for dynamic content |
| **Class skill** | A self-contained skill class extending `ClassSkill`, bundling instructions, resources, and scripts |
| **File skill** | A skill discovered from a `SKILL.md` file on disk, with reference documents and executable script files |
| **`script_runner`** | A callable (sync or async) satisfying the `SkillScriptRunner` protocol — required when file skills have scripts |
| **`SkillsProvider`** | Registers code-defined, class-based, and file-based skills in a single provider |

## Skills in This Sample

### volume-converter (code skill)

Defined entirely in Python code using decorators:

- **`@skill.resource`** — `conversion-table`: gallons↔liters conversion factors
- **`@skill.script`** — `convert`: converts a value using a multiplication factor

Code scripts run **in-process** — no subprocess or external runner needed.

### temperature-converter (class skill)

Defined as a `TemperatureConverterSkill` class extending `ClassSkill`:

- **`@ClassSkill.resource`** — `temperature-conversion-formulas`: °F↔°C↔K formulas
- **`@ClassSkill.script`** — `convert-temperature`: converts between temperature scales

Class-based scripts run **in-process** — no subprocess or external runner needed.

### unit-converter (file skill)

Discovered from `skills/unit-converter/SKILL.md`:

- **Reference**: `references/CONVERSION_TABLES.md` — supported unit conversions and their factors
- **Script**: `scripts/convert.py` — converts a value using a multiplication factor (e.g. miles to kilometers)

File scripts are executed as **local Python subprocesses** via the
`script_runner` callback.

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  SkillsProvider(                                            │
│    DeduplicatingSkillsSource(                               │
│      AggregatingSkillsSource([                              │
│        FileSkillsSource("./skills",       # file skills     │
│            script_runner=runner),                            │
│        InMemorySkillsSource([                               │
│            volume_skill,                  # code skill      │
│            temp_converter,                # class skill     │
│        ]),                                                  │
│      ])                                                     │
│    )                                                        │
│  )                                                          │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│  script_runner(skill, script, args)                          │
│                                                             │
│  • Code scripts (@skill.script) → in-process call           │
│  • Class scripts (@ClassSkill.script) → in-process call     │
│  • File scripts (scripts/*.py) → subprocess via             │
│    the callback function                                    │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

Set environment variables (or create a `.env` file):

```
FOUNDRY_PROJECT_ENDPOINT=https://your-project.openai.azure.com/
AZURE_OPENAI_MODEL=gpt-4o-mini
```

Authenticate with Azure CLI:

```bash
az login
```

## Running the Sample

```bash
cd python
uv run samples/02-agents/skills/mixed_skills/mixed_skills.py
```

## Directory Structure

```
mixed_skills/
├── mixed_skills.py                # Main sample — wires code + file skills together
├── README.md
└── skills/
    └── unit-converter/            # File-based skill (discovered from SKILL.md)
        ├── SKILL.md
        ├── references/
        │   └── CONVERSION_TABLES.md
        └── scripts/
            └── convert.py
```

## Learn More

- [File-Based Skills Sample](../file_based_skill/)
- [Code-Defined Skills Sample](../code_defined_skill/)
- [Script Approval Sample](../script_approval/)
- [Agent Skills Specification](https://agentskills.io/)
