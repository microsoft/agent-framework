# Microsoft Agent Framework - Project Definition

## Purpose
This document defines the core mission, scope, and objectives of the Microsoft Agent Framework project.

## Classification
- **Domain:** Foundation
- **Stability:** Semi-stable
- **Abstraction:** Conceptual
- **Confidence:** Established

## Project Overview

### Mission
The Microsoft Agent Framework is a multi-language framework for building, orchestrating, and deploying AI agents with support for both .NET and Python.

### Core Objectives
1. **Multi-Language Support**: Provide first-class implementations in both Python and .NET
2. **Agent Orchestration**: Enable complex multi-agent workflows with graph-based execution
3. **Extensibility**: Support multiple LLM providers (OpenAI, Azure OpenAI, Azure AI, Anthropic, etc.)
4. **Production-Ready**: Include observability, telemetry, and enterprise features
5. **Developer Experience**: Provide clear APIs, comprehensive samples, and excellent documentation

### Key Features
- **Single Agents**: Chat agents with tool calling, threads, and memory
- **Multi-Agent Workflows**: Graph-based orchestration with conditional routing, loops, and concurrent execution
- **Tool Integration**:
  - Model Context Protocol (MCP) support
  - OpenAPI tool generation
  - Custom function tools
- **Memory & State**: Vector stores, checkpointing, and state management
- **Observability**: OpenTelemetry integration, logging, and telemetry
- **Guardrails**: Content filters and safety mechanisms
- **Agent-to-Agent (A2A) Communication**: Protocol for inter-agent communication
- **Copilot Studio Integration**: Support for Microsoft Copilot Studio agents

## Target Audiences

### Primary Users
1. **Application Developers**: Building AI-powered applications with agents
2. **Enterprise Teams**: Deploying production agent systems
3. **AI Researchers**: Experimenting with agent architectures and workflows

### Secondary Users
1. **Framework Contributors**: Extending the framework with new features
2. **Tool Developers**: Creating integrations and connectors
3. **Documentation Writers**: Improving guides and samples

## Project Structure

### Python Implementation
- **Location**: `python/` directory
- **Package**: `agent-framework` with tier-based imports
- **Key Components**: Core framework, connectors (OpenAI, Azure, etc.), workflows, observability

### .NET Implementation
- **Location**: `dotnet/` directory
- **Namespace**: `Microsoft.Agents.AI.*`
- **Key Components**: Core abstractions, provider integrations, workflows, hosting

### Cross-Platform
- **Workflow Samples**: `workflow-samples/` with declarative YAML definitions
- **Documentation**: `docs/` (being migrated to context network)

## Relationship Network
- **Prerequisite Information**: None (this is a foundational document)
- **Related Information**:
  - [Architecture Overview](architecture.md)
  - [Development Principles](principles.md)
- **Dependent Information**:
  - All domain-specific documentation
  - [Development Processes](../processes/development.md)
- **Alternative Perspectives**:
  - Python-specific view: [Python Domain](../domains/python/index.md)
  - .NET-specific view: [.NET Domain](../domains/dotnet/index.md)

## Navigation Guidance
- **Access Context**: Start here when first learning about the project
- **Common Next Steps**:
  - Understanding architecture → [Architecture Overview](architecture.md)
  - Contributing → [Development Processes](../processes/development.md)
  - Technical decisions → [Decision Records](../decisions/index.md)
- **Related Tasks**: Onboarding new contributors, project planning, feature scoping

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial document created during context network setup
