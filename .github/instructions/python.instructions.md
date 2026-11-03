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

## Semantic API Review

For public API and integration changes, apply the standards in this order:

1. Start from public imports and the smallest realistic initialization example. Check the common path and each
   materially different execution mode before reading implementation details.
2. Trace parameters through construction, factories, request preparation, execution, persistence, and cleanup.
   Look for accepted-but-unused settings and differences between execution paths.
3. Check whether names expose required inputs, data direction, and ownership without relying on constructor conditions.
4. Identify resource, history, continuation, cache, approval, and checkpoint ownership where applicable. Check
   cross-request sharing and failure windows.
5. Review observable compatibility, including defaults, wire shapes, option precedence, retention, and failure
   behavior, not only signature-checker results.
6. Match evidence to the claim. Offline tests do not establish live deployment behavior. An upstream fix needs
   release evidence. An investigation result is not approval for its proposed implementation.

Findings should identify the affected behavior, a concrete scenario, and its consequence. Do not prescribe a preferred
architecture as a correctness finding when multiple designs satisfy the contract. Treat unresolved alternatives as
design questions. Review author-supplied focus notes as context, not a limit on review scope.
