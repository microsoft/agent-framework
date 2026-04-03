# Workflow Getting Started Samples

The workflow samples demonstrate the fundamental concepts and functionality of workflows in Agent Framework.

## Samples Overview

### Foundational Concepts - Start Here

Please begin with the [Start Here](./_StartHere) samples in order. These three samples introduce the core concepts of executors, edges, agents in workflows, streaming, and workflow construction.

> The folder name starts with an underscore (`_StartHere`) to ensure it appears first in the explorer view.

| Sample | Concepts |
|--------|----------|
| [Streaming](./_StartHere/01_Streaming) | Extends workflows with event streaming |
| [Agents](./_StartHere/02_AgentsInWorkflows) | Use agents in workflows |
| [Agentic Workflow Patterns](./_StartHere/03_AgentWorkflowPatterns) | Demonstrates common agentic workflow patterns |
| [Multi-Service Workflows](./_StartHere/04_MultiModelService) | Shows using multiple AI services in the same workflow |
| [Sub-Workflows](./_StartHere/05_SubWorkflows) | Demonstrates composing workflows hierarchically by embedding workflows as executors |
| [Mixed Workflow with Agents and Executors](./_StartHere/06_MixedWorkflowAgentsAndExecutors) | Shows how to mix agents and executors with adapter pattern for type conversion and protocol handling |
| [Writer-Critic Workflow](./_StartHere/07_WriterCriticWorkflow) | Demonstrates iterative refinement with quality gates, max iteration safety, multiple message handlers, and conditional routing for feedback loops |

Once completed, please proceed to the other samples listed below.

### Agents

| Sample | Concepts |
|--------|----------|
| [Foundry Agents in Workflows](./Agents/FoundryAgent) | Demonstrates using Microsoft Foundry agents in a workflow through `ChatClientAgent` |
| [Custom Agent Executors](./Agents/CustomAgentExecutors) | Shows how to create a custom agent executor for more complex scenarios |
| [Workflow as an Agent](./Agents/WorkflowAsAnAgent) | Illustrates how to encapsulate a workflow as an agent |
| [Group Chat with Tool Approval](./Agents/GroupChatToolApproval) | Shows multi-agent group chat with tool approval requests and human-in-the-loop interaction |

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
