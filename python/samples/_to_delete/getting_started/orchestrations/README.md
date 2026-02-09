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

## Samples Overview

| Sample                                            | File                                                                                 | Concepts                                                                                                         |
| ------------------------------------------------- | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Concurrent Orchestration (Default Aggregator)     | [concurrent_agents.py](./concurrent_agents.py)                                       | Fan-out to multiple agents; fan-in with default aggregator returning combined ChatMessages                       |
| Concurrent Orchestration (Custom Aggregator)      | [concurrent_custom_aggregator.py](./concurrent_custom_aggregator.py)                 | Override aggregator via callback; summarize results with an LLM                                                  |
| Concurrent Orchestration (Custom Agent Executors) | [concurrent_custom_agent_executors.py](./concurrent_custom_agent_executors.py)       | Child executors own ChatAgents; concurrent fan-out/fan-in via ConcurrentBuilder                                  |
| Concurrent Orchestration (Participant Factory)    | [concurrent_participant_factory.py](./concurrent_participant_factory.py)             | Use participant factories for state isolation between workflow instances                                         |
| Group Chat with Agent Manager                     | [group_chat_agent_manager.py](./group_chat_agent_manager.py)                         | Agent-based manager using `with_orchestrator(agent=)` to select next speaker                                     |
| Group Chat Philosophical Debate                   | [group_chat_philosophical_debate.py](./group_chat_philosophical_debate.py)           | Agent manager moderates long-form, multi-round debate across diverse participants                                |
| Group Chat with Simple Function Selector          | [group_chat_simple_selector.py](./group_chat_simple_selector.py)                     | Group chat with a simple function selector for next speaker                                                      |
| Handoff (Simple)                                  | [handoff_simple.py](./handoff_simple.py)                                             | Single-tier routing: triage agent routes to specialists, control returns to user after each specialist response  |
| Handoff (Autonomous)                              | [handoff_autonomous.py](./handoff_autonomous.py)                                     | Autonomous mode: specialists iterate independently until invoking a handoff tool using `.with_autonomous_mode()` |
| Handoff (Participant Factory)                     | [handoff_participant_factory.py](./handoff_participant_factory.py)                   | Use participant factories for state isolation between workflow instances                                         |
| Handoff with Code Interpreter                     | [handoff_with_code_interpreter_file.py](./handoff_with_code_interpreter_file.py)     | Retrieve file IDs from code interpreter output in handoff workflow                                               |
| Magentic Workflow (Multi-Agent)                   | [magentic.py](./magentic.py)                                                         | Orchestrate multiple agents with Magentic manager and streaming                                                  |
| Magentic + Human Plan Review                      | [magentic_human_plan_review.py](./magentic_human_plan_review.py)                     | Human reviews/updates the plan before execution                                                                  |
| Magentic + Checkpoint Resume                      | [magentic_checkpoint.py](./magentic_checkpoint.py)                                   | Resume Magentic orchestration from saved checkpoints                                                             |
| Sequential Orchestration (Agents)                 | [sequential_agents.py](./sequential_agents.py)                                       | Chain agents sequentially with shared conversation context                                                       |
| Sequential Orchestration (Custom Executor)        | [sequential_custom_executors.py](./sequential_custom_executors.py)                   | Mix agents with a summarizer that appends a compact summary                                                      |
| Sequential Orchestration (Participant Factories)  | [sequential_participant_factory.py](./sequential_participant_factory.py)             | Use participant factories for state isolation between workflow instances                                         |

## Tips

**Magentic checkpointing tip**: Treat `MagenticBuilder.participants` keys as stable identifiers. When resuming from a checkpoint, the rebuilt workflow must reuse the same participant names; otherwise the checkpoint cannot be applied and the run will fail fast.

**Handoff workflow tip**: Handoff workflows maintain the full conversation history including any `ChatMessage.additional_properties` emitted by your agents. This ensures routing metadata remains intact across all agent transitions. For specialist-to-specialist handoffs, use `.add_handoff(source, targets)` to configure which agents can route to which others with a fluent, type-safe API.

**Sequential orchestration note**: Sequential orchestration uses a few small adapter nodes for plumbing:
- `input-conversation` normalizes input to `list[ChatMessage]`
- `to-conversation:<participant>` converts agent responses into the shared conversation
- `complete` publishes the final output event (type='output')

These may appear in event streams (executor_invoked/executor_completed). They're analogous to concurrent's dispatcher and aggregator and can be ignored if you only care about agent activity.

## Environment Variables

- **AzureOpenAIChatClient**: Set Azure OpenAI environment variables as documented [here](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/chat_client/README.md#environment-variables).

- **OpenAI** (used in some orchestration samples):
  - [OpenAIChatClient env vars](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_chat_client/README.md)
  - [OpenAIResponsesClient env vars](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_responses_client/README.md)
