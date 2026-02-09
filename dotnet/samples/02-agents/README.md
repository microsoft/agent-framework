# Agents (.NET)

Deep-dive samples covering agents, tools, middleware, conversations, and providers.

## Agent Capabilities

| Sample | What You'll Learn |
|--------|-------------------|
| [Structured Output](./StructuredOutput.cs) | Configure agents to return typed JSON responses |
| [Background Responses](./BackgroundResponses.cs) | Handle long-running tasks with polling and resumption |
| [RAG](./Rag.cs) | Add retrieval augmented generation with vector search |
| [Declarative Agents](./DeclarativeAgents.cs) | Load agent definitions from YAML files |
| [Observability](./Observability.cs) | Add OpenTelemetry tracing, metrics, and logging |

## Tools

| Sample | What You'll Learn |
|--------|-------------------|
| [Function Tools](./tools/FunctionTools.cs) | Define and register function tools |
| [Tool Approval](./tools/ToolApproval.cs) | Require human approval before tool invocation |
| [Code Interpreter](./tools/CodeInterpreter.cs) | Use hosted code interpreter for math and code |
| [File Search](./tools/FileSearch.cs) | Search uploaded documents with file search tool |
| [Web Search](./tools/WebSearch.cs) | Search the internet with web search tool |
| [Hosted MCP Tools](./tools/HostedMcpTools.cs) | Use server-side MCP tools via Responses API |
| [Local MCP Tools](./tools/LocalMcpTools.cs) | Use tools from a local MCP server process |

## Middleware

| Sample | What You'll Learn |
|--------|-------------------|
| [Defining Middleware](./middleware/DefiningMiddleware.cs) | Basic middleware setup with function tools |
| [Chat Client Middleware](./middleware/ChatClientMiddleware.cs) | Intercept LLM requests at the chat client level |
| [PII Filtering](./middleware/PIIFiltering.cs) | Redact personally identifiable information |
| [Guardrails](./middleware/Guardrails.cs) | Block forbidden content with keyword filtering |
| [Function Override](./middleware/FunctionOverride.cs) | Modify or override function tool results |
| [Human Approval](./middleware/HumanApproval.cs) | Prompt users for consent before function calls |
| [Per-Request Middleware](./middleware/PerRequestMiddleware.cs) | Scope middleware to a single agent run |

## Conversations

| Sample | What You'll Learn |
|--------|-------------------|
| [Persistent Conversation](./conversations/PersistentConversation.cs) | Serialize and resume agent sessions |
| [Custom Storage](./conversations/CustomStorage.cs) | Implement custom chat history storage |

## Providers

| Sample | Backend |
|--------|---------|
| [Azure AI Foundry](./providers/AzureAIFoundry.cs) | Azure AI Foundry Responses API (default) |
| [Azure OpenAI](./providers/AzureOpenAI.cs) | Azure OpenAI Chat Completion |
| [OpenAI](./providers/OpenAIProvider.cs) | OpenAI Chat Completion |
| [Anthropic](./providers/AnthropicProvider.cs) | Anthropic Claude (direct or via Foundry) |
| [Ollama](./providers/OllamaProvider.cs) | Ollama local models |
| [GitHub Copilot](./providers/GitHubCopilot.cs) | GitHub Copilot SDK |
| [Copilot Studio](./providers/CopilotStudio.cs) | Microsoft Copilot Studio via A2A |
| [Custom](./providers/CustomProvider.cs) | Fully custom AIAgent implementation |
