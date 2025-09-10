# Microsoft Agent Framework Workflows

## Overview

Microsoft Agent Framework Workflows empowers you to build intelligent automation systems that seamlessly blend AI agents with business processes. With its type-safe architecture and intuitive design, you can orchestrate complex workflows without getting bogged down in infrastructure complexity, allowing you to focus on your core business logic.

## Key Features

- **Type Safety**: Strong typing ensures messages flow correctly between components, with comprehensive validation that prevents runtime errors.
- **Flexible Control Flow**: Graph-based architecture allows for intuitive modeling of complex workflows with `executors` and `edges`. Conditional routing, parallel processing, and dynamic execution paths are all supported.
- **External Integration**: Built-in request/response patterns for seamless integration with external APIs, and human-in-the-loop scenarios.
- **Checkpointing**: Save workflow states via checkpoints, enabling recovery and resumption of long-running processes on server sides.
- **Multi-Agent Orchestration**: Built-in patterns for coordinating multiple AI agents, including sequential, concurrent, hand-off, and magentic.

## Core Concepts

- **Executors**: represent individual processing units within a workflow. They can be AI agents or custom logic components. They receive input messages, perform specific tasks, and produce output messages.
- **Edges**: define the connections between executors, determining the flow of messages. They can include conditions to control routing based on message contents.
- **Workflows**: are directed graphs composed of executors and edges. They define the overall process, starting from an initial executor and proceeding through various paths based on conditions and logic defined in the edges.

## Getting Started

Begin your journey with Microsoft Agent Framework Workflows by exploring our getting started samples:

- [C# Getting Started Sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/GettingStarted/Workflows)
- [Python Getting Started Sample](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/workflow)

## Next Steps

Dive deeper into the concepts and capabilities of Microsoft Agent Framework Workflows by continuing to the [Workflows Concepts](./concepts.md) page.
