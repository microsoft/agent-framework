# Provider Samples Overview

This directory groups provider-specific samples for Agent Framework.

| Folder | What you will find |
| --- | --- |
| [`anthropic/`](anthropic/) | Anthropic Claude samples using both `AnthropicClient` and `ClaudeAgent`, including tools, MCP, sessions, and Foundry Anthropic integration. |
| [`amazon/`](amazon/) | AWS Bedrock samples using `BedrockChatClient`, including tool-enabled agent usage. |
| [`azure/`](azure/) | Azure OpenAI chat completion samples using `OpenAIChatCompletionClient`, including basic usage, explicit configuration, tools, and sessions. |
| [`copilotstudio/`](copilotstudio/) | Microsoft Copilot Studio agent samples, including required environment/app registration setup and explicit authentication patterns. |
| [`custom/`](custom/) | Framework extensibility samples for building custom `BaseAgent` and `BaseChatClient` implementations, including layer-composition guidance. |
| [`foundry/`](foundry/) | Microsoft Foundry and Foundry Local samples using `FoundryChatClient`, `FoundryAgent`, `RawFoundryAgentChatClient`, and `FoundryLocalClient` for hosted agents, Responses API, local inference, tools, MCP, and sessions. |
| [`gemini/`](gemini/) | Google Gemini samples covering tool calling, streaming, extended thinking, grounding, and built-in code execution. |
| [`github_copilot/`](github_copilot/) | `GitHubCopilotAgent` samples showing basic usage, session handling, permission-scoped shell/file/url access, and MCP integration. |
| [`mistral/`](mistral/) | Mistral AI embedding generation with configurable models and output dimensions. |
| [`ollama/`](ollama/) | Local Ollama samples using `OllamaChatClient` (recommended) plus OpenAI-compatible Ollama setup, including reasoning and multimodal examples. |
| [`openai/`](openai/) | OpenAI provider samples for Chat and Chat Completion clients, including tools, structured output, sessions, MCP, web search, and multimodal tasks. |

Each folder has its own README with setup requirements and file-by-file details.

## Security & Untrusted Data

When configuring providers with function tools or external data access, review the [Agent Safety](https://learn.microsoft.com/en-us/agent-framework/concepts/agents/safety) guidance on Microsoft Learn, then [`../security/`](../security/) for production security controls:

1. [`email_security_example.py`](../security/email_security_example.py): Prompt injection defense with `SecureAgentConfig` and `quarantined_llm`.
2. [`github_mcp_example.py`](../security/github_mcp_example.py): Securing external MCP tools with `SecureMCPToolProxy`.
3. [`repo_confidentiality_example.py`](../security/repo_confidentiality_example.py): Preventing confidential data exfiltration across tool invocations.
4. [FIDES Developer Guide](../security/FIDES_DEVELOPER_GUIDE.md): Architecture reference and security middleware documentation.
