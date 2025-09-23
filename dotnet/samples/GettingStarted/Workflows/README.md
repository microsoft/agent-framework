# Workflow Getting Started Samples

The getting started with workflow samples demonstrate the fundamental concepts and functionalities of workflows in Agent Framework.

## Samples Overview

### Foundational Concepts - Start Here

Please begin with the [Foundational](./_Foundational) samples in order. These three samples introduce the core concepts of executors, edges, agents in workflows, streaming, and workflow construction.

> The folder name starts with an underscore (`_Foundational`) to ensure it appears first in the explorer view.

| Sample | Concepts |
|--------|----------|
| [Executors and Edges](./_Foundational/01_ExecutorsAndEdges) | Minimal workflow with basic executors and edges |
| [Streaming](./_Foundational/02_Streaming) | Extends workflows with event streaming |
| [Agents](./_Foundational/03_AgentsInWorkflows) | Use agents in workflows |
| [Agentic Workflow Patterns](./_Foundational/04_AgentWorkflowPatterns) | Demonstrates common agentic workflow patterns |
| [Multi-Service Workflows](./_Foundational/05_MultiModelService) | Shows using multiple AI services in the same workflow |

Once completed, please proceed to other samples listed below.

> Note that you don't need to follow a strict order after the foundational samples. However, some samples build upon concepts from previous ones, so it's beneficial to be aware of the dependencies.

### Agents

| Sample | Concepts |
|--------|----------|
| [Foundry Agents in Workflows](./Agents/FoundryAgent) | Demonstrates using Azure Foundry Agents within a workflow |
| [Custom Agent Executors](./Agents/CustomAgentExecutors) | Shows how to create a custom agent executor for more complex scenarios |
| [Workflow as an Agent](./Agents/WorkflowAsAgent) | Illustrates how to encapsulate a workflow as an agent |

### Concurrent Execution

| Sample | Concepts |
|--------|----------|
| [Fan-Out and Fan-In](./Concurrent) | Introduces parallel processing with fan-out and fan-in patterns |

### Loop

| Sample | Concepts |
|--------|----------|
| [Looping](./Loop) | Shows how to create a loop within a workflow |

### Workflow Shared States

| Sample | Concepts |
|--------|----------|
| [Shared States](./SharedStates) | Demonstrates shared states between executors for data sharing and coordination |

### Conditional Edges

| Sample | Concepts |
|--------|----------|
| [Edge Conditions](./ConditionalEdges/01_EdgeCondition) | Introduces conditional edges for dynamic routing based on executor outputs |
| [Switch-Case Routing](./ConditionalEdges/02_SwitchCase) | Extends conditional edges with switch-case routing for multiple paths |
| [Multi-Selection Routing](./ConditionalEdges/03_MultiSelection) | Demonstrates multi-selection routing where one executor can trigger multiple downstream executors |

> These 3 samples build upon each other. It's recommended to explore them in sequence to fully grasp the concepts.

### Declarative Workflows

| Sample | Concepts |
|--------|----------|
| [DeclarativeWorkflow](./DeclarativeWorkflow) | Demonstrates execution of declartive workflows. |

### Checkpointing

| Sample | Concepts |
|--------|----------|
| [Checkpoint and Resume](./Checkpoint/CheckpointAndResume) | Introduces checkpoints for saving and restoring workflow state for time travel purposes |
| [Checkpoint and Rehydrate](./Checkpoint/CheckpointAndRehydrate) | Demonstrates hydrating a new workflow instance from a saved checkpoint |
| [Checkpoint with Human-in-the-Loop](./Checkpoint/CheckpointWithHumanInTheLoop) | Combines checkpointing with human-in-the-loop interactions |

### Human-in-the-Loop

| Sample | Concepts |
|--------|----------|
| [Basic Human-in-the-Loop](./HumanInTheLoop/HumanIntheLoopBasic) | Introduces human-in-the-loop interaction using input ports and external requests |
