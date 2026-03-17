# Brainstorming on MAF Harness

**Reference Document:** [Agent Harness in Microsoft Agent Framework](https://microsoft-my.sharepoint.com/:w:/r/personal/bentho_microsoft_com/Documents/Agent%20Harness%20in%20Microsoft%20Agent%20Framework.docx?d=w49895009445b4f74be796340601906a2&csf=1&web=1&e=SWyNP7)

---

## What Is the Agent Harness?

The runtime control plane that enables reliable, long-running agent execution. Not a specific agent. Not a specific set of tools. It's the **infrastructure layer** that any agent can run within.

What it provides:

- **Outer loop** — model ↔ tools ↔ state ↔ repair, running as long as it needs to
- **State & durability** — checkpoints, resume, memory
- **Tool plumbing** — registry, schema, invocation, error handling
- **Governance** — permissions, human-in-the-loop, policies
- **Context management** — compaction, eviction, externalization
- **Observability** — traces, transcripts, replay

---

## The Three-Layer Model

Everything in the harness maps to one of three layers:

| Layer | Question it answers | Examples |
|---|---|---|
| **Harness** (Control Plane) | _How_ does the agent execute? | Turn loop, checkpointing, stop conditions, context pressure, policy, tracing |
| **Environment** (Capability Plane) | _What_ can the agent do? | Filesystem, shell, browser, APIs, artifact storage — pluggable per deployment |
| **Persona** (Configuration) | _Who_ is the agent? | System instructions, tool visibility, risk tolerance, autonomy level, what "done" means |

Different personas need different environments:

| Capability | Chat-Only | API Agent | Research | Coding | Ops/Infra |
|---|---|---|---|---|---|
| Filesystem | No | No | Optional | **Yes** | Optional |
| Shell | No | No | No | **Yes** (sandboxed) | Restricted |
| Web Search | No | Optional | **Yes** | Optional | No |
| Browser | No | No | **Yes** | No | No |
| HTTP APIs | No | **Yes** | Yes | Optional | **Yes** |

---

## Where We Stand: Gap Analysis

MAF was compared against DeepAgents, Amplifier, Opencode, Copilot CLI, OpenAI Codex, and Claude Code. Every one of them has these capabilities. MAF has some partially, most not at all.

### P0 — Must Have

| Capability | Layer | What MAF Has Today |
|---|---|---|
| **Filesystem tools** | Environment | Hosted tools only (remote code interpreter, file search) — no local filesystem access |
| **Shell execution** | Environment | Nothing — no ability to run shell commands locally or sandboxed |
| **Context compaction** | Harness | Nothing built-in — developers must implement summarization/windowing manually |
| **Todo / planning tool** | Harness | Magentic has advanced planning, but no simple self-organizing task list for agents |
| **Sub-agent delegation** | Harness | Partial — orchestration patterns exist (Sequential, Concurrent, Group Chat, etc.) but state isolation between parent/child is incomplete |
| **Memory** | Environment | Partial — Python core has `_memory.py`, but no unified cross-platform story |

### P1 — Important but Deferrable

| Capability | Layer | What MAF Has Today |
|---|---|---|
| **Skills / prompt presets** | Persona | Nothing — instructions must be authored from scratch every time |
| **Model routing / cost-aware scheduling** | Harness | Nothing — no dynamic model selection based on task complexity or cost |
| **Computer use** | Environment | Nothing — future interface for screen/mouse/keyboard interaction |

### Open Priority Debates (from document reviewers)

- **Todo/Planning — P0 or P1?** "An agent _can_ execute tasks using only filesystem + shell. For simple tasks, P1 is fine. For Claude Code-like complex multi-step tasks, this is P0."
- **Sub-Agent Delegation — definitely P0?** "A lot of task planners and coding agents use sub-agents to run multiple tasks. Good mental model: take coding agents as the main use case."
- **What is our MVP persona?** If it's a coding agent, that drives which P0 items matter most.

---

## Feature Details

### Filesystem Tools

Create a `FilesystemTool` with operations: `read`, `write`, `edit`, `list`, `glob`, `grep`.

The key design decision is **abstraction**: define a `FilesystemProtocol` interface with pluggable backends.

- `LocalFilesystem` — direct local access (the default; used when running inside Foundry Hosted Agents)
- `HostedFilesystem` — remote sandbox access (agent runs locally, filesystem lives in a remote sandbox of the user's choice)

Must include: path validation, traversal prevention, pagination for large files. Consider: snapshot/restore for tracking file changes during execution.

### Shell / Command Execution

Same interface-based pattern as filesystem. `LocalShellTool` for direct execution, `HostedShellTool` for remote sandboxes.

Configuration surface: timeout, output truncation, working directory, environment variables.

Open question: What sandboxing and permission model? How do we prevent destructive commands?

### Context Compaction

Two API tiers — **simple for most developers, advanced for full control**:

**Simple (menu-driven):**
```csharp
harnessBuilder.AddCompaction(Approach.Balanced, Size.Compact, summarizingChatClient);
```

**Advanced (pipeline) — ordered stages, least to most aggressive:**
1. **Gentle:** Collapse old tool-call groups into short summaries (`ToolResultCompactionStrategy`)
2. **Moderate:** LLM-based summarization of older conversation spans (`SummarizationCompactionStrategy`)
3. **Aggressive:** Sliding window — keep only last N user turns (`SlidingWindowCompactionStrategy`)
4. **Emergency:** Drop oldest groups until under token budget (`TruncationCompactionStrategy`)

Triggers: `TokensExceed(threshold)`, `TurnsExceed(count)`, custom. Reference thresholds from competitors: 85% token capacity trigger, keep last 10%, fallback at 170K tokens / 6 messages.

Open question: How do triggers compose when multiple strategies are pipelined?

### Todo / Planning Tool

`TodoTool` with `write_todos` operation. `TodoItem` has content + status (pending / in progress / completed).

`TodoMiddleware` injects current todos into the system prompt — this is what gives the agent the ability to self-plan and track progress.

### Sub-Agent Delegation

MAF already has orchestration (Sequential, Concurrent, Group Chat, Magentic, Handoff, Human-in-the-loop). The gap is **state isolation**: sub-agents need their own message history and todo state, isolated from the parent, returning results as tool responses.

### Memory

Loads memories from backend storage, injects into system prompt automatically. Open questions: How does memory interact with compaction? Should compacted summaries become long-term memories? Which backends out of the box?

### Skills / Prompt Presets (P1)

`SkillsMiddleware` loads reusable instruction sets from `SKILL.md` files with YAML frontmatter (Anthropic Skills format). Progressive disclosure — metadata first, content on demand. Skill discovery from filesystem paths.

### Model Routing (P1)

`ModelRouterMiddleware` with strategies: cost-aware (minimize cost for task requirements) and heuristic (rule-based, e.g., stronger model for code tasks).

---

## Developer Experience: The Builder API

Everything hangs off a **fluent builder pattern**:

```
harnessBuilder
    .AddCompaction(...)
    .AddTool(filesystemTool)
    .AddTool(shellTool)
    .AddMemory(...)
    .AddTodo(...)
    ...
```

Key considerations:

- **Composability** — developers opt in/out of individual capabilities. Minimal harness = just the outer loop. Full harness = everything.
- **Hosting** — the builder must integrate cleanly with DI and hosting (ASP.NET, Azure Functions).
- **Presets** — should we offer opinionated starters? (`HarnessPresets.CodingAgent`, `HarnessPresets.Conversational`, `HarnessPresets.Research`)
- **Two-tier deployment** — "develop local, deploy remote":
  - _Local:_ Direct filesystem/shell on the developer machine, fast iteration, debugging, human-in-the-loop
  - _Production (Foundry Hosted Agents):_ Managed containers, autoscaling, identity, observability, publishing to Teams / M365 Copilot / Web
- The interface-based tool abstractions (`LocalFilesystem` ↔ `HostedFilesystem`, `LocalShell` ↔ `HostedShell`) are what make the two-tier model work.

---

## Validation

- **Prompt evaluation** — test default harness prompts (compaction, slot filling, etc.) across OpenAI, Azure OpenAI, Anthropic, and other providers
- **Custom prompt override** — developers can replace default prompts; we need to document and validate the override mechanism
- **Compaction testing** — verify different pipeline configurations produce correct and useful results
- **Test strategy** — unit tests, integration tests, model-in-the-loop evaluation, benchmarks

---

## Tutorials & Onboarding

Suggested progression:

1. Getting started — minimal harness setup
2. Adding compaction to a long-running conversation
3. Using tools (filesystem, shell) within the harness
4. Slot filling / guided conversations
5. Task management and structured output
6. Advanced — custom compaction pipelines, memory, sub-agents

---

## Competitive Reference

| Tool | Filesystem | Shell | Compaction | Todo | Sub-Agent | Skills | Memory | Model Routing |
|---|---|---|---|---|---|---|---|---|
| **DeepAgents** | filesystem.py | shell.py | graph.py | todo.py | subagents.py | skills.py | memory.py | — |
| **Amplifier** | tool-filesystem | tool-bash | context-simple | tool-todo | tool-task | tool-skills | bundle-memory | scheduler-cost-aware |
| **Opencode** | read.ts | bash.ts | compaction.ts | todo.ts | task.ts | skill.ts | storage.ts | provider.ts (partial) |
| **Copilot CLI** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| **OpenAI Codex** | read_file.rs | shell.rs | compact.rs | plan.rs | collab.rs | skills/ | message_history.rs | models_manager/ |
| **Claude Code** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |

