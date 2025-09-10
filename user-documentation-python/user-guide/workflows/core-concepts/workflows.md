# Microsoft Agent Framework Workflows Core Concepts: Workflows

This document provides an in-depth look at the **Workflows** component of the Microsoft Agent Framework Workflow system.

## Overview

A Workflow ties everything together and manages execution. It's the orchestrator that coordinates executor execution, message routing, and event streaming.

### Building Workflows



Coming soon...


### Workflow Execution

Workflows support both streaming and non-streaming execution modes:



Coming soon...


### Workflow Validation

The framework performs comprehensive validation when building workflows:

- **Type Compatibility**: Ensures message types are compatible between connected executors
- **Graph Connectivity**: Verifies all executors are reachable from the start executor
- **Executor Binding**: Confirms all executors are properly bound and instantiated
- **Edge Validation**: Checks for duplicate edges and invalid connections

### Execution Model

The framework uses a modified [Pregel](https://kowshik.github.io/JPregel/pregel_paper.pdf) execution model with clear data flow semantics and superstep-based processing.

### Pregel-Style Supersteps

Workflow execution is organized into discrete supersteps, where each superstep processes all available messages in parallel:

```text
Superstep N:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Collect All    │───▶│  Route Messages │───▶│  Execute All    │
│  Pending        │    │  Based on Type  │    │  Target         │
│  Messages       │    │  & Conditions   │    │  Executors      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
┌─────────────────┐    ┌─────────────────┐             │
│  Start Next     │◀───│  Emit Events &  │◀────────────┘
│  Superstep      │    │  New Messages   │
└─────────────────┘    └─────────────────┘
```

### Key Execution Characteristics

- **Superstep Isolation**: All executors in a superstep run concurrently without interfering with each other
- **Message Delivery**: Messages are delivered in parallel to all matching edges
- **Event Streaming**: Events are emitted in real-time as executors complete processing
- **Type Safety**: Runtime type validation ensures messages are routed to compatible handlers

## Next Step

- [Learn about events](./events.md) to understand how to monitor and observe workflow execution.

