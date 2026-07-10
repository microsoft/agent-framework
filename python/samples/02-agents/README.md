# Agent Concepts

Samples covering the core agent capabilities in Microsoft Agent Framework: creating
agents, configuring chat clients, adding tools and middleware, managing conversations,
using skills, and integrating with external protocols.

If you are brand new to Agent Framework, work through the getting-started samples
in [`../01-get-started/`](../01-get-started/) first — they build up agent
fundamentals in order.

## Installation

Agent Framework ships as `agent-framework` on PyPI. For additional provider
integrations select the extras you need:

| Extra | Package |
|-------|---------|
| `agent-framework-openai` | OpenAI / Azure OpenAI chat and responses |
| `agent-framework-foundry` | Foundry chat, agents, and hosted agents |
| `agent-framework-ollama` | Ollama local inference |
| `agent-framework-anthropic` | Anthropic Claude |
| `agent-framework-gemini` | Google Gemini |
| `agent-framework-bedrock` | AWS Bedrock |

## Samples Overview

Samples are organized by concept. Each directory has its own README with a per-file
table. Below is the high-level map.

### Core Concepts — Start Here

| Directory | What you learn |
|-----------|---------------|
| [`chat_client/`](chat_client/) | Creating and configuring chat clients. Custom client implementation. Streaming and non-streaming modes. |
| [`tools/`](tools/) | Defining function tools, approvals, invocation limits, tool error recovery, agent-as-tool, dynamic tool loading. |
| [`conversations/`](conversations/) | Multi-turn conversations. History providers (file, Redis, Cosmos DB). Session suspend/resume. |
| [`middleware/`](middleware/) | Agent and chat middleware. Decorators, class-based middleware, exception handling, message injection, shared state. |

### Memory & Context

| Directory | What you learn |
|-----------|---------------|
| [`compaction/`](compaction/) | Message compaction — summarization, custom compaction providers, token-aware tokenizers. |
| [`context_providers/`](context_providers/) | Injecting context at runtime. File-based providers, code-act (Hyperlight/Monty), dynamic context loading. |

### Advanced Patterns

| Directory | What you learn |
|-----------|---------------|
| [`harness/`](harness/) | Building fully-featured agent applications with research, data processing, and console UI patterns. |
| [`skills/`](skills/) | Defining and loading agent skills from files, code, classes, and MCP servers. |
| [`evaluation/`](evaluation/) | Evaluating agent responses. Keyword checks, rubric-based scoring, multimodal evaluation. |
| [`security/`](security/) | Email security scanning, confidentiality checks, MCP-based security tooling. |

### Observability & Dev Tools

| Directory | What you learn |
|-----------|---------------|
| [`observability/`](observability/) | OpenTelemetry tracing, custom metrics, workflow observability, Grafana dashboards. |
| [`devui/`](devui/) | Interactive agent development UI. Real-time tracing, chat interface, tool inspection. |

### Provider Integration

| Directory | What you learn |
|-----------|---------------|
| [`providers/`](providers/) | Configuration for each supported provider (OpenAI, Azure OpenAI, Foundry, Anthropic, Gemini, Ollama, Bedrock, Mistral, GitHub Copilot). |
| [`mcp/`](mcp/) | Model Context Protocol — local MCP servers, tool consent, auto-approval, cross-agent MCP. |
| [`a2a/`](a2a/) | Agent-to-Agent protocol — exposing agents as A2A services, polling, protocol selection, stream reconnection. |
| [`declarative/`](declarative/) | Defining agents declaratively with YAML. Inline YAML, MCP tool binding, Foundry integration. |

### Special Purpose

| Directory | What you learn |
|-----------|---------------|
| [`embeddings/`](embeddings/) | Generating and using embeddings with OpenAI, Azure OpenAI, and Ollama. |
| [`multimodal_input/`](multimodal_input/) | Agents that process images, audio, and other non-text inputs. |

## Additional Files

| File | Description |
|------|-------------|
| [`auto_retry.py`](auto_retry.py) | Transient error handling with automatic retry on agent runs. |
| [`background_responses.py`](background_responses.py) | Running agent tasks asynchronously without blocking the caller. |
| [`response_stream.py`](response_stream.py) | Streaming agent responses with chunk-by-chunk processing. |
| [`typed_options.py`](typed_options.py) | Using TypedDict for type-safe chat client options. |
| [`feature_stage_introspection.py`](feature_stage_introspection.py) | Querying which features and API surfaces are stable vs preview. |

## Provider Environment Variables

Most samples use `OpenAIChatCompletionClient` or provider-specific clients.
Configure credentials via environment variables:

| Provider | Required Variables |
|----------|-------------------|
| OpenAI | `OPENAI_API_KEY`, optionally `OPENAI_BASE_URL` and `OPENAI_MODEL_ID` |
| Azure OpenAI | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, Azure CLI credentials |
| Foundry | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, Azure CLI credentials |
| Anthropic | `ANTHROPIC_API_KEY` |
| Gemini | `GEMINI_API_KEY` |
| Ollama | `OLLAMA_BASE_URL` (defaults to `http://localhost:11434`) |

## Migrating to Agent Framework

If you are coming from Semantic Kernel or AutoGen, see the migration samples:

| From | Directory |
|------|-----------|
| Semantic Kernel | [`../semantic-kernel-migration/`](../semantic-kernel-migration/) |
| AutoGen | [`../autogen-migration/`](../autogen-migration/) |
