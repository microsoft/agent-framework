# Workflow Getting Started Samples

## Installation

To install the base `agent_framework.workflow` package, please run:

```bash
pip install agent-framework-workflow
```

You can install the workflow package with visualization dependency:

```bash
pip install agent-framework-workflow[viz]
```

To export visualization images you also need to [install GraphViz](https://graphviz.org/download/).

## Samples Overview

## Foundational Concepts - Start Here

Begin with the `foundational` folder in order. These three samples introduce the core ideas of executors, edges, agents in workflows, and streaming.

| Sample | File | Concepts |
|--------|------|----------|
| Executors and Edges | [foundational/step1_executors_and_edges.py](./foundational/step1_executors_and_edges.py) | Minimal workflow with basic executors and edges |
| Agents in a Workflow | [foundational/step2_agents_in_a_workflow.py](./foundational/step2_agents_in_a_workflow.py) | Introduces `AgentExecutor`; calling agents inside a workflow |
| Streaming | [foundational/step3_streaming.py](./foundational/step3_streaming.py) | Extends workflows with event streaming |

Once comfortable with these, explore the rest of the samples.

---

## Samples Overview (by directory)

### agents
| Sample | File | Concepts |
|---|---|---|
| Azure Chat Agents Streaming | [agents/azure_chat_agents_streaming.py](./agents/azure_chat_agents_streaming.py) | Directly adds Azure agents as edges and handling streaming events |
| Custom Agent Executors | [agents/custom_agent_executors.py](./agents/custom_agent_executors.py) | Create executors to handle agent run methods |
| Foundry Chat Agents Streaming | [agents/foundry_chat_agents_streaming.py](./agents/foundry_chat_agents_streaming.py) | Directly adds Foundry agents as edges and handling streaming events |
| Workflow as Agent | [ai_agent/workflow_as_agent.py](./agents/workflow_as_agent.py) | Wrap a workflow so it can behave like an agent |
| Workflow as Agent + HITL | [ai_agent/workflow_as_agent_human_in_the_loop.py](./agents/workflow_as_agent_human_in_the_loop.py) | Extend workflow-as-agent with human-in-the-loop capability |

### checkpoint
| Sample | File | Concepts |
|---|---|---|
| Checkpoint & Resume | [checkpoint/checkpoint_with_resume.py](./checkpoint/checkpoint_with_resume.py) | Create checkpoints, inspect them, and resume execution |

### conditional_edges
| Sample | File | Concepts |
|---|---|---|
| Edge Condition | [conditional_edges/edge_condition.py](./conditional_edges/edge_condition.py) | Conditional routing based on agent classification |
| Switch-Case Edge Group | [conditional_edges/switch_case_edge_group.py](./conditional_edges/switch_case_edge_group.py) | Switch-case branching using classifier outputs |
| Multi-Selection Edge Group | [conditional_edges/multi_selection_edge_group.py](./conditional_edges/multi_selection_edge_group.py) | Select one or many targets dynamically (subset fan-out) |

### fan_out_fan_in
| Sample | File | Concepts |
|---|---|---|
| Concurrent (Fan-out/Fan-in) | [fan_out_fan_in/fan_out_fan_in_edges.py](./fan_out_fan_in/fan_out_fan_in_edges.py) | Dispatch to multiple executors and aggregate results |
| Map-Reduce with Visualization | [fan_out_fan_in/map_reduce_and_visualization.py](./fan_out_fan_in/map_reduce_and_visualization.py) | Fan-out/fan-in pattern with GraphViz/diagram export |

### human_in_the_loop
| Sample | File | Concepts |
|---|---|---|
| Human-In-The-Loop (Guessing Game) | [human_in_the_loop/guessing_game_with_human_input.py](./human_in_the_loop/guessing_game_with_human_input.py) | Interactive request/response prompts with a human |

### loop
| Sample | File | Concepts |
|---|---|---|
| Simple Loop | [loop/simple_loop.py](./loop/simple_loop.py) | Feedback loop where an agent judges ABOVE/BELOW/MATCHED |

### orchestration
| Sample | File | Concepts |
|---|---|---|
| Magentic Workflow (Multi-Agent) | [orchestration/magentic.py](./orchestration/magentic.py) | Orchestrate multiple agents with Magentic manager and streaming |
| Magentic + Human Plan Review | [orchestration/magentic_human_plan_update.py](./orchestration/magentic_human_plan_update.py) | Human reviews/updates the plan before execution |

### sequential
| Sample | File | Concepts |
|---|---|---|
| Sequential Executors | [sequential/sequential_executors.py](./sequential/sequential_executors.py) | Sequential workflow with explicit executor setup |
| Sequential (Streaming) | [sequential/sequential_streaming.py](./sequential/sequential_streaming.py) | Stream events from a simple sequential run |

### shared_states
| Sample | File | Concepts |
|---|---|---|
| Shared States | [shared_states/shared_states_with_agents.py](./shared_states/shared_states_with_agents.py) | Store in shared state once and later reuse across agents |

### sub_workflow
| Sample | File | Concepts |
|---|---|---|
| Sub-Workflow (Basics) | [sub_workflow/sub_workflow_basics.py](./sub_workflow/sub_workflow.py) | Wrap a workflow as an executor and orchestrate sub-workflows |
| Sub-Workflow: Request Interception | [sub_workflow/sub_workflow_request_interception.py](./sub_workflow/sub_workflow_request_interception.py) | Intercept/forward requests with decorators and request handling |
| Sub-Workflow: Parallel Requests | [sub_workflow/sub_workflow_parallel_requests.py](./sub_workflow/sub_workflow_parallel_requests.py) | Multi-type interception and external forwarding patterns |

### tracing
| Sample | File | Concepts |
|---|---|---|
| Tracing (Basics) | [tracing/tracing_basics.py](./tracing/tracing_basics.py) | Use basic tracing for workflow telemetry |

### visualization
| Sample | File | Concepts |
|---|---|---|
| Concurrent with Visualization | [visualization/concurrent_with_visualization.py](./visualization/concurrent_with_visualization.py) | Fan-out/fan-in workflow with diagram export |

Notes
- Agent‑based samples use provider SDKs (Azure/OpenAI, etc.). Ensure credentials are configured, or adapt agents accordingly.

### Environment Variables

- **AzureChatClient**: Set Azure OpenAI environment variables as documented [here](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/chat_client/README.md#environment-variables).  
  These variables are required for samples that construct `AzureChatClient`

- **OpenAI** (used in orchestration samples):  
  - [OpenAIChatClient env vars](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_chat_client/README.md)  
  - [OpenAIResponsesClient env vars](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_responses_client/README.md)
