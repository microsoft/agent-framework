# Mixed Skills — Code Skills and File Skills

This sample demonstrates how to combine **code-defined skills** and
**file-based skills** in a single agent using `CallbackSkillScriptExecutor`
and `SkillsProvider`.

## Concepts

| Concept | Description |
|---------|-------------|
| **Code skill** | A `Skill` created in Python with `@skill.script` decorators for in-process callable functions and `@skill.resource` for dynamic content |
| **File skill** | A skill discovered from a `SKILL.md` file on disk, with reference documents and executable script files |
| **`CallbackSkillScriptExecutor`** | Routes script execution through a user-provided callback — required when combining code and file skills |
| **`SkillsProvider`** | Registers both code-defined and file-based skills in a single provider |

## Skills in This Sample

### pin-generator (code skill)

Defined entirely in Python code using decorators:

- **`@skill.resource`** — `pin-guidelines`: PIN length recommendations by use case
- **`@skill.script`** — `generate-pin`: generates a cryptographically secure numeric PIN of configurable length

Code scripts run **in-process** — no subprocess or external executor needed.

### password-generator (file skill)

Discovered from `skills/password-generator/SKILL.md`:

- **Reference**: `references/PASSWORD_GUIDELINES.md` — password length and character set recommendations
- **Script**: `scripts/generate.py` — generates a secure password with configurable length

File scripts are executed as **local Python subprocesses** via the
`CallbackSkillScriptExecutor` callback.

## How It Works

```
┌─────────────────────────────────────────────────────┐
│  SkillsProvider(                                     │
│      skill_paths="./skills",         # file skills   │
│      skills=[pin_generator_skill],   # code skills   │
│      script_executor=executor,                       │
│  )                                                   │
└─────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│  CallbackSkillScriptExecutor(callback=...)          │
│                                                     │
│  • Code scripts (@skill.script) → in-process call   │
│  • File scripts (scripts/*.py) → subprocess via     │
│    the callback function                            │
└─────────────────────────────────────────────────────┘
```

## Prerequisites

Set environment variables (or create a `.env` file):

```
AZURE_AI_PROJECT_ENDPOINT=https://your-project.openai.azure.com/
AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4o-mini
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
    └── password-generator/        # File-based skill (discovered from SKILL.md)
        ├── SKILL.md
        ├── references/
        │   └── PASSWORD_GUIDELINES.md
        └── scripts/
            └── generate.py
```

## Learn More

- [File-Based Skills Sample](../file_based_skill/)
- [Code-Defined Skills Sample](../code_defined_skill/)
- [Script Approval Sample](../script_approval/)
- [Agent Skills Specification](https://agentskills.io/)
