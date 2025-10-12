# Microsoft Agent Framework - Architecture Overview

## Purpose
This document provides a high-level overview of the Microsoft Agent Framework architecture, covering both Python and .NET implementations.

## Classification
- **Domain:** Foundation
- **Stability:** Semi-stable
- **Abstraction:** Structural
- **Confidence:** Established

## Core Architecture Principles

### Multi-Language Parity
Both Python and .NET implementations aim for feature parity, with language-specific idioms:
- **Python**: Async-first, flat import structure, namespace packages
- **.NET**: Standard .NET patterns, dependency injection, hosting abstractions

### Layered Architecture

#### Layer 1: Core Abstractions
- **Agents**: ChatAgent, tool management, thread handling
- **Chat Client Protocol**: Unified interface for LLM providers
- **Tools**: Function calling, MCP, OpenAPI integration
- **Types**: Core models and data structures

#### Layer 2: Provider Integrations
- **OpenAI**: OpenAI API integration
- **Azure**: Azure OpenAI, Azure AI Foundry
- **Anthropic**: Claude integration (Python)
- **Ollama**: Local model support
- **Copilot Studio**: Microsoft Copilot Studio agents
- **A2A**: Agent-to-Agent communication

#### Layer 3: Advanced Features
- **Workflows**: Graph-based multi-agent orchestration
- **Observability**: OpenTelemetry, logging, telemetry
- **Memory**: Vector stores, context providers
- **Guardrails**: Content filtering and safety

## Python Architecture

### Import Structure (Tier-Based)

**Tier 0 - Core** (`agent_framework`):
```python
from agent_framework import ChatAgent, ai_function
from agent_framework import get_logger
```

**Tier 1 - Components** (`agent_framework.<component>`):
```python
from agent_framework.vector_data import VectorStoreModel
from agent_framework.workflows import Workflow
from agent_framework.guardrails import ContentFilter
from agent_framework.observability import configure_tracing
```

**Tier 2 - Connectors** (`agent_framework.<vendor>`):
```python
from agent_framework.openai import OpenAIChatClient
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.anthropic import AnthropicChatClient
```

### Package Organization
- **Core Package**: `agent-framework-core` (main package)
- **Connector Packages**: Independently versioned (e.g., `agent-framework-azure-ai`)
- **Namespace Packages**: Allow selective installation
- **Lazy Loading**: Minimize import overhead

### Key Design Patterns
- **Async-First**: All I/O operations use async/await
- **Protocol-Based**: Chat client protocol for provider abstraction
- **Composition Over Inheritance**: Prefer attributes over subclassing
- **Lazy Imports**: Reduce startup time and dependency footprint

## .NET Architecture

### Namespace Structure

```
Microsoft.Agents.AI/                    # Core agent functionality
Microsoft.Agents.AI.Abstractions/       # Core abstractions
Microsoft.Agents.AI.OpenAI/            # OpenAI integration
Microsoft.Agents.AI.AzureAI/           # Azure AI integration
Microsoft.Agents.AI.A2A/               # Agent-to-Agent
Microsoft.Agents.AI.CopilotStudio/     # Copilot Studio
Microsoft.Agents.AI.Workflows/         # Workflow engine
Microsoft.Agents.AI.Hosting/           # Hosting abstractions
```

### Key Design Patterns
- **Dependency Injection**: Standard ASP.NET Core DI patterns
- **Hosting Abstractions**: Support for ASP.NET Core hosting
- **Builder Pattern**: Fluent APIs for configuration
- **Interface Segregation**: Clean abstractions for extensibility

## Workflow Architecture

### Graph-Based Execution
Workflows are directed graphs where:
- **Nodes (Executors)**: Agents or functions that perform work
- **Edges**: Data flows between executors
- **Ports**: Input/output interfaces for data exchange

### Key Features
- **Conditional Routing**: Edge conditions, switch-case, multi-selection
- **Concurrent Execution**: Fan-out/fan-in patterns
- **Looping**: Iterative patterns with loop-back edges
- **Checkpointing**: Save/restore workflow state
- **Human-in-the-Loop**: External interactions via input ports
- **Streaming**: Real-time event streaming

### Execution Model
1. Start at entry executor
2. Execute current node
3. Evaluate edge conditions
4. Route to next executor(s)
5. Continue until terminal state
6. Support concurrent branches

### Declarative Workflows
YAML-based workflow definitions:
```yaml
executors:
  - id: agent1
    type: agent
  - id: agent2
    type: agent

edges:
  - from: agent1
    to: agent2
    condition: "output.contains('escalate')"
```

## Tool Integration Architecture

### Model Context Protocol (MCP)
- **Standard Protocol**: Industry-standard for tool integration
- **Server Discovery**: Automatic tool discovery from MCP servers
- **Authentication**: Support for authenticated MCP servers
- **Bidirectional**: Agents can expose themselves as MCP tools

### OpenAPI Integration
- **Schema-Based**: Generate tools from OpenAPI specifications
- **Automatic Serialization**: Handle request/response formatting
- **Authentication**: Support for API key and OAuth flows

### Custom Function Tools
- **Decorator-Based**: `@ai_function` for Python, attributes for .NET
- **Type Hints**: Automatic schema generation from type information
- **Async Support**: Native async function support

## Observability Architecture

### OpenTelemetry Integration
- **Traces**: Agent execution, tool calls, workflow steps
- **Metrics**: Token usage, latency, success rates
- **Logs**: Structured logging with correlation

### Telemetry
- **Events**: Agent lifecycle, tool execution, workflow state
- **Callbacks**: Custom telemetry handlers
- **Exporters**: Multiple backend support (Azure Monitor, Jaeger, etc.)

## Memory & State Architecture

### Vector Stores
- **Abstract Interface**: Provider-agnostic vector store protocol
- **Implementations**: Redis, in-memory, custom backends
- **RAG Support**: Retrieval-augmented generation patterns

### Context Providers
- **Memory Integration**: mem0 and other memory services
- **Context Management**: Automatic context injection
- **History Tracking**: Conversation history persistence

### Checkpointing
- **State Serialization**: JSON-based workflow state
- **Time-Travel**: Restore to previous execution points
- **Debugging**: Inspect workflow state at any point

## Agent-to-Agent (A2A) Architecture

### Communication Protocol
- **HTTP-Based**: RESTful agent endpoints
- **Message Format**: Standardized message structure
- **Discovery**: Agent capability advertisement
- **Routing**: Message routing between agents

### Hosting
- **ASP.NET Core**: .NET hosting support
- **ASGI/WSGI**: Python hosting support
- **Authentication**: Secure inter-agent communication

## Relationship Network
- **Prerequisite Information**: [Project Definition](project_definition.md)
- **Related Information**:
  - [Development Principles](principles.md)
  - [Python Package Setup](../design/python-package-setup.md)
- **Dependent Information**:
  - [Python Domain](../domains/python/index.md)
  - [.NET Domain](../domains/dotnet/index.md)
  - [Workflows Domain](../domains/workflows/index.md)
- **Implementation Details**:
  - [Decision Records](../decisions/index.md)
  - [Design Documents](../design/index.md)

## Navigation Guidance
- **Access Context**: When understanding system design or making architectural decisions
- **Common Next Steps**:
  - Python specifics → [Python Domain](../domains/python/index.md)
  - .NET specifics → [.NET Domain](../domains/dotnet/index.md)
  - Implementation patterns → [Design Documents](../design/index.md)
- **Related Tasks**: Architecture reviews, integration planning, system design

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial document created during context network setup
