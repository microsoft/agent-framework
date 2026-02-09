# 02 — Advanced Single-Agent Concepts

These samples explore individual agent capabilities in depth. Each file is self-contained and can be run with `python <filename>`.

## Agent Capabilities

| Sample | Description |
|---|---|
| [structured_output.py](structured_output.py) | Get typed, structured responses using Pydantic models |
| [response_stream.py](response_stream.py) | Deep dive into `ResponseStream` — hooks, transforms, and chaining |
| [typed_options.py](typed_options.py) | Provider-specific typed options with IDE autocomplete |
| [rag.py](rag.py) | Retrieval-Augmented Generation with context providers |
| [declarative_agents.py](declarative_agents.py) | Define agents in YAML with `AgentFactory` |
| [observability.py](observability.py) | Add OpenTelemetry tracing, logging, and metrics |

## Tools

| Sample | Description |
|---|---|
| [tools/function_tools.py](tools/function_tools.py) | Advanced function tools with type annotations and kwargs injection |
| [tools/tool_approval.py](tools/tool_approval.py) | Human-in-the-loop approval before tool execution |
| [tools/code_interpreter.py](tools/code_interpreter.py) | Hosted code interpreter for Python execution |
| [tools/file_search.py](tools/file_search.py) | Search through uploaded documents with vector stores |
| [tools/web_search.py](tools/web_search.py) | Real-time web search for current information |
| [tools/hosted_mcp_tools.py](tools/hosted_mcp_tools.py) | Provider-managed MCP server connections |
| [tools/local_mcp_tools.py](tools/local_mcp_tools.py) | Client-managed MCP connections via Streamable HTTP |

## Conversations & Persistence

| Sample | Description |
|---|---|
| [conversations/persistent_conversation.py](conversations/persistent_conversation.py) | Custom message store with serialize/deserialize |
| [conversations/redis_storage.py](conversations/redis_storage.py) | Redis-backed conversation persistence |
| [conversations/suspend_resume.py](conversations/suspend_resume.py) | Suspend and resume conversation threads |

## Providers

Each provider sample is a minimal "hello world" showing setup and a single query.

| Sample | Provider |
|---|---|
| [providers/openai_provider.py](providers/openai_provider.py) | OpenAI (Responses API) |
| [providers/azure_openai.py](providers/azure_openai.py) | Azure OpenAI |
| [providers/azure_ai_foundry.py](providers/azure_ai_foundry.py) | Azure AI Foundry |
| [providers/anthropic_provider.py](providers/anthropic_provider.py) | Anthropic (Claude) |
| [providers/ollama_provider.py](providers/ollama_provider.py) | Ollama (local models) |
| [providers/github_copilot.py](providers/github_copilot.py) | GitHub Copilot |
| [providers/copilot_studio.py](providers/copilot_studio.py) | Copilot Studio |
| [providers/custom_provider.py](providers/custom_provider.py) | Custom (BaseAgent) |

## Prerequisites

- Python 3.10+
- `pip install agent-framework`
- Provider-specific API keys (see each sample's docstring)

## Next Steps

- **Get Started**: [../01-get-started/](../01-get-started/) — Introductory samples
- **Workflows**: [../03-workflows/](../03-workflows/) — Multi-agent orchestration
- **Hosting**: [../04-hosting/](../04-hosting/) — Deploy agents in production
