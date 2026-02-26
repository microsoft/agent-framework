# Workflows Getting Started Samples

## Installation

Microsoft Agent Framework Workflows support ships with the core `agent-framework` or `agent-framework-core` package, so no extra installation step is required.

To install with visualization support:

```bash
pip install agent-framework[viz] --pre
```

To export visualization images you also need to [install GraphViz](https://graphviz.org/download/).

## Samples Overview

## Foundational Concepts - Start Here

Begin with the `_start-here` folder in order. These three samples introduce the core ideas of executors, edges, agents in workflows, and streaming.

| Sample               | File                                                                                      | Concepts                                                            |
| -------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Executors and Edges  | [\_start-here/step1_executors_and_edges.py](./_start-here/step1_executors_and_edges.py)   | Minimal workflow with basic executors and edges                     |
| Agents in a Workflow | [\_start-here/step2_agents_in_a_workflow.py](./_start-here/step2_agents_in_a_workflow.py) | Introduces adding Agents as nodes; calling agents inside a workflow |
| Streaming (Basics)   | [\_start-here/step3_streaming.py](./_start-here/step3_streaming.py)                       | Extends workflows with event streaming                              |

Once comfortable with these, explore the rest of the samples below.

---

## Samples Overview (by directory)

### agents

| Sample                                 | File                                                                                                           | Concepts                                                                                             |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Azure Chat Agents (Streaming)          | [agents/azure_chat_agents_streaming.py](./agents/azure_chat_agents_streaming.py)                               | Add Azure Chat agents as edges and handle streaming events                                           |
| Azure AI Agents (Streaming)            | [agents/azure_ai_agents_streaming.py](./agents/azure_ai_agents_streaming.py)                                   | Add Azure AI agents as edges and handle streaming events                                             |
| Azure AI Agents (Shared Thread)        | [agents/azure_ai_agents_with_shared_session.py](./agents/azure_ai_agents_with_shared_session.py)                 | Share a common message session between multiple Azure AI agents in a workflow                        |
| Custom Agent Executors                 | [agents/custom_agent_executors.py](./agents/custom_agent_executors.py)                                         | Create executors to handle agent run methods                                                         |
| Workflow as Agent (Reflection Pattern) | [agents/workflow_as_agent_reflection_pattern.py](./agents/workflow_as_agent_reflection_pattern.py)             | Wrap a workflow so it can behave like an agent (reflection pattern)                                  |
| Workflow as Agent + HITL               | [agents/workflow_as_agent_human_in_the_loop.py](./agents/workflow_as_agent_human_in_the_loop.py)               | Extend workflow-as-agent with human-in-the-loop capability                                           |
| Workflow as Agent with Session         | [agents/workflow_as_agent_with_session.py](./agents/workflow_as_agent_with_session.py)                           | Use AgentSession to maintain conversation history across workflow-as-agent invocations                |
| Workflow as Agent kwargs               | [agents/workflow_as_agent_kwargs.py](./agents/workflow_as_agent_kwargs.py)                                     | Pass custom context (data, user tokens) via kwargs through workflow.as_agent() to @ai_function tools |

### checkpoint

| Sample                         | File                                                                                                                       | Concepts                                                                                           |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Checkpoint & Resume            | [checkpoint/checkpoint_with_resume.py](./checkpoint/checkpoint_with_resume.py)                                             | Create checkpoints, inspect them, and resume execution                                             |
| Checkpoint & HITL Resume       | [checkpoint/checkpoint_with_human_in_the_loop.py](./checkpoint/checkpoint_with_human_in_the_loop.py)                       | Combine checkpointing with human approvals and resume pending HITL requests                        |
| Checkpointed Sub-Workflow      | [checkpoint/sub_workflow_checkpoint.py](./checkpoint/sub_workflow_checkpoint.py)                                           | Save and resume a sub-workflow that pauses for human approval                                      |
| Handoff + Tool Approval Resume | [orchestrations/handoff_with_tool_approval_checkpoint_resume.py](./orchestrations/handoff_with_tool_approval_checkpoint_resume.py) | Handoff workflow that captures tool-call approvals in checkpoints and resumes with human decisions |
| Workflow as Agent Checkpoint   | [checkpoint/workflow_as_agent_checkpoint.py](./checkpoint/workflow_as_agent_checkpoint.py)                                 | Enable checkpointing when using workflow.as_agent() with checkpoint_storage parameter              |

### composition

| Sample                             | File                                                                                                   | Concepts                                                                                      |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| Sub-Workflow (Basics)              | [composition/sub_workflow_basics.py](./composition/sub_workflow_basics.py)                             | Wrap a workflow as an executor and orchestrate sub-workflows                                  |
| Sub-Workflow: Request Interception | [composition/sub_workflow_request_interception.py](./composition/sub_workflow_request_interception.py) | Intercept and forward sub-workflow requests using @handler for SubWorkflowRequestMessage      |
| Sub-Workflow: Parallel Requests    | [composition/sub_workflow_parallel_requests.py](./composition/sub_workflow_parallel_requests.py)       | Multiple specialized interceptors handling different request types from same sub-workflow     |
| Sub-Workflow: kwargs Propagation   | [composition/sub_workflow_kwargs.py](./composition/sub_workflow_kwargs.py)                             | Pass custom context (user tokens, config) from parent workflow through to sub-workflow agents |

### control-flow

| Sample                     | File                                                                                       | Concepts                                                |
| -------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| Sequential Executors       | [control-flow/sequential_executors.py](./control-flow/sequential_executors.py)             | Sequential workflow with explicit executor setup        |
| Sequential (Streaming)     | [control-flow/sequential_streaming.py](./control-flow/sequential_streaming.py)             | Stream events from a simple sequential run              |
| Edge Condition             | [control-flow/edge_condition.py](./control-flow/edge_condition.py)                         | Conditional routing based on agent classification       |
| Switch-Case Edge Group     | [control-flow/switch_case_edge_group.py](./control-flow/switch_case_edge_group.py)         | Switch-case branching using classifier outputs          |
| Multi-Selection Edge Group | [control-flow/multi_selection_edge_group.py](./control-flow/multi_selection_edge_group.py) | Select one or many targets dynamically (subset fan-out) |
| Simple Loop                | [control-flow/simple_loop.py](./control-flow/simple_loop.py)                               | Feedback loop where an agent judges ABOVE/BELOW/MATCHED |
| Workflow Cancellation      | [control-flow/workflow_cancellation.py](./control-flow/workflow_cancellation.py)           | Cancel a running workflow using asyncio tasks           |

### human-in-the-loop

| Sample                                     | File                                                                                                         | Concepts                                                                                              |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Human-In-The-Loop (Guessing Game)          | [human-in-the-loop/guessing_game_with_human_input.py](./human-in-the-loop/guessing_game_with_human_input.py) | Interactive request/response prompts with a human via `ctx.request_info()`                            |
| Agents with Approval Requests in Workflows | [human-in-the-loop/agents_with_approval_requests.py](./human-in-the-loop/agents_with_approval_requests.py)   | Agents that create approval requests during workflow execution and wait for human approval to proceed |
| Agents with Declaration-Only Tools         | [human-in-the-loop/agents_with_declaration_only_tools.py](./human-in-the-loop/agents_with_declaration_only_tools.py) | Workflow pauses when agent calls a client-side tool (`func=None`), caller supplies the result         |

Builder-oriented request-info samples are maintained in the orchestration sample set
(sequential, concurrent, and group-chat builder variants).

### tool-approval

Builder-based tool approval samples are maintained in the orchestration sample set.

### observability

| Sample                   | File                                                                                   | Concepts                                                                                                               |
| ------------------------ | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Executor I/O Observation | [observability/executor_io_observation.py](./observability/executor_io_observation.py) | Observe executor input/output data via executor_invoked events (type='executor_invoked') and executor_completed events (type='executor_completed') without modifying executor code |

For additional observability samples in Agent Framework, see the [observability concept samples](../02-agents/observability/README.md). The [workflow observability sample](../02-agents/observability/workflow_observability.py) demonstrates integrating observability into workflows.

### orchestration

Orchestration-focused samples (Sequential, Concurrent, Handoff, GroupChat, Magentic), including builder-based
`workflow.as_agent(...)` variants, are documented in the [orchestrations](./orchestrations/README.md) directory.

### parallelism

| Sample                               | File                                                                                                         | Concepts                                                             |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| Concurrent (Fan-out/Fan-in)          | [parallelism/fan_out_fan_in_edges.py](./parallelism/fan_out_fan_in_edges.py)                                 | Dispatch to multiple executors and aggregate results                 |
| Aggregate Results of Different Types | [parallelism/aggregate_results_of_different_types.py](./parallelism/aggregate_results_of_different_types.py) | Handle results of different types from multiple concurrent executors |
| Map-Reduce with Visualization        | [parallelism/map_reduce_and_visualization.py](./parallelism/map_reduce_and_visualization.py)                 | Fan-out/fan-in pattern with diagram export                           |

### state-management

| Sample                           | File                                                                                             | Concepts                                                          |
| -------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| State with Agents                | [state-management/state_with_agents.py](./state-management/state_with_agents.py) | Store in state once and later reuse across agents                 |
| Workflow Kwargs (Custom Context) | [state-management/workflow_kwargs.py](./state-management/workflow_kwargs.py)                     | Pass custom context (data, user tokens) via kwargs to `@tool` tools |

### visualization

| Sample                        | File                                                                                               | Concepts                                    |
| ----------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| Concurrent with Visualization | [visualization/concurrent_with_visualization.py](./visualization/concurrent_with_visualization.py) | Fan-out/fan-in workflow with diagram export |

### declarative

YAML-based declarative workflows allow you to define multi-agent orchestration patterns without writing Python code. See the [declarative workflows README](./declarative/README.md) for more details on YAML workflow syntax and available actions.

| Sample | File | Concepts |
|---|---|---|
| Agent to Function Tool | [declarative/agent_to_function_tool/](./declarative/agent_to_function_tool/) | Chain agent output to InvokeFunctionTool actions |
| Conditional Workflow | [declarative/conditional_workflow/](./declarative/conditional_workflow/) | Nested conditional branching based on user input |
| Customer Support | [declarative/customer_support/](./declarative/customer_support/) | Multi-agent customer support with routing |
| Deep Research | [declarative/deep_research/](./declarative/deep_research/) | Research workflow with planning, searching, and synthesis |
| Function Tools | [declarative/function_tools/](./declarative/function_tools/) | Invoking Python functions from declarative workflows |
| Human-in-Loop | [declarative/human_in_loop/](./declarative/human_in_loop/) | Interactive workflows that request user input |
| Invoke Function Tool | [declarative/invoke_function_tool/](./declarative/invoke_function_tool/) | Call registered Python functions with InvokeFunctionTool |
| Marketing | [declarative/marketing/](./declarative/marketing/) | Marketing content generation workflow |
| Simple Workflow | [declarative/simple_workflow/](./declarative/simple_workflow/) | Basic workflow with variable setting, conditionals, and loops |
| Student Teacher | [declarative/student_teacher/](./declarative/student_teacher/) | Student-teacher interaction pattern |

### resources

- Sample text inputs used by certain workflows:
  - [resources/long_text.txt](./resources/long_text.txt)
  - [resources/email.txt](./resources/email.txt)
  - [resources/spam.txt](./resources/spam.txt)
  - [resources/ambiguous_email.txt](./resources/ambiguous_email.txt)

Notes

- Agent-based samples use provider SDKs (Azure/OpenAI, etc.). Ensure credentials are configured, or adapt agents accordingly.

Sequential orchestration uses a few small adapter nodes for plumbing:

- "input-conversation" normalizes input to `list[Message]`
- "to-conversation:<participant>" converts agent responses into the shared conversation
- "complete" publishes the final output event (type='output')
  These may appear in event streams (executor_invoked/executor_completed). They're analogous to
  concurrent’s dispatcher and aggregator and can be ignored if you only care about agent activity.

### AzureOpenAIResponsesClient vs AzureAIAgent

Workflow and orchestration samples use `AzureOpenAIResponsesClient` rather than the CRUD-style `AzureAIAgent` client. The key difference:

- **`AzureOpenAIResponsesClient`** — A lightweight client that uses the underlying Agent Service V2 (Responses API) for non-CRUD-style agents. Orchestrations use this client because agents are created locally and do not require server-side lifecycle management (create/update/delete). This is the recommended client for orchestration patterns (Sequential, Concurrent, Handoff, GroupChat, Magentic).

- **`AzureAIAgent`** — A CRUD-style client for server-managed agents. Use this when you need persistent, server-side agent definitions with features like file search, code interpreter sessions, or thread management provided by the Azure AI Agent Service.

### Environment Variables

Workflow samples that use `AzureOpenAIResponsesClient` expect:

- `AZURE_AI_PROJECT_ENDPOINT` (Azure AI Foundry Agent Service (V2) project endpoint)
- `AZURE_AI_MODEL_DEPLOYMENT_NAME` (model deployment name)

These values are passed directly into the client constructor via `os.getenv()` in sample code.
