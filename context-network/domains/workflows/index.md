# Workflows Domain

## Purpose
Navigation hub for workflow-related documentation, covering multi-agent orchestration architecture and implementation.

## Classification
- **Domain:** Workflows
- **Stability:** Semi-stable
- **Abstraction:** Structural
- **Confidence:** Established

## Overview

Workflows provide graph-based multi-agent orchestration with support for conditional routing, concurrent execution, looping, checkpointing, and human-in-the-loop interactions.

## Architecture

### Core Concepts

**Graph-Based Execution**:
- **Nodes (Executors)**: Agents or functions that perform work
- **Edges**: Data flows between executors (static or conditional)
- **Ports**: Input/output interfaces for data exchange

### Key Features

1. **Conditional Routing**
   - Edge conditions
   - Switch-case patterns
   - Multi-selection routing

2. **Concurrent Execution**
   - Fan-out/fan-in patterns
   - Parallel processing
   - Shared state management

3. **Looping**
   - Iterative patterns
   - Loop-back edges
   - Convergence conditions

4. **Checkpointing**
   - Save/restore workflow state
   - Time-travel debugging
   - Resume from failure points

5. **Human-in-the-Loop**
   - External interactions via input ports
   - Approval workflows
   - Manual intervention points

6. **Streaming**
   - Real-time event streaming
   - Progress monitoring
   - Intermediate results

## Execution Model

1. Start at entry executor
2. Execute current node
3. Evaluate edge conditions
4. Route to next executor(s)
5. Support concurrent branches
6. Continue until terminal state

## Declarative Workflows

YAML-based workflow definitions for cross-platform workflows:

```yaml
executors:
  - id: agent1
    type: agent
    config:
      name: "Analyst"

  - id: agent2
    type: agent
    config:
      name: "Writer"

edges:
  - from: agent1
    to: agent2
    condition: "output.contains('approved')"
```

Location: `workflow-samples/` directory

## Implementation

### Python
- Package: `agent_framework.workflows`
- Import: `from agent_framework.workflows import Workflow`
- Location: `python/packages/core/agent_framework/_workflows/`

### .NET
- Namespace: `Microsoft.Agents.AI.Workflows`
- Package: `Microsoft.Agents.AI.Workflows`
- Declarative: `Microsoft.Agents.AI.Workflows.Declarative`

## Common Patterns

See extensive workflow samples in:
- .NET: `dotnet/samples/GettingStarted/Workflows/`
- Python: `python/samples/getting_started/workflows/`
- Cross-platform: `workflow-samples/`

Patterns include:
- Sequential orchestration
- Concurrent/parallel execution
- Conditional routing
- Looping
- Agent handoffs
- Multi-service coordination

## Related Documentation

### Foundation
- [Architecture Overview](../../foundation/architecture.md) - Workflow architecture section

### Domains
- [Python Workflows](../python/index.md#workflows)
- [.NET Workflows](../dotnet/index.md#workflows)

### Decisions
Relevant ADRs for workflow features

## Relationship Network
- **Prerequisite Information**:
  - [Architecture Overview](../../foundation/architecture.md)
- **Related Information**:
  - [Python Domain](../python/index.md)
  - [.NET Domain](../dotnet/index.md)
- **Implementation Details**:
  - Sample workflows: `workflow-samples/`, `dotnet/samples/GettingStarted/Workflows/`, `python/samples/getting_started/workflows/`

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial domain index created during context network setup
