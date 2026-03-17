# MAF Brainstorming Session
> March, 17th 2026

## Reference Documents

- [OpenClaw Agent Harness](https://microsoft-my.sharepoint.com/:w:/p/shahen/IQAU5F524RvtTpzjAZIjMf0BAQqMMPYCMRRPnX0eslRiPb0?e=MLF6CL)
- [Agent Platform Comparison](https://m365.cloud.microsoft/chat/pages/eyJ1IjoiaHR0cHM6Ly9taWNyb3NvZnQuc2hhcmVwb2ludC5jb20vY29udGVudHN0b3JhZ2UveDhGTk8teHRza3VDUlgyX2ZNVEhMYmRXU2tHOE93Skt2VTBCX3pNTDFaVT9uYXY9Y3owbE1rWmpiMjUwWlc1MGMzUnZjbUZuWlNVeVJuZzRSazVQTFhoMGMydDFRMUpZTWw5bVRWUklUR0prVjFOclJ6aFBkMHBMZGxVd1FsOTZUVXd4V2xVbVpEMWlKVEl4TUhscVMzWlphRU5CVlVkV2IwUndhVlpzZUZKekxXTkNZMjltVm1jME1VSnlabVZpWWxKeVNXdFZlamd5YlRBelJtVnhXVlJaVmtwQlkzQlVkMnc0TUNabVBUQXhXVlJZVWxWVVNqSk1WbFV6UlZsWE4xTmFSek5JVDBGUFRWSkNXRWhLUzFFbVl6MGxNa1ltWVQxTWIyOXdRWEJ3Sm5BOUpUUXdabXgxYVdSNEpUSkdiRzl2Y0Mxd1lXZGxMV052Ym5SaGFXNWxjaVo0UFNVM1FpVXlNbmNsTWpJbE0wRWxNakpVTUZKVVZVaDRkR0ZYVG5saU0wNTJXbTVSZFdNeWFHaGpiVlozWWpKc2RXUkROV3BpTWpFNFdXbEZkMlZYY0V4a2JHeHZVVEJHVmxJeFduWlNTRUp3Vm0xNE5GVnVUWFJaTUVwcVlqSmFWMXA2VVhoUmJrcHRXbGRLYVZWdVNrcGhNVlkyVDBSS2RFMUVUa2RhV0VaYVZrWnNWMU5yUm1walJsSXpZa1JuZDJaRVFYaFhWbEpaVld4V1ZWUldUa0pPTUdSWlZGVk9SbFpVVWs5U2EydDVVMVJqZVZGc2FGWldSa3BDVFRGSkpUTkVKVEl5SlRKREpUSXlhU1V5TWlVelFTVXlNbU5oTkRSbFlUZGtMVEF5TWpjdE5ERm1OQzFpWVRsaUxUUm1OV1kyTlRWaVpEZGpPU1V5TWlVM1JBPT0ifQ?auth=2&ct=1773767195553&or=Teams-HL&LOF=1)
- [LangChain Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)
- [CodeAct](https://arxiv.org/abs/2402.01030)
- [AI Accelerator - Foundry](https://microsoft.sharepoint.com/:p:/t/CoreAIStudioOutboundProduct/IQAFfbFIu5E7RLMcFmX_7C6EAU2xt1TxnGbR36EN6JTwX0Y?e=9UsKZ6)
- [Foundry Developer Portal (Hosted Agents)](https://hosted-agents-builder.lemonriver-6a2ef1ee.westus2.azurecontainerapps.io/getting-started)


## Next Steps

Demo for MVP session on campus next week.

1. Code Act: How to with MAF
1. Harness Preview: Single agent with compaction, tools (including shell or file-system), and simple orchestration loop.

Deploy agent with harness as _Foundry Hosted Agent_.


## What Is the Agent Harness?

The runtime control plane that enables reliable, long-running agent execution. Not a specific agent. Not a specific set of tools. It's the **infrastructure layer** that any agent can run within.

What it provides:

- **Outer loop** — model ↔ tools ↔ state ↔ repair, running as long as it needs to
- **State & durability** — checkpoints, resume, memory
- **Tool plumbing** — registry, schema, invocation, error handling
- **Governance** — permissions, human-in-the-loop, policies
- **Context management** — compaction, eviction, externalization
- **Observability** — traces, transcripts, replay


### Where We Stand

MAF compared against DeepAgents, Amplifier, Opencode, Copilot CLI, OpenAI Codex, and Claude Code — every one of them has these capabilities. MAF has some partially, most not at all.

| Priority | Capability | Layer | MAF Today |
|---|:---|:---|:---|
| **P0** | Agent/User Orchestration | Harness | 🟡 Workflows or part of `AIAgent`? |
| **P0** | Session Persistence | Harness | 🟢 `AgentSession`/`AIContextProvider` |
| **P0** | Context Compaction | Harness | 🟢 In preview |
| **P0** | Memory | Environment | 🟡 Partial — Python core only |
| **P0** | Permissions / Scoping | Harness | 🔴 Nothing |
| **P0** | Tool: Composite Tool Calling | Harness | 🔴 Needs definition |
| **P0** | Tool: Filesystem | Environment | 🟢 Local access |
| **P0** | Tool: Shell Execution | Environment | 🟢 Local access |
| **P0** | Tool: Todo / Planning | Harness | 🔴 Nothing |
| **P0** | Sub-Agent Delegation | Harness | 🟡 Partial — orchestration exists, state isolation incomplete |
| **P1** | Skills / Prompt Presets | Persona | 🔴 Nothing |
| **P1** | Model Routing | Harness | 🔴 Nothing |
| **P1** | Agent Budgets | Persona | 🔴 Nothing |
| **P1** | Prompt Caching | Persona | 🔴 Nothing |

### Open Issues

- How does this look in DevUI?



## Features

### Agent/User Orchestration

How does the harness manage structured, multi-turn data collection from the user? 
What's the interaction model between the outer loop and user-facing slot-filling prompts? 
How does it compose with compaction and task management? How does the agent re-ask or repair slot values after partial completion?

### Session Persistence

`AgentSession` is directly serializable and there is also a `ChatHistoryProvider` option for more complex storage needs. 

Open questions: 
- How to handle schema evolution? 
- How to version `AgentSession`? 
- How to support partial loading for long histories?
- Does a session include more than conversation context (i.e. messages)?

### Compaction Strategy

Two API tiers — **simple for most developers, advanced for full control**.

**Simple (menu-driven)** — developer picks from preset enums:
```csharp
builder.AddCompaction(Approach.Balanced, Size.Compact, summarizingChatClient);
```

**Advanced (pipeline)** — ordered stages, least to most aggressive:
```csharp
builder.AddCompaction(
    new PipelineCompactionStrategy(
        // 1. Gentle: collapse old tool-call groups into short summaries
        new ToolResultCompactionStrategy(CompactionTriggers.MessagesExceed(7)),

        // 2. Moderate: use an LLM to summarize older conversation spans into a concise message
        new SummarizationCompactionStrategy(summarizerChatClient, CompactionTriggers.TokensExceed(0x6000)),

        // 3. Aggressive: keep only the last N user turns and their responses
        new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(32)),

        // 4. Emergency: drop oldest groups until under the token budget
        new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(0x8000))));
```

1. **Gentle:** Collapse old tool-call groups into short summaries (`ToolResultCompactionStrategy`)
2. **Moderate:** LLM-based summarization of older conversation spans (`SummarizationCompactionStrategy`)
3. **Aggressive:** Sliding window — keep only last N user turns (`SlidingWindowCompactionStrategy`)

### Memories

Loads from backend storage, injects into system prompt automatically.

### Permissions / Scoping

Agent Scopes define the explicit boundaries within which an agent is allowed to operate, constraining where it can act 
(for example, a single folder or service) and what level of access it has (such as read‑only, write, or execute). 
By enforcing scoped resources and permissions, this feature ensures the agent’s actions remain intentionally limited, 
predictable, and aligned with least‑privilege principles—preventing overreach even when the agent could otherwise reason 
about broader options.

### Tools: File System / Shell

Both should follow the same pattern: **interface-based, with pluggable backends**. Local is the default. Remote/sandboxed is supported.

- **File System** — `FilesystemTool` with `read`, `write`, `edit`, `list`, `glob`, `grep`. Backed by a `FilesystemProtocol` with `LocalFilesystem` (direct access) and `HostedFilesystem` (remote sandbox). Must include path validation, traversal prevention, large-file pagination. Consider snapshot/restore for tracking changes during execution.

- **Shell** — `LocalShellTool` / `HostedShellTool`. Configurable timeout, output truncation, working directory, environment variables. Open question: what sandboxing and permission model?

- **Computer Use (TODO)** — same interface pattern for screen/mouse/keyboard interaction. Future work. Security and governance implications are significant.

### Tools: Task Management

`TodoTool` with `write_todos`. `TodoItem` has content + status (pending / in progress / completed). `TodoMiddleware` injects current todos into the system prompt — this is what gives the agent the ability to self-plan and track its own progress.

Open debate: P0 or P1? "An agent _can_ work with only filesystem + shell. But for Claude Code-like complex multi-step tasks, this is P0."

### Data Driven: Input Schema / Structured Data Output

How does the harness support defining what data the agent needs (input schema) and what the agent produces (structured output)? Is this related to or distinct from slot filling? How does the developer define and validate schemas?
### Sub-Agent Delegation

MAF already has orchestration (Sequential, Concurrent, Group Chat, Magentic, Handoff, Human-in-the-loop). The gap is **state isolation**: sub-agents need their own message history and todo state, isolated from the parent, returning results as tool responses. "A lot of task planners and coding agents use sub-agents. This feels P0."

### Skills / Prompt Presets (P1)

`SkillsMiddleware` loads reusable instruction sets from `SKILL.md` files with YAML frontmatter (Anthropic Skills format). Progressive disclosure — metadata first, content on demand. Skill discovery from filesystem paths.

### Model Routing (P1)

`ModelRouterMiddleware` with strategies: cost-aware (minimize cost for task requirements) and heuristic (rule-based, e.g., stronger model for code tasks).

### Agent Budgets

Agent Budgets define a hard execution limit—such as a maximum number of tokens, turns, or tool calls—within which an agent must 
decide whether to act and how far to pursue a task, directly shaping planning, delegation, and early stopping behavior. 
Unlike a context‑management budget, which governs what information is retained or loaded, an agent budget constrains execution itself, 
informing decisions like skipping steps, reducing depth, or terminating when the remaining budget cannot justify further action.

### Prompt Caching (P1)

Prompt caching is important for coding agents.  
When an agent is iterating on a coding problem, the same or similar prompts are often repeated.
We need a great caching story to speed up iteration and reduce costs.


## Shape

Everything hangs off a **fluent builder pattern**.  
Ideally this builder is identical with the agent-builder pattern, so developers 
can seamlessly transition from "building an agent" to "building a harness for that agent" without learning a new API. 

Example:

```
builder
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


## Validation

- **Prompt evaluation** — test default harness prompts (compaction, slot filling, etc.) across OpenAI, Azure OpenAI, Anthropic, and other providers
- **Custom prompt override** — developers can replace default prompts; need to document and validate the override mechanism
- **Compaction testing** — verify different pipeline configurations produce correct and useful results
- **Test strategy** — unit tests, integration tests, model-in-the-loop evaluation, benchmarks


## Tutorials

Suggested progression:

1. Getting started — minimal harness setup
2. Adding compaction to a long-running conversation
3. Using tools (filesystem, shell) within the harness
4. Slot filling / guided conversations
5. Task management and structured output
6. Advanced — custom compaction pipelines, memory, sub-agents

