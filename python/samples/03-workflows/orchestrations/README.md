# Orchestration Getting Started Samples

## Installation

The orchestrations package is included when you install `agent-framework` (which pulls in all optional packages):

```bash
pip install agent-framework
```

Or install the orchestrations package directly:

```bash
pip install agent-framework-orchestrations
```

Orchestration builders are available via the `agent_framework.orchestrations` submodule:

```python
from agent_framework.orchestrations import (
    SequentialBuilder,
    ConcurrentBuilder,
    HandoffBuilder,
    GroupChatBuilder,
    MagenticBuilder,
)
```

## Samples Overview (by directory)

### concurrent

| Sample                                            | File                                                                                                 | Concepts                                                                                                    |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Concurrent Orchestration (Default Aggregator)     | [concurrent_agents.py](./concurrent_agents.py)                                 | Fan-out to multiple agents; fan-in with default aggregator returning combined Messages                     |
| Concurrent Orchestration (Custom Aggregator)      | [concurrent_custom_aggregator.py](./concurrent_custom_aggregator.py)           | Override aggregator via callback; summarize results with an LLM                                            |
| Concurrent Orchestration (Custom Agent Executors) | [concurrent_custom_agent_executors.py](./concurrent_custom_agent_executors.py) | Child executors own Agents; concurrent fan-out/fan-in via ConcurrentBuilder                               |
| Concurrent Orchestration as Agent                 | [concurrent_workflow_as_agent.py](../agents/concurrent_workflow_as_agent.py)           | Build a ConcurrentBuilder workflow and expose it as an agent via `workflow.as_agent(...)`                 |
| Tool Approval with ConcurrentBuilder              | [concurrent_builder_tool_approval.py](../tool-approval/concurrent_builder_tool_approval.py)   | Require human approval for sensitive tools across concurrent participants                                  |
| ConcurrentBuilder Request Info                    | [concurrent_request_info.py](../human-in-the-loop/concurrent_request_info.py)                     | Review concurrent agent outputs before aggregation using `.with_request_info()`                            |

### sequential

| Sample                                     | File                                                                                                 | Concepts                                                                                      |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Sequential Orchestration (Agents)          | [sequential_agents.py](./sequential_agents.py)                                 | Chain agents sequentially with shared conversation context                                   |
| Sequential Orchestration (Custom Executor) | [sequential_custom_executors.py](./sequential_custom_executors.py)             | Mix agents with a summarizer that appends a compact summary                                 |
| Sequential Orchestration as Agent          | [sequential_workflow_as_agent.py](../agents/sequential_workflow_as_agent.py)           | Build a SequentialBuilder workflow and expose it as an agent via `workflow.as_agent(...)`   |
| Tool Approval with SequentialBuilder       | [sequential_builder_tool_approval.py](../tool-approval/sequential_builder_tool_approval.py)   | Require human approval for sensitive tools in SequentialBuilder workflows                    |
| SequentialBuilder Request Info             | [sequential_request_info.py](../human-in-the-loop/sequential_request_info.py)                     | Request info for agent responses mid-orchestration using `.with_request_info()`             |

### group-chat

| Sample                               | File                                                                                                         | Concepts                                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Group Chat with Agent Manager        | [group_chat_agent_manager.py](./group_chat_agent_manager.py)                           | Agent-based manager using `with_orchestrator(agent=)` to select next speaker                        |
| Group Chat Philosophical Debate      | [group_chat_philosophical_debate.py](./group_chat_philosophical_debate.py)           | Agent manager moderates long-form, multi-round debate across diverse participants                    |
| Group Chat with Simple Selector      | [group_chat_simple_selector.py](./group_chat_simple_selector.py)                       | Group chat with a simple function selector for next speaker                                          |
| Group Chat Orchestration as Agent    | [group_chat_workflow_as_agent.py](../agents/group_chat_workflow_as_agent.py)                   | Build a GroupChatBuilder workflow and wrap it as an agent for composition                            |
| Tool Approval with GroupChatBuilder  | [group_chat_builder_tool_approval.py](../tool-approval/group_chat_builder_tool_approval.py)           | Require human approval for sensitive tools in group chat orchestration                               |
| GroupChatBuilder Request Info        | [group_chat_request_info.py](../human-in-the-loop/group_chat_request_info.py)                           | Steer group discussions with periodic guidance using `.with_request_info()`                          |

### handoff

| Sample                                   | File                                                                                                             | Concepts                                                                                                         |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Handoff (Simple)                         | [handoff_simple.py](./handoff_simple.py)                                                         | Single-tier routing: triage agent routes to specialists, control returns to user after each specialist response |
| Handoff (Autonomous)                     | [handoff_autonomous.py](./handoff_autonomous.py)                                                 | Autonomous mode: specialists iterate independently until invoking a handoff tool using `.with_autonomous_mode()` |
| Handoff with Code Interpreter            | [handoff_with_code_interpreter_file.py](./handoff_with_code_interpreter_file.py)                 | Retrieve file IDs from code interpreter output in handoff workflow                                               |
| Handoff with Tool Approval + Checkpoint  | [handoff_with_tool_approval_checkpoint_resume.py](./handoff_with_tool_approval_checkpoint_resume.py) | Capture tool-approval decisions in checkpoints and resume from persisted state                                  |
| Handoff Orchestration as Agent           | [handoff_workflow_as_agent.py](../agents/handoff_workflow_as_agent.py)                                   | Build a HandoffBuilder workflow and expose it as an agent, including HITL request/response flow                |

### magentic

| Sample                       | File                                                                                       | Concepts                                                              |
| ---------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| Magentic Workflow            | [magentic.py](./magentic.py)                                             | Orchestrate multiple agents with a Magentic manager and streaming     |
| Magentic + Human Plan Review | [magentic_human_plan_review.py](./magentic_human_plan_review.py)       | Human reviews or updates the plan before execution                    |
| Magentic + Checkpoint Resume | [magentic_checkpoint.py](./magentic_checkpoint.py)                     | Resume Magentic orchestration from saved checkpoints                  |
| Magentic Orchestration as Agent | [magentic_workflow_as_agent.py](../agents/magentic_workflow_as_agent.py)    | Build a MagenticBuilder workflow and reuse it as an agent             |

## Tips

**Participant output selection**: Orchestration builders use participant-oriented names for Workflow Output selection.
Use `output_from=[...]` when participant responses should be Workflow Output (`type='output'` events), and
`intermediate_output_from=[...]` when participant responses should be Intermediate Output (`type='intermediate'`
events). `output_from` is an allow-list for Workflow Output, not a routing rule for every other participant output.
Unselected participant responses are hidden unless `intermediate_output_from` selects them.

| Selection | Workflow Output | Intermediate Output | Hidden payloads |
| --- | --- | --- | --- |
| Omit both selections | Builder default Workflow Output contract | None | Builder-specific non-output participant payloads |
| `output_from="all"` | Every output-capable participant | None | None |
| `output_from=[writer]` | Only `writer` | None | All other participant payloads |
| `output_from=[writer], intermediate_output_from="all_other"` | Only `writer` | Every output-capable participant not selected by `output_from` | None |
| `intermediate_output_from="all_other"` | None, except builder-internal default output executors where applicable | Every output-capable participant | Builder-internal plumbing payloads |
| `output_from=[], intermediate_output_from="all_other"` | None, except builder-internal default output executors where applicable | Every output-capable participant | Builder-internal plumbing payloads |
| `output_from=[writer], intermediate_output_from=[researcher, reviewer]` | Only `writer` | `researcher` and `reviewer` | Any other participant payloads |

Invalid selections fail at construction or build time:

| Invalid selection | Why it fails |
| --- | --- |
| `output_from="all_other"` | `"all_other"` is only valid for `intermediate_output_from` |
| `intermediate_output_from="all"` | `"all"` is only valid for `output_from` |
| The same participant in both selections | One payload cannot be both Workflow Output and Intermediate Output |
| Duplicate participant selections | Duplicates are treated as configuration errors |
| Unknown participant selections | Typos and missing participants are rejected |
| `output_from=[], intermediate_output_from=[]` | Both explicit selections are empty |

By default, Sequential keeps the last participant as Workflow Output. Concurrent, GroupChat, and Magentic keep their
synthetic aggregator/orchestrator/manager executors as Workflow Output, while participant responses stay hidden unless
selected. Handoff keeps participants as Workflow Output by default.

When an orchestration workflow is exposed via `workflow.as_agent()`, Workflow Output becomes normal text content in
the `AgentResponse`; Intermediate Output becomes `text_reasoning` content. This preserves `.text` while making
selected progress available for callers that inspect message contents.

**Magentic checkpointing tip**: Treat `MagenticBuilder.participants` keys as stable identifiers. When resuming from a checkpoint, the rebuilt workflow must reuse the same participant names; otherwise the checkpoint cannot be applied and the run will fail fast.

**Handoff workflow tip**: Handoff workflows maintain the full conversation history including any `Message.additional_properties` emitted by your agents. This ensures routing metadata remains intact across all agent transitions. For specialist-to-specialist handoffs, use `.add_handoff(source, targets)` to configure which agents can route to which others with a fluent, type-safe API.

**Handoff `require_per_service_call_history_persistence`**: All agents in a handoff workflow **must** set `require_per_service_call_history_persistence=True`. `HandoffBuilder.build()` will raise a `ValueError` if any participant is missing this flag. This is required because handoff middleware short-circuits tool calls via `MiddlewareTermination`, and without per-service-call history persistence, local history would store tool results the service never received, causing mismatches on subsequent turns.

**Sequential orchestration note**: Sequential orchestration uses a few small adapter nodes for plumbing:
- `input-conversation` normalizes input to `list[Message]`
- `to-conversation:<participant>` converts agent responses into the shared conversation
- `complete` publishes the Workflow Output event (`type='output'`)

These may appear in event streams (executor_invoked/executor_completed). They're analogous to concurrent's dispatcher and aggregator and can be ignored if you only care about agent activity.

## Why FoundryChatClient?

Orchestration samples use `FoundryChatClient` because they create agents locally and do not require
server-side lifecycle management. `FoundryChatClient` is a lightweight, project-backed client that fits
patterns like Sequential, Concurrent, Handoff, GroupChat, and Magentic.

## Environment Variables

Orchestration samples that use `FoundryChatClient` expect:

- `FOUNDRY_PROJECT_ENDPOINT` (Azure AI Foundry Agent Service (V2) project endpoint)
- `FOUNDRY_MODEL` (model deployment name)

These values are passed directly into the client constructor via `os.getenv()` in sample code.
