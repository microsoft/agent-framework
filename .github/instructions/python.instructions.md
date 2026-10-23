---
applyTo: 'python/**'
---

Before reviewing Python changes, read and apply the canonical
[Python coding standards](../../python/CODING_STANDARD.md). Use
[python/AGENTS.md](../../python/AGENTS.md) and the nearest package or sample `AGENTS.md`
for task-specific architecture and workflow guidance.

- Review new or materially edited code against the standards. Do not report unrelated legacy convention violations
  elsewhere in a touched file.
- Independently report material correctness or security defects visible in affected files, even when they predate
  the changed lines.
- Treat `MUST` and `MUST NOT` violations as review findings.
- Report `SHOULD` and `SHOULD NOT` violations when they have a material correctness, API, maintainability,
  performance, or usability impact.
- Do not report `MAY` choices as violations.
- Do not duplicate purely mechanical findings that Ruff, Pyright, or another required CI check will report.
