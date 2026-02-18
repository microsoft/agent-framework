# Provider Samples Overview

This directory groups provider-specific samples for Agent Framework.

| Folder | What you will find |
| --- | --- |
| [`anthropic/`](anthropic/) | Anthropic Claude samples using both `AnthropicClient` and `ClaudeAgent`, including tools, MCP, sessions, and Foundry Anthropic integration. |
| [`amazon/`](amazon/) | AWS Bedrock samples using `BedrockChatClient`, including tool-enabled agent usage. |
| [`azure_ai/`](azure_ai/) | Azure AI Foundry V2 (`azure-ai-projects`) samples with `AzureAIClient`, from basic setup to advanced patterns like search, memory, A2A, MCP, and provider methods. |
| [`azure_ai_agent/`](azure_ai_agent/) | Azure AI Foundry V1 (`azure-ai-agents`) samples with `AzureAIAgentsProvider`, including provider methods and common hosted tool integrations. |
| [`azure_openai/`](azure_openai/) | Azure OpenAI samples for Assistants, Chat, and Responses clients, with examples for sessions, tools, MCP, file search, and code interpreter. |
| [`copilotstudio/`](copilotstudio/) | Microsoft Copilot Studio agent samples, including required environment/app registration setup and explicit authentication patterns. |
| [`custom/`](custom/) | Framework extensibility samples for building custom `BaseAgent` and `BaseChatClient` implementations, including layer-composition guidance. |
| [`foundry_local/`](foundry_local/) | Foundry Local samples using `FoundryLocalClient` for local model inference with streaming, non-streaming, and tool-calling patterns. |
| [`github_copilot/`](github_copilot/) | `GitHubCopilotAgent` samples showing basic usage, session handling, permission-scoped shell/file/url access, and MCP integration. |
| [`ollama/`](ollama/) | Local Ollama samples using `OllamaChatClient` (recommended) plus OpenAI-compatible Ollama setup, including reasoning and multimodal examples. |
| [`openai/`](openai/) | OpenAI provider samples for Assistants, Chat, and Responses clients, including tools, structured output, sessions, MCP, web search, and multimodal tasks. |

Each folder has its own README with setup requirements and file-by-file details.
