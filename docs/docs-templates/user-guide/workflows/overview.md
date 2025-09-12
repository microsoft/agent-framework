# Microsoft Agent Framework Workflows

## Overview

Microsoft Agent Framework Workflows empowers you to build intelligent automation systems that seamlessly blend AI agents with business processes. With its type-safe architecture and intuitive design, you can orchestrate complex workflows without getting bogged down in infrastructure complexity, allowing you to focus on your core business logic.

## How is a Workflows different from an AI Agent?

While an AI agent and a workflow can involve multiple steps to achieve a goal, they serve different purposes and operate at different levels of abstraction:

- **AI Agent**: An AI agent is typically driven by a large language model (LLM) and it has access to various tools to help it accomplish tasks. The steps an agent takes are dynamic and determined by the LLM based on the context of the conversation and the tools available. <img src="./resources/images/ai-agent.png" width="380" />
- **Workflow**: A workflow, on the other hand, is a predefined sequence of operations that can include AI agents as components. Workflows are designed to handle complex business processes that may involve multiple agents, human interactions, and integrations with external systems. The flow of a workflow is explicitly defined, allowing for more control over the execution path. <img src="./resources/images/workflows-overview.png" width="580" />

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
