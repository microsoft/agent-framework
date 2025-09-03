# Workflow Getting Started Samples

## Installation

To install the base `workflow` package, please run:

```bash
pip install agent-framework-workflow
```

You can install the workflow package with visualization dependency:

```bash
pip install agent-framework-workflow[viz]
```

To export visualization images you also need to [install GraphViz](https://graphviz.org/download/).

## Samples Overview

| Sample | File | Concepts |
|---|---|---|
| Sequential | [step_01a_sequential.py](./step_01a_sequential.py) | Minimal sequential workflow with two executors |
| Sequential (Streaming) | [step_01b_sequential_streaming.py](./step_01b_sequential_streaming.py) | Stream events from a simple sequential run |

> Note: Samples going forward use streaming methods.

| Sample | File | Concepts |
|---|---|---|
| Agents In A Workflow | [step_02_agents_in_a_workflow.py](./step_02_agents_in_a_workflow.py) | Introduce `AgentExecutor`; call agents inside a workflow |

> The remaining samples leverage the use of at least one agent.

| Sample | File | Concepts |
|---|---|---|
| Concurrent (Fan‑out/Fan‑in) | [step_03a_concurrent.py](./step_03a_concurrent.py) | Dispatch to multiple agent executors and aggregate results |
| Concurrent + Visualization | [step_03b_concurrent_with_visualization.py](./step_03b_concurrent_with_visualization.py) | Same as 3a plus `WorkflowViz` (Mermaid/GraphViz) export |
| Edge Condition | [step_04_edge_condition.py](./step_04_edge_condition.py) | Conditional routing based on an agent’s classification |
| Shared States | [step_05_shared_states.py](./step_05_shared_states.py) | Store once in shared state; later read to call a reply agent and finalize |
| Switch‑Case Edge Group | [step_06a_switch_case_edge_group.py](./step_06a_switch_case_edge_group.py) | Switch‑case branching using an agent classifier and `Case/Default` |
| Multi‑Selection Edge Group | [step_06b_multi_selection_edge_group.py](./step_06b_multi_selection_edge_group.py) | Select one or many targets dynamically (subset fan‑out) using an agent classifier |
| Simple Loop | [step_07_simple_loop.py](./step_07_simple_loop.py) | Feedback loop where an agent judges ABOVE/BELOW/MATCHED |
| Human‑In‑The‑Loop (HITL) | [step_08_human_in_the_loop.py](./step_08_human_in_the_loop.py) | Simple request/response prompts to a human (guessing game) |
| Checkpoint & Resume | [step_09_checkpoint.py](./step_09_checkpoint.py) | Create checkpoints, inspect them, and resume from a selected point |
| Sub‑Workflow (Basics) | [step_10a_sub_workflow.py](./step_10a_sub_workflow.py) | Wrap a workflow as an executor and orchestrate sub‑workflows |
| Sub‑Workflow: Interception | [step_10b_sub_workflow_request_interception.py](./step_10b_sub_workflow_request_interception.py) | Intercept/forward requests with `@intercepts_request` and `RequestResponse` |
| Sub‑Workflow: Parallel Requests | [step_10c_sub_workflow_parallel_requests.py](./step_10c_sub_workflow_parallel_requests.py) | Proper multi‑type interception and external forwarding patterns |
| Magentic Workflow (Multi‑Agent) | [step_11a_magentic.py](./step_11a_magentic.py) | Orchestrate multiple agents with Magentic manager and streaming callbacks |
| Magentic + Human Plan Review | [step_11b_magentic_human_plan_update.py](./step_11b_magentic_human_plan_update.py) | Human reviews/updates the plan before execution via request/response |

Notes
- Agent‑based samples use provider SDKs (Azure/OpenAI, etc.). Ensure credentials are configured, or adapt agents accordingly.

### Environment Variables

- AzureChatClient: set Azure OpenAI environment variables as documented here:
  https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/chat_client/README.md#environment-variables
  These variables are required for samples that construct `AzureChatClient` (e.g., 02, 03a, 03b, 04–07, 08, 09).

- OpenAI (used in step 11):
  - OpenAIChatClient env vars: https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_chat_client/README.md
  - OpenAIResponsesClient env vars: https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_responses_client/README.md
