# Microsoft Agent Framework - .NET Codebase Index

> **Last Updated:** October 14, 2025  
> **Solution:** `agent-framework-dotnet.slnx`  
> **Root Path:** `dotnet/`

## 📑 Table of Contents

- [Overview](#overview)
- [Solution Structure](#solution-structure)
- [Core Libraries](#core-libraries)
- [Provider Libraries](#provider-libraries)
- [Hosting Libraries](#hosting-libraries)
- [Workflow Libraries](#workflow-libraries)
- [Tests](#tests)
- [Samples](#samples)
- [Build Configuration](#build-configuration)
- [Dependencies](#dependencies)

---

## Overview

The Microsoft Agent Framework for .NET provides a comprehensive SDK for building AI agents with support for multiple providers (OpenAI, Azure AI, Copilot Studio), workflows, hosting, and advanced features like observability, dependency injection, and human-in-the-loop patterns.

**Key Features:**
- Multi-provider support (OpenAI, Azure AI, Copilot Studio, A2A)
- Workflow orchestration with declarative YAML support
- Built-in observability with OpenTelemetry
- Dependency injection and hosting extensions
- Model Context Protocol (MCP) support
- Agent-to-Agent (A2A) communication
- Checkpoint/resume capabilities

---

## Solution Structure

```
dotnet/
├── src/                          # Core library source code
├── tests/                        # Unit and integration tests
├── samples/                      # Sample applications and tutorials
├── eng/                          # Build engineering files
├── nuget/                        # NuGet packaging configuration
└── *.props, *.targets, *.config # Build configuration files
```

---

## Core Libraries

### 1. **Microsoft.Agents.AI.Abstractions** ⭐
**Location:** `src/Microsoft.Agents.AI.Abstractions/`  
**Purpose:** Core abstractions and interfaces for the Agent Framework  
**Key Components:**
- `AIAgent` - Base agent interface
- `AgentThread` - Conversation thread abstraction
- `AgentRunOptions` - Configuration for agent execution
- `AgentRunResponse` - Response handling
- `ChatMessageStore` - Message storage abstraction
- `AIContext` - Context management for agents

**Dependencies:**
- Microsoft.Extensions.AI.Abstractions
- Microsoft.Extensions.Logging.Abstractions

**Files (19 total):**
```
├── AIAgent.cs
├── AgentThread.cs
├── AgentRunOptions.cs
├── AgentRunResponse.cs
├── AgentRunResponse{T}.cs
├── AgentRunResponseExtensions.cs
├── AgentRunResponseUpdate.cs
├── AgentThreadMetadata.cs
├── AIAgentMetadata.cs
├── AIContentExtensions.cs
├── AIContext.cs
├── AIContextProvider.cs
├── ChatMessageStore.cs
├── DelegatingAIAgent.cs
├── InMemoryAgentThread.cs
├── InMemoryChatMessageStore.cs
├── ServiceIdAgentThread.cs
└── AgentAbstractionsJsonUtilities.cs
```

---

### 2. **Microsoft.Agents.AI** ⭐
**Location:** `src/Microsoft.Agents.AI/`  
**Purpose:** Core implementation of the Agent Framework  
**Key Components:**
- `AIAgentBuilder` - Fluent API for building agents
- `OpenTelemetryAgent` - Built-in observability
- `FunctionInvocationDelegatingAgent` - Function calling support
- Chat client implementations

**Dependencies:**
- Microsoft.Agents.AI.Abstractions
- Microsoft.Extensions.AI
- Microsoft.Extensions.DependencyInjection.Abstractions
- System.Diagnostics.DiagnosticSource

**Directory Structure:**
```
├── AIAgentBuilder.cs
├── AIAgentBuilderExtensions.cs
├── AgentExtensions.cs
├── AgentJsonUtilities.cs
├── AnonymousDelegatingAIAgent.cs
├── FunctionInvocationDelegatingAgent.cs
├── OpenTelemetryAgent.cs
├── OpenTelemetryConsts.cs
└── ChatClient/
    ├── ChatClientAgent.cs
    ├── ChatClientAgentBuilder.cs
    ├── ChatClientAgentExtensions.cs
    └── [6 more files]
```

---

## Provider Libraries

### 3. **Microsoft.Agents.AI.OpenAI**
**Location:** `src/Microsoft.Agents.AI.OpenAI/`  
**Purpose:** OpenAI provider implementation  
**Key Components:**
- `OpenAIChatClientAgent` - Chat completion support
- `OpenAIResponseClientAgent` - Response API support (including o1 models)
- Extensions for OpenAI-specific features

**Files:**
```
├── OpenAIChatClientAgent.cs
├── OpenAIResponseClientAgent.cs
├── ChatClient/
│   └── [2 files]
└── Extensions/
    └── [5 files]
```

---

### 4. **Microsoft.Agents.AI.AzureAI**
**Location:** `src/Microsoft.Agents.AI.AzureAI/`  
**Purpose:** Azure AI Foundry integration  
**Key Components:**
- `PersistentAgentsClientExtensions` - Azure AI persistent agents support

**Dependencies:**
- Azure.AI.Agents.Persistent

---

### 5. **Microsoft.Agents.AI.CopilotStudio**
**Location:** `src/Microsoft.Agents.AI.CopilotStudio/`  
**Purpose:** Microsoft Copilot Studio integration  
**Key Components:**
- `CopilotStudioAgent` - Copilot Studio agent implementation
- `CopilotStudioAgentThread` - Thread management
- `ActivityProcessor` - Activity processing

**Files:**
```
├── CopilotStudioAgent.cs
├── CopilotStudioAgentThread.cs
└── ActivityProcessor.cs
```

---

### 6. **Microsoft.Agents.AI.A2A**
**Location:** `src/Microsoft.Agents.AI.A2A/`  
**Purpose:** Agent-to-Agent (A2A) communication protocol  
**Key Components:**
- `A2AAgent` - A2A client implementation
- `A2AHostAgent` - A2A server implementation
- `A2AAgentThread` - A2A thread management

**Directory Structure:**
```
├── A2AAgent.cs
├── A2AHostAgent.cs
├── A2AAgentThread.cs
├── A2AAgentLogMessages.cs
└── Extensions/
    └── [9 files]
```

**Dependencies:**
- A2A (protocol library)

---

## Hosting Libraries

### 7. **Microsoft.Agents.AI.Hosting**
**Location:** `src/Microsoft.Agents.AI.Hosting/`  
**Purpose:** Dependency injection and hosting support  
**Key Components:**
- `AgentCatalog` - Agent registration and discovery
- `LocalAgentRegistry` - Local agent management
- `HostApplicationBuilderAgentExtensions` - DI extensions

**Files:**
```
├── AgentCatalog.cs
├── LocalAgentCatalog.cs
├── LocalAgentRegistry.cs
└── HostApplicationBuilderAgentExtensions.cs
```

---

### 8. **Microsoft.Agents.AI.Hosting.A2A**
**Location:** `src/Microsoft.Agents.AI.Hosting.A2A/`  
**Purpose:** A2A hosting support  
**Key Components:**
- Message converters for A2A protocol
- Agent hosting extensions

---

### 9. **Microsoft.Agents.AI.Hosting.A2A.AspNetCore**
**Location:** `src/Microsoft.Agents.AI.Hosting.A2A.AspNetCore/`  
**Purpose:** ASP.NET Core A2A hosting  
**Key Components:**
- `WebApplicationExtensions` - ASP.NET Core integration

---

### 10. **Microsoft.Agents.AI.Hosting.OpenAI**
**Location:** `src/Microsoft.Agents.AI.Hosting.OpenAI/`  
**Purpose:** OpenAI-compatible API hosting  
**Key Components:**
- `EndpointRouteBuilderExtensions` - API endpoint configuration
- Response models and converters

**Directory Structure:**
```
├── EndpointRouteBuilderExtensions.cs
└── Responses/
    └── [10 files]
```

---

## Workflow Libraries

### 11. **Microsoft.Agents.AI.Workflows** ⭐
**Location:** `src/Microsoft.Agents.AI.Workflows/`  
**Purpose:** Multi-agent workflow orchestration  
**Key Components:**
- `Workflow` - Workflow definition and execution
- `WorkflowBuilder` - Fluent workflow construction API
- `Executor` - Workflow step execution abstraction
- `CheckpointManager` - Checkpoint/resume support
- `WorkflowHostAgent` - Host agents within workflows

**Major Features:**
- Graph-based workflow orchestration
- Concurrent and sequential execution
- Conditional edges and routing
- Human-in-the-loop support
- Checkpoint/resume capabilities
- OpenTelemetry observability
- State management and message routing

**Directory Structure:**
```
├── Workflow.cs
├── WorkflowBuilder.cs
├── WorkflowBuilderExtensions.cs
├── AgentWorkflowBuilder.cs
├── Executor.cs
├── ExecutorOptions.cs
├── Edge.cs
├── Run.cs
├── StreamingRun.cs
├── Checkpointing/              [28 files - checkpoint/resume implementation]
├── Execution/                  [34 files - execution engine]
├── InProc/                     [4 files - in-process execution]
├── Observability/              [5 files - OpenTelemetry integration]
├── Reflection/                 [6 files - reflection-based executors]
├── Specialized/                [3 files - specialized executors]
└── Visualization/              [1 file - workflow visualization]
```

**Total:** 156 files

---

### 12. **Microsoft.Agents.AI.Workflows.Declarative** ⭐
**Location:** `src/Microsoft.Agents.AI.Workflows.Declarative/`  
**Purpose:** YAML-based declarative workflow definitions  
**Key Components:**
- `DeclarativeWorkflowBuilder` - Build workflows from YAML
- `DeclarativeWorkflowLanguage` - YAML schema definitions
- PowerFx integration for expressions
- Code generation (T4 templates)

**Major Features:**
- YAML workflow definitions
- Schema validation
- PowerFx expression evaluation
- Azure agent provider integration
- Event-driven architecture

**Directory Structure:**
```
├── DeclarativeWorkflowBuilder.cs
├── DeclarativeWorkflowLanguage.cs
├── DeclarativeWorkflowOptions.cs
├── AzureAgentProvider.cs
├── WorkflowAgentProvider.cs
├── CodeGen/                    [81 files - T4 templates and generated code]
├── Entities/                   [2 files]
├── Events/                     [6 files]
├── Exceptions/                 [3 files]
├── Extensions/                 [14 files]
├── Interpreter/                [12 files - YAML interpreter]
├── Kit/                        [9 files]
├── ObjectModel/                [19 files - workflow object model]
└── PowerFx/                    [7 files - PowerFx integration]
```

**Dependencies:**
- Microsoft.Bot.ObjectModel
- Microsoft.Bot.ObjectModel.Json
- Microsoft.Bot.ObjectModel.PowerFx
- Microsoft.PowerFx.Interpreter

**Total:** 159 files

---

## Tests

### Unit Tests

| Project | Location | Focus |
|---------|----------|-------|
| **Microsoft.Agents.AI.Abstractions.UnitTests** | `tests/Microsoft.Agents.AI.Abstractions.UnitTests/` | Core abstractions |
| **Microsoft.Agents.AI.UnitTests** | `tests/Microsoft.Agents.AI.UnitTests/` | Core functionality |
| **Microsoft.Agents.AI.A2A.UnitTests** | `tests/Microsoft.Agents.AI.A2A.UnitTests/` | A2A protocol |
| **Microsoft.Agents.AI.AzureAI.UnitTests** | `tests/Microsoft.Agents.AI.AzureAI.UnitTests/` | Azure AI integration |
| **Microsoft.Agents.AI.OpenAI.UnitTests** | `tests/Microsoft.Agents.AI.OpenAI.UnitTests/` | OpenAI provider |
| **Microsoft.Agents.AI.Hosting.UnitTests** | `tests/Microsoft.Agents.AI.Hosting.UnitTests/` | Hosting features |
| **Microsoft.Agents.AI.Hosting.A2A.Tests** | `tests/Microsoft.Agents.AI.Hosting.A2A.Tests/` | A2A hosting |
| **Microsoft.Agents.AI.Workflows.UnitTests** | `tests/Microsoft.Agents.AI.Workflows.UnitTests/` | Workflows (41 files) |
| **Microsoft.Agents.AI.Workflows.Declarative.UnitTests** | `tests/Microsoft.Agents.AI.Workflows.Declarative.UnitTests/` | Declarative workflows (94 files) |

### Integration Tests

| Project | Location | Focus |
|---------|----------|-------|
| **AgentConformance.IntegrationTests** | `tests/AgentConformance.IntegrationTests/` | Cross-provider conformance |
| **AzureAIAgentsPersistent.IntegrationTests** | `tests/AzureAIAgentsPersistent.IntegrationTests/` | Azure AI persistent agents |
| **CopilotStudio.IntegrationTests** | `tests/CopilotStudio.IntegrationTests/` | Copilot Studio integration |
| **OpenAIAssistant.IntegrationTests** | `tests/OpenAIAssistant.IntegrationTests/` | OpenAI Assistants API |
| **OpenAIChatCompletion.IntegrationTests** | `tests/OpenAIChatCompletion.IntegrationTests/` | OpenAI Chat Completions |
| **OpenAIResponse.IntegrationTests** | `tests/OpenAIResponse.IntegrationTests/` | OpenAI Response API |
| **Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests** | `tests/Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests/` | Declarative workflows |

**Test Framework:** xUnit with FluentAssertions, Moq, and xretry

---

## Samples

### Getting Started - Agents
**Location:** `samples/GettingStarted/Agents/`  
**Tutorial Path (16 Steps):**

1. **Agent_Step01_Running** - Basic agent execution
2. **Agent_Step02_MultiturnConversation** - Conversation management
3. **Agent_Step03_UsingFunctionTools** - Function calling
4. **Agent_Step04_UsingFunctionToolsWithApprovals** - Human approval for tools
5. **Agent_Step05_StructuredOutput** - Structured JSON responses
6. **Agent_Step06_PersistedConversations** - Persistent threads
7. **Agent_Step07_3rdPartyThreadStorage** - Custom storage
8. **Agent_Step08_Observability** - OpenTelemetry integration
9. **Agent_Step09_DependencyInjection** - DI patterns
10. **Agent_Step10_AsMcpTool** - Model Context Protocol
11. **Agent_Step11_UsingImages** - Vision/multimodal support
12. **Agent_Step12_AsFunctionTool** - Agent as a tool
13. **Agent_Step13_Memory** - Memory integration
14. **Agent_Step14_Middleware** - Custom middleware
15. **Agent_Step15_Plugins** - Plugin architecture
16. **Agent_Step16_ChatReduction** - Context window management

### Agent Providers
**Location:** `samples/GettingStarted/AgentProviders/`  
**Samples (11 providers):**

- `Agent_With_A2A` - Agent-to-Agent protocol
- `Agent_With_AzureFoundryAgent` - Azure AI Foundry agents
- `Agent_With_AzureFoundryModel` - Azure AI Foundry models
- `Agent_With_AzureOpenAIChatCompletion` - Azure OpenAI chat
- `Agent_With_AzureOpenAIResponses` - Azure OpenAI response API
- `Agent_With_CustomImplementation` - Custom agent implementation
- `Agent_With_Ollama` - Ollama local models
- `Agent_With_ONNX` - ONNX Runtime GenAI
- `Agent_With_OpenAIAssistants` - OpenAI Assistants API
- `Agent_With_OpenAIChatCompletion` - OpenAI chat completions
- `Agent_With_OpenAIResponses` - OpenAI response API (o1 models)

### OpenAI Advanced
**Location:** `samples/GettingStarted/AgentWithOpenAI/`

- `Agent_OpenAI_Step01_Running` - OpenAI basics
- `Agent_OpenAI_Step02_Reasoning` - Reasoning models (o1)

### Model Context Protocol (MCP)
**Location:** `samples/GettingStarted/ModelContextProtocol/`

- `Agent_MCP_Server` - Basic MCP server
- `Agent_MCP_Server_Auth` - MCP with authentication
- `FoundryAgent_Hosted_MCP` - Azure Foundry MCP integration

### Workflows - Foundational
**Location:** `samples/GettingStarted/Workflows/_Foundational/`

1. **01_ExecutorsAndEdges** - Basic workflow concepts
2. **02_Streaming** - Streaming workflow execution
3. **03_AgentsInWorkflows** - Integrating agents in workflows
4. **04_AgentWorkflowPatterns** - Common patterns
5. **05_MultiModelService** - Multi-model workflows

### Workflows - Concurrent
**Location:** `samples/GettingStarted/Workflows/Concurrent/`

- `Concurrent` - Parallel execution
- `MapReduce` - Map-reduce patterns

### Workflows - Conditional Edges
**Location:** `samples/GettingStarted/Workflows/ConditionalEdges/`

- `01_EdgeCondition` - Conditional routing
- `02_SwitchCase` - Switch/case patterns
- `03_MultiSelection` - Multiple path selection

### Workflows - Declarative
**Location:** `samples/GettingStarted/Workflows/Declarative/`

- `ExecuteCode` - Execute code in workflows
- `ExecuteWorkflow` - Nested workflows
- `GenerateCode` - Code generation

### Workflows - Advanced Features
**Location:** `samples/GettingStarted/Workflows/`

- **Agents/** - Custom agent executors, Foundry agents, workflow-as-agent
- **Checkpoint/** - Checkpoint/rehydrate, resume, human-in-the-loop
- **HumanInTheLoop/** - Human approval patterns
- **Loop/** - Looping constructs
- **Observability/** - Application Insights, Aspire Dashboard
- **SharedStates/** - State sharing between executors
- **Visualization/** - Workflow visualization

### Semantic Kernel Migration
**Location:** `samples/SemanticKernelMigration/`  
**Purpose:** Migration guides from Semantic Kernel

**Providers:**
- OpenAI (3 steps)
- AzureOpenAI (3 steps)
- OpenAI Assistants (4 steps)
- AzureOpenAI Assistants (4 steps)
- OpenAI Responses (4 steps)
- AzureOpenAI Responses (4 steps)
- Azure AI Foundry (4 steps)
- Agent Orchestrations (3 steps)

### Full Applications

#### A2AClientServer
**Location:** `samples/A2AClientServer/`  
**Projects:**
- `A2AClient` - Client implementation
- `A2AServer` - Server implementation

#### AgentWebChat
**Location:** `samples/AgentWebChat/`  
**Projects (Aspire-based):**
- `AgentWebChat.Web` - Blazor web UI
- `AgentWebChat.AgentHost` - Agent backend
- `AgentWebChat.AppHost` - Aspire orchestrator
- `AgentWebChat.ServiceDefaults` - Shared defaults

---

## Build Configuration

### Key Files

| File | Purpose |
|------|---------|
| `agent-framework-dotnet.slnx` | Solution file (XML format) |
| `Directory.Build.props` | Shared MSBuild properties |
| `Directory.Build.targets` | Shared MSBuild targets |
| `Directory.Packages.props` | Central package management (CPM) |
| `global.json` | .NET SDK version pinning |
| `nuget.config` | NuGet feed configuration |

### MSBuild Engineering
**Location:** `eng/MSBuild/`

- `Shared.props` - Common properties
- `Shared.targets` - Common targets
- `LegacySupport.props` - Legacy framework support

### NuGet Configuration
**Location:** `nuget/`

- `nuget-package.props` - NuGet metadata
- `icon.png` - Package icon
- `NUGET.md` - NuGet documentation

---

## Dependencies

### Core Dependencies (from Directory.Packages.props)

**Microsoft Extensions:**
- Microsoft.Extensions.AI (9.9.1)
- Microsoft.Extensions.AI.Abstractions (9.9.1)
- Microsoft.Extensions.DependencyInjection (9.0.9)
- Microsoft.Extensions.Logging (9.0.9)
- Microsoft.Extensions.Hosting (9.0.9)

**Azure SDKs:**
- Azure.AI.Agents.Persistent (1.2.0-beta.5)
- Azure.AI.OpenAI (2.5.0-beta.1)
- Azure.Identity (1.17.0)
- Azure.Monitor.OpenTelemetry.Exporter (1.4.0)

**OpenAI:**
- OpenAI (2.5.0)

**Observability:**
- OpenTelemetry (1.12.0)
- OpenTelemetry.Api (1.12.0)
- OpenTelemetry.Instrumentation.AspNetCore (1.12.0)

**Workflows:**
- Microsoft.Bot.ObjectModel (1.2025.1003.2)
- Microsoft.PowerFx.Interpreter (1.4.0)

**Protocols:**
- A2A (0.3.1-preview)
- ModelContextProtocol (0.4.0-preview.2)

**Agent SDKs:**
- Microsoft.Agents.CopilotStudio.Client (1.2.41)

**Testing:**
- xUnit (2.9.3)
- FluentAssertions (8.7.1)
- Moq (4.18.4)

**Other Inference SDKs:**
- OllamaSharp (5.4.7)
- Microsoft.ML.OnnxRuntimeGenAI (0.9.2)
- Anthropic.SDK (5.6.0)

---

## Shared Code

### LegacySupport
**Location:** `src/LegacySupport/`  
**Purpose:** Polyfills for older .NET frameworks

**Includes:**
- CallerArgumentExpressionAttribute
- CompilerFeatureRequiredAttribute
- Nullable attributes
- UnreachableException
- ExperimentalAttribute
- IsExternalInit
- RequiredMemberAttribute
- Trim attributes (DynamicallyAccessedMembers, etc.)

### Shared Utilities
**Location:** `src/Shared/`

**Categories:**
- **Demos/** - Demo helpers (`SampleEnvironment.cs`)
- **IntegrationTests/** - Test configuration (Azure AI, OpenAI)
- **Samples/** - Sample base classes (`BaseSample.cs`, xUnit helpers)
- **Throw/** - Argument validation helpers

---

## Quick Reference

### Project Count Summary

| Category | Count |
|----------|-------|
| Core Libraries | 12 |
| Unit Test Projects | 9 |
| Integration Test Projects | 7 |
| Sample Projects | ~90 |
| **Total Projects** | **~120** |

### Target Frameworks

Primary targets (configured in Directory.Build.props):
- .NET 9.0
- .NET 8.0
- .NET Framework 4.8 (legacy support)

### Getting Started Quick Links

- [Main README](./README.md)
- [Getting Started Samples](./samples/GettingStarted/)
- [Agent Providers](./samples/GettingStarted/AgentProviders/)
- [Workflows](./samples/GettingStarted/Workflows/)
- [Documentation](https://learn.microsoft.com/agent-framework/)

---

## Navigation Tips

### Finding Specific Features

| Feature | Location |
|---------|----------|
| Core agent interfaces | `src/Microsoft.Agents.AI.Abstractions/` |
| Agent builders | `src/Microsoft.Agents.AI/AIAgentBuilder.cs` |
| OpenAI integration | `src/Microsoft.Agents.AI.OpenAI/` |
| Azure AI integration | `src/Microsoft.Agents.AI.AzureAI/` |
| Workflow orchestration | `src/Microsoft.Agents.AI.Workflows/` |
| YAML workflows | `src/Microsoft.Agents.AI.Workflows.Declarative/` |
| Dependency injection | `src/Microsoft.Agents.AI.Hosting/` |
| A2A protocol | `src/Microsoft.Agents.AI.A2A/` |
| Observability | `src/Microsoft.Agents.AI/OpenTelemetryAgent.cs` |
| Checkpointing | `src/Microsoft.Agents.AI.Workflows/Checkpointing/` |

### Common Development Tasks

| Task | Command/Location |
|------|------------------|
| Build solution | `dotnet build` |
| Run tests | `dotnet test` |
| Run sample | `cd samples/[sample-name] && dotnet run` |
| Create NuGet packages | `dotnet pack` |
| View workflow examples | `workflow-samples/*.yaml` |

---

**Generated:** October 14, 2025  
**Version:** 1.0  
**Maintainer:** Microsoft Agent Framework Team

