## What Is the Agent Harness?

The runtime control plane that enables reliable, long-running agent execution. Not a specific agent. Not a specific set of tools. It's the **infrastructure layer** that any agent can run within.

What it provides:

- **Outer loop** — model ↔ tools ↔ state ↔ repair, running as long as it needs to
- **State & durability** — checkpoints, resume, memory
- **Tool plumbing** — registry, schema, invocation, error handling
- **Governance** — permissions, human-in-the-loop, policies
- **Context management** — compaction, eviction, externalization
- **Observability** — traces, transcripts, replay

### The Three-Layer Model

| Layer | Question it answers | Examples |
|---|---|---|
| **Harness** (Control Plane) | _How_ does the agent execute? | Turn loop, checkpointing, stop conditions, context pressure, policy, tracing |
| **Environment** (Capability Plane) | _What_ can the agent do? | Filesystem, shell, browser, APIs, artifact storage — pluggable per deployment |
| **Persona** (Configuration) | _Who_ is the agent? | System instructions, tool visibility, risk tolerance, autonomy level, what "done" means |

### Persona × Tool Matrix

| Capability | Chat-Only | API Agent | Research | Coding | Ops/Infra |
|---|---|---|---|---|---|
| Filesystem | No | No | Optional | **Yes** | Optional |
| Shell | No | No | No | **Yes** (sandboxed) | Restricted |
| Web Search | No | Optional | **Yes** | Optional | No |
| Browser | No | No | **Yes** | No | No |
| HTTP APIs | No | **Yes** | Yes | Optional | **Yes** |

### Where We Stand (Gap Analysis)

MAF compared against DeepAgents, Amplifier, Opencode, Copilot CLI, OpenAI Codex, and Claude Code — every one of them has these capabilities. MAF has some partially, most not at all.

| Priority | Capability | Layer | MAF Today |
|---|---|---|---|
| **P0** | Filesystem tools | Environment | Local access |
| **P0** | Shell execution | Environment | Local access |
| **P0** | Context compaction | Harness | Pipeline + initial strategies |
| **P0** | Todo / planning tool | Harness | Nothing |
| **P0** | Sub-agent delegation | Harness | Partial — orchestration exists, state isolation incomplete |
| **P0** | Memory | Environment | Partial — Python core only |
| **P1** | Skills / prompt presets | Persona | Nothing |
| **P1** | Model routing | Harness | Nothing |

---

## Features

### Agent/User Orchestration

#### Slot Filling (a.k.a. "Guided Conversations")

How does the harness manage structured, multi-turn data collection from the user? What's the interaction model between the outer loop and user-facing slot-filling prompts? How does it compose with compaction and task management? How does the agent re-ask or repair slot values after partial completion?

### Compaction Strategy

Two API tiers — **simple for most developers, advanced for full control**.

**Simple (menu-driven)** — developer picks from preset enums:
```csharp
harnessBuilder.AddCompaction(Approach.Balanced, Size.Compact, summarizingChatClient);
```

**Advanced (pipeline)** — ordered stages, least to most aggressive:
1. **Gentle:** Collapse old tool-call groups into short summaries (`ToolResultCompactionStrategy`)
2. **Moderate:** LLM-based summarization of older conversation spans (`SummarizationCompactionStrategy`)
3. **Aggressive:** Sliding window — keep only last N user turns (`SlidingWindowCompactionStrategy`)
4. **Emergency:** Drop oldest groups until under token budget (`TruncationCompactionStrategy`)

Triggers: `TokensExceed(threshold)`, `TurnsExceed(count)`, custom. Reference thresholds from competitors: 85% token capacity trigger, keep last 10%, fallback at 170K tokens / 6 messages.

Open questions: What are the right defaults? How do triggers compose when multiple strategies are pipelined?

### Tools: File System / Shell

Both follow the same pattern: **interface-based, with pluggable backends**. Local is the default. Remote/sandboxed is supported.

- **File System** — `FilesystemTool` with `read`, `write`, `edit`, `list`, `glob`, `grep`. Backed by a `FilesystemProtocol` with `LocalFilesystem` (direct access) and `HostedFilesystem` (remote sandbox). Must include path validation, traversal prevention, large-file pagination. Consider snapshot/restore for tracking changes during execution.

- **Shell** — `LocalShellTool` / `HostedShellTool`. Configurable timeout, output truncation, working directory, environment variables. Open question: what sandboxing and permission model?

- **Computer Use (TODO)** — same interface pattern for screen/mouse/keyboard interaction. Future work. Security and governance implications are significant.

### Task Management

`TodoTool` with `write_todos`. `TodoItem` has content + status (pending / in progress / completed). `TodoMiddleware` injects current todos into the system prompt — this is what gives the agent the ability to self-plan and track its own progress.

Open debate: P0 or P1? "An agent _can_ work with only filesystem + shell. But for Claude Code-like complex multi-step tasks, this is P0."

### Data Driven: Input Schema / Structured Data Output

How does the harness support defining what data the agent needs (input schema) and what the agent produces (structured output)? Is this related to or distinct from slot filling? How does the developer define and validate schemas?

### Memories

Loads from backend storage, injects into system prompt automatically. Open questions: How does memory interact with compaction — should compacted summaries become long-term memories? Which backends out of the box? What's the cross-session story?

### Sub-Agent Delegation

MAF already has orchestration (Sequential, Concurrent, Group Chat, Magentic, Handoff, Human-in-the-loop). The gap is **state isolation**: sub-agents need their own message history and todo state, isolated from the parent, returning results as tool responses. "A lot of task planners and coding agents use sub-agents. This feels P0."

### Skills / Prompt Presets (P1)

`SkillsMiddleware` loads reusable instruction sets from `SKILL.md` files with YAML frontmatter (Anthropic Skills format). Progressive disclosure — metadata first, content on demand. Skill discovery from filesystem paths.

### Model Routing (P1)

`ModelRouterMiddleware` with strategies: cost-aware (minimize cost for task requirements) and heuristic (rule-based, e.g., stronger model for code tasks).

---

## Shape

Everything hangs off a **fluent builder pattern**:

```
harnessBuilder
    .AddCompaction(...)
    .AddTool(filesystemTool)
    .AddTool(shellTool)
    .AddMemory(...)
    .AddTodo(...)
```

- **Composability** — developers opt in/out of individual capabilities. Minimal harness = just the outer loop. Full harness = everything.
- **Hosting** — must integrate cleanly with DI and hosting (ASP.NET, Azure Functions).
- **Presets** — opinionated starters? (`HarnessPresets.CodingAgent`, `HarnessPresets.Conversational`, `HarnessPresets.Research`)
- **Two-tier deployment** — "develop local, deploy remote":
  - _Local:_ Direct filesystem/shell, fast iteration, debugging, human-in-the-loop
  - _Production (Foundry Hosted Agents):_ Managed containers, autoscaling, identity, observability, Teams / M365 Copilot / Web
- The interface-based tool abstractions (`LocalFilesystem` ↔ `HostedFilesystem`, `LocalShell` ↔ `HostedShell`) are what make the two-tier model work.

---

## Validation

- **Prompt evaluation** — test default harness prompts (compaction, slot filling, etc.) across OpenAI, Azure OpenAI, Anthropic, and other providers
- **Custom prompt override** — developers can replace default prompts; need to document and validate the override mechanism
- **Compaction testing** — verify different pipeline configurations produce correct and useful results
- **Test strategy** — unit tests, integration tests, model-in-the-loop evaluation, benchmarks

---

## Tutorials

Suggested progression:

1. Getting started — minimal harness setup
2. Adding compaction to a long-running conversation
3. Using tools (filesystem, shell) within the harness
4. Slot filling / guided conversations
5. Task management and structured output
6. Advanced — custom compaction pipelines, memory, sub-agents

