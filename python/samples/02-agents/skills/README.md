# Agent Skills Samples

These samples demonstrate how to use **Agent Skills** — modular packages of instructions, resources, and scripts that extend an agent's capabilities. Skills follow the [Agent Skills specification](https://agentskills.io/) and use progressive disclosure to optimize token usage.

## Learning Path

Start with file-based or code-defined skills, then explore combining them and adding approval workflows.

| Sample | Description |
|--------|-------------|
| [**file_based_skill**](file_based_skill/) | Define skills as `SKILL.md` files on disk with reference documents and executable scripts. Uses the unit-converter skill. |
| [**code_defined_skill**](code_defined_skill/) | Define skills entirely in Python code using `Skill`, `@skill.resource`, and `@skill.script` decorators. Uses a code-defined unit-converter skill. |
| [**mixed_skills**](mixed_skills/) | Combine code-defined and file-based skills in a single agent. Uses a code-defined volume-converter and a file-based unit-converter. |
| [**script_approval**](script_approval/) | Require human-in-the-loop approval before executing skill scripts |

## Key Concepts

### Progressive Disclosure

Skills use a three-step interaction model to minimize token usage:

1. **Advertise** — Skill names and descriptions (~100 tokens each) are injected into the system prompt
2. **Load** — Full instructions are loaded on-demand via the `load_skill` tool
3. **Access** — Resources are read via `read_skill_resource`; scripts are executed via `run_skill_script`

### File-Based vs Code-Defined Skills

| Aspect | File-Based | Code-Defined |
|--------|-----------|--------------|
| Definition | `SKILL.md` files on disk | `Skill` instances in Python |
| Resources | Static files in `references/` and `assets/` directories | Callable functions via `@skill.resource` decorator |
| Scripts | Python files in `scripts/` directory (executed via subprocess) | Callable functions via `@skill.script` decorator (executed in-process) |
| Discovery | Automatic via `skill_paths` parameter | Explicit via `skills` parameter |
| Dynamic content | No (static files only) | Yes (functions can generate content at runtime) |

Both types can be combined in a single `SkillsProvider` — see the [mixed_skills](mixed_skills/) sample.

### Script Execution

Skills can include executable scripts. How a script runs depends on how it was defined:

| | Code-Defined Scripts | File-Based Scripts |
|---|---|---|
| **Defined via** | `@skill.script` decorator | `.py` files in `scripts/` directory |
| **Execution** | In-process (direct function call) | Delegated to a `script_runner` |
| **`script_runner` needed?** | No — runs in-process automatically | **Yes** — required |

The `script_runner` parameter on `SkillsProvider` is only applicable to **file-based** scripts. Code-defined scripts are always executed in-process regardless of this setting. See [file_based_skill](file_based_skill/) for an example using a `SkillScriptRunner` callable with a subprocess runner, and [code_defined_skill](code_defined_skill/) for in-process scripts that need no runner.

## Prerequisites

All samples require:
- An [Azure AI Foundry](https://ai.azure.com/) project with a deployed model (e.g. `gpt-4o-mini`)
- Azure CLI authentication (`az login`)
- Environment variables set in a `.env` file (see `python/.env.example`)

## Suppressing the experimental warning

The Agent Skills APIs in these samples are still experimental. Each sample includes
a short commented `warnings.filterwarnings(...)` snippet near the imports. Uncomment
it if you want to suppress the Skills warning before using the experimental APIs.
