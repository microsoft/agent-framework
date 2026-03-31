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

**Magentic checkpointing tip**: Treat `MagenticBuilder.participants` keys as stable identifiers. When resuming from a checkpoint, the rebuilt workflow must reuse the same participant names; otherwise the checkpoint cannot be applied and the run will fail fast.

**Handoff workflow tip**: Handoff workflows maintain the full conversation history including any `Message.additional_properties` emitted by your agents. This ensures routing metadata remains intact across all agent transitions. For specialist-to-specialist handoffs, use `.add_handoff(source, targets)` to configure which agents can route to which others with a fluent, type-safe API.

**Sequential orchestration note**: Sequential orchestration uses a few small adapter nodes for plumbing:
- `input-conversation` normalizes input to `list[Message]`
- `to-conversation:<participant>` converts agent responses into the shared conversation
- `complete` publishes the final output event (type='output')

These may appear in event streams (executor_invoked/executor_completed). They're analogous to concurrent's dispatcher and aggregator and can be ignored if you only care about agent activity.

## Why AzureOpenAIResponsesClient?

Orchestration samples use `AzureOpenAIResponsesClient` rather than the CRUD-style `AzureAIAgent` client. Orchestrations create agents locally and do not require server-side lifecycle management (create/update/delete). `AzureOpenAIResponsesClient` is a lightweight client that uses the underlying Agent Service V2 (Responses API) for non-CRUD-style agents, which is ideal for orchestration patterns like Sequential, Concurrent, Handoff, GroupChat, and Magentic.

## Environment Variables

Orchestration samples that use `AzureOpenAIResponsesClient` expect:

- `AZURE_AI_PROJECT_ENDPOINT` (Azure AI Foundry Agent Service (V2) project endpoint)
- `AZURE_AI_MODEL_DEPLOYMENT_NAME` (model deployment name)

These values are passed directly into the client constructor via `os.getenv()` in sample code.
