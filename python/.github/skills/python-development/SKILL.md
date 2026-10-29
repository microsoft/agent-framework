---
name: python-development
description: >
  Workflow guidance for developing Python code in the Agent Framework
  repository. Use this when writing or modifying Python source files under
  python/.
---

# Python Development Workflow

The canonical engineering rules are in
[`python/CODING_STANDARD.md`](../../../CODING_STANDARD.md). Read and apply that
document before changing Python source. Do not create or maintain a competing
copy of the standards in this skill.

## Before Editing

1. Read `python/AGENTS.md` and the nearest package `AGENTS.md`.
2. Identify whether the change affects package source, tests, samples, public
   exports, package governance, or more than one of those surfaces.
3. Read the task-specific skill when applicable:
   - `python-testing` for test design, integration markers, and test commands.
   - `python-code-quality` for formatting, linting, and type checking.
   - `python-package-management` for package creation, dependencies, public
     lazy exports, and package lifecycle.
   - `python-feature-lifecycle` for staged API decorators and promotion.

## Implementing Changes

- Follow established patterns in the owning package unless they conflict with
  `python/CODING_STANDARD.md`.
- Keep the common public path import-light and review public API changes for
  compatibility and ergonomics.
- Update source, typing surfaces, tests, samples, and documentation together
  when they represent the same contract.
- For root `agent_framework` export changes, follow the synchronized runtime,
  `__all__`, and `.pyi` workflow in `python-package-management`.
- Do not broaden a change into unrelated cleanup solely because nearby code
  predates the current standard.

## Validation

Run the smallest relevant commands from `python/`. Use
`python-code-quality` and `python-testing` to select package-scoped syntax,
typing, and test commands before escalating to broader checks.

When a convention, command, or workflow changes, update the canonical document
or owning task-specific skill rather than duplicating the new guidance here.
