# Microsoft Agent Framework consumer skills

This directory contains installable Agent Skills for developers building applications with Microsoft Agent Framework.
These are public distribution artifacts, not contributor instructions for working on the Agent Framework repository.

## Available skills

| Skill | Purpose |
| --- | --- |
| `agent-framework-builder-python` | Build, modify, evaluate, integrate, and host Python Agent Framework applications. |

## Install

Preview and install the default-branch version with GitHub CLI:

```bash
gh skill preview microsoft/agent-framework agent-framework-builder-python@main
gh skill install microsoft/agent-framework agent-framework-builder-python@main
```

The explicit `@main` ref is required until a tagged Agent Framework release includes the skill. Until then,
unqualified `gh skill` installs and search discovery can resolve an older release that does not contain it.

Or use the cross-agent skills CLI:

```bash
npx skills add microsoft/agent-framework --skill agent-framework-builder-python
```

## Repository maintenance contract

- Coding agents working on Agent Framework itself must not treat the skills in this directory as repository
  instructions or automatically load them for normal framework development.
- Keep the skills outside `.github/skills`, `.agents/skills`, and `.claude/skills` so repository agents do not
  discover them as project skills.
- Review the Python consumer skill whenever a change affects public APIs, package names or maturity, canonical samples,
  configuration, evaluation, integrations, or hosting guidance.
- Update only the affected guidance. Do not copy internal contributor conventions into the consumer skill.
