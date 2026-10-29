# Harness agent builder

Use a harness when the product needs an opinionated operating loop around a normal `Agent`: planning, todos, memory,
approval handling, compaction, or optional autonomous capabilities.

`create_harness_agent` is a convenience composition, not a separate agent abstraction. It returns an `Agent`
implementing `SupportsAgentRun`. Everything it assembles can also be composed manually from an `Agent`, middleware,
context providers, history, and instructions.

## Choose the composition direction

- Start with `create_harness_agent` and disable or replace features when the product wants most harness capabilities.
- Start with `Agent` and add individual components when the product needs only a few capabilities or exact ordering.
- Use a workflow instead when explicit graph topology, routing, checkpointed stages, or intermediate outputs define
  correctness.

## Important defaults and opt-ins

Keep only the defaults that affect architecture or safety in working memory; read the
[harness documentation](https://learn.microsoft.com/agent-framework/concepts/harness) or the factory docstring for the
complete option list.

- Todo, plan/execute mode, file memory, tool approval, history persistence, and telemetry are enabled by default.
- Compaction is active only when token budgets or custom strategies are supplied.
- Web search is added only when the client supports it and it is not disabled.
- File access, Agent Skills, background agents, shell execution, and looping are opt-in.
- Background agents, file access, looping, and shell tooling have experimental or prerelease constraints; check
  current feature maturity before depending on them.

## Operational gotchas

- Use an `AgentSession` when standing approval state or multi-turn behavior matters.
- File memory and file access are separate. File access tools require approval by default; file-memory writes do not.
- For hosted or untrusted workloads, disable file memory or supply tenant-scoped storage with quotas, retention, and
  server-owned cleanup. Do not rely on the shared default working-directory store.
- Load skills and background agents only from trusted sources; their content crosses the model and tool boundary.
- Bound autonomous loops and stop for unresolved approvals or user input.
- Treat shell command filters as a usability guard, not a security boundary. The host owns sandboxing and executor
  lifecycle. Apply resource limits to the host agent process as well as the shell container; container memory
  limits do not cover output captured outside the container. `LocalShellTool` and `DockerShellTool` independently
  limit retained normal and error output through `max_stdout_bytes` and `max_stderr_bytes`, each defaulting to
  64 KiB. Both settings must be positive; they do not impose a total process-memory limit.

## Validation

- Exercise enabled modes, memory, skills, and file roots rather than testing factory construction alone.
- Verify approval behavior for side effects.
- Prove loop termination and resource cleanup for optional autonomous features.

## Learn more

- [Harness concepts](https://learn.microsoft.com/agent-framework/concepts/harness)
- [First harness sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/06_agent_harness.py)
- [Harness samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/harness)
