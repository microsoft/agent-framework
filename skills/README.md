# Microsoft Agent Framework consumer skills

This directory contains installable Agent Skills for developers building applications with Microsoft Agent Framework.
These are public distribution artifacts, not contributor instructions for working on the Agent Framework repository.

## Available skills

| Skill | Purpose |
| --- | --- |
| `agent-framework-builder-python` | Build, modify, evaluate, integrate, and host Python Agent Framework applications. |
| `agent-framework-builder-dotnet` | Build, modify, evaluate, integrate, and host .NET Agent Framework applications. |

## Install

Preview and install the default-branch version with GitHub CLI:

```bash
gh skill preview microsoft/agent-framework agent-framework-builder-python@main
gh skill install microsoft/agent-framework agent-framework-builder-python@main

gh skill preview microsoft/agent-framework agent-framework-builder-dotnet@main
gh skill install microsoft/agent-framework agent-framework-builder-dotnet@main
```

The explicit `@main` ref is required until a tagged Agent Framework release includes the skill. Until then,
unqualified `gh skill` installs and search discovery can resolve an older release that does not contain it.

Or use the cross-agent skills CLI:

```bash
npx skills add microsoft/agent-framework --skill agent-framework-builder-python
npx skills add microsoft/agent-framework --skill agent-framework-builder-dotnet
```

## Repository maintenance contract

- Coding agents working on Agent Framework itself must not treat the skills in this directory as repository
  instructions or automatically load them for normal framework development.
- Keep the skills outside `.github/skills`, `.agents/skills`, and `.claude/skills` so repository agents do not
  discover them as project skills.

### Purpose and scope

Consumer skills are decision guidance, not product documentation. Microsoft Learn is the documentation source for
developing with Microsoft Agent Framework. Skills help coding agents make high-level development choices and find the
current documentation for implementing them.

Include selection criteria, concise trade-offs, and constraints that materially change a choice: plain agent versus
harness agent versus workflow, extension points, integrations, state ownership, and hosting patterns. Link to Learn
for implementation guidance and to API documentation or maintained samples when needed.

Do not add API or option inventories, implementation details, setup or deployment procedures, exhaustive examples,
release notes, per-bug workarounds, or internal contributor conventions. This applies to both `SKILL.md` and files under
`references/`; a reference file is not a place to accumulate documentation.

For example:

- Include the choice between application-managed and service-managed history and its trade-offs. Do not include
  serialization fields, continuation-token mechanics, or every provider's storage options.
- Include the choice between self-hosted and Foundry-hosted execution. Do not include deployment commands,
  environment-variable inventories, or protocol replay sequences.
- Include the need for interactive authorization when choosing a hosting pattern. Link to documentation for consent
  handling instead of reproducing the request and response sequence.

### When to update a skill

A public API, package, sample, configuration, evaluation, integration, or hosting change does not automatically require
a consumer skill update. Update a skill only when the change makes an existing development recommendation incorrect,
adds a materially different choice, or invalidates a documentation link. Otherwise, leave the skill unchanged.

Before adding content, identify the development decision it changes. If no decision changes, put the content in
Microsoft Learn, API documentation, samples, or contributor guidance instead. Prefer revising an existing recommendation
over appending another rule, and update only the affected guidance.
