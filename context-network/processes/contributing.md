# Contributing to Microsoft Agent Framework

## Purpose
Quick reference guide for contributing to the project, based on CONTRIBUTING.md.

## Classification
- **Domain:** Process
- **Stability:** Stable
- **Abstraction:** Procedural
- **Confidence:** Established

## Quick Reference

### DO
- Follow standard coding conventions ([.NET](https://learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/coding-conventions), Python via ruff)
- Give priority to current project style
- Use pre-commit hooks for Python
- Include tests when adding features or fixing bugs
- Keep discussions focused
- State clearly when you're taking on an issue
- Blog and tweet about your contributions

### DON'T
- Surprise us with big PRs (discuss first)
- Submit code you didn't write without discussion
- Alter licensing files or headers
- Make new APIs without filing an issue first

## Workflow

1. **Create/Find Issue**
   - Skip for trivial changes
   - Reuse existing issues when applicable
   - Get agreement from team on approach

2. **Fork & Branch**
   - Create personal fork on GitHub
   - Branch off `main` with descriptive name

3. **Develop**
   - Make and commit changes
   - Add tests for new features/fixes
   - Run quality checks:
     - Python: `uv run poe check`
     - .NET: `dotnet build && dotnet test && dotnet format`

4. **Pull Request**
   - Create PR against `main` branch
   - State what issue/improvement is addressed
   - Verify CI checks pass

5. **Review & Merge**
   - Wait for feedback from maintainers
   - Address review comments
   - Merge occurs after approval and green checks

## Development Scripts

### Python
See [Development Processes](development.md) for complete commands.

Quick reference from `python/` directory:
```bash
uv run poe setup -p 3.13    # Initial setup
uv run poe check             # Run all quality checks
uv run poe test              # Run tests with coverage
```

### .NET
From `dotnet/` directory:
```bash
dotnet build    # Build
dotnet test     # Run tests
dotnet format   # Auto-fix linting
```

## Breaking Changes

Contributions must maintain API signature and behavioral compatibility. Breaking changes will be rejected. File an issue to discuss if you believe a breaking change is warranted.

## Relationship Network
- **Prerequisite Information**: None
- **Related Information**:
  - [Development Processes](development.md)
  - [Development Principles](../foundation/principles.md)
- **Source Document**: `CONTRIBUTING.md` (repository root)

## Navigation Guidance
- **Access Context**: Before making contributions, for quick reference
- **Common Next Steps**:
  - Setup environment → [Development Processes](development.md)
  - Understand standards → [Development Principles](../foundation/principles.md)
- **Related Tasks**: Contributing code, filing issues, reviewing PRs

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial document created during context network setup from CONTRIBUTING.md
