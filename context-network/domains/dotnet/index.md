# .NET Implementation Domain

## Purpose
Navigation hub for all .NET-specific documentation, architecture, and implementation details.

## Classification
- **Domain:** .NET
- **Stability:** Semi-stable
- **Abstraction:** Structural
- **Confidence:** Established

## Overview

The .NET implementation of Microsoft Agent Framework is located in `dotnet/` and provides a complete agent framework using standard .NET patterns, dependency injection, and hosting abstractions.

## Package Structure

### Core Packages
- `Microsoft.Agents.AI`: Core agent functionality
- `Microsoft.Agents.AI.Abstractions`: Core abstractions and interfaces
- `Microsoft.Agents.AI.OpenAI`: OpenAI integration
- `Microsoft.Agents.AI.AzureAI`: Azure AI integration
- `Microsoft.Agents.AI.A2A`: Agent-to-Agent communication
- `Microsoft.Agents.AI.CopilotStudio`: Copilot Studio integration

### Workflows
- `Microsoft.Agents.AI.Workflows`: Workflow engine
- `Microsoft.Agents.AI.Workflows.Declarative`: YAML-based workflow definitions

### Hosting
- `Microsoft.Agents.AI.Hosting`: Hosting abstractions
- `Microsoft.Agents.AI.Hosting.A2A`: A2A hosting support
- `Microsoft.Agents.AI.Hosting.A2A.AspNetCore`: ASP.NET Core integration
- `Microsoft.Agents.AI.Hosting.OpenAI`: OpenAI hosting support

## Key Architectural Patterns

### Dependency Injection
Standard ASP.NET Core DI patterns for service configuration.

### Hosting Abstractions
Support for ASP.NET Core hosting with middleware and service registration.

### Builder Pattern
Fluent APIs for configuration.

### Interface Segregation
Clean abstractions for extensibility.

## Development Setup

See [Development Processes](../../processes/development.md#net-development) for setup instructions.

Quick start:
```bash
cd dotnet/
dotnet build
dotnet test
```

## Code Quality Standards

- Follow [.NET coding conventions](https://learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/coding-conventions)
- Use `dotnet format` for consistent formatting
- XML documentation comments for public APIs
- Async/await for I/O operations
- IDisposable/IAsyncDisposable for resource management

See [Development Principles](../../foundation/principles.md#net-standards) for complete standards.

## Key Implementation Areas

### Agents
- Single agents with tool support
- Agent threads and conversation management
- Tool registration and execution

### Workflows
- Graph-based orchestration
- Declarative YAML workflows
- Checkpoint and state management
- Human-in-the-loop support

### Hosting
- ASP.NET Core integration
- Agent-to-Agent hosting
- Service registration patterns

## Related Documentation

### Foundation
- [Project Definition](../../foundation/project_definition.md)
- [Architecture Overview](../../foundation/architecture.md)
- [Development Principles](../../foundation/principles.md)

### Processes
- [Development Setup](../../processes/development.md)
- [Contributing](../../processes/contributing.md)

### Decisions
- [Decision Records](../../decisions/index.md)

## Relationship Network
- **Prerequisite Information**:
  - [Project Definition](../../foundation/project_definition.md)
  - [Architecture Overview](../../foundation/architecture.md)
- **Related Information**:
  - [Python Domain](../python/index.md)
  - [Workflows Domain](../workflows/index.md)
- **Implementation Details**:
  - .NET package documentation: `dotnet/src/*/README.md`
  - Sample code: `dotnet/samples/`

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial domain index created during context network setup
