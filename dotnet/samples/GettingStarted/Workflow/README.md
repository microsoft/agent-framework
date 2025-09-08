# Workflow Getting Started Samples

The getting started with workflow samples demonstrate the fundamental concepts and functionalities of workflows in Agent Framework.

## Samples Overview

### Foundational Concepts - Start Here

Please begin with the [Foundational](./Foundational) samples in order. These three samples introduce the core concepts of executors, edges, agents in workflows, streaming, and workflow construction.

| Sample | Concepts |
|--------|----------|
| [Executors and Edges](./Foundational/01_ExecutorsAndEdges) | Minimal workflow with basic executors and edges |
| [Streaming](./Foundational/02_Streaming) | Extends workflows with event streaming |
| [Agents](./Foundational/03_AgentsInWorkflows) | Use agents in workflows |

Once completed, please proceed to other samples listed below.

> Note that you don't need to follow a strict order after the foundational samples. However, some samples build upon concepts from previous ones, so it's beneficial to be aware of the dependencies.

### Concurrent Execution

| Sample | Concepts |
|--------|----------|
| [Fan-Out and Fan-In](./Concurrent) | Introduces parallel processing with fan-out and fan-in patterns |

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
