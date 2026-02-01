# Durable Agent Samples

This directory contains samples demonstrating durable agent hosting patterns for the Microsoft Agent Framework.

## Directory Structure

- **[azure_functions/](./azure_functions/)** - Samples for hosting durable agents in Azure Functions with the Durable Extension
- **[console_apps/](./console_apps/)** - Samples for hosting durable agents using the Durable Task Scheduler in console applications

## Overview

Durable agent hosting enables distributed agent execution with persistent conversation state, orchestration capabilities, and reliable streaming. These patterns are essential for building scalable, production-ready agent applications.

### Azure Functions

The Azure Functions samples demonstrate how to host agents in Azure Functions using the Durable Extension. These samples show HTTP endpoints for agent interaction, durable orchestrations, and integration with Azure services.

Key features:
- HTTP-triggered agent endpoints
- Durable orchestrations for multi-step workflows
- Per-session state management
- Reliable streaming with Redis
- Human-in-the-loop patterns

See the [Azure Functions README](./azure_functions/README.md) for detailed setup instructions.

### Console Apps

The Console Apps samples demonstrate the worker-client architecture pattern using the Durable Task Scheduler. These samples run locally or in any hosting environment that supports Python applications.

Key features:
- Worker-client architecture
- Distributed agent execution
- Persistent conversation state
- Orchestration patterns (chaining, concurrency, conditionals)
- Reliable streaming

See the [Console Apps README](./console_apps/README.md) for detailed setup instructions.

## Getting Started

Each subdirectory contains its own README with specific setup instructions and prerequisites. Both patterns require:

- Python 3.9 or later
- Azure OpenAI Service with a deployed model
- Appropriate durable infrastructure (Durable Task Scheduler or Azure Functions with Durable Extension)

## Related Documentation

- [Durable Task Framework Documentation](https://durabletask.github.io/)
- [Azure Functions Durable Extension](https://learn.microsoft.com/azure/azure-functions/durable/)
- [Agent Framework Documentation](https://aka.ms/agent-framework)
