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
- When a change affects public APIs, packages, samples, configuration, evaluation, integrations, or hosting guidance,
  review and update the corresponding consumer skill as maintained product documentation.
- Read a consumer skill during repository work only when that maintenance check is relevant; do not let its standalone
  application defaults override repository-specific instructions.

## Architectural Decision Records (ADRs)

ADRs in `docs/decisions/` capture significant design decisions and their rationale. They document considered alternatives, trade-offs, and the reasoning behind choices.

**Templates:**
- `adr-template.md` - Full template with detailed sections
- `adr-short-template.md` - Abbreviated template for simpler decisions

When proposing architectural changes, create an ADR to capture options considered and the decision rationale. See [docs/decisions/README.md](../docs/decisions/README.md) for the full process.
