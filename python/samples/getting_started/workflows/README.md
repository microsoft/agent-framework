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
| Azure AI Agents (Shared Thread)        | [agents/azure_ai_agents_with_shared_thread.py](./agents/azure_ai_agents_with_shared_thread.py)                 | Share a common message thread between multiple Azure AI agents in a workflow                         |
| Azure Chat Agents (Function Bridge)    | [agents/azure_chat_agents_function_bridge.py](./agents/azure_chat_agents_function_bridge.py)                   | Chain two agents with a function executor that injects external context                              |
| Azure Chat Agents (Tools + HITL)       | [agents/azure_chat_agents_tool_calls_with_feedback.py](./agents/azure_chat_agents_tool_calls_with_feedback.py) | Tool-enabled writer/editor pipeline with human feedback gating                                       |
| Custom Agent Executors                 | [agents/custom_agent_executors.py](./agents/custom_agent_executors.py)                                         | Create executors to handle agent run methods                                                         |
| Sequential Workflow as Agent           | [agents/sequential_workflow_as_agent.py](./agents/sequential_workflow_as_agent.py)                             | Build a sequential workflow orchestrating agents, then expose it as a reusable agent                 |
| Concurrent Workflow as Agent           | [agents/concurrent_workflow_as_agent.py](./agents/concurrent_workflow_as_agent.py)                             | Build a concurrent fan-out/fan-in workflow, then expose it as a reusable agent                       |
| Magentic Workflow as Agent             | [agents/magentic_workflow_as_agent.py](./agents/magentic_workflow_as_agent.py)                                 | Configure Magentic orchestration with callbacks, then expose the workflow as an agent                |
| Workflow as Agent (Reflection Pattern) | [agents/workflow_as_agent_reflection_pattern.py](./agents/workflow_as_agent_reflection_pattern.py)             | Wrap a workflow so it can behave like an agent (reflection pattern)                                  |
| Workflow as Agent + HITL               | [agents/workflow_as_agent_human_in_the_loop.py](./agents/workflow_as_agent_human_in_the_loop.py)               | Extend workflow-as-agent with human-in-the-loop capability                                           |
| Workflow as Agent with Thread          | [agents/workflow_as_agent_with_thread.py](./agents/workflow_as_agent_with_thread.py)                           | Use AgentThread to maintain conversation history across workflow-as-agent invocations                |
| Workflow as Agent kwargs               | [agents/workflow_as_agent_kwargs.py](./agents/workflow_as_agent_kwargs.py)                                     | Pass custom context (data, user tokens) via kwargs through workflow.as_agent() to @ai_function tools |
| Handoff Workflow as Agent              | [agents/handoff_workflow_as_agent.py](./agents/handoff_workflow_as_agent.py)                                   | Use a HandoffBuilder workflow as an agent with HITL via FunctionCallContent/FunctionResultContent    |

### checkpoint

| Sample                         | File                                                                                                                       | Concepts                                                                                           |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Checkpoint & Resume            | [checkpoint/checkpoint_with_resume.py](./checkpoint/checkpoint_with_resume.py)                                             | Create checkpoints, inspect them, and resume execution                                             |
| Checkpoint & HITL Resume       | [checkpoint/checkpoint_with_human_in_the_loop.py](./checkpoint/checkpoint_with_human_in_the_loop.py)                       | Combine checkpointing with human approvals and resume pending HITL requests                        |
| Checkpointed Sub-Workflow      | [checkpoint/sub_workflow_checkpoint.py](./checkpoint/sub_workflow_checkpoint.py)                                           | Save and resume a sub-workflow that pauses for human approval                                      |
| Handoff + Tool Approval Resume | [checkpoint/handoff_with_tool_approval_checkpoint_resume.py](./checkpoint/handoff_with_tool_approval_checkpoint_resume.py) | Handoff workflow that captures tool-call approvals in checkpoints and resumes with human decisions |
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
| SequentialBuilder Request Info             | [human-in-the-loop/sequential_request_info.py](./human-in-the-loop/sequential_request_info.py)               | Request info for agent responses mid-workflow using `.with_request_info()` on SequentialBuilder       |
| ConcurrentBuilder Request Info             | [human-in-the-loop/concurrent_request_info.py](./human-in-the-loop/concurrent_request_info.py)               | Review concurrent agent outputs before aggregation using `.with_request_info()` on ConcurrentBuilder  |
| GroupChatBuilder Request Info              | [human-in-the-loop/group_chat_request_info.py](./human-in-the-loop/group_chat_request_info.py)               | Steer group discussions with periodic guidance using `.with_request_info()` on GroupChatBuilder       |

### tool-approval

Tool approval samples demonstrate using `@tool(approval_mode="always_require")` to gate sensitive tool executions with human approval. These work with the high-level builder APIs.

| Sample                          | File                                                                                                     | Concepts                                                              |
| ------------------------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| SequentialBuilder Tool Approval | [tool-approval/sequential_builder_tool_approval.py](./tool-approval/sequential_builder_tool_approval.py) | Sequential workflow with tool approval gates for sensitive operations |
| ConcurrentBuilder Tool Approval | [tool-approval/concurrent_builder_tool_approval.py](./tool-approval/concurrent_builder_tool_approval.py) | Concurrent workflow with tool approvals across parallel agents        |
| GroupChatBuilder Tool Approval  | [tool-approval/group_chat_builder_tool_approval.py](./tool-approval/group_chat_builder_tool_approval.py) | Group chat workflow with tool approval for multi-agent collaboration  |

### observability

| Sample                   | File                                                                                   | Concepts                                                                                                               |
| ------------------------ | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Executor I/O Observation | [observability/executor_io_observation.py](./observability/executor_io_observation.py) | Observe executor input/output data via ExecutorInvokedEvent and ExecutorCompletedEvent without modifying executor code |

For additional observability samples in Agent Framework, see the [observability getting started samples](../observability/README.md). The [sample](../observability/workflow_observability.py) demonstrates integrating observability into workflows.

### orchestration

| Sample                                            | File                                                                                                       | Concepts                                                                                                         |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Concurrent Orchestration (Default Aggregator)     | [orchestration/concurrent_agents.py](./orchestration/concurrent_agents.py)                                 | Fan-out to multiple agents; fan-in with default aggregator returning combined ChatMessages                       |
| Concurrent Orchestration (Custom Aggregator)      | [orchestration/concurrent_custom_aggregator.py](./orchestration/concurrent_custom_aggregator.py)           | Override aggregator via callback; summarize results with an LLM                                                  |
| Concurrent Orchestration (Custom Agent Executors) | [orchestration/concurrent_custom_agent_executors.py](./orchestration/concurrent_custom_agent_executors.py) | Child executors own ChatAgents; concurrent fan-out/fan-in via ConcurrentBuilder                                  |
| Concurrent Orchestration (Participant Factory)    | [orchestration/concurrent_participant_factory.py](./orchestration/concurrent_participant_factory.py)       | Use participant factories for state isolation between workflow instances                                         |
| Group Chat with Agent Manager                     | [orchestration/group_chat_agent_manager.py](./orchestration/group_chat_agent_manager.py)                   | Agent-based manager using `with_orchestrator(agent=)` to select next speaker                                     |
| Group Chat Philosophical Debate                   | [orchestration/group_chat_philosophical_debate.py](./orchestration/group_chat_philosophical_debate.py)     | Agent manager moderates long-form, multi-round debate across diverse participants                                |
| Group Chat with Simple Function Selector          | [orchestration/group_chat_simple_selector.py](./orchestration/group_chat_simple_selector.py)               | Group chat with a simple function selector for next speaker                                                      |
| Handoff (Simple)                                  | [orchestration/handoff_simple.py](./orchestration/handoff_simple.py)                                       | Single-tier routing: triage agent routes to specialists, control returns to user after each specialist response  |
| Handoff (Autonomous)                              | [orchestration/handoff_autonomous.py](./orchestration/handoff_autonomous.py)                               | Autonomous mode: specialists iterate independently until invoking a handoff tool using `.with_autonomous_mode()` |
| Handoff (Participant Factory)                     | [orchestration/handoff_participant_factory.py](./orchestration/handoff_participant_factory.py)             | Use participant factories for state isolation between workflow instances                                         |
| Magentic Workflow (Multi-Agent)                   | [orchestration/magentic.py](./orchestration/magentic.py)                                                   | Orchestrate multiple agents with Magentic manager and streaming                                                  |
| Magentic + Human Plan Review                      | [orchestration/magentic_human_plan_review.py](./orchestration/magentic_human_plan_review.py)               | Human reviews/updates the plan before execution                                                                  |
| Magentic + Checkpoint Resume                      | [orchestration/magentic_checkpoint.py](./orchestration/magentic_checkpoint.py)                             | Resume Magentic orchestration from saved checkpoints                                                             |
| Sequential Orchestration (Agents)                 | [orchestration/sequential_agents.py](./orchestration/sequential_agents.py)                                 | Chain agents sequentially with shared conversation context                                                       |
| Sequential Orchestration (Custom Executor)        | [orchestration/sequential_custom_executors.py](./orchestration/sequential_custom_executors.py)             | Mix agents with a summarizer that appends a compact summary                                                      |
| Sequential Orchestration (Participant Factories)  | [orchestration/sequential_participant_factory.py](./orchestration/sequential_participant_factory.py)       | Use participant factories for state isolation between workflow instances                                         |

**Magentic checkpointing tip**: Treat `MagenticBuilder.participants` keys as stable identifiers. When resuming from a checkpoint, the rebuilt workflow must reuse the same participant names; otherwise the checkpoint cannot be applied and the run will fail fast.

**Handoff workflow tip**: Handoff workflows maintain the full conversation history including any
`ChatMessage.additional_properties` emitted by your agents. This ensures routing metadata remains
intact across all agent transitions. For specialist-to-specialist handoffs, use `.add_handoff(source, targets)`
to configure which agents can route to which others with a fluent, type-safe API.

### parallelism

| Sample                               | File                                                                                                         | Concepts                                                             |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| Concurrent (Fan-out/Fan-in)          | [parallelism/fan_out_fan_in_edges.py](./parallelism/fan_out_fan_in_edges.py)                                 | Dispatch to multiple executors and aggregate results                 |
| Aggregate Results of Different Types | [parallelism/aggregate_results_of_different_types.py](./parallelism/aggregate_results_of_different_types.py) | Handle results of different types from multiple concurrent executors |
| Map-Reduce with Visualization        | [parallelism/map_reduce_and_visualization.py](./parallelism/map_reduce_and_visualization.py)                 | Fan-out/fan-in pattern with diagram export                           |

### state-management

| Sample                           | File                                                                                             | Concepts                                                                   |
| -------------------------------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| Shared States                    | [state-management/shared_states_with_agents.py](./state-management/shared_states_with_agents.py) | Store in shared state once and later reuse across agents                   |
| Workflow Kwargs (Custom Context) | [state-management/workflow_kwargs.py](./state-management/workflow_kwargs.py)                     | Pass custom context (data, user tokens) via kwargs to `@ai_function` tools |

=======
| Sample | File | Concepts |
|---|---|---|
| Shared States | [state-management/shared_states_with_agents.py](./state-management/shared_states_with_agents.py) | Store in shared state once and later reuse across agents |
| Workflow Kwargs (Custom Context) | [state-management/workflow_kwargs.py](./state-management/workflow_kwargs.py) | Pass custom context (data, user tokens) via kwargs to `@tool` tools |

### visualization

| Sample                        | File                                                                                               | Concepts                                    |
| ----------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| Concurrent with Visualization | [visualization/concurrent_with_visualization.py](./visualization/concurrent_with_visualization.py) | Fan-out/fan-in workflow with diagram export |

### declarative

YAML-based declarative workflows allow you to define multi-agent orchestration patterns without writing Python code. See the [declarative workflows README](./declarative/README.md) for more details on YAML workflow syntax and available actions.

| Sample               | File                                                                     | Concepts                                                      |
| -------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------- |
| Conditional Workflow | [declarative/conditional_workflow/](./declarative/conditional_workflow/) | Nested conditional branching based on user input              |
| Customer Support     | [declarative/customer_support/](./declarative/customer_support/)         | Multi-agent customer support with routing                     |
| Deep Research        | [declarative/deep_research/](./declarative/deep_research/)               | Research workflow with planning, searching, and synthesis     |
| Function Tools       | [declarative/function_tools/](./declarative/function_tools/)             | Invoking Python functions from declarative workflows          |
| Human-in-Loop        | [declarative/human_in_loop/](./declarative/human_in_loop/)               | Interactive workflows that request user input                 |
| Marketing            | [declarative/marketing/](./declarative/marketing/)                       | Marketing content generation workflow                         |
| Simple Workflow      | [declarative/simple_workflow/](./declarative/simple_workflow/)           | Basic workflow with variable setting, conditionals, and loops |
| Student Teacher      | [declarative/student_teacher/](./declarative/student_teacher/)           | Student-teacher interaction pattern                           |

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

- **AzureOpenAIChatClient**: Set Azure OpenAI environment variables as documented [here](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/chat_client/README.md#environment-variables).
  These variables are required for samples that construct `AzureOpenAIChatClient`

- **OpenAI** (used in orchestration samples):
  - [OpenAIChatClient env vars](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_chat_client/README.md)
  - [OpenAIResponsesClient env vars](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/openai_responses_client/README.md)
