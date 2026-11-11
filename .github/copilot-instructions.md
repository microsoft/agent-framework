# GitHub Copilot Instructions

Microsoft Agent Framework - a multi-language framework for building, orchestrating, and deploying AI agents.

## Repository Structure

- `python/` - Python implementation → see [python/AGENTS.md](../python/AGENTS.md)
- `dotnet/` - C#/.NET implementation → see [dotnet/AGENTS.md](../dotnet/AGENTS.md)
- `docs/` - Design documents and architectural decision records
- `skills/` - Public, installable Agent Skills for developers using Agent Framework

## Public Consumer Skills

The skills under `skills/` are distribution artifacts for developers building Agent Framework applications. They are
not project skills for contributors working in this repository:

- Do not load or invoke them as instructions for normal Agent Framework repository work.
- Keep them outside `.github/skills`, `.agents/skills`, and `.claude/skills` so coding agents do not auto-discover them.
- Read a consumer skill during repository work only when maintaining its decision guidance; do not let its standalone
  application defaults override repository-specific instructions.

Consumer skills are decision guidance, not product documentation. Microsoft Learn is the documentation source for
developing with Microsoft Agent Framework.

- Help coding agents choose an approach: plain agent, harness agent, or workflow; extension points; integrations;
  state ownership; and hosting patterns. Include concise trade-offs, constraints that materially change those choices,
  and links to current Learn guidance.
- Do not add API or option inventories, implementation details, setup or deployment procedures, exhaustive examples,
  release notes, or per-bug workarounds. This applies to both `SKILL.md` and files under `references/`; moving detail
  into a reference does not make it appropriate.
- A framework change does not automatically require a skill update. Update a consumer skill only when the change makes
  an existing development recommendation incorrect, adds a materially different choice, or invalidates a documentation
  link, except for the cleanup rule below. Otherwise, leave the skill unchanged.
- If a framework change invalidates implementation details already present in a skill or its references, remove those
  details or replace them with decision guidance and a link to current documentation. This cleanup exception does not
  permit expanding the details or adding new implementation details.
- Before adding content, identify the development decision it changes. If no decision changes, the content belongs in
  Microsoft Learn, API documentation, samples, or contributor guidance, not in the consumer skill. Prefer revising an
  existing recommendation over appending another rule.

See the [consumer skill maintenance contract](../skills/README.md#repository-maintenance-contract) for scope examples.

## Architectural Decision Records (ADRs)

ADRs in `docs/decisions/` capture significant design decisions and their rationale. They document considered alternatives, trade-offs, and the reasoning behind choices.

**Templates:**
- `adr-template.md` - Full template with detailed sections
- `adr-short-template.md` - Abbreviated template for simpler decisions

When proposing architectural changes, create an ADR to capture options considered and the decision rationale. See [docs/decisions/README.md](../docs/decisions/README.md) for the full process.
