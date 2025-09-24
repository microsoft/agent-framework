# Workflow Getting Started Samples

## Installation

Workflow support ships with the core `agent-framework` package, so no extra installation step is required.

To install with visualization support:

```bash
pip install agent-framework[viz]
```

To export visualization images you also need to [install GraphViz](https://graphviz.org/download/).

## Samples Overview

## Foundational Concepts - Start Here

Begin with the `_start-here` folder in order. These three samples introduce the core ideas of executors, edges, agents in workflows, and streaming.

| Sample | File | Concepts |
|--------|------|----------|
| Executors and Edges | [_start-here/step1_executors_and_edges.py](./_start-here/step1_executors_and_edges.py) | Minimal workflow with basic executors and edges |
| Agents in a Workflow | [_start-here/step2_agents_in_a_workflow.py](./_start-here/step2_agents_in_a_workflow.py) | Introduces adding Agents as nodes; calling agents inside a workflow |
| Streaming (Basics) | [_start-here/step3_streaming.py](./_start-here/step3_streaming.py) | Extends workflows with event streaming |

Once comfortable with these, explore the rest of the samples below.

---

## Samples Overview (by directory)

### agents
| Sample | File | Concepts |
|---|---|---|
| Azure Chat Agents (Streaming) | [agents/azure_chat_agents_streaming.py](./agents/azure_chat_agents_streaming.py) | Add Azure agents as edges and handle streaming events |
| Custom Agent Executors | [agents/custom_agent_executors.py](./agents/custom_agent_executors.py) | Create executors to handle agent run methods |
| Foundry Chat Agents (Streaming) | [agents/foundry_chat_agents_streaming.py](./agents/foundry_chat_agents_streaming.py) | Add Foundry agents as edges and handle streaming events |
| Workflow as Agent (Reflection Pattern) | [agents/workflow_as_agent_reflection_pattern.py](./agents/workflow_as_agent_reflection_pattern.py) | Wrap a workflow so it can behave like an agent (reflection pattern) |
| Workflow as Agent + HITL | [agents/workflow_as_agent_human_in_the_loop.py](./agents/workflow_as_agent_human_in_the_loop.py) | Extend workflow-as-agent with human-in-the-loop capability |

### checkpoint
| Sample | File | Concepts |
|---|---|---|
| Checkpoint & Resume | [checkpoint/checkpoint_with_resume.py](./checkpoint/checkpoint_with_resume.py) | Create checkpoints, inspect them, and resume execution |
| Checkpoint & HITL Resume | [checkpoint/checkpoint_with_human_in_the_loop.py](./checkpoint/checkpoint_with_human_in_the_loop.py) | Combine checkpointing with human approvals and resume pending HITL requests |

### composition
| Sample | File | Concepts |
|---|---|---|
| Sub-Workflow (Basics) | [composition/sub_workflow_basics.py](./composition/sub_workflow_basics.py) | Wrap a workflow as an executor and orchestrate sub-workflows |
| Sub-Workflow: Request Interception | [composition/sub_workflow_request_interception.py](./composition/sub_workflow_request_interception.py) | Intercept and forward requests with decorators and request handling |
| Sub-Workflow: Parallel Requests | [composition/sub_workflow_parallel_requests.py](./composition/sub_workflow_parallel_requests.py) | Multi-type interception and external forwarding patterns |

### control-flow
| Sample | File | Concepts |
|---|---|---|
| Sequential Executors | [control-flow/sequential_executors.py](./control-flow/sequential_executors.py) | Sequential workflow with explicit executor setup |
| Sequential (Streaming) | [control-flow/sequential_streaming.py](./control-flow/sequential_streaming.py) | Stream events from a simple sequential run |
| Edge Condition | [control-flow/edge_condition.py](./control-flow/edge_condition.py) | Conditional routing based on agent classification |
| Switch-Case Edge Group | [control-flow/switch_case_edge_group.py](./control-flow/switch_case_edge_group.py) | Switch-case branching using classifier outputs |
| Multi-Selection Edge Group | [control-flow/multi_selection_edge_group.py](./control-flow/multi_selection_edge_group.py) | Select one or many targets dynamically (subset fan-out) |
| Simple Loop | [control-flow/simple_loop.py](./control-flow/simple_loop.py) | Feedback loop where an agent judges ABOVE/BELOW/MATCHED |

### human-in-the-loop
| Sample | File | Concepts |
|---|---|---|
| Human-In-The-Loop (Guessing Game) | [human-in-the-loop/guessing_game_with_human_input.py](./human-in-the-loop/guessing_game_with_human_input.py) | Interactive request/response prompts with a human |

### observability
| Sample | File | Concepts |
|---|---|---|
| Tracing (Basics) | [observability/tracing_basics.py](./observability/tracing_basics.py) | Use basic tracing for workflow telemetry |

### orchestration
| Sample | File | Concepts |
|---|---|---|
| Concurrent Orchestration (Default Aggregator) | [orchestration/concurrent_agents.py](./orchestration/concurrent_agents.py) | Fan-out to multiple agents; fan-in with default aggregator returning combined ChatMessages |
| Concurrent Orchestration (Custom Aggregator) | [orchestration/concurrent_custom_aggregator.py](./orchestration/concurrent_custom_aggregator.py) | Override aggregator via callback; summarize results with an LLM |
| Concurrent Orchestration (Custom Agent Executors) | [orchestration/concurrent_custom_agent_executors.py](./orchestration/concurrent_custom_agent_executors.py) | Child executors own ChatAgents; concurrent fan-out/fan-in via ConcurrentBuilder |
| Magentic Workflow (Multi-Agent) | [orchestration/magentic.py](./orchestration/magentic.py) | Orchestrate multiple agents with Magentic manager and streaming |
| Magentic + Human Plan Review | [orchestration/magentic_human_plan_update.py](./orchestration/magentic_human_plan_update.py) | Human reviews/updates the plan before execution |
| Sequential Orchestration (Agents) | [orchestration/sequential_agents.py](./orchestration/sequential_agents.py) | Chain agents sequentially with shared conversation context |
| Sequential Orchestration (Custom Executor) | [orchestration/sequential_custom_executors.py](./orchestration/sequential_custom_executors.py) | Mix agents with a summarizer that appends a compact summary |

### parallelism
| Sample | File | Concepts |
|---|---|---|
| Concurrent (Fan-out/Fan-in) | [parallelism/fan_out_fan_in_edges.py](./parallelism/fan_out_fan_in_edges.py) | Dispatch to multiple executors and aggregate results |
| Aggregate Results of Different Types | [parallelism/aggregate_results_of_different_types.py](./parallelism/aggregate_results_of_different_types.py) | Handle results of different types from multiple concurrent executors |
| Map-Reduce with Visualization | [parallelism/map_reduce_and_visualization.py](./parallelism/map_reduce_and_visualization.py) | Fan-out/fan-in pattern with diagram export |

### state-management
| Sample | File | Concepts |
|---|---|---|
| Shared States | [state-management/shared_states_with_agents.py](./state-management/shared_states_with_agents.py) | Store in shared state once and later reuse across agents |

### visualization
| Sample | File | Concepts |
|---|---|---|
| Concurrent with Visualization | [visualization/concurrent_with_visualization.py](./visualization/concurrent_with_visualization.py) | Fan-out/fan-in workflow with diagram export |

### resources
- Sample text inputs used by certain workflows:
  - [resources/long_text.txt](./resources/long_text.txt)
  - [resources/email.txt](./resources/email.txt)
  - [resources/spam.txt](./resources/spam.txt)
  - [resources/ambiguous_email.txt](./resources/ambiguous_email.txt)

Notes
- Agent-based samples use provider SDKs (Azure/OpenAI, etc.). Ensure credentials are configured, or adapt agents accordingly.

Sequential orchestration uses a few small adapter nodes for plumbing:
- "input-conversation" normalizes input to `list[ChatMessage]`
- "to-conversation:<participant>" converts agent responses into the shared conversation
- "complete" publishes the final `WorkflowOutputEvent`
These may appear in event streams (ExecutorInvoke/Completed). They’re analogous to
concurrent’s dispatcher and aggregator and can be ignored if you only care about agent activity.

### Environment Variables

- **AzureChatClient**: Set Azure OpenAI environment variables as documented [here](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/chat_client/README.md#environment-variables).  
  These variables are required for samples that construct `AzureChatClient`

- **OpenAI** (used in orchestration samples):  
  - [OpenAIChatClient env vars](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_chat_client/README.md)  
  - [OpenAIResponsesClient env vars](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_responses_client/README.md)
