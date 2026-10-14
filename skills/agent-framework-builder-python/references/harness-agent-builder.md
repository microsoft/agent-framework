# Harness agent builder

Use this path when the application needs a batteries-included agent operating loop rather than an explicit workflow
graph.

`create_harness_agent` is released. Some capabilities it can enable are still experimental or prerelease, so assess
them independently instead of labeling the entire harness experimental.

The factory is a convenience composition over the regular `Agent` building blocks, not a separate runtime. Both
directions are valid:

- Start with `create_harness_agent` to get the full opinionated feature set, then disable or replace capabilities the
  application does not need.
- Start with `Agent` and add the same instructions, chat middleware, agent middleware, context providers, history,
  compaction, approval, and loop behavior explicitly.

Both approaches produce a normal agent implementing `SupportsAgentRun`; choose based on whether fast assembly or
fine-grained composition is more important.

## When to choose a harness

Choose `create_harness_agent` when the agent should:

- plan work with todos and plan/execute modes;
- keep file-backed, session-scoped memory;
- apply tool approval and standing approval rules;
- optionally load Agent Skills or use provider-supported web search;
- optionally access files, delegate to background agents, execute shell commands, or loop until work completes;
- expose the normal `Agent` interface to callers.

Use a workflow when graph topology, routing, checkpointing, or caller-visible intermediate outputs define correctness.

## Minimal setup

```python
from __future__ import annotations

import asyncio
import os

from agent_framework import create_harness_agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


async def main() -> None:
    agent = create_harness_agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=AzureCliCredential(),
        ),
        name="my-harness-agent",
        agent_instructions="Help users plan and complete multi-step tasks.",
        disable_file_memory=True,
        disable_web_search=True,
    )
    session = agent.create_session()
    print(await agent.run("Plan a weekend trip.", session=session))


if __name__ == "__main__":
    asyncio.run(main())
```

The session is important when the default tool auto-approval middleware is enabled because standing approval state is
session-scoped.

## Capability defaults

| Capability | Current behavior |
| --- | --- |
| Function invocation and per-service-call history persistence | Enabled by the harness |
| Todo provider and plan/execute mode | Enabled unless disabled or replaced |
| File memory | Enabled by default; backed by a filesystem store unless replaced |
| File access | Opt-in through `file_access_store`; experimental |
| Tool auto-approval middleware | Enabled unless disabled; still respects tool approval requirements |
| Web search | Added only when the client supports it and it is not disabled |
| Compaction | Enabled when token budgets or custom compaction strategies are supplied |
| Skills | Opt-in through `skills_paths` or `skills_provider` |
| Background agents | Opt-in and experimental |
| Shell | Opt-in, prerelease, and requires `agent-framework-tools` |
| Looping | Opt-in and experimental; bound with `loop_max_iterations` |
| OpenTelemetry | Wired through the harness telemetry layer |

Do not describe an optional capability as active unless its required option is present.

## Compaction

Supply both budgets for the default token-aware strategies:

```python
agent = create_harness_agent(
    client=client,
    max_context_window_tokens=128_000,
    max_output_tokens=16_384,
    agent_instructions="Research carefully and cite reliable sources.",
)
```

Without token budgets or custom before/after strategies, compaction is disabled.

## File memory and file access

- File memory is session-scoped and enabled by default. Treat it as persisted application data.
- File access is separate and opt-in through an `AgentFileStore`, commonly `FileSystemAgentFileStore`.
- File access tools require approval by default.
- Prefer `FileAccessProvider.read_only_tools_auto_approval_rule` when reads may run automatically but writes must
  remain approval-gated.
- Use `file_access_disable_write_tools=True` when the application must be read-only.
- Keep stores rooted in an intentional application directory.
- For hosted or untrusted workloads, do not use the shared default `{cwd}/agent-file-memory` store without operational
  controls. Either disable file memory or supply tenant-scoped storage with enforced byte and file-count quotas,
  retention limits, and server-owned cleanup. File-memory writes do not require tool approval, so storage isolation
  and resource limits must be enforced by the host.

Example source:
[Harness data processing](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/harness/harness_data_processing.py).

## Skills

Use `skills_paths` for file-based Agent Skills and `skills_provider` for custom or code-defined skills. When neither is
provided, no `SkillsProvider` is added.

- Load skills only from trusted locations.
- Treat externally supplied skill content as untrusted input.
- Keep skill loading, resource reads, and script execution approval-gated unless the application intentionally changes
  those policies.

## Looping and background work

Looping is opt-in:

```python
from agent_framework import create_harness_agent, todos_remaining, todos_remaining_message

agent = create_harness_agent(
    client=client,
    loop_should_continue=todos_remaining(looping_modes=["execute"]),
    loop_next_message=todos_remaining_message,
    loop_max_iterations=10,
)
```

- Always set a reasonable iteration cap.
- Stop for pending approvals or user input.
- Give background agents unique names, narrow responsibilities, and explicit result contracts.
- Treat background-agent input and output as potential prompt-injection and data-exfiltration boundaries.

Looping and background agents currently emit experimental warnings.

## Shell integration

Pass `shell_executor` only when command execution is an explicit product requirement.

- Install the prerelease `agent-framework-tools` distribution for the supplied shell implementations.
- Confine the working directory and environment.
- Keep command execution approval-gated.
- Treat command filters as a usability safeguard, not a security boundary.
- The caller owns the executor lifecycle.

## Validation

1. Construct the harness and create a session.
2. Run a trivial prompt.
3. Exercise todos and modes if enabled.
4. Verify file memory and file-access roots.
5. Verify approval behavior for a side-effecting tool.
6. Prove loop termination and iteration limits when looping is enabled.
7. Clean up shell and background-agent resources.

Current examples:

- [First harness](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/06_agent_harness.py)
- [Research harness](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/harness/harness_research.py)
